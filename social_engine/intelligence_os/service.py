from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from .db import connect, decode, encode, initialize, utc_now
from .governance import PolicyEngine
from .intelligence import AutomationService, ResearchIntelligence
from .models import CopilotMaster, MasterModelUnavailable, new_session_id
from .operations import AttentionService, AuditLog, EventBus, JobService
from .registry import CapabilityRegistry
from .transactions import TransactionService


MASTER_PROMPT = """You are Infenergy's master intelligence and operating partner.
Understand the owner's goal before choosing capabilities. Use authoritative internal data when available and current external research when needed. Distinguish observed facts, derived metrics, inference, forecast, hypothesis, recommendation, and owner decision. Have a point of view. Do not make the owner operate low-level tools. Do not bluff. Respect current permissions, approvals, budgets, and policies. Use dry-run mode when required. Preserve provenance and explain material actions. Never expand your own permissions. The owner is the final authority. Use only the registered Infenergy semantic tools; do not use ambient shell, filesystem, publishing, credential, or deployment tools.
"""


class IntelligenceOS:
    def __init__(self, data_dir: str, registry: CapabilityRegistry, policies: PolicyEngine):
        self.data_dir = data_dir
        self.registry = registry
        self.policies = policies
        self.transactions = TransactionService(data_dir, registry, policies)
        self.audit = AuditLog(data_dir)
        self.events = EventBus(data_dir)
        self.jobs = JobService(data_dir)
        self.attention = AttentionService(data_dir)
        self.master = CopilotMaster(data_dir)
        initialize(data_dir)

    def create_conversation(self, *, owner_id: str = "owner", title: str = "Infenergy Command") -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        session_id = new_session_id()
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_conversations VALUES (?, ?, ?, ?, 'ACTIVE', '{}', ?, ?)",
                (identifier, owner_id, title, session_id, now, now),
            )
            connection.commit()
        return self.get_conversation(identifier)

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_conversations WHERE id=?", (conversation_id,)).fetchone()
            messages = connection.execute(
                "SELECT * FROM os_messages WHERE conversation_id=? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        if not row:
            raise KeyError(f"conversation_not_found:{conversation_id}")
        result = dict(row)
        result["active_context"] = decode(result.pop("active_context_json"), {})
        result["messages"] = []
        for item in messages:
            message = dict(item)
            message["metadata"] = decode(message.pop("metadata_json"), {})
            result["messages"].append(message)
        return result

    def latest_conversation(self, owner_id: str = "owner") -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute(
                "SELECT id FROM os_conversations WHERE owner_id=? AND status='ACTIVE' ORDER BY updated_at DESC LIMIT 1",
                (owner_id,),
            ).fetchone()
        return self.get_conversation(row["id"]) if row else self.create_conversation(owner_id=owner_id)

    def list_conversations(self, limit: int = 30) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT id, owner_id, title, status, created_at, updated_at FROM os_conversations ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def execute_capability(
        self,
        capability: str,
        arguments: dict[str, Any],
        *,
        actor: str = "owner",
        dry_run: bool = False,
        operation_id: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        return self.transactions.execute(
            capability, arguments, actor=actor, dry_run=dry_run,
            operation_id=operation_id, approval_id=approval_id,
        )

    def command(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        actor: str = "owner",
    ) -> dict[str, Any]:
        conversation = self.get_conversation(conversation_id) if conversation_id else self.latest_conversation(actor)
        self._message(conversation["id"], "user", message)
        try:
            response = asyncio.run(
                self.master.converse(
                    message,
                    session_id=conversation["copilot_session_id"],
                    system_message=MASTER_PROMPT + "\nAvailable capabilities:\n" + self.registry.semantic_catalog(),
                    tools=self._copilot_tools(actor),
                )
            )
            content = response["content"]
            self._message(conversation["id"], "assistant", content, response)
            self.audit.record(
                actor=actor, model_or_tool=response["model"], action="MASTER_RESPONSE",
                status="COMPLETED", result={"conversation_id": conversation["id"]},
            )
            return {"status": "COMPLETED", "conversation_id": conversation["id"], "message": content, "model": response["model"]}
        except MasterModelUnavailable as exc:
            status = exc.status.__dict__
            content = (
                f"Master intelligence is unavailable: {status['reason']}. "
                f"Configured model: {status['configured_model']}. "
                f"Actual available models: {[item.get('id') for item in status['available_models']]}. "
                "No strategic-model downgrade was performed."
            )
            self._message(conversation["id"], "assistant", content, {"blocked": True, "model_status": status})
            self.audit.record(
                actor=actor, model_or_tool="github-copilot-sdk", action="MASTER_RESPONSE_BLOCKED",
                status="BLOCKED", result=status,
            )
            return {"status": "BLOCKED", "conversation_id": conversation["id"], "message": content, "model_status": status}

    def executive_state(self) -> dict[str, Any]:
        health = self.execute_capability("system.health", {}, operation_id=f"state-health-{uuid.uuid4().hex}")
        automations = AutomationService(self.data_dir)
        return {
            "time_utc": utc_now(),
            "health": health.get("result", {}),
            "attention": self.attention.list_open(10),
            "jobs": self.jobs.list(20),
            "policies": self.policies.list_policies(),
            "recent_events": self.events.list(20),
            "recent_activity": self.audit.list(20),
            "research_findings": ResearchIntelligence(self.data_dir).list_findings(20),
            "automations": automations.list(),
            "automation_runs": automations.list_runs(20),
            "watches": automations.list_watches(),
            "conversation": self.latest_conversation(),
        }

    def _copilot_tools(self, actor: str) -> list[Any]:
        from copilot import Tool
        from copilot.tools import ToolResult

        tools = []
        for descriptor in self.registry.list():
            capability_id = descriptor["id"]

            async def handler(invocation: Any, capability_id: str = capability_id) -> ToolResult:
                try:
                    payload = dict(invocation.arguments or {})
                    dry_run = bool(payload.pop("dry_run", False))
                    approval_id = payload.pop("approval_id", None)
                    result = self.execute_capability(
                        capability_id, payload, actor=actor, dry_run=dry_run,
                        approval_id=approval_id,
                    )
                    return ToolResult(
                        text_result_for_llm=json.dumps(result, ensure_ascii=False, default=str),
                        result_type="success",
                    )
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    return ToolResult(text_result_for_llm=error, result_type="failure", error=error)

            schema = dict(descriptor["input_schema"])
            properties = dict(schema.get("properties", {}))
            properties.update({
                "dry_run": {"type": "boolean", "description": "Preview without mutation."},
                "approval_id": {"type": "string", "description": "Owner-approved request identifier."},
            })
            schema["properties"] = properties
            tools.append(Tool(
                name=capability_id.replace(".", "_"),
                description=descriptor["description"], parameters=schema,
                handler=handler, skip_permission=True,
                metadata={"capability_id": capability_id, "risk_level": descriptor["risk_level"]},
            ))
        return tools

    def _message(self, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> str:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_messages VALUES (?, ?, ?, ?, ?, ?)",
                (identifier, conversation_id, role, content, encode(metadata or {}), now),
            )
            connection.execute("UPDATE os_conversations SET updated_at=? WHERE id=?", (now, conversation_id))
            connection.commit()
        return identifier