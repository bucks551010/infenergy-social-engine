"""Lean, persistent marketing-decision loop; it observes and prioritizes, never posts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from . import analytics_ingestion, consumer_intelligence, competitor_intelligence, creative_cognition, market_strategy, opportunity_graph, performance_learning, research_router, strategy_lock

HEARTBEAT_LEVELS = {"LIGHT_HEARTBEAT", "STANDARD_HEARTBEAT", "DEEP_HEARTBEAT", "DEEP_REFRESH"}
DEFAULT_BUDGETS = {
    "LIGHT_HEARTBEAT": {"max_research_tasks": 1, "max_sources_retrieved": 2, "max_competitor_refreshes": 1},
    "STANDARD_HEARTBEAT": {"max_research_tasks": 3, "max_sources_retrieved": 6, "max_competitor_refreshes": 3},
    "DEEP_HEARTBEAT": {"max_research_tasks": 5, "max_sources_retrieved": 10, "max_competitor_refreshes": 5},
    "DEEP_REFRESH": {"max_research_tasks": 5, "max_sources_retrieved": 10, "max_competitor_refreshes": 5},
}
EXPLORATION_RESERVE = 0.25
SEASONAL_LOOKAHEAD = (
    {"id": "gulf_hurricane_readiness", "months": (6, 7, 8, 9, 10), "lead_days": 21, "territory": "preparedness over panic"},
    {"id": "summer_heat_and_travel", "months": (5, 6, 7, 8, 9), "lead_days": 14, "territory": "portable practical power"},
    {"id": "winter_outage_planning", "months": (11, 12, 1, 2), "lead_days": 21, "territory": "household continuity"},
)


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


def seasonal_lookahead(*, now: datetime | None = None) -> list[dict[str, Any]]:
    """Return upcoming preparation windows without creating paste-ready content."""
    now = now or datetime.now(timezone.utc)
    active: list[dict[str, Any]] = []
    for window in SEASONAL_LOOKAHEAD:
        if now.month in window["months"]:
            active.append({**window, "status": "PRE_STAGE", "observed_at": now.isoformat()})
    return active


def visual_novelty(records: list[dict[str, Any]], *, limit: int = 30) -> dict[str, Any]:
    """Report bounded visual repetition dimensions from the existing visual memory."""
    recent = [record for record in records[-limit:] if isinstance(record, dict)]
    dimensions = {
        "scene": [str(record.get("v5_scene") or "") for record in recent],
        "archetype": [str(record.get("v5_archetype") or "") for record in recent],
        "product_presence": [str(record.get("v5_product_presence") or "") for record in recent],
        "signature": [str(record.get("visual_signature") or "") for record in recent],
    }
    summary = {}
    for name, values in dimensions.items():
        populated = [value for value in values if value]
        unique = len(set(populated))
        summary[name] = {"samples": len(populated), "unique": unique, "repeat_rate": round(1.0 - unique / max(1, len(populated)), 3)}
    return {"window": limit, "dimensions": summary, "healthy": all(item["repeat_rate"] <= 0.7 for item in summary.values())}


def exploration_status(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep a fixed allocation outside previously supported patterns."""
    recent = [record for record in records[-40:] if isinstance(record, dict)]
    exploratory = sum(bool(record.get("exploration")) for record in recent)
    share = exploratory / max(1, len(recent))
    return {"samples": len(recent), "exploration_share": round(share, 3), "minimum_share": EXPLORATION_RESERVE, "ready": share >= EXPLORATION_RESERVE or not recent}


