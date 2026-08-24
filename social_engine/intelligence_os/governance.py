from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import connect, decode, encode, initialize, utc_now
from .registry import Capability


READ_LEVELS = {"READ", "RECOMMEND", "EXECUTE_WITH_APPROVAL", "AUTONOMOUS"}
EXECUTE_LEVELS = {"EXECUTE_WITH_APPROVAL", "AUTONOMOUS"}


@dataclass(frozen=True)
class Authorization:
    allowed: bool
    requires_approval: bool
    reason: str
    policy_id: str | None = None
    approval_id: str | None = None


class PolicyEngine:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def create_policy(
        self,
        *,
        capability: str,
        rule: str,
        approval_level: str,
        created_by: str,
        scope: dict[str, Any] | None = None,
        limits: dict[str, Any] | None = None,
        valid_until: str | None = None,
    ) -> dict[str, Any]:
        if approval_level not in READ_LEVELS:
            raise ValueError(f"invalid_approval_level:{approval_level}")
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                """
                INSERT INTO os_policies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (
                    identifier, capability, encode(scope or {}), rule, approval_level,
                    encode(limits or {}), now, valid_until, created_by, now, now,
                ),
            )
            connection.commit()
        return self.get_policy(identifier)

    def get_policy(self, policy_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_policies WHERE id=?", (policy_id,)).fetchone()
        if not row:
            raise KeyError(f"policy_not_found:{policy_id}")
        data = dict(row)
        data["scope"] = decode(data.pop("scope_json"), {})
        data["limits"] = decode(data.pop("limits_json"), {})
        return data

    def list_policies(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        where = "WHERE status='ACTIVE'" if active_only else ""
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                f"SELECT * FROM os_policies {where} ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["scope"] = decode(data.pop("scope_json"), {})
            data["limits"] = decode(data.pop("limits_json"), {})
            result.append(data)
        return result

    def authorize(
        self,
        capability: Capability,
        payload: dict[str, Any],
        *,
        actor: str,
        approval_id: str | None = None,
    ) -> Authorization:
        if capability.risk_level == "READ":
            return Authorization(True, False, "read_capability")
        if approval_id and self._approval_is_valid(approval_id, capability.id, actor, payload):
            return Authorization(True, False, "approved_one_time_operation", approval_id=approval_id)
        policies = self._matching_policies(capability.id, payload)
        if not policies:
            return Authorization(False, True, "default_deny_mutation")
        policy = policies[0]
        level = policy["approval_level"]
        if level == "AUTONOMOUS":
            return Authorization(True, False, "autonomous_policy", policy["id"])
        if level == "EXECUTE_WITH_APPROVAL":
            return Authorization(False, True, "owner_approval_required", policy["id"])
        return Authorization(False, False, f"policy_level_{level.lower()}_does_not_allow_execution", policy["id"])

    def request_approval(self, capability: str, actor: str, request: dict[str, Any]) -> str:
        encoded_request = encode(request)
        with connect(self.data_dir) as connection:
            existing = connection.execute(
                "SELECT id FROM os_approvals WHERE capability=? AND actor=? AND request_json=? AND status='PENDING' ORDER BY created_at DESC LIMIT 1",
                (capability, actor, encoded_request),
            ).fetchone()
        if existing:
            return str(existing["id"])
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_approvals VALUES (?, ?, ?, ?, 'PENDING', NULL, NULL, ?, NULL)",
                (identifier, capability, actor, encoded_request, utc_now()),
            )
            connection.commit()
        return identifier

    def decide_approval(self, approval_id: str, *, approved: bool, decided_by: str, note: str = "") -> dict[str, Any]:
        status = "APPROVED" if approved else "REJECTED"
        with connect(self.data_dir) as connection:
            changed = connection.execute(
                """
                UPDATE os_approvals SET status=?, decided_by=?, decision_note=?, decided_at=?
                WHERE id=? AND status='PENDING'
                """,
                (status, decided_by, note, utc_now(), approval_id),
            ).rowcount
            connection.commit()
        if not changed:
            raise ValueError("approval_not_pending_or_missing")
        return {"id": approval_id, "status": status, "decided_by": decided_by, "note": note}

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_approvals WHERE id=?", (approval_id,)).fetchone()
        if not row:
            raise KeyError(f"approval_not_found:{approval_id}")
        result = dict(row)
        result["request"] = decode(result.pop("request_json"), {})
        return result

    def list_approvals(self, *, actor: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if actor:
            clauses.append("actor=?")
            values.append(actor)
        if status:
            clauses.append("status=?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(limit, 200)))
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                f"SELECT id FROM os_approvals {where} ORDER BY created_at DESC LIMIT ?", values
            ).fetchall()
        return [self.get_approval(row["id"]) for row in rows]

    def consume_approval(self, approval_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            changed = connection.execute(
                "UPDATE os_approvals SET status='CONSUMED' WHERE id=? AND status='APPROVED'",
                (approval_id,),
            ).rowcount
            connection.commit()
        if not changed:
            raise ValueError("approval_not_approved_or_already_consumed")
        return self.get_approval(approval_id)

    def supersede_pending(self, *, capability: str, actor: str, except_id: str) -> int:
        now = utc_now()
        with connect(self.data_dir) as connection:
            changed = connection.execute(
                """
                UPDATE os_approvals
                SET status='SUPERSEDED', decided_by='system', decision_note='Replaced by executed owner approval', decided_at=?
                WHERE capability=? AND actor=? AND status='PENDING' AND id<>?
                """,
                (now, capability, actor, except_id),
            ).rowcount
            connection.commit()
        return changed

    def _matching_policies(self, capability: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                """
                SELECT * FROM os_policies
                WHERE status='ACTIVE' AND capability IN (?, '*')
                  AND valid_from <= ? AND (valid_until IS NULL OR valid_until >= ?)
                ORDER BY CASE capability WHEN ? THEN 0 ELSE 1 END, created_at DESC
                """,
                (capability, now, now, capability),
            ).fetchall()
        matches: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            scope = decode(data["scope_json"], {})
            if all(payload.get(key) == value for key, value in scope.items()):
                matches.append(data)
        return matches

    def _approval_is_valid(self, approval_id: str, capability: str, actor: str, payload: dict[str, Any]) -> bool:
        with connect(self.data_dir) as connection:
            row = connection.execute(
                "SELECT request_json FROM os_approvals WHERE id=? AND capability=? AND actor=? AND status='APPROVED'",
                (approval_id, capability, actor),
            ).fetchone()
        return bool(row and decode(row["request_json"], {}) == payload)