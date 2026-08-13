"""Bounded creative-concept decisions that preserve the locked strategy."""

from __future__ import annotations

from typing import Any


PROTECTED_STRATEGY_FIELDS = (
    "product",
    "audience",
    "customer_moment",
    "human_need",
    "human_value",
    "benefit",
    "positioning",
    "claim_limits",
    "proof",
    "reader_job",
)

_CONCEPT_FAMILIES = (
    ("customer_moment", "Start in the supported customer moment and make the product a supporting proof.", "recognition of a real situation", "context-led scene with one practical callout"),
    ("decision_support", "Turn the verified facts into a choice the reader can make.", "a relevant tradeoff or decision", "comparison or priority ladder"),
    ("product_fit", "Show the job the product can support without claiming jobs it cannot prove.", "a concrete planning consideration", "product as evidence beside a decision checklist"),
)

_CONTRACT_STOPWORDS = {
    "about", "actually", "after", "before", "could", "every", "first", "from",
    "have", "into", "learn", "might", "other", "should", "their", "there",
    "these", "think", "those", "which", "would", "your",
}


def _findings(attempt: dict[str, Any]) -> set[str]:
    diagnosis = attempt.get("cognitive_diagnosis") if isinstance(attempt.get("cognitive_diagnosis"), dict) else {}
    return {
        str(item)
        for item in (
            attempt.get("current_candidate_findings")
            or attempt.get("critic_findings")
            or diagnosis.get("reason_codes")
            or []
        )
        if str(item)
    }


def metacognitive_review(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Escalate only after bounded, repeated local repair has not improved."""
    if len(attempts) < 3:
        return {"action": "CONTINUE_LOCAL_REPAIR", "reason": "insufficient_bounded_evidence", "evidence": {}}

    recent = attempts[-3:]
    scores = [float(item.get("orchestrator_critic_score") or item.get("score") or 0.0) for item in recent]
    persistent = set.intersection(*[_findings(item) for item in recent]) if all(_findings(item) for item in recent) else set()
    same_owner = len({
        str(((item.get("cognitive_diagnosis") or {}).get("repair_owner") or ""))
        for item in recent
    }) == 1
    non_improving = all(later <= earlier for earlier, later in zip(scores, scores[1:]))
    material_findings = persistent & {"hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"}
    if non_improving and same_owner and material_findings:
        return {
            "action": "ESCALATE_CREATIVE_CONCEPT",
            "reason": "LOCAL_REPAIR_DIMINISHING_RETURNS",
            "evidence": {"scores": scores, "persistent_findings": sorted(material_findings), "same_repair_owner": True},
        }
    return {
        "action": "CONTINUE_LOCAL_REPAIR",
        "reason": "local_repair_still_has_evidence_of_value",
        "evidence": {"scores": scores, "persistent_findings": sorted(persistent)},
    }


def concept_competition(strategy: dict[str, Any], feed_intelligence: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Create compact, strategy-derived alternatives without changing locked fields."""
    benefit = str(strategy.get("benefit") or strategy.get("important_capability") or "verified product facts")
    moment = str(strategy.get("customer_moment") or "the supported customer moment")
    reader_job = str(strategy.get("reader_job") or "HELP_ME_CHOOSE")
    feed_need = ", ".join((feed_intelligence or {}).get("what_feed_needs_next") or [])
    concepts = []
    for index, (identifier, thesis, conversation, visual_idea) in enumerate(_CONCEPT_FAMILIES, start=1):
        concepts.append({
            "id": identifier,
            "creative_thesis": thesis,
            "hook_approach": f"Connect {moment} to {benefit} through a {reader_job.lower()} question.",
            "human_entry_point": moment,
            "product_role": "supporting proof" if identifier == "customer_moment" else "decision evidence",
            "proof_role": "verified facts only",
            "conversation_mechanism": conversation,
            "visual_idea": visual_idea,
            "art_direction": feed_need or "clear hierarchy with one decision-relevant proof",
            "claim_risk": "low: preserves claim limits",
            "protected_strategy": {key: strategy.get(key) for key in PROTECTED_STRATEGY_FIELDS if key in strategy},
            "competition_rank": index,
        })
    return concepts


def select_concept(concepts: list[dict[str, Any]], *, feed_intelligence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prefer a concept that counters documented feed repetition, deterministically."""
    if not concepts:
        return {}
    needs = " ".join((feed_intelligence or {}).get("what_feed_needs_next") or []).lower()
    if "human/product balance" in needs:
        return next((item for item in concepts if item.get("id") == "customer_moment"), concepts[0])
    if "layout" in needs:
        return next((item for item in concepts if item.get("id") == "decision_support"), concepts[0])
    return concepts[0]


def pre_render_gate(*, concept: dict[str, Any], hook: str, body: str, visual_thesis: str, claim_safe: bool) -> dict[str, Any]:
    """Reject weak concepts before image rendering; generic engagement bait never passes."""
    hook_lower, body_lower = hook.lower(), body.lower()
    promise_terms = {token for token in hook_lower.split() if len(token) > 4 and token not in _CONTRACT_STOPWORDS}
    payoff_terms = {token for token in body_lower.split() if len(token) > 4 and token not in _CONTRACT_STOPWORDS}
    hook_payoff = bool(promise_terms & payoff_terms)
    generic_bait = any(phrase in hook_lower for phrase in ("what do you think", "tell us below", "would you use this"))
    conversation = bool(concept.get("conversation_mechanism")) and not generic_bait
    thesis_terms = {token for token in str(concept.get("creative_thesis") or "").lower().split() if len(token) > 4}
    alignment = bool(thesis_terms & ({token for token in visual_thesis.lower().split() if len(token) > 4} | payoff_terms))
    novelty = bool(concept.get("id")) and "portable power gives you power away from outlets" not in body_lower
    checks = {
        "hook_payoff": hook_payoff,
        "novelty": novelty,
        "conversation": conversation,
        "copy_visual_alignment": alignment,
        "claim_feasibility": bool(claim_safe),
    }
    return {
        "decision": "CONCEPT_READY" if all(checks.values()) else "REVISE_CONCEPT",
        "checks": checks,
        "hook_promise": hook,
        "payoff_location": "body" if hook_payoff else "",
        "payoff_evidence": sorted(promise_terms & payoff_terms),
        "payoff_strength": "supported" if hook_payoff else "weak",
        "hook_payoff_result": "PASS" if hook_payoff else "FAIL",
    }


def replay_attempt_history(
    *,
    strategy: dict[str, Any],
    attempts: list[dict[str, Any]],
    hook: str,
    body: str,
    visual_thesis: str,
    claim_safe: bool,
    feed_intelligence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay a completed candidate history without any model, renderer, or publisher call."""
    metacognition = metacognitive_review(attempts)
    concepts = concept_competition(strategy, feed_intelligence)
    winner = select_concept(concepts, feed_intelligence=feed_intelligence)
    gate = pre_render_gate(
        concept=winner,
        hook=hook,
        body=body,
        visual_thesis=visual_thesis,
        claim_safe=claim_safe,
    )
    return {
        "metacognition": metacognition,
        "concepts": concepts,
        "winner": winner,
        "pre_render_gate": gate,
        "external_operations": [],
    }