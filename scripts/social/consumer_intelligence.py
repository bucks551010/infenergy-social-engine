"""Decision-relevant customer evidence and relationship normalization."""
from __future__ import annotations

from typing import Any


REQUIRED = ("audience", "customer_moment", "human_need", "offering", "source", "confidence")


def normalize(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only evidence that can inform audience, angle, or offering choice."""
    records: list[dict[str, Any]] = []
    for signal in signals:
        if not all(signal.get(key) not in (None, "") for key in REQUIRED):
            continue
        record = {key: signal.get(key, "") for key in (
            "audience", "customer_moment", "situation", "question", "misconception",
            "frustration", "expectation", "objection", "desired_outcome", "human_need",
            "responsibility", "offering", "topic", "source", "provenance",
        )}
        record["confidence"] = max(0.0, min(1.0, float(signal["confidence"])))
        records.append(record)
    return records


def relationships(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Expose the creative relationship chain without demographic expansion."""
    return [{key: str(record.get(key, "")) for key in (
        "audience", "customer_moment", "question", "human_need", "topic", "offering"
    )} for record in records]