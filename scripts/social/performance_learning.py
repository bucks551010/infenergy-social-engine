"""Cautious performance interpretation that produces hypotheses, never permanent truth."""
from __future__ import annotations

from typing import Any


def observe(*, strategy: dict[str, Any], metrics: dict[str, float], platform: str) -> dict[str, Any]:
    engagement = sum(float(metrics.get(key, 0) or 0) for key in ("saves", "shares", "comments", "clicks", "conversions"))
    confidence = 0.2 if engagement < 3 else 0.45
    return {"type": "PERFORMANCE_EVIDENCE", "platform": platform, "strategy": {key: strategy.get(key, "") for key in ("audience", "customer_moment", "human_need", "topic", "angle", "offering", "positioning")}, "metrics": metrics, "confidence": confidence, "interpretation": "a weak directional signal, not strategic truth", "next_change": "test a related angle with one controlled difference", "uncertainty": "single-post performance cannot establish causality"}