def record_decision(data_dir: str, *, post_id: str, strategy: dict[str, Any], direction: dict[str, Any], human_truth: dict[str, Any], prompt_governance: dict[str, Any]) -> None:
    """Persist bounded decision metadata; static owner truth is never modified."""
    state = load(data_dir)
    entry = {
        "post_id": post_id,
        "tension_id": direction.get("tension_id", ""),
        "reader_job": strategy.get("reader_job", ""),
        "scene": direction.get("scene", ""),
        "archetype": direction.get("archetype", ""),
        "product_presence": direction.get("product_presence", ""),
        "prompt_governance": prompt_governance.get("status", ""),
        "reader_value_ready": human_truth.get("ready", False),
        "exploration": bool(direction.get("tension_id")),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state.setdefault("decision_history", []).append(entry)
    state["decision_history"] = state["decision_history"][-500:]
    state.setdefault("visual_usage", []).append({
        "v5_scene": entry["scene"], "v5_archetype": entry["archetype"],
        "v5_product_presence": entry["product_presence"], "visual_signature": direction.get("scene", ""),
    })
    state["visual_usage"] = state["visual_usage"][-500:]
    state["visual_novelty"] = visual_novelty(state["visual_usage"])
    state["exploration"] = exploration_status(state["decision_history"])
    save(data_dir, state)


def propose_static_update(data_dir: str, *, proposal_type: str, rationale: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Queue a non-executable owner proposal; this function never changes static truth."""
    if not proposal_type.strip() or not rationale.strip() or not evidence:
        raise ValueError("proposal_type, rationale, and evidence are required")
    proposal = {
        "proposal_type": proposal_type.strip(),
        "rationale": rationale.strip(),
        "evidence": [dict(item) for item in evidence if isinstance(item, dict)][:10],
        "status": "PENDING_OWNER_APPROVAL",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state = load(data_dir)
    state.setdefault("static_proposals", []).append(proposal)
    state["static_proposals"] = state["static_proposals"][-100:]
    save(data_dir, state)
    return proposal


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
    publication_records: list[dict[str, Any]] | None = None,
    business_personality: str = "",
    capability: str = "",
    offering_truth: list[str] | None = None,
    budget: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Observe only decision-relevant deltas and emit opportunities; no copy or publishing."""
    if level not in HEARTBEAT_LEVELS:
        raise ValueError(f"unsupported heartbeat level: {level}")
    state = load(data_dir)
    active_budget = DEFAULT_BUDGETS[level] | (budget or {})
    observations: list[dict[str, Any]] = []
    evidence = (list(research_evidence or []) + list(performance_observations or []))[:active_budget["max_sources_retrieved"]]
    for record in publication_records or []:
        stage = analytics_ingestion.due(record)
        if not stage:
            continue
        for observation in analytics_ingestion.collect_meta(record):
            if observation.get("status"):
                state.setdefault("operational_failures", []).append(observation)
                continue
            observation["window"] = stage
            record.setdefault("analytics_observations", []).append(observation)
            evidence.append(performance_learning.learn(publication_record=record, observation=observation))
    evidence = evidence[:active_budget["max_sources_retrieved"]]
    creative_observations = [item for item in evidence if item.get("creative_relationships")]
    creative_learning = performance_learning.aggregate_creative_learning(creative_observations)
    state["creative_learning"] = creative_learning
    visual_records = state.get("visual_usage", [])
    state["visual_novelty"] = visual_novelty(visual_records)
    state["exploration"] = exploration_status(state.get("decision_history", []))
    state["seasonal_lookahead"] = seasonal_lookahead()
    consumers = consumer_intelligence.normalize(consumer_signals or [])
    state["consumer_relationships"] = consumer_intelligence.relationships(consumers)
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
    state["positioning"] = position
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
    reference_level = {"LIGHT_HEARTBEAT": "LIGHT", "STANDARD_HEARTBEAT": "STANDARD", "DEEP_HEARTBEAT": "DEEP", "DEEP_REFRESH": "DEEP"}[level]
    graph = creative_cognition.load_reference_graph(data_dir)
    has_external = any(item.get("source_type") != "internal_repository" for item in graph.get("references", []))
    knowledge_need = ""
    if reference_level == "STANDARD" and not has_external:
        knowledge_need = "information design and social layout principles"
    elif reference_level == "DEEP" and (graph.get("stagnation_review") or {}).get("needs_diversification", True):
        knowledge_need = "visual storytelling and product presentation principles"
    creative_heartbeat = creative_cognition.reference_heartbeat(data_dir, level=reference_level, knowledge_need=knowledge_need)
    campaign = _campaign_decision(state, level=level, creative_learning=creative_learning)
    if campaign["decision"] in {"start", "evolve"}:
        opportunity_graph.upsert(state["opportunities"], reason=campaign["reason"], support=[{"type": "CAMPAIGN_DECISION", "provenance": "living_intelligence", "confidence": campaign["confidence"]}])
    state["campaign_state"] = campaign
    state["last_heartbeat"] = {"level": level, "observations": len(observations), "at": datetime.now(timezone.utc).isoformat()}
    state.setdefault("heartbeat_history", {})[level] = state["last_heartbeat"] | {"budget": active_budget}
    if level in {"DEEP_HEARTBEAT", "DEEP_REFRESH"}:
        state["deep_review"] = {
            "assumptions_to_challenge": ["audience fit", "customer moments", "positioning defensibility", "overused needs and angles"],
            "research_needed": not bool(consumers and competitors),
            "action": "research_more" if not (consumers and competitors) else "review_current_evidence",
        }
    save(data_dir, state)
    return {"status": "ok", "observations": observations, "budget": active_budget, "research_evidence": evidence, "consumer_relationships": consumer_intelligence.relationships(consumers),
            "category_conversation": category_map, "whitespace": gap, "positioning": position, "opportunities": state["opportunities"], "creative_reference_heartbeat": creative_heartbeat, "creative_learning": creative_learning, "campaign_meeting": campaign}


def _campaign_decision(state: dict[str, Any], *, level: str, creative_learning: dict[str, Any]) -> dict[str, Any]:
    """A material, bounded campaign meeting triggered only by STANDARD/DEEP state."""
    if level == "LIGHT_HEARTBEAT":
        return {"decision": "no_change", "reason": "light heartbeat does not convene campaign meetings", "confidence": 0.0}
    ready = [item for item in state.get("opportunities", []) if item.get("state") in {"NEW", "READY"}]
    prior = state.get("campaign_state", {})
    if prior.get("decision") in {"start", "evolve"} and not ready:
        return {"decision": "pause", "reason": "no current evidence-backed opportunity sustains the campaign", "confidence": 0.6, "participants": ["Campaign Architect", "Creative Director", "Performance Analyst"]}
    if len(ready) >= 2 or creative_learning.get("supported_patterns"):
        return {"decision": "evolve" if prior.get("decision") in {"start", "evolve"} else "start", "reason": "multiple evidence-backed opportunities or repeated creative learning justify a coordinated sequence", "confidence": 0.65, "participants": ["Campaign Architect", "Creative Director", "Human Connection Strategist", "Platform Creative Strategist", "Performance Analyst"], "next_content_priority": "campaign_sequence"}
    return {"decision": "no_change", "reason": "insufficient material campaign evidence", "confidence": 0.45, "participants": ["Campaign Architect"]}


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
    result = {"decision": "strategy_selected", "participants": participants, "opportunity_id": opportunity["id"], "candidate_strategies": candidates,
            "evaluations": evaluations, "approved_strategy": locked | {"opportunity_id": opportunity["id"], "claim_limits": edge["claim_limit"]}}
    state["last_council_decision"] = {"decision": result["decision"], "opportunity_id": opportunity["id"], "at": datetime.now(timezone.utc).isoformat()}
    return result


def decision_record(*, trigger: str, heartbeat_result: dict[str, Any], council_result: dict[str, Any]) -> dict[str, Any]:
    """Concise owner explainability record; intentionally excludes hidden reasoning."""
    strategy = council_result.get("approved_strategy", {})
    return {"trigger": trigger, "intelligence_snapshot_id": heartbeat_result.get("positioning", {}).get("territory", ""), "audience": strategy.get("audience", ""), "customer_moment": strategy.get("customer_moment", ""), "human_need": strategy.get("human_need", ""), "research_tasks": heartbeat_result.get("research_evidence", []), "competitors_considered": heartbeat_result.get("observations", []), "category_conversation_summary": heartbeat_result.get("category_conversation", {}), "whitespace": heartbeat_result.get("whitespace", {}), "positioning": strategy.get("positioning", ""), "non_price_edge": strategy.get("non_price_edge", {}), "candidate_strategies": council_result.get("candidate_strategies", []), "council_objections": council_result.get("disagreements", []), "selected_strategy": strategy, "claim_limits": strategy.get("claim_limits", ""), "publish_decision": "pending_quality_governance"}


def operational_status(data_dir: str) -> dict[str, Any]:
    state = load(data_dir)
    items = state.get("opportunities", [])
    proposals = state.get("static_proposals", [])
    return {"last_light_heartbeat": state.get("heartbeat_history", {}).get("LIGHT_HEARTBEAT"), "last_standard_heartbeat": state.get("heartbeat_history", {}).get("STANDARD_HEARTBEAT"), "last_deep_heartbeat": state.get("heartbeat_history", {}).get("DEEP_HEARTBEAT"), "opportunities_ready": sum(item.get("state") == "READY" for item in items), "opportunities_research_needed": sum(item.get("state") == "RESEARCH_NEEDED" for item in items), "last_council_decision": state.get("last_council_decision"), "recent_failures": state.get("operational_failures", [])[-10:], "pending_owner_proposals": sum(item.get("status") == "PENDING_OWNER_APPROVAL" for item in proposals if isinstance(item, dict)), "unresolved_operational_blockers": ["authenticated_railway_content_preview_not_verified"]}