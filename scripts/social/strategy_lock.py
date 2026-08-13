"""Authoritative production parent object and downstream expression contracts."""
from __future__ import annotations

from typing import Any

REQUIRED = ("audience", "customer_moment", "human_need", "angle", "positioning", "non_price_edge", "benefit", "human_outcome", "claim_limits")


def lock(candidate: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
    strategy = candidate | {key: context.get(key, candidate.get(key, "")) for key in (
        "human_value", "topic", "reader_job", "important_capability", "benefit", "human_outcome",
        "competitive_context", "proof", "claim_limits", "visual_objective", "CTA_strategy",
    )}
    strategy["desired_memory"] = candidate.get("reader_memory", "")
    missing = [key for key in REQUIRED if not strategy.get(key)]
    if missing:
        raise ValueError(f"strategy lock missing: {', '.join(missing)}")
    return strategy


def copy_expression(strategy: dict[str, Any]) -> dict[str, Any]:
    return {key: strategy[key] for key in REQUIRED} | {"expression": "copy", "central_angle": strategy["angle"]}


def visual_expression(strategy: dict[str, Any]) -> dict[str, Any]:
    return {key: strategy[key] for key in REQUIRED} | {"expression": "visual", "central_angle": strategy["angle"], "visual_objective": strategy.get("visual_objective", "reinforce the human outcome")}


def human_connection_critique(*, strategy: dict[str, Any], copy: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
    human = strategy.get("human_need", "").lower()
    copy_text = " ".join(str(value) for value in copy.values()).lower()
    visual_text = " ".join(str(value) for value in visual.values()).lower()
    natural = not any(word in copy_text for word in ("fear", "panic", "guaranteed"))
    return {"copy_expresses_connection": bool(human and human in copy_text), "visual_reinforces_connection": bool(human and (human in visual_text or strategy.get("human_outcome", "").lower() in visual_text)), "natural": natural, "passed": natural}


def integrity(strategy: dict[str, Any], copy: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
    """Verify outputs retain the lock rather than only trusting the input path."""
    required = ("audience", "customer_moment", "human_need", "human_value", "topic", "angle", "offering", "benefit", "human_outcome", "positioning", "non_price_edge", "claim_limits")
    mismatches = [key for key in required if copy.get("strategy_lock", {}).get(key, strategy.get(key)) != strategy.get(key) or visual.get("strategy_lock", {}).get(key, strategy.get(key)) != strategy.get(key)]
    cta_match = copy.get("cta", strategy.get("CTA_strategy")) == strategy.get("CTA_strategy")
    if not cta_match:
        mismatches.append("CTA")
    verdict = "ALIGNED" if not mismatches else "MATERIAL_DRIFT" if any(key in {"audience", "angle", "claim_limits", "offering"} for key in mismatches) else "MINOR_DRIFT"
    return {"verdict": verdict, "mismatches": mismatches, "publishable": verdict != "MATERIAL_DRIFT"}