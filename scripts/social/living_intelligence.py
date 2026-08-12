"""Lean, persistent marketing-decision loop; it observes and prioritizes, never posts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from . import consumer_intelligence, competitor_intelligence, market_strategy, opportunity_graph, performance_learning, research_router, strategy_lock

HEARTBEAT_LEVELS = {"LIGHT_HEARTBEAT", "STANDARD_HEARTBEAT", "DEEP_HEARTBEAT", "DEEP_REFRESH"}


def _path(data_dir: str) -> str:
    return os.path.join(data_dir, "social", "living_intelligence.json")


def load(data_dir: str) -> dict[str, Any]:
    try:
        with open(_path(data_dir), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"first_party": {}, "competitors": {}, "opportunities": []}


def save(data_dir: str, state: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_path(data_dir)), exist_ok=True)
    with open(_path(data_dir), "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def human_connection(*, audience: str, moment: str, situation: str, need: str, capability: str, benefit: str, outcome: str, responsibility: str = "", friction: str = "") -> dict[str, str]:
    """Express a human meaning only when supported by a real customer moment."""
    meaning = ""
    text = f"{moment} {situation} {need}".lower()
    if any(word in text for word in ("outage", "storm", "emergency", "family")):
        meaning = "preparedness and confidence"
    elif any(word in text for word in ("travel", "commute", "away")):
        meaning = "freedom and convenience"
    return {"person": audience, "situation": situation, "what_matters": need, "responsibility_or_expectation": responsibility,
        "friction": friction, "human_need": need, "offering_capability": capability, "benefit": benefit,
        "outcome": outcome, "human_meaning": meaning}


def non_price_edge(*, capability: str, benefit: str, evidence: list[str], communication_edge: str = "") -> dict[str, str]:
    if evidence and capability and benefit:
        return {"kind": "PRODUCT_EDGE", "reason": f"{capability} supports {benefit}", "proof": "; ".join(evidence[:2])}
    if communication_edge:
        return {"kind": "MARKETING_COMMUNICATION_EDGE", "reason": communication_edge, "proof": "communication clarity, not superiority"}
    return {"kind": "NO_DEFENSIBLE_EDGE", "reason": "No supported reason beyond price", "proof": ""}


def heartbeat(
    data_dir: str,
    *,
    level: str = "LIGHT_HEARTBEAT",
    website_url: str = "",
    consumer_signals: list[dict[str, Any]] | None = None,
    competitor_observations: list[dict[str, Any]] | None = None,
    research_evidence: list[dict[str, Any]] | None = None,
    performance_observations: list[dict[str, Any]] | None = None,
    business_personality: str = "",
    capability: str = "",
    offering_truth: list[str] | None = None,
) -> dict[str, Any]:
    """Observe only decision-relevant deltas and emit opportunities; no copy or publishing."""
    if level not in HEARTBEAT_LEVELS:
        raise ValueError(f"unsupported heartbeat level: {level}")
    state = load(data_dir)
    observations: list[dict[str, Any]] = []
    evidence = list(research_evidence or []) + list(performance_observations or [])
    consumers = consumer_intelligence.normalize(consumer_signals or [])
    competitors, competitor_changes = competitor_intelligence.observe(competitor_observations or [], state.get("competitors", {}))
    state["competitors"] = competitors
    if website_url:
        prior = (state.get("first_party") or {}).get(website_url, {}).get("content_hash", "")
        current = research_router.inspect_first_party(website_url, prior)
        state.setdefault("first_party", {})[website_url] = current
        if current["changed"] or not prior:
            observations.append({"type": "first_party_change", "source": website_url, "signal": "business messaging or product change"})
    for change in competitor_changes:
        observations.append({"type": "competitor_change", "source": change["competitor"], "signal": change["change"]})
    category_map = market_strategy.conversation(competitors, consumers)
    gap = market_strategy.whitespace(conversation_map=category_map, business_personality=business_personality, capability=capability)
    position = market_strategy.positioning(whitespace_result=gap, business_personality=business_personality, offering_truth=offering_truth or [], audience_importance=0.8 if consumers else 0.0)
    for observation in observations:
        support = [{"type": "FIRST_PARTY_EVIDENCE" if observation["type"] == "first_party_change" else "COMPETITIVE_EVIDENCE", "provenance": observation["source"], "confidence": 0.7}]
        opportunity_graph.upsert(state["opportunities"], reason=observation["signal"], support=support)
    for consumer in consumers:
        support = [{"type": "CUSTOMER_EVIDENCE", "provenance": consumer.get("provenance") or consumer["source"], "confidence": consumer["confidence"]}]
        opportunity_graph.upsert(state["opportunities"], reason=consumer.get("question") or consumer["human_need"], support=support)
    for item in evidence:
        if float(item.get("confidence", 0) or 0) <= 0:
            continue
        opportunity_graph.upsert(state["opportunities"], reason=item.get("interpretation") or item.get("decision_affected") or "evidence update", support=[item])
    state["last_heartbeat"] = {"level": level, "observations": len(observations), "at": datetime.now(timezone.utc).isoformat()}
    if level in {"DEEP_HEARTBEAT", "DEEP_REFRESH"}:
        state["deep_review"] = {
            "assumptions_to_challenge": ["audience fit", "customer moments", "positioning defensibility", "overused needs and angles"],
            "research_needed": not bool(consumers and competitors),
            "action": "research_more" if not (consumers and competitors) else "review_current_evidence",
        }
    save(data_dir, state)
    return {"status": "ok", "observations": observations, "research_evidence": evidence, "consumer_relationships": consumer_intelligence.relationships(consumers),
            "category_conversation": category_map, "whitespace": gap, "positioning": position, "opportunities": state["opportunities"]}


def council(state: dict[str, Any], *, strategy_inputs: dict[str, Any]) -> dict[str, Any]:
    """Select a strategy from evidence; roles appear only when their evidence exists."""
    ready = [item for item in state.get("opportunities", []) if item.get("state") in {"NEW", "READY"}]
    if not ready:
        return {"decision": "do_not_generate", "reason": "no evidence-backed opportunity", "participants": ["Opportunity Strategist"]}
    opportunity = ready[0]
    participants = ["Business Intelligence Delegate", "Audience Advocate", "Human Connection Strategist", "Opportunity Strategist", "Final Reviewer"]
    if strategy_inputs.get("competitor_context"):
        participants.append("Competitor Strategist")
    customer = strategy_inputs.get("customer", {})
    edge = market_strategy.non_price_edge(customer=customer, capability=strategy_inputs.get("capability", ""), benefit=strategy_inputs.get("benefit", ""), evidence=opportunity.get("support", []), competitor_context=strategy_inputs.get("competitor_context", ""))
    candidates = market_strategy.angles(customer=customer, positioning_result=strategy_inputs.get("positioning", {}), edge=edge, why_now=opportunity["reason"], limit=int(strategy_inputs.get("candidate_count", 3)))
    if not candidates:
        return {"decision": "do_not_generate", "reason": "no credible positioning-backed angle", "participants": participants}
    # Roles evaluate different criteria, not separate fictional agents.
    evaluations = {"Audience Advocate": bool(customer.get("customer_moment")), "Human Connection Strategist": bool(customer.get("human_need")), "Brand Steward": bool(strategy_inputs.get("positioning", {}).get("credible")), "Research/Claim Officer": edge["edge_type"] != "NO_DEFENSIBLE_EDGE", "Adversarial Critic": edge["edge_type"] != "NO_DEFENSIBLE_EDGE"}
    blockers = [role for role, passed in evaluations.items() if not passed and role in {"Brand Steward", "Research/Claim Officer", "Adversarial Critic"}]
    if blockers:
        return {"decision": "research_more", "reason": "non-overridable evidence or identity objection", "participants": participants, "evaluations": evaluations, "disagreements": blockers}
    selected = candidates[0]
    try:
        locked = strategy_lock.lock(selected, context=strategy_inputs)
    except ValueError as exc:
        return {"decision": "research_more", "reason": str(exc), "participants": participants, "evaluations": evaluations}
    return {"decision": "strategy_selected", "participants": participants, "opportunity_id": opportunity["id"], "candidate_strategies": candidates,
            "evaluations": evaluations, "approved_strategy": locked | {"opportunity_id": opportunity["id"], "claim_limits": edge["claim_limit"]}}