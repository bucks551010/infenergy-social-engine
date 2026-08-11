"""Transformation mapper — Spec Section 4."""

from __future__ import annotations

from .libraries import transformations


def for_audience(audience_id: str) -> list[dict[str, str]]:
    return [
        {"from": t["from"], "to": t["to"]}
        for t in transformations()
        if audience_id in t.get("audiences", [])
    ]


def default_pair(audience_id: str) -> tuple[str, str]:
    matches = for_audience(audience_id)
    if matches:
        return matches[0]["from"], matches[0]["to"]
    return "uncertain", "in_control"
