from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .db import connect, encode, initialize, utc_now


DEFAULT_MASTER_MODEL = "gpt-5.6-sol"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class ModelStatus:
    provider: str
    configured_model: str
    authenticated: bool
    available: bool
    available_models: list[dict[str, Any]]
    reason: str
    checked_at: str


class MasterModelUnavailable(RuntimeError):
    def __init__(self, status: ModelStatus):
        self.status = status
        super().__init__(
            f"master_model_unavailable:{status.configured_model}:{status.reason}; "
            f"available_models={[item.get('id') for item in status.available_models]}"
        )


class CopilotMaster:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.model = os.environ.get("INFENERGY_MASTER_MODEL", DEFAULT_MASTER_MODEL).strip() or DEFAULT_MASTER_MODEL
        self.command_timeout = self._command_timeout()
        initialize(data_dir)

    @staticmethod
    def _command_timeout() -> float:
        try:
            configured = float(os.environ.get("INFENERGY_COMMAND_TIMEOUT_SECONDS", DEFAULT_COMMAND_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            configured = DEFAULT_COMMAND_TIMEOUT_SECONDS
        return max(60.0, min(configured, 900.0))

    async def status_async(self) -> ModelStatus:
        checked_at = utc_now()
        try:
            from copilot import CopilotClient
        except ImportError:
            return self._save(ModelStatus("github-copilot-sdk", self.model, False, False, [], "github-copilot-sdk_not_installed", checked_at))
        client = CopilotClient()
        try:
            await client.start()
            auth = await client.get_auth_status()
            authenticated = bool(getattr(auth, "isAuthenticated", False))
            if not authenticated:
                return self._save(ModelStatus("github-copilot-sdk", self.model, False, False, [], getattr(auth, "statusMessage", "not_authenticated") or "not_authenticated", checked_at))
            models = await client.list_models()
            available_models = [
                {"id": str(getattr(item, "id", "")), "name": str(getattr(item, "name", ""))}
                for item in models
            ]
            available_ids = {item["id"].lower() for item in available_models}
            available = self.model.lower() in available_ids
            reason = "available" if available else "configured_master_model_not_in_authenticated_model_list"
            return self._save(ModelStatus("github-copilot-sdk", self.model, True, available, available_models, reason, checked_at))
        except Exception as exc:
            return self._save(ModelStatus("github-copilot-sdk", self.model, False, False, [], f"{type(exc).__name__}:{exc}", checked_at))
        finally:
            try:
                await client.stop()
            except Exception:
                pass

    def status(self) -> ModelStatus:
        return asyncio.run(self.status_async())

    async def converse(
        self,
        prompt: str,
        *,
        session_id: str,
        system_message: str,
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        status = await self.status_async()
        if not status.available:
            raise MasterModelUnavailable(status)
        from copilot import CopilotClient
        from copilot.session import PermissionDecisionUserNotAvailable

        def reject_ambient_tools(request: Any, invocation: Any) -> Any:
            return PermissionDecisionUserNotAvailable()

        client = CopilotClient()
        try:
            await client.start()
            session = await client.create_session(
                model=self.model,
                session_id=session_id,
                client_name="infenergy-intelligence-os",
                tools=tools or [],
                system_message={"mode": "append", "content": system_message},
                available_tools=[f"custom:{getattr(tool, 'name', '')}" for tool in (tools or [])],
                on_permission_request=reject_ambient_tools,
                working_directory=str(Path(__file__).resolve().parents[2]),
            )
            response = await session.send_and_wait(
                prompt,
                agent_mode="autopilot",
                timeout=self.command_timeout,
            )
            content = str(getattr(getattr(response, "data", None), "content", "") or "")
            await session.disconnect()
            return {"content": content, "model": self.model, "provider": "github-copilot-sdk", "session_id": session_id}
        finally:
            await client.stop()

    def _save(self, status: ModelStatus) -> ModelStatus:
        with connect(self.data_dir) as connection:
            connection.execute(
                """
                INSERT INTO os_models VALUES (?, ?, 'master_reasoning', NULL, 'SUBSCRIPTION', 'VARIABLE', ?, ?, '{}', ?)
                ON CONFLICT(id) DO UPDATE SET capabilities_json=excluded.capabilities_json,
                    available=excluded.available, checked_at=excluded.checked_at
                """,
                (status.configured_model, status.provider, encode({"models": status.available_models, "reason": status.reason}), int(status.available), status.checked_at),
            )
            connection.commit()
        return status


def new_session_id() -> str:
    return f"infenergy-{uuid.uuid4().hex}"