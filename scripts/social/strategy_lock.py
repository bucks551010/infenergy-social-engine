"""Authoritative production parent object and downstream expression contracts."""
from __future__ import annotations

from typing import Any

from . import copy_intelligence

REQUIRED = ("audience", "customer_moment", "human_need", "angle", "positioning", "non_price_edge", "benefit", "human_outcome", "claim_limits")

_EVIDENCE_REQUIREMENTS = {
    "runtime": (("runtime", "how long", "lasts", "duration"), ("runtime", "hour", "hours", "duration")),
    "compatibility": (("compatible", "compatibility", "works with", "will it run", "supports"), ("compatible", "compatibility", "supported device", "works with", "supports")),
    "performance": (("performance", "output", "load", "speed", "charging time", "charge time"), ("performance", "output", "load", "speed", "charging time", "charge time")),
    "capacity": (("capacity", "coverage", "range"), ("capacity", "coverage", "range")),
    "efficiency": (("efficiency", "efficient", "losses"), ("efficiency", "efficient", "losses")),
    "savings": (("save money", "saves money", "saving money", "savings", "cheaper", "cost less"), ("savings", "cost", "price", "financial")),
    "comparative_superiority": (("best", "better than", "outperforms", "fastest", "highest"), ("comparison", "compared", "benchmark", "independent test")),
}


def _evidence_requirements(text: str) -> list[str]:
    low = text.lower()
    return [
        requirement for requirement, (intent_terms, _) in _EVIDENCE_REQUIREMENTS.items()
        if any(term in low for term in intent_terms)
    ]


def lesson_condition(red_team_result: dict[str, Any]) -> str:
    """Return the stable scope key used for evidence-backed strategy lessons."""
    requirements = red_team_result.get("evidence_requirements") if isinstance(red_team_result, dict) else []
    requirement = str(requirements[0]).strip() if isinstance(requirements, list) and requirements else "evidence"
    return f"{requirement}_angle_without_verified_evidence"


def lock(candidate: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
    strategy = candidate | {key: context.get(key, candidate.get(key, "")) for key in (
        "human_value", "topic", "reader_job", "important_capability", "benefit", "human_outcome",
        "competitive_context", "proof", "claim_limits", "visual_objective", "CTA_strategy",
    )}
    strategy["desired_memory"] = candidate.get("reader_memory", "")
    missing = [key for key in REQUIRED if not strategy.get(key)]
    if missing:
        raise ValueError(f"strategy lock missing: {', '.join(missing)}")
    strategy.setdefault("strategy_version", 1)
    strategy.setdefault("strategy_lifecycle", "LOCKED")
    strategy.setdefault("strategy_audit", [])
    return strategy


def red_team(candidate: dict[str, Any], *, verified_facts: list[str], forbidden_claims: list[str] | None = None) -> dict[str, Any]:
    """Challenge evidence-incompatible proposals before Strategy Lock is authoritative.

    This is a bounded, deterministic council check. It can challenge a
    proposal but cannot select a product, audience, benefit, or claim limit.
    """
    angle = str(candidate.get("angle") or "").lower()
    hook = str(candidate.get("hook_promise") or candidate.get("hook") or "").lower()
    evidence = " ".join(str(item) for item in verified_facts).lower()
    forbidden = " ".join(str(item) for item in forbidden_claims or []).lower()
    requirements = _evidence_requirements(f"{angle} {hook}")
    evidence_gaps: list[str] = []
    evidence_available: dict[str, bool] = {}
    for requirement in requirements:
        evidence_terms = _EVIDENCE_REQUIREMENTS[requirement][1]
        supported = any(term in evidence for term in evidence_terms)
        evidence_available[requirement] = supported
        if not supported:
            evidence_gaps.append(f"verified_{requirement}_evidence_missing")
        if any(term in forbidden for term in _EVIDENCE_REQUIREMENTS[requirement][0]):
            evidence_gaps.append(f"claim_limits_prohibit_unverified_{requirement}")
    if evidence_gaps:
        return {
            "verdict": "CHANGE_ANGLE",
            "reason": "angle_requires_unverified_evidence",
            "challenge_evidence": evidence_gaps,
            "participants": ["Strategy Owner", "Strategy Red Team", "Evidence / Claim Intelligence", "Human Connection Strategist"],
            "can_lock": False,
            "evidence_requirements": requirements,
            "evidence_available": evidence_available,
        }
    return {
        "verdict": "PASS",
        "reason": "angle_is_supported_by_available_evidence",
        "challenge_evidence": [],
        "participants": ["Strategy Owner", "Strategy Red Team", "Evidence / Claim Intelligence"],
        "can_lock": True,
        "evidence_requirements": requirements,
        "evidence_available": evidence_available,
    }


def reconsider_angle(strategy: dict[str, Any], *, reason: str, evidence: list[str], new_angle: str, new_hook_promise: str) -> dict[str, Any]:
    """Governed partial reopen: only angle, hook promise, and topic path may change."""
    preserved = (
        "audience", "customer_moment", "human_need", "human_value", "offering",
        "positioning", "benefit", "proof", "claim_limits", "reader_job",
    )
    repaired = dict(strategy)
    prior_version = int(strategy.get("strategy_version") or 1)
    repaired.update({
        "angle": new_angle,
        "hook_promise": new_hook_promise,
        "strategy_version": prior_version + 1,
        "previous_strategy_version": prior_version,
        "strategy_lifecycle": "RELOCKED",
        "strategy_audit": list(strategy.get("strategy_audit") or []) + [{
            "event": "GOVERNED_STRATEGY_RECONSIDERATION",
            "challenge_reason": reason,
            "challenge_evidence": list(evidence),
            "fields_reopened": ["angle", "hook_promise", "topic_path"],
            "fields_preserved": list(preserved),
            "new_values": {"angle": new_angle, "hook_promise": new_hook_promise},
            "relock_reason": "repaired angle can be fulfilled using verified product evidence",
        }],
    })
    return repaired


def post_sanitization_coherence(strategy: dict[str, Any], *, hook: str, body: str, removed_claims: list[str]) -> dict[str, Any]:
    """Determine whether safe claim removal made the locked angle nonviable."""
    payoff_ok, payoff_reason = copy_intelligence.contract_ok(hook, body)
    factual_promise = _evidence_requirements(f"{strategy.get('angle', '')} {hook}")
    if removed_claims and not payoff_ok and factual_promise:
        return {
            "verdict": "STRATEGY_RECONSIDERATION_REQUIRED",
            "reason": "angle_evidence_incompatible_after_claim_removal",
            "evidence": list(removed_claims) + [payoff_reason],
            "repair_owner": "Strategy Intelligence",
            "repair_scope": "angle_and_hook_promise",
        }
    if removed_claims and not payoff_ok:
        return {
            "verdict": "COPY_REPAIR_REQUIRED",
            "reason": "claim_removal_broke_hook_payoff",
            "evidence": list(removed_claims) + [payoff_reason],
            "repair_owner": "Copy Intelligence",
            "repair_scope": "copy",
        }
    return {
        "verdict": "COPY_STILL_COHERENT",
        "reason": payoff_reason,
        "evidence": list(removed_claims),
        "repair_owner": "none",
        "repair_scope": "none",
    }


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