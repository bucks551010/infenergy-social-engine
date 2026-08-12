"""Small competitor observation cache with meaningful delta detection."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Any


FIELDS = ("positioning", "messages", "benefits", "customer_moments", "human_values", "questions", "territories", "visual_patterns")


def discover(configured: list[dict[str, Any]], *, category: str) -> list[dict[str, Any]]:
    """Return configured competitors relevant to a category; discovery is explicit, not a crawl."""
    return [item for item in configured if category.lower() in [str(c).lower() for c in item.get("categories", [])]]


def observe(observations: list[dict[str, Any]], previous: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updated: dict[str, Any] = dict(previous)
    changes: list[dict[str, Any]] = []
    for raw in observations:
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        record = {field: raw.get(field, [] if field != "positioning" else "") for field in FIELDS}
        record["category"] = raw.get("category", "")
        record["source"] = raw.get("source", "")
        record["confidence"] = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        fingerprint = sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        prior = updated.get(name, {})
        record["fingerprint"] = fingerprint
        updated[name] = record
        if fingerprint != prior.get("fingerprint"):
            changes.append({"competitor": name, "category": record["category"], "change": "new" if not prior else "marketing_message_changed", "confidence": record["confidence"]})
    return updated, changes