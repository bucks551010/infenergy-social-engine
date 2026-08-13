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
    visual = publication_record.get("visual") or {}
    copy = publication_record.get("copy") or {}
    packet = publication_record.get("creative_decision_packet") or {}
    return observe(strategy=strategy, metrics=raw, platform=str(observation.get("platform", ""))) | {
        "observation": observation,
        "state": "NEW_HYPOTHESIS",
        "support_count": 1,
        "contradiction_count": 0,
        "relationship": "Audience x Angle x Platform",
        "creative_relationships": {
            "layout_family_x_platform": [visual.get("layout_logic", ""), observation.get("platform", "")],
            "hook_family_x_platform": [strategy.get("genre_id", ""), observation.get("platform", "")],
            "copy_grammar_x_reader_job": [visual.get("copy_grammar", ""), strategy.get("reader_job", "")],
            "product_role_x_objective": [(visual.get("layout_grammar") or {}).get("product_role", ""), strategy.get("angle", "")],
            "human_presence_x_customer_moment": [(visual.get("layout_grammar") or {}).get("human_role", ""), strategy.get("customer_moment", "")],
            "benefit_presentation_x_audience": [(visual.get("benefit_translation") or {}).get("PRACTICAL_BENEFIT", ""), strategy.get("audience", "")],
            "text_density_x_platform": [(visual.get("layout_grammar") or {}).get("text_density", ""), observation.get("platform", "")],
            "visual_concept_x_audience": [(packet.get("SELECTED_ANSWER") or {}).get("creative_concept", ""), strategy.get("audience", "")],
        },
    }


def aggregate_creative_learning(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Promote only repeated, non-conflicted creative relationships to suggestions."""
    hypotheses: dict[str, dict[str, Any]] = {}
    for observation in observations:
        for dimension, values in (observation.get("creative_relationships") or {}).items():
            key = f"{dimension}:{'|'.join(map(str, values))}"
            hypotheses[key] = update_hypothesis(hypotheses.get(key), observation)
            hypotheses[key]["dimension"] = dimension
            hypotheses[key]["values"] = values
    supported = [item for item in hypotheses.values() if item["state"] == "SUPPORTED_PATTERN" and item["contradiction_count"] == 0]
    return {"hypotheses": hypotheses, "supported_patterns": supported, "recommendations": [{"dimension": item["dimension"], "values": item["values"], "action": "prefer as one controlled future test, not a permanent rule", "confidence": item["confidence"]} for item in supported]}