"""Shared utilities for agents in this package."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def agent_dir(data_dir: str, agent_name: str) -> str:
    path = os.path.join(data_dir, "agents", agent_name)
    os.makedirs(path, exist_ok=True)
    return path


def write_snapshot(data_dir: str, agent_name: str, payload: dict) -> str:
    path = os.path.join(agent_dir(data_dir, agent_name), f"{agent_name}_{utc_stamp()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path


def read_json(path: str, default: Any) -> Any:
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def latest_snapshot(data_dir: str, agent_name: str) -> dict | None:
    folder = agent_dir(data_dir, agent_name)
    try:
        entries = sorted(
            (e for e in os.listdir(folder) if e.endswith(".json")),
            reverse=True,
        )
    except FileNotFoundError:
        return None
    if not entries:
        return None
    return read_json(os.path.join(folder, entries[0]), None)


def env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, "")).strip() or default)
    except (TypeError, ValueError):
        return default
