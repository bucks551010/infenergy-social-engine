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


def campaign_runtime_decision(
    campaign: dict[str, Any] | None,
    *,
    audience_signals: list[dict[str, Any]] | None = None,
    open_threads: list[dict[str, Any]] | None = None,
    deferred_threads: list[dict[str, Any]] | None = None,
    performance_lessons: list[str] | None = None,
    stronger_opportunity: bool = False,
    product_pressure: bool = False,
) -> dict[str, Any]:
    """Decide campaign lifecycle before a post without replacing Audience Value."""
    prior = dict(campaign or {})
    signals = list(audience_signals or [])
    threads = list(open_threads or [])
    deferred = list(deferred_threads or [])
    performance = list(performance_lessons or [])
    status = str(prior.get("status") or "").upper()
    objective = str(prior.get("objective") or "")
    human_problem = str(prior.get("human_problem") or "")

    if not prior and not (objective and human_problem):
        return {"decision": "NO_CAMPAIGN", "campaign_state": {"status": "NO_CAMPAIGN", "campaign_health": "NOT_STARTED"}, "reason": "no sustained audience problem has been identified"}
    if not status or status == "NO_CAMPAIGN":
        if not (objective and human_problem) and signals:
            seed = signals[0]
            objective = str(seed.get("objective") or "help the audience make a better next decision")
            human_problem = str(seed.get("human_reality") or seed.get("tension") or "")
        if not (objective and human_problem):
            return {"decision": "NO_CAMPAIGN", "campaign_state": {"status": "NO_CAMPAIGN", "campaign_health": "NOT_STARTED"}, "reason": "the available signal supports only an isolated post"}
        decision = "START"
        reason = "a meaningful human problem has an objective and at least one distinct next question"
        status = "ACTIVE"
        phase = "RECOGNITION"
    elif status == "PAUSED":
        if prior.get("revisit_condition") and (signals or threads):
            decision = "CONTINUE"
            reason = "the revisit condition now has matching audience or thread evidence"
            status = "ACTIVE"
            phase = str(prior.get("current_phase") or "DEEPENING")
        else:
            return {"decision": "PAUSE", "campaign_state": prior, "reason": str(prior.get("pause_reason") or "the campaign awaits a stronger reason to resume")}
    elif status == "ENDED":
        return {"decision": "END", "campaign_state": prior, "reason": str(prior.get("end_reason") or "campaign objective is complete")}
    elif stronger_opportunity or product_pressure:
        return {"decision": "PAUSE", "campaign_state": prior | {"status": "PAUSED", "pause_reason": "a stronger fresh opportunity is current" if stronger_opportunity else "commercial pressure would reduce audience trust", "revisit_condition": "Resume when the unresolved campaign question again has stronger audience value than fresh opportunities.", "threads_open": threads, "threads_deferred": deferred, "campaign_health": "PAUSED_FOR_VALUE"}, "reason": "campaign continuity does not outrank current audience value"}
    elif not threads and prior.get("questions_answered"):
        return {"decision": "END", "campaign_state": prior | {"status": "ENDED", "end_reason": "the objective has been addressed and no independent question remains", "campaign_health": "COMPLETE", "threads_open": []}, "reason": "remaining campaign content would be reinforcement without a new purpose"}
    elif performance:
        decision = "EVOLVE"
        reason = "performance evidence changes the kind of value the audience needs next"
        status = "ACTIVE"
        phase = "DECISION_SUPPORT"
    else:
        decision = "CONTINUE"
        reason = "an unresolved campaign question still advances audience understanding"
        status = "ACTIVE"
        phase = str(prior.get("current_phase") or "DEEPENING")

    state = prior | {
        "campaign_id": str(prior.get("campaign_id") or f"campaign:{human_problem[:40].lower().replace(' ', '_')}"),
        "objective": objective,
        "human_problem": human_problem,
        "audience_starting_state": str(prior.get("audience_starting_state") or "the audience recognizes a routine but not its decision structure"),
        "narrative_thesis": str(prior.get("narrative_thesis") or "useful understanding should make the next decision clearer"),
        "current_audience_understanding": str(prior.get("current_audience_understanding") or "recognition is emerging"),
        "audience_understanding": str(prior.get("audience_understanding") or prior.get("current_audience_understanding") or "recognition is emerging"),
        "human_reality": str(prior.get("human_reality") or (signals[0].get("human_reality") if signals else "")),
        "current_phase": phase,
        "status": status,
        "questions_answered": list(prior.get("questions_answered") or []),
        "questions_created": list(prior.get("questions_created") or []),
        "unresolved_questions": [thread.get("unresolved_question") for thread in threads if thread.get("unresolved_question")],
        "assumptions_challenged": list(prior.get("assumptions_challenged") or []),
        "value_delivered": list(prior.get("value_delivered") or []),
        "proof_used": list(prior.get("proof_used") or []),
        "content_roles_used": list(prior.get("content_roles_used") or []),
        "threads_open": threads,
        "threads_deferred": deferred,
        "performance_lessons": performance,
        "product_pressure": product_pressure,
        "commercial_pressure": list(prior.get("commercial_pressure") or []),
        "creative_fatigue": str(prior.get("creative_fatigue") or "LOW"),
        "next_possible_moves": [thread.get("unresolved_question") for thread in threads if thread.get("unresolved_question")],
        "campaign_health": "ACTIVE_WITH_VALUE",
    }
    return {"decision": decision, "campaign_state": state, "reason": reason}


