"""Cautious performance interpretation that produces hypotheses, never permanent truth."""
from __future__ import annotations

from typing import Any


def update_hypothesis(existing: dict[str, Any] | None, observation: dict[str, Any]) -> dict[str, Any]:
    """Merge supporting or contradictory observations without discarding either."""
    existing = dict(existing or {})
    engagement = sum(float(value or 0) for value in observation.get("metrics", {}).values())
    positive = engagement >= 3
    supports = list(existing.get("supporting_observations", []))
    contradicts = list(existing.get("contradictory_observations", []))
    (supports if positive else contradicts).append(observation)
    support_count, contradiction_count = len(supports), len(contradicts)
    state = "CONFLICTED" if support_count and contradiction_count else "SUPPORTED_PATTERN" if support_count >= 3 else "EMERGING_PATTERN" if support_count >= 2 else "WEAK_SIGNAL" if support_count else "NEW_HYPOTHESIS"
    return existing | {"supporting_observations": supports, "contradictory_observations": contradicts, "support_count": support_count, "contradiction_count": contradiction_count, "confidence": round(min(0.75, 0.15 * support_count + 0.1 * contradiction_count), 2), "state": state, "platforms": sorted(set(existing.get("platforms", [])) | {str(observation.get("platform", ""))})}


def observe(*, strategy: dict[str, Any], metrics: dict[str, float], platform: str) -> dict[str, Any]:
    engagement = sum(float(metrics.get(key, 0) or 0) for key in ("saves", "shares", "comments", "clicks", "conversions"))
    confidence = 0.2 if engagement < 3 else 0.45
    return {"type": "PERFORMANCE_EVIDENCE", "platform": platform, "strategy": {key: strategy.get(key, "") for key in ("audience", "customer_moment", "human_need", "topic", "angle", "offering", "positioning")}, "metrics": metrics, "confidence": confidence, "interpretation": "a weak directional signal, not strategic truth", "next_change": "test a related angle with one controlled difference", "uncertainty": "single-post performance cannot establish causality"}


def learn(*, publication_record: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Turn a raw platform observation into a low-confidence relationship hypothesis."""
    raw = observation.get("raw_observation", {}).get("metrics", {})
    strategy = publication_record.get("strategic_brief") or publication_record.get("strategy_lock") or {}
    return observe(strategy=strategy, metrics=raw, platform=str(observation.get("platform", ""))) | {
        "observation": observation,
        "state": "NEW_HYPOTHESIS",
        "support_count": 1,
        "contradiction_count": 0,
        "relationship": "Audience x Angle x Platform",
    }