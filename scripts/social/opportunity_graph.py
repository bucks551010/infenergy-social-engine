"""Bounded opportunity state with provenance-aware support."""
from __future__ import annotations

from hashlib import sha256
from typing import Any


VALID_STATES = {"NEW", "RESEARCH_NEEDED", "READY", "DEFERRED", "SELECTED", "USED", "EXPIRED", "REJECTED"}


def upsert(items: list[dict[str, Any]], *, reason: str, support: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key = sha256((reason + repr(support)).encode()).hexdigest()[:16]
    if not any(item.get("id") == key for item in items):
        state = "READY" if support else "RESEARCH_NEEDED"
        items.append({"id": key, "state": state, "reason": reason, "support": support})
    return items