def apply_campaign_post(campaign: dict[str, Any], audience_value: dict[str, Any]) -> dict[str, Any]:
    """Persist only decision-relevant audience movement after the real post decision."""
    state = dict(campaign)
    if state.get("status") != "ACTIVE" or not audience_value or audience_value.get("abstain"):
        return state
    role_by_concept = {
        "dependency": "RECOGNITION", "priority": "DEEPENING", "requirements": "EDUCATION",
        "fit": "DECISION_SUPPORT", "tradeoff": "APPLICATION",
    }
    idea = audience_value.get("idea") or {}
    question = str(audience_value.get("reader_question") or "")
    created = str(audience_value.get("unresolved_question") or "")
    takeaway = str(audience_value.get("reader_takeaway") or "")
    state["questions_answered"] = (list(state.get("questions_answered") or []) + [question])[-12:]
    state["questions_created"] = (list(state.get("questions_created") or []) + ([created] if created else []))[-12:]
    state["current_audience_understanding"] = takeaway or state.get("current_audience_understanding", "")
    state["audience_understanding"] = state["current_audience_understanding"]
    state["value_delivered"] = (list(state.get("value_delivered") or []) + [takeaway])[-12:]
    state["content_roles_used"] = (list(state.get("content_roles_used") or []) + [role_by_concept.get(str(idea.get("current_concept") or ""), "REFLECTION")])[-12:]
    state["threads_open"] = [audience_value.get("continuity_thread")] if audience_value.get("continuity_thread", {}).get("status") == "OPEN" else []
    state["threads_deferred"] = list(audience_value.get("continuity_thread", {}).get("branch_successors") or [])
    return state


def campaign_decision_input(recent: dict[str, Any], campaign_decision: dict[str, Any]) -> dict[str, Any]:
    """Let a PAUSED campaign yield only its own thread pressure to fresher value."""
    prepared = dict(recent)
    campaign = campaign_decision.get("campaign_state") or {}
    prepared["campaign_state"] = campaign
    if campaign_decision.get("decision") != "PAUSE":
        return prepared
    campaign_thread_ids = {
        str(thread.get("thread_id") or "")
        for thread in list(campaign.get("threads_open") or []) + list(campaign.get("threads_deferred") or [])
        if isinstance(thread, dict)
    }
    if campaign_thread_ids:
        prepared["continuity_threads"] = [
            thread for thread in prepared.get("continuity_threads", [])
            if str(thread.get("thread_id") or "") not in campaign_thread_ids
        ]
    return prepared


