from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from .foundation import bootstrap


UI_DIR = Path(__file__).resolve().parent / "ui"


def handle(method: str, path: str, body: dict[str, Any] | None, data_dir: str) -> tuple[int, str, bytes]:
    service = bootstrap(data_dir)
    payload = body or {}
    try:
        if method == "GET" and path in {"/os", "/os/"}:
            return _file("index.html")
        if method == "GET" and path.startswith("/os/assets/"):
            return _file(path.rsplit("/", 1)[-1])
        if method == "GET" and path == "/api/os/state":
            return _json(200, service.executive_state())
        if method == "GET" and path == "/api/os/capabilities":
            return _json(200, {"capabilities": service.registry.list()})
        if method == "GET" and path == "/api/os/conversations":
            return _json(200, {"conversations": service.list_conversations()})
        if method == "POST" and path == "/api/os/conversations":
            conversation = service.create_conversation(
                owner_id=str(payload.get("owner_id", "owner")),
                title=str(payload.get("title", "Infenergy Command")),
            )
            return _json(201, {"conversation": conversation})
        if method == "GET" and path == "/api/os/transactions":
            return _json(200, {"transactions": service.transactions.list()})
        if method == "POST" and path == "/api/os/command":
            message = str(payload.get("message", "")).strip()
            if not message:
                return _json(400, {"error": "message_required"})
            return _json(200, service.command(message, conversation_id=payload.get("conversation_id"), actor=str(payload.get("actor", "owner"))))
        if method == "POST" and path == "/api/os/execute":
            capability = str(payload.get("capability", "")).strip()
            if not capability:
                return _json(400, {"error": "capability_required"})
            result = service.execute_capability(
                capability, payload.get("arguments", {}), actor=str(payload.get("actor", "owner")),
                dry_run=bool(payload.get("dry_run", False)), operation_id=payload.get("operation_id"),
                approval_id=payload.get("approval_id"),
            )
            return _json(200, result)
        if method == "POST" and path.startswith("/api/os/approvals/"):
            approval_id = path.rsplit("/", 1)[-1]
            result = service.policies.decide_approval(
                approval_id, approved=bool(payload.get("approved", False)),
                decided_by=str(payload.get("decided_by", "owner")), note=str(payload.get("note", "")),
            )
            return _json(200, result)
        if method == "POST" and path == "/api/os/undo":
            return _json(200, service.transactions.undo_last(actor=str(payload.get("actor", "owner"))))
        if method == "POST" and path.startswith("/api/os/transactions/") and path.endswith("/rollback"):
            transaction_id = path.split("/")[-2]
            return _json(200, service.transactions.rollback(transaction_id, actor=str(payload.get("actor", "owner"))))
        return _json(404, {"error": "not_found"})
    except KeyError as exc:
        return _json(404, {"error": str(exc)})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:
        return _json(500, {"error": f"{type(exc).__name__}: {exc}"})


def _json(status: int, payload: dict[str, Any]) -> tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


def _file(name: str) -> tuple[int, str, bytes]:
    if name not in {"index.html", "app.js", "styles.css"}:
        return _json(404, {"error": "asset_not_found"})
    path = UI_DIR / name
    if not path.exists():
        return _json(404, {"error": "asset_not_found"})
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return 200, f"{content_type}; charset=utf-8", path.read_bytes()