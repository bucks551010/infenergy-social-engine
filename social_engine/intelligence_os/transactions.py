from __future__ import annotations

import uuid
from typing import Any

from .db import connect, decode, encode, initialize, utc_now
from .governance import PolicyEngine
from .operations import AuditLog, EventBus
from .registry import CapabilityRegistry, ExecutionContext, validate_input


class TransactionService:
    def __init__(self, data_dir: str, registry: CapabilityRegistry, policies: PolicyEngine):
        self.data_dir = data_dir
        self.registry = registry
        self.policies = policies
        self.audit = AuditLog(data_dir)
        self.events = EventBus(data_dir)
        initialize(data_dir)

    def execute(
        self,
        capability_id: str,
        payload: dict[str, Any],
        *,
        actor: str = "owner",
        dry_run: bool = False,
        operation_id: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        capability = self.registry.get(capability_id)
        errors = validate_input(capability.input_schema, payload)
        if errors:
            raise ValueError(";".join(errors))
        if dry_run and not capability.supports_dry_run:
            raise ValueError(f"dry_run_not_supported:{capability_id}")

        operation_id = operation_id or uuid.uuid4().hex
        existing = self._by_operation_id(operation_id)
        if existing:
            return {
                **existing,
                "transaction_id": existing["id"],
                "result": existing["after_state"],
                "rollback_available": bool(
                    existing["status"] == "COMPLETED"
                    and existing["rollback_data"]
                    and not existing["dry_run"]
                ),
                "idempotent_replay": True,
            }

        authorization = self.policies.authorize(
            capability, payload, actor=actor, approval_id=approval_id
        )
        required_approval = None
        if dry_run and not authorization.allowed:
            required_approval = {
                "required": authorization.requires_approval,
                "reason": authorization.reason,
                "policy_id": authorization.policy_id,
            }
        elif not authorization.allowed:
            pending_approval = authorization.approval_id
            if authorization.requires_approval and not pending_approval:
                pending_approval = self.policies.request_approval(capability_id, actor, payload)
            audit_id = self.audit.record(
                actor=actor,
                model_or_tool=capability_id,
                action="CAPABILITY_DENIED",
                status="WAITING_APPROVAL" if authorization.requires_approval else "DENIED",
                result={"reason": authorization.reason},
                approval_id=pending_approval,
            )
            return {
                "status": "WAITING_APPROVAL" if authorization.requires_approval else "DENIED",
                "capability": capability_id,
                "reason": authorization.reason,
                "approval_id": pending_approval,
                "audit_id": audit_id,
            }

        transaction_id = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_transactions VALUES (?, ?, ?, ?, ?, 'PLANNING', '{}', '{}', '{}', '[]', ?, ?, ?)",
                (
                    transaction_id, operation_id, capability.name, actor, int(dry_run),
                    approval_id, now, now,
                ),
            )
            connection.commit()

        context = ExecutionContext(
            data_dir=self.data_dir,
            actor=actor,
            dry_run=dry_run,
            transaction_id=transaction_id,
            operation_id=operation_id,
        )
        operation_record_id = uuid.uuid4().hex
        before = {"input": payload}
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_transaction_operations VALUES (?, ?, 0, ?, ?, ?, '{}', '{}', 'PLANNED', NULL, ?)",
                (operation_record_id, transaction_id, capability_id, encode(payload), encode(before), now),
            )
            connection.execute(
                "UPDATE os_transactions SET status=?, before_state_json=?, updated_at=? WHERE id=?",
                ("DRY_RUN" if dry_run else "RUNNING", encode(before), utc_now(), transaction_id),
            )
            connection.commit()

        self.events.emit(
            "CAPABILITY_EXECUTION_STARTED",
            source="transaction_service",
            subject_type="transaction",
            subject_id=transaction_id,
            payload={"capability": capability_id, "dry_run": dry_run},
            materiality=0.4 if capability.risk_level != "READ" else 0.1,
        )
        try:
            result = capability.handler(payload, context)
            if not isinstance(result, dict):
                result = {"result": result}
            rollback_data = result.pop("_rollback", {}) if capability.supports_rollback else {}
            irreversible = result.pop("_irreversible", [])
            status = "DRY_RUN_COMPLETE" if dry_run else "COMPLETED"
            with connect(self.data_dir) as connection:
                connection.execute(
                    """
                    UPDATE os_transactions SET status=?, after_state_json=?, rollback_data_json=?,
                        irreversible_json=?, updated_at=? WHERE id=?
                    """,
                    (status, encode(result), encode(rollback_data), encode(irreversible), utc_now(), transaction_id),
                )
                connection.execute(
                    """
                    UPDATE os_transaction_operations SET after_json=?, rollback_json=?, status='COMPLETED'
                    WHERE id=?
                    """,
                    (encode(result), encode(rollback_data), operation_record_id),
                )
                connection.commit()
            audit_id = self.audit.record(
                actor=actor, model_or_tool=capability_id, action="CAPABILITY_EXECUTED",
                status=status, result=result, transaction_id=transaction_id,
                approval_id=approval_id,
            )
            self.events.emit(
                "CAPABILITY_EXECUTION_COMPLETED",
                source="transaction_service",
                subject_type="transaction",
                subject_id=transaction_id,
                payload={"capability": capability_id, "status": status},
                materiality=0.5 if capability.risk_level != "READ" else 0.1,
            )
            return {
                "status": status,
                "transaction_id": transaction_id,
                "operation_id": operation_id,
                "audit_id": audit_id,
                "capability": capability_id,
                "dry_run": dry_run,
                "result": result,
                "required_approval": required_approval,
                "rollback_available": bool(capability.supports_rollback and rollback_data and not dry_run),
                "irreversible": irreversible,
            }
        except Exception as exc:
            with connect(self.data_dir) as connection:
                connection.execute(
                    "UPDATE os_transactions SET status='FAILED', updated_at=? WHERE id=?",
                    (utc_now(), transaction_id),
                )
                connection.execute(
                    "UPDATE os_transaction_operations SET status='FAILED', error=? WHERE id=?",
                    (f"{type(exc).__name__}: {exc}", operation_record_id),
                )
                connection.commit()
            self.audit.record(
                actor=actor, model_or_tool=capability_id, action="CAPABILITY_FAILED",
                status="FAILED", result={"error": str(exc)}, transaction_id=transaction_id,
            )
            self.events.emit(
                "CAPABILITY_EXECUTION_FAILED", source="transaction_service",
                subject_type="transaction", subject_id=transaction_id,
                payload={"capability": capability_id, "error": str(exc)}, materiality=0.8,
            )
            raise

    def rollback(self, transaction_id: str, *, actor: str = "owner") -> dict[str, Any]:
        transaction = self.get(transaction_id)
        if transaction["dry_run"]:
            raise ValueError("dry_run_transaction_has_no_mutation")
        if transaction["status"] != "COMPLETED":
            raise ValueError(f"transaction_not_rollbackable:{transaction['status']}")
        operations = transaction["operations"]
        if not operations:
            raise ValueError("transaction_has_no_operations")
        operation = operations[-1]
        capability = self.registry.get(operation["capability"])
        if not capability.supports_rollback or capability.rollback_handler is None:
            raise ValueError("capability_does_not_support_rollback")
        context = ExecutionContext(
            data_dir=self.data_dir,
            actor=actor,
            dry_run=False,
            transaction_id=transaction_id,
            operation_id=transaction["operation_id"],
        )
        result = capability.rollback_handler(operation["rollback"], context)
        with connect(self.data_dir) as connection:
            connection.execute(
                "UPDATE os_transactions SET status='ROLLED_BACK', updated_at=? WHERE id=?",
                (utc_now(), transaction_id),
            )
            connection.execute(
                "UPDATE os_transaction_operations SET status='ROLLED_BACK' WHERE id=?",
                (operation["id"],),
            )
            connection.commit()
        audit_id = self.audit.record(
            actor=actor, model_or_tool=capability.id, action="TRANSACTION_ROLLED_BACK",
            status="ROLLED_BACK", result=result, transaction_id=transaction_id,
        )
        self.events.emit(
            "TRANSACTION_ROLLED_BACK", source="transaction_service",
            subject_type="transaction", subject_id=transaction_id,
            payload={"capability": capability.id}, materiality=0.6,
        )
        return {"status": "ROLLED_BACK", "transaction_id": transaction_id, "audit_id": audit_id, "result": result}

    def undo_last(self, *, actor: str = "owner") -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute(
                """
                SELECT id FROM os_transactions
                WHERE actor=? AND status='COMPLETED' AND rollback_data_json NOT IN ('{}', '')
                ORDER BY updated_at DESC LIMIT 1
                """,
                (actor,),
            ).fetchone()
        if not row:
            raise ValueError("no_reversible_transaction_found")
        return self.rollback(row["id"], actor=actor)

    def get(self, transaction_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_transactions WHERE id=?", (transaction_id,)).fetchone()
            operations = connection.execute(
                "SELECT * FROM os_transaction_operations WHERE transaction_id=? ORDER BY ordinal",
                (transaction_id,),
            ).fetchall()
        if not row:
            raise KeyError(f"transaction_not_found:{transaction_id}")
        result = dict(row)
        result["dry_run"] = bool(result["dry_run"])
        for key in ("before_state_json", "after_state_json", "rollback_data_json", "irreversible_json"):
            result[key[:-5]] = decode(result.pop(key), {})
        result["operations"] = []
        for item in operations:
            operation = dict(item)
            for key in ("input_json", "before_json", "after_json", "rollback_json"):
                operation[key[:-5]] = decode(operation.pop(key), {})
            result["operations"].append(operation)
        return result

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            ids = [row["id"] for row in connection.execute(
                "SELECT id FROM os_transactions ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()]
        return [self.get(identifier) for identifier in ids]

    def _by_operation_id(self, operation_id: str) -> dict[str, Any] | None:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT id FROM os_transactions WHERE operation_id=?", (operation_id,)).fetchone()
        return self.get(row["id"]) if row else None