def product_narrative_decision(
    campaign: dict[str, Any],
    audience_value: dict[str, Any],
    *,
    verified_facts: list[str],
    product_name: str = "",
) -> dict[str, Any]:
    """Choose product prominence after relevance; never use relevance as sales intensity."""
    relevance = str(audience_value.get("product_relevance") or "NOT_RELEVANT")
    question = str(audience_value.get("reader_question") or "")
    reality = str(audience_value.get("human_reality") or "")
    understanding = str(campaign.get("current_audience_understanding") or "")
    campaign_role = str((campaign.get("content_roles_used") or ["REFLECTION"])[-1])
    pressure = bool(campaign.get("product_pressure") or campaign.get("commercial_pressure"))
    if relevance not in {"NATURALLY_RELEVANT", "DIRECTLY_RELEVANT"}:
        return {"role": "NONE", "commercial_intensity": "NONE", "cta_class": "NO_CTA", "product_entry_question": "", "narrative_hijack": False, "reason": "product relevance has not been earned"}
    if not (question and reality and verified_facts):
        return {"role": "NONE", "commercial_intensity": "NONE", "cta_class": "NO_CTA", "narrative_hijack": True, "reason": "NARRATIVE_HIJACK: product lacks the campaign question, human reality, or verified evidence"}
    role = {
        "EDUCATION": "EVIDENCE", "DECISION_SUPPORT": "FIT_DEMONSTRATION",
        "APPLICATION": "APPLICATION", "PROOF": "EVIDENCE",
    }.get(campaign_role, "DECISION_SUPPORT")
    if pressure:
        role = "EXAMPLE" if role != "FIT_DEMONSTRATION" else "DECISION_SUPPORT"
    fact = verified_facts[0]
    intensity = "LIGHT" if relevance == "NATURALLY_RELEVANT" else "MODERATE"
    cta = "COMPARE" if role == "FIT_DEMONSTRATION" else "LEARN"
    return {
        "role": role, "commercial_intensity": intensity, "cta_class": cta,
        "product_entry_question": question, "product_entry_need": str(audience_value.get("practical_value") or ""),
        "product_entry_decision": str(audience_value.get("reader_takeaway") or ""),
        "human_reality": reality,
        "product_entry_campaign_context": understanding, "verified_fact": fact,
        "product_name": product_name or "this verified offering", "narrative_hijack": False,
        "visual_direction": "Show the decision criterion beside the verified capability; keep the human task as the primary visual subject.",
        "reason": "the verified fact answers the current campaign question without replacing the audience-value lesson",
    }


def product_expression_for_engine_a(
    *,
    campaign: dict[str, Any],
    reader_job: str,
    question: str,
    human_reality: str,
    practical_value: str,
    takeaway: str,
    verified_facts: list[str],
    product_name: str = "",
) -> dict[str, Any]:
    """Apply the existing product-entry policy after Engine A selects a product opportunity."""
    role_campaign = dict(campaign)
    role_campaign.setdefault("content_roles_used", ["DECISION_SUPPORT" if reader_job == "HELP_ME_CHOOSE" else "EDUCATION"])
    return product_narrative_decision(
        role_campaign,
        {
            "product_relevance": "NATURALLY_RELEVANT",
            "reader_question": question,
            "human_reality": human_reality,
            "practical_value": practical_value,
            "reader_takeaway": takeaway,
        },
        verified_facts=verified_facts,
        product_name=product_name,
    )


def product_entry_copy(audience_value: dict[str, Any], narrative: dict[str, Any]) -> str:
    """Render a product bridge as evidence, not a product-first reset."""
    if narrative.get("role") == "NONE" or narrative.get("narrative_hijack"):
        return ""
    expression = audience_value.get("expression") or {}
    return "\n\n".join(part for part in (
        expression.get("hook", audience_value.get("reader_question", "")),
        expression.get("why_interesting", ""),
        f"The question here is: {narrative['product_entry_question']}",
        f"For {audience_value.get('human_reality', '')}, {narrative['product_name']} is useful as a {narrative['role'].lower().replace('_', ' ')}: {narrative['verified_fact']}",
        f"Use that fact to test the requirement, not to skip it. {audience_value.get('practical_value', '')}",
        audience_value.get("reader_takeaway", ""),
        f"Remember: {expression.get('memory_anchor', audience_value.get('desired_memory_anchor', ''))}",
    ) if part)


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
    return {"last_light_heartbeat": state.get("heartbeat_history", {}).get("LIGHT_HEARTBEAT"), "last_standard_heartbeat": state.get("heartbeat_history", {}).get("STANDARD_HEARTBEAT"), "last_deep_heartbeat": state.get("heartbeat_history", {}).get("DEEP_HEARTBEAT"), "opportunities_ready": sum(item.get("state") == "READY" for item in items), "opportunities_research_needed": sum(item.get("state") == "RESEARCH_NEEDED" for item in items), "last_council_decision": state.get("last_council_decision"), "recent_failures": state.get("operational_failures", [])[-10:], "unresolved_operational_blockers": ["authenticated_railway_content_preview_not_verified"]}