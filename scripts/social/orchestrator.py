"""Social Intelligence Orchestrator (Master Build §4, §66, §90, §98).

Runs the end-to-end pipeline for a single post:

  1. Engine selection (rotation of A/B/C for balanced feed)
  2. Strategic brief (engine)
  3. Copy assembly (structure → beats → memory anchor)
  4. Visual direction (semantic role → format → art direction → prompt)
  5. Text/visual allocation
  6. Carousel expansion (when needed)
  7. Claim ledger
  8. Quality gate + Creative Director final test
  9. Memory recording (content + visual)

The orchestrator is deterministic given the same recent-history +
rotation index; it can safely run without network access. Real LLMs
and image generators are plugged in via the ``VisualProvider`` and
``ModelRouter`` layers.
"""

from __future__ import annotations

import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import (
    audience_value,
    carousel_director,
    claim_intelligence,
    claim_governance,
    copy_intelligence,
    creative_cognition,
    creative_intelligence,
    engines,
    libraries,
    lean_intelligence,
    memory_intelligence,
    model_router,
    opportunity_engine,
    quality_intelligence,
    recovery,
    strategy_lock,
    human_connection_review,
    visual_intelligence,
    visual_provider,
)


_DEFAULT_CTA_BY_JOB = {
    "TEACH_ME": "Learn more",
    "HELP_ME": "See how it works",
    "EXPLAIN_THIS": "Learn more",
    "SHOW_ME": "See how it works",
    "WARN_ME": "See how to stay ready",
    "PREPARE_ME": "Get outage-ready",
    "HELP_ME_CHOOSE": "Compare options",
    "SAVE_ME_TIME": "Shop the fix",
    "SAVE_ME_MONEY": "Compare options",
    "MAKE_ME_CURIOUS": "Learn more",
    "GIVE_ME_A_REFERENCE": "Save this",
    "START_A_CONVERSATION": "Share your take",
}


# Optional Business Intelligence Foundation hookup. Gated on the
# ENABLE_BUSINESS_INTELLIGENCE env flag so all existing behavior is
# preserved when the foundation is not enabled.
def _bi_enabled() -> bool:
    return os.environ.get("ENABLE_BUSINESS_INTELLIGENCE", "").lower() in {"1", "true", "yes", "on"}


def _load_bi_creative_context(offering_id: str = "") -> dict[str, Any] | None:
    if not _bi_enabled():
        return None
    try:
        from business_intelligence import api as bi_api
        from business_intelligence import profile as bi_profile
    except ImportError:
        return None
    try:
        if not bi_profile.load_current():
            bi_api.rebuild_profile()
        return bi_api.compile_creative_context(offering_id=offering_id)
    except Exception:
        return None


def _bi_preferred_pillar(ctx: dict[str, Any] | None) -> str | None:
    if not ctx:
        return None
    territories = ctx.get("content_territories") or []
    ranked = sorted(
        territories,
        key=lambda t: (t.get("brand_relevance", 0.0) + t.get("audience_relevance", 0.0)),
        reverse=True,
    )
    return ranked[0]["territory_id"] if ranked else None


def _bi_audience_hint(ctx: dict[str, Any] | None) -> str | None:
    if not ctx:
        return None
    seg = ctx.get("audience_segment") or {}
    return seg.get("segment_id") or None


def _bi_verified_facts(ctx: dict[str, Any] | None) -> list[str]:
    if not ctx:
        return []
    return list(ctx.get("verified_facts", []))


def _apply_verified_fact_opportunity(brief: engines.EngineBrief, remediation: dict[str, Any]) -> None:
    opportunity = remediation.get("verified_fact_opportunity")
    if not isinstance(opportunity, dict):
        return
    fact = str(opportunity.get("verified_fact") or "").strip()
    if not fact:
        return
    brief.question = str(opportunity.get("question") or brief.question)
    brief.angle = str(opportunity.get("angle") or brief.angle)
    brief.curiosity = str(opportunity.get("human_reality") or brief.curiosity)
    brief.reader_job = str(opportunity.get("reader_job") or brief.reader_job)
    brief.topic_path = {
        **brief.topic_path,
        "topic": str(opportunity.get("product_name") or brief.topic_path.get("topic") or "Product details"),
        "microtopic": fact,
        "angle": brief.angle,
    }
    brief.opportunity_score = float(opportunity.get("opportunity_score") or brief.opportunity_score)
    brief.opportunity_shortlist = list(remediation.get("verified_fact_opportunities") or [opportunity])
    brief.rationale.append("verified_facts_only_recovery")


def _bi_forbidden_claims(ctx: dict[str, Any] | None) -> list[str]:
    if not ctx:
        return []
    return list(ctx.get("forbidden_claims", []))


def _bi_visual_prohibitions(ctx: dict[str, Any] | None) -> list[str]:
    if not ctx:
        return []
    return list((ctx.get("brand_prohibitions") or {}).get("visual", []))


_CATEGORY_PILLAR_MAP = {
    "electric bikes": "electric_mobility",
    "e-bikes": "electric_mobility",
    "ebikes": "electric_mobility",
    "portable power": "portable_power",
    "emergency power": "portable_power",
    "travel power": "portable_power",
    "phone power banks": "portable_power",
}


def _category_to_pillar(category: str) -> str | None:
    return _CATEGORY_PILLAR_MAP.get(str(category or "").strip().lower())


def _quality_gated_product_free_opportunity(candidates: list[Any]) -> tuple[Any, list[Any]]:
    """Choose randomly only after product-free opportunities clear quality gates."""
    eligible = [
        candidate for candidate in candidates
        if float(candidate.scores.get("novelty", 0.0)) >= 0.5
        and float(candidate.scores.get("usefulness", 0.0)) >= 0.55
        and float(candidate.scores.get("platform_fit", 0.0)) >= 0.5
        and float(candidate.scores.get("visual_potential", 0.0)) >= 0.5
    ]
    if not eligible:
        raise RuntimeError("no viable opportunities generated")
    best_score = max(float(candidate.total) for candidate in eligible)
    band = [candidate for candidate in eligible if float(candidate.total) >= best_score - 0.08]
    return secrets.SystemRandom().choice(band), band


def _build_engine_brief(
    engine: Any,
    *,
    engine_name: str,
    preferred_engine: str | None,
    recent: dict[str, Any],
    audience_hint: str | None,
    seasonal_context: str | None,
    preferred_pillar: str | None,
    excluded_concepts: list[str],
    rotation_index: int,
    selected_opportunity_id: str,
) -> engines.EngineBrief:
    """Build a brief without allowing a manual product target to exhaust a viable field."""
    kwargs = {
        "recent": recent,
        "audience_hint": audience_hint,
        "seasonal_context": seasonal_context,
        "preferred_pillar": preferred_pillar,
        "excluded_concepts": excluded_concepts,
        "rotation_index": rotation_index,
        "selected_opportunity_id": selected_opportunity_id,
    }
    try:
        return engine.build(**kwargs)
    except RuntimeError as exc:
        if (
            engine_name == "A"
            and str(exc) == "no viable opportunities generated"
            and (audience_hint or preferred_pillar)
        ):
            kwargs["audience_hint"] = None
            kwargs["preferred_pillar"] = None
            return engine.build(**kwargs)
        raise


def _bi_brand_voice(ctx: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ctx:
        return None
    return ctx.get("voice") or None


def _bi_pick_offering(rotation_index: int) -> dict[str, Any] | None:
    """Rotate through catalog offerings when BI is active."""
    if not _bi_enabled():
        return None
    try:
        from business_intelligence import api as bi_api
    except ImportError:
        return None
    try:
        profile = bi_api.get_business_profile()
        offerings = profile.get("offerings", []) or []
        if not offerings:
            return None
        return offerings[rotation_index % len(offerings)]
    except Exception:
        return None

def _bi_pick_eligible_offering(rotation_index: int, excluded_product_ids: set[str]) -> dict[str, Any] | None:
    if not excluded_product_ids:
        return _bi_pick_offering(rotation_index)
    if not _bi_enabled():
        return None
    try:
        from business_intelligence import api as bi_api
        offerings = bi_api.get_business_profile().get("offerings", []) or []
        for offset in range(len(offerings)):
            candidate = offerings[(rotation_index + offset) % len(offerings)]
            candidate_id = str(candidate.get("offering_id") or candidate.get("sku") or "")
            if candidate_id and candidate_id not in excluded_product_ids:
                return candidate
    except Exception:
        return None
    return None


def _bi_get_offering(product_id: str) -> dict[str, Any] | None:
    """Look up one specific catalog offering by id/sku (an explicit caller
    request), independent of the ENABLE_BUSINESS_INTELLIGENCE creative-context flag."""
    if not product_id:
        return None
    try:
        from business_intelligence import api as bi_api
    except ImportError:
        return None
    try:
        found = bi_api.get_offering(product_id)
        if found:
            return found
        # The persisted profile snapshot can be stale relative to the
        # current catalog source (e.g. it was assembled before the
        # products CSV was resolvable in this environment) and simply
        # not contain this offering yet. Force one rebuild and retry
        # before giving up -- this is a deterministic, local-only,
        # non-LLM operation, safe to run on an explicit forced lookup.
        bi_api.rebuild_profile()
        return bi_api.get_offering(product_id)
    except Exception:
        return None


def _runtime_strategy_lock(brief: engines.EngineBrief, lean_context: dict[str, Any], offering: dict[str, Any] | None, data_dir: str | None = None) -> dict[str, Any]:
    """Use selected product/audience evidence when Council has not provided a lock."""
    human = lean_context.get("human_value") or {}
    relationships = lean_context.get("relationships") or {}
    understanding = lean_context.get("understanding") or {}
    marketing = lean_context.get("marketing") or {}
    facts = list(understanding.get("important_capabilities") or marketing.get("approved_marketing_claims") or [])
    benefit = str((human.get("benefits") or facts or ["practical product-fit guidance"])[0])
    moment = str(relationships.get("customer_moment") or (understanding.get("primary_use_cases") or ["choosing portable backup power"])[0])
    need = str(relationships.get("primary_problem") or (marketing.get("customer_questions") or ["a practical power decision"])[0])
    human_value = str(relationships.get("human_value") or "practical clarity")
    candidate = {
        "audience": brief.audience_segment,
        "customer_moment": moment,
        "human_need": need,
        "human_value": human_value,
        "topic": brief.topic_path.get("topic", ""),
        "angle": brief.angle,
        "offering": str((offering or {}).get("name") or lean_context.get("identity", {}).get("product_name") or "product guidance"),
        "positioning": "verified product-fit guidance",
        "non_price_edge": {"kind": "DECISION_SUPPORT_EDGE", "reason": "helps customers choose from verified product facts"},
        "important_capability": facts[0] if facts else "verified product facts",
        "benefit": benefit,
        "human_outcome": human_value,
        "reader_job": brief.reader_job,
        "competitive_context": "not inferred without evidence",
        "proof": facts,
        "claim_limits": "Use only verified product facts; do not imply unsupported protection or urgency.",
        "visual_objective": "make the product-fit decision easier to understand",
        "CTA_strategy": marketing.get("cta") or _DEFAULT_CTA_BY_JOB.get(brief.reader_job, "Learn more"),
    }
    red_team = strategy_lock.red_team(
        candidate,
        verified_facts=list((offering or {}).get("verified_facts") or facts),
        forbidden_claims=list((offering or {}).get("forbidden_claims") or []),
    )
    product_id = str((offering or {}).get("offering_id") or (offering or {}).get("sku") or "")
    prior_lessons: list[dict[str, Any]] = []
    for requirement in red_team.get("evidence_requirements", []):
        prior_lessons.extend(memory_intelligence.strategy_lessons(
            product_id=product_id,
            condition=f"{requirement}_angle_without_verified_evidence",
            data_dir=data_dir,
        ))
    if not red_team["can_lock"]:
        candidate["angle"] = f"Use verified product facts to assess {benefit}"
        candidate["hook_promise"] = f"Which verified facts help with {benefit}?"
        brief.angle = candidate["angle"]
    locked = strategy_lock.lock(candidate, context=candidate)
    locked["strategy_red_team"] = red_team
    locked["prior_scoped_lessons"] = prior_lessons
    locked["strategy_audit"].append({
        "event": "PRE_LOCK_STRATEGY_RED_TEAM",
        "verdict": red_team["verdict"],
        "challenge_evidence": red_team["challenge_evidence"],
        "action": "angle_redirected_before_lock" if not red_team["can_lock"] else "locked_without_change",
    })
    return locked


def _audience_value_strategy_lock(brief: engines.EngineBrief) -> dict[str, Any]:
    """Lock a product-free Engine B decision without weakening general review gates."""
    value = brief.audience_value
    candidate = {
        "audience": brief.audience_segment,
        "customer_moment": value["human_reality"].replace("_", " "),
        "human_need": "practical clarity",
        "human_value": "useful judgment",
        "topic": brief.topic_path.get("topic", "audience value"),
        "angle": value["reader_takeaway"],
        "offering": "audience-value education",
        "positioning": "product-free audience value",
        "non_price_edge": {"kind": "AUDIENCE_VALUE", "reason": value["why_it_matters"]},
        "important_capability": "a useful decision framework",
        "benefit": value["practical_value"],
        "human_outcome": value["reflection_value"],
        "reader_job": brief.reader_job,
        "competitive_context": "not applicable to product-free education",
        "proof": [],
        "claim_limits": "Do not name a product, SKU, link, price, or purchase outcome; state only the audience-value insight.",
        "visual_objective": "make the human decision or routine visible",
        "CTA_strategy": "",
        "reader_memory": value["desired_memory_anchor"],
    }
    return strategy_lock.lock(candidate, context=candidate)


# --- Engine rotation --------------------------------------------------------


def _pick_engine(rotation_index: int, engine_mix: tuple[str, ...] = ("A", "B", "B", "C", "B", "A", "B")) -> str:
    """Round-robin over a weighted mix.

    Master Build §98 explicitly wants B (audience value) to be the
    plurality with A + C sprinkled in for conversion + brand
    reinforcement.
    """
    if not engine_mix:
        return "B"
    return engine_mix[rotation_index % len(engine_mix)]


# --- Copy assembly ---------------------------------------------------------


def _llm_copy_beats(
    brief: engines.EngineBrief,
    structure_beats: list[str],
    bi_ctx: dict[str, Any] | None,
    offering: dict[str, Any] | None = None,
    copy_grammar: str = "",
    revision_feedback: list[str] | None = None,
) -> dict[str, str] | None:
    """Ask Gemini to write the actual beat copy (Master Build §15 Copy Architect).

    Returns ``None`` on any failure so the caller falls back to the
    deterministic template assembly below.
    """
    voice = _bi_brand_voice(bi_ctx) or {}
    # Prefer the specifically-anchored offering's own facts/benefits over the
    # generic business-wide context so forced-product posts are actually
    # about that product instead of a generic topic-library angle.
    verified = list((offering or {}).get("verified_facts") or []) or _bi_verified_facts(bi_ctx)
    forbidden = list((offering or {}).get("forbidden_claims") or []) or _bi_forbidden_claims(bi_ctx)
    benefits = list((offering or {}).get("functional_benefits") or [])
    pain_points = list((offering or {}).get("problems_addressed") or [])

    prompt_parts = [
        "You are the copy architect for Infenergy Power's social content engine.",
        f"Reader job: {brief.reader_job}. Topic: {brief.topic_path.get('topic', '')}.",
        f"Angle/insight: {brief.angle}.",
        f"Information gap or curiosity: {brief.curiosity or brief.information_gap}.",
        f"Audience segment: {brief.audience_segment}. Tone: {brief.tone}.",
        f"Genre: {brief.genre.get('id', '')}.",
    ]
    if copy_grammar:
        prompt_parts.append(f"Use this original copy grammar, not canned wording: {copy_grammar}.")
    if offering and offering.get("name"):
        prompt_parts.append(
            f"This post must be specifically about this anchored product: {offering.get('name')}. "
            "Ground the angle/hook/body in this product, not a generic category topic."
        )
    if benefits:
        prompt_parts.append("Core benefits to draw from: " + "; ".join(benefits) + ".")
    if pain_points:
        prompt_parts.append("Primary pain point it addresses: " + "; ".join(pain_points) + ".")
    if brief.misconception:
        prompt_parts.append(f"Misconception to correct: {brief.misconception}.")
    if voice.get("brand_personality"):
        prompt_parts.append(f"Brand voice: {voice.get('brand_personality')}.")
    if verified:
        prompt_parts.append("Verified facts you may cite: " + "; ".join(verified) + ".")
    if forbidden:
        prompt_parts.append("Never state or imply: " + "; ".join(forbidden) + ".")
    if revision_feedback:
        prompt_parts.append(
            "Revise the copy to resolve these critic findings while preserving the locked audience, "
            "customer moment, product, verified facts, and claim limits: "
            + "; ".join(revision_feedback)
            + "."
        )
    prompt_parts.append(
        "Write truthful, specific, non-generic copy. Avoid AI-slop phrases such as "
        "'game-changer', 'unlock', 'revolutionize', 'in today's fast-paced world', 'buckle up'."
    )
    prompt_parts.append(
        "Return a JSON object with exactly these keys, each a short 1-2 sentence string, "
        "no markdown: " + ", ".join(structure_beats) + "."
    )

    result = model_router.generate_json("copy_editing", " ".join(prompt_parts))
    if not isinstance(result, dict):
        return None
    if not all(str(result.get(b, "")).strip() for b in structure_beats):
        return None
    return {b: str(result[b]).strip() for b in structure_beats}


def _revision_objectives(feedback: list[str] | None, strategy: dict[str, Any]) -> list[str]:
    """Translate current critic findings into concrete, strategy-bound edits."""
    findings = {str(item) for item in feedback or []}
    objectives: list[str] = []
    if any(item.startswith(("runtime_", "unsupported_numeric_claim", "unverified_specification", "capacity_not_verified", "wattage_not_verified")) for item in findings):
        objectives.append("Remove unsupported numeric, runtime, and product-performance claims; do not replace them with new numbers.")
    if "primary_benefit_not_explicit" in findings:
        benefit = str(strategy.get("benefit") or "").strip()
        if benefit:
            objectives.append(f"State this verified primary benefit clearly and naturally: {benefit}.")
    if "humanness below bar" in findings:
        objectives.append(
            f"Write from the customer's real moment ({strategy.get('customer_moment', '')}) and concern "
            f"({strategy.get('human_need', '')}), not abstract product language."
        )
    if "generic_or_ai_like_language" in findings:
        objectives.append("Use concrete plain language; remove stock marketing transitions, vague hype, and repetitive CTA phrasing.")
    if "hook-payoff mismatch" in findings:
        objectives.append(
            "Make the body directly answer or fulfill the hook's promise using the locked customer moment, primary benefit, and verified facts."
        )
    return objectives


def _engine_a_decision_insight(narrative: dict[str, Any], verified_facts: list[str]) -> dict[str, Any]:
    """Derive the decision relationship that a fit demonstration must explain."""
    facts = [str(fact).strip() for fact in verified_facts if str(fact).strip()]
    capacity = next((fact for fact in facts if "wh" in fact.lower()), "")
    output = next((fact for fact in facts if "w" in fact.lower() and "wh" not in fact.lower()), "")
    access = next((fact for fact in facts if "v" in fact.lower()), "")
    fact_roles = [
        {"fact": output, "decision_role": "available_output", "human_relevance": "compare it with the device requirement"},
        {"fact": access, "decision_role": "connection_access", "human_relevance": "confirm the needed connection is available"},
        {"fact": capacity, "decision_role": "stored_reserve", "human_relevance": "estimate reserve only after fit is established"},
    ]
    return {
        "decision_question": str(narrative.get("product_entry_question") or "").strip(),
        "structure": "DEPENDENCY" if output and access and capacity else "BOUNDARY_CHECK",
        "criterion_a": "the device's actual requirement and needed connection",
        "criterion_b": "the stored-energy reserve",
        "relationship": "available output and connection determine whether the device can be supported in the first place; stored capacity describes reserve after that compatibility check",
        "why_relationship_matters": "a larger stored-energy number cannot establish fit when the required output or connection is unknown",
        "decision_consequence": "compare the device requirement with the published output and access first, then judge whether the published reserve suits the work period",
        "practical_check": "find the device requirement and connection, then compare both with the published product details",
        "verified_product_evidence": [item for item in fact_roles if item["fact"]],
        "limitation_or_boundary": "the product facts do not establish fit until the reader checks the actual device requirement",
        "human_application": str(narrative.get("human_reality") or "the current situation").strip(),
        "memory_anchor": "Establish fit before estimating reserve.",
    }


def _render_engine_a_decision_beats(
    beat_content: dict[str, str],
    narrative: dict[str, Any],
    insight: dict[str, Any],
) -> dict[str, str]:
    """Render the discovered decision structure without turning product facts into compatibility claims."""
    question = str(insight.get("decision_question") or "").strip()
    product = str(narrative.get("product_name") or "this offering").strip()
    evidence = [item for item in insight.get("verified_product_evidence", []) if isinstance(item, dict) and item.get("fact")]
    evidence_text = " ".join(
        f"Its published {item['fact']} describes {item['decision_role'].replace('_', ' ')}."
        for item in evidence
    )
    result = dict(beat_content)
    result["hook"] = question or str(result.get("hook") or "")
    result["answer"] = (
        f"{insight['relationship'].capitalize()}. {insight['why_relationship_matters'].capitalize()}."
    )
    result["explanation"] = (
        f"For {insight['human_application']}, {insight['decision_consequence']}."
    )
    result["example"] = (
        f"{product} is a fit example, not an automatic answer. {evidence_text} "
        f"{insight['limitation_or_boundary'].capitalize()}."
    )
    result["takeaway"] = str(insight["memory_anchor"])
    return result


def _engine_a_product_expression_beats(
    beat_content: dict[str, str],
    narrative: dict[str, Any],
    verified_facts: list[str],
) -> dict[str, str]:
    """Make an Engine A fit demonstration teach a portable decision relationship."""
    if narrative.get("role") not in {"FIT_DEMONSTRATION", "DECISION_SUPPORT"} or narrative.get("narrative_hijack"):
        return beat_content
    return _render_engine_a_decision_beats(
        beat_content,
        narrative,
        _engine_a_decision_insight(narrative, verified_facts),
    )


def _llm_concept_stems(brief: engines.EngineBrief, anchor: str) -> list[str] | None:
    """Ask Gemini for creative-concept stems (Master Build §30 / §15 Art Director)."""
    prompt = (
        "You are the creative director for Infenergy Power's social content engine. "
        f"Topic/angle: {brief.angle}. Memory anchor: {anchor or brief.angle}. "
        f"Genre: {brief.genre.get('id', '')}. "
        "Propose exactly 3 distinct, concrete visual concepts for a social graphic that "
        "communicates this idea (no camera jargon, one sentence each). "
        "Return JSON: {\"concepts\": [\"...\", \"...\", \"...\"]}."
    )
    result = model_router.generate_json("visual_direction", prompt)
    if not isinstance(result, dict):
        return None
    stems = result.get("concepts")
    if not isinstance(stems, list) or len(stems) < 2:
        return None
    cleaned = [str(s).strip() for s in stems if str(s).strip()]
    return cleaned or None


def _assemble_copy(*, brief: engines.EngineBrief, structure_beats: list[str]) -> dict[str, str]:
    """Populate beat content from the strategic brief.

    This is deliberately rule-based text assembly — a downstream LLM can
    replace it with richer language, but the shape/beats/anchor are
    already defined so the LLM's job is bounded (§99 auditability).
    """
    audience_value = brief.audience_value
    if audience_value and not audience_value.get("abstain"):
        question = str(audience_value.get("reader_question") or brief.question).strip()
        explanation = str(audience_value.get("why_it_matters") or brief.curiosity).strip()
        practical = str(audience_value.get("practical_value") or brief.angle).strip()
        takeaway = str(audience_value.get("reader_takeaway") or brief.angle).strip()
        value_templates = {
            "hook": question,
            "question": question,
            "answer": explanation,
            "explanation": explanation,
            "example": str(audience_value.get("reflection_value") or "").strip(),
            "takeaway": takeaway,
            "lesson": takeaway,
            "application": practical,
            "what_to_do": practical,
            "implication": str(audience_value.get("reflection_value") or takeaway).strip(),
            "why": explanation,
            "what_happens": str(audience_value.get("reflection_value") or "").strip(),
            "scenario": question,
            "consequence": explanation,
        }
        return {beat: value_templates.get(beat, takeaway) for beat in structure_beats}

    curiosity = brief.curiosity or brief.information_gap or brief.angle
    misc = brief.misconception or ""
    reality = brief.angle
    q = brief.question or f"What most people miss about {brief.topic_path.get('topic', 'this')}"
    gap = brief.information_gap or brief.curiosity or brief.angle

    templates: dict[str, str] = {
        "hook": q if q.endswith("?") else f"{q}?",
        "answer": f"{brief.angle}.",
        "explanation": f"The reason is {gap}.",
        "example": f"For example, in a real scenario: {brief.curiosity}.",
        "takeaway": f"Remember: {brief.angle}.",
        "problem": misc or f"Most people assume {brief.angle}.",
        "why": f"Because {gap}.",
        "what_happens": f"Which leads to {brief.curiosity}.",
        "what_to_do": f"So the practical move is to {brief.angle.lower()}.",
        "myth": misc or f"Common belief: {brief.angle}.",
        "reality": f"Actually: {reality}.",
        "implication": f"So {gap}.",
        "scenario": f"Imagine {brief.curiosity}.",
        "consequence": f"The result: {gap}.",
        "lesson": f"The takeaway: {brief.angle}.",
        "question": q,
        "surprising_answer": f"The answer: {brief.angle}.",
        "application": f"How to use it: {brief.angle}.",
    }
    # Return only beats the caller asked for
    return {b: templates.get(b, "") for b in structure_beats}


def _assemble_verified_fact_recovery_copy(
    *,
    brief: engines.EngineBrief,
    structure_beats: list[str],
    verified_fact: str,
) -> dict[str, str]:
    """Build a fact-scoped recovery candidate without reopening claim generation."""
    disclosure = f"Published specification: {verified_fact}."
    review_prompt = "Keep that published detail visible when reviewing the product."
    templates = {
        "hook": brief.question,
        "question": brief.question,
        "answer": disclosure,
        "explanation": disclosure,
        "example": review_prompt,
        "takeaway": review_prompt,
        "lesson": review_prompt,
        "application": review_prompt,
        "what_to_do": review_prompt,
        "implication": review_prompt,
        "why": disclosure,
        "what_happens": review_prompt,
    }
    return {beat: str(templates.get(beat, review_prompt)).strip() for beat in structure_beats}


# --- Pipeline result -------------------------------------------------------


@dataclass
class PostPackage:
    post_id: str
    engine: str
    brief: dict[str, Any]
    copy: dict[str, Any]
    visual: dict[str, Any]
    carousel: dict[str, Any] | None
    claim_ledger: dict[str, Any]
    quality: dict[str, Any]
    creative_director: dict[str, Any]
    text_visual_allocation: dict[str, Any]
    provider_result: dict[str, Any]
    published: bool = False
    published_at: str | None = None
    business_context: dict[str, Any] | None = None
    anchored_offering: dict[str, Any] | None = None
    creative_decision_packet: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "engine": self.engine,
            "brief": self.brief,
            "copy": self.copy,
            "visual": self.visual,
            "carousel": self.carousel,
            "claim_ledger": self.claim_ledger,
            "quality": self.quality,
            "creative_director": self.creative_director,
            "text_visual_allocation": self.text_visual_allocation,
            "provider_result": self.provider_result,
            "published": self.published,
            "published_at": self.published_at,
            "business_context": self.business_context,
            "anchored_offering": self.anchored_offering,
            "creative_decision_packet": self.creative_decision_packet,
        }


class SocialIntelligenceOrchestrator:
    """The public entry point."""

    def __init__(
        self,
        *,
        provider: visual_provider.VisualProvider | None = None,
        quality_threshold: float = 78.0,
        data_dir: str | None = None,
    ) -> None:
        self.provider = provider or visual_provider.default_provider()
        self.quality_threshold = quality_threshold
        self.data_dir = data_dir

    # --- One post -----------------------------------------------------------

    def create_post(
        self,
        *,
        rotation_index: int = 0,
        platform: str = "instagram_feed",
        audience_hint: str | None = None,
        seasonal_context: str | None = None,
        preferred_engine: str | None = None,
        preferred_pillar: str | None = None,
        verified_facts: list[str] | None = None,
        record_memory: bool = True,
        product_id_override: str = "",
        approved_strategy: dict[str, Any] | None = None,
        revision_feedback: list[str] | None = None,
        remediation_context: dict[str, Any] | None = None,
    ) -> PostPackage:
        # 0. Recent state → recency-aware decisions
        recent = memory_intelligence.recent(self.data_dir, limit=20)
        living_state: dict[str, Any] | None = None
        try:
            from . import living_intelligence
            living_data_dir = self.data_dir or memory_intelligence._default_data_dir()
            living_state = living_intelligence.load(living_data_dir)
            campaign_meeting = living_intelligence.campaign_runtime_decision(
                living_state.get("campaign_state", {}),
                audience_signals=list(recent.get("audience_signals", [])),
                open_threads=list(recent.get("continuity_threads", [])),
                performance_lessons=list(recent.get("performance_lessons", [])),
                product_pressure=bool(recent.get("commercial_pressure", [])),
            )
            recent = living_intelligence.campaign_decision_input(recent, campaign_meeting)
        except Exception:
            recent["campaign_state"] = {}
            living_state = None

        # 0b. Optional BI Foundation hydration — only when the caller
        # didn't already specify a value and the flag is on.
        remediation = dict(remediation_context or {})
        excluded_product_ids = {str(value) for value in remediation.get("excluded_product_ids", []) if str(value)}
        excluded_concepts = list(dict.fromkeys([
            *(str(value) for value in remediation.get("excluded_concepts", []) if str(value)),
            *(str(value) for value in recent.get("attempt_only_exclusions", []) if str(value)),
        ]))
        bi_offering = _bi_get_offering(product_id_override) if product_id_override else _bi_pick_eligible_offering(rotation_index, excluded_product_ids)
        bi_ctx = _load_bi_creative_context(
            str((bi_offering or {}).get("offering_id") or (bi_offering or {}).get("sku") or "")
        )
        if product_id_override:
            forced_offering = _bi_get_offering(product_id_override)
            if forced_offering:
                bi_offering = forced_offering
                if not preferred_pillar:
                    preferred_pillar = _category_to_pillar(forced_offering.get("category", ""))
        if bi_offering:
            recent["product_context"] = list(bi_offering.get("verified_facts") or []) + [str(bi_offering.get("name") or "")]
        lean_context = lean_intelligence.compile_product_social_intelligence(bi_offering)
        relationship_context = lean_context.get("relationships") or {}
        if bi_ctx:
            if not preferred_pillar:
                preferred_pillar = relationship_context.get("pillar_id") or _bi_preferred_pillar(bi_ctx)
            if not audience_hint:
                audience_hint = relationship_context.get("audience_id") or _bi_audience_hint(bi_ctx)
            if not verified_facts:
                # Prefer facts from the specifically-anchored product when we have one
                if bi_offering and bi_offering.get("verified_facts"):
                    verified_facts = list(bi_offering.get("verified_facts", []))
                else:
                    verified_facts = _bi_verified_facts(bi_ctx)

        # 1. Cheap global opportunity competition. Only its winning record is
        # allowed to reach strategy, copy, evidence, and visual generation.
        require_product_free = bool(remediation.get("require_product_free"))
        selected_replacement = remediation.get("replacement_candidate") if isinstance(remediation.get("replacement_candidate"), dict) else None
        competitive_pool: list[dict[str, Any]] = []
        if selected_replacement:
            competitive_pool = list(remediation.get("opportunity_shortlist") or [])
            selected_opportunity = selected_replacement
        elif require_product_free:
            product_free_candidates = opportunity_engine.generate(
                engine="B",
                recent_pillars=recent.get("pillars", []),
                recent_genres=recent.get("genres", []),
                recent_topics=recent.get("topics", []),
                recent_microtopics=recent.get("microtopics", []),
                audience_hint=audience_hint,
                seasonal_context=seasonal_context,
                preferred_pillar=preferred_pillar,
                excluded_concepts=excluded_concepts,
                limit=8,
            )
            selected_candidate, quality_band = _quality_gated_product_free_opportunity(product_free_candidates)
            selected_opportunity = {
                **recovery.compact_candidate(selected_candidate, 1),
                "candidate_id": "B:product_free_random_band",
                "engine": "B",
                "selection_method": "quality_gated_random_band",
                "eligible_band_size": len(quality_band),
            }
            competitive_pool = [
                {**recovery.compact_candidate(candidate, rank), "candidate_id": f"B:product_free:{rank}", "engine": "B"}
                for rank, candidate in enumerate(quality_band, start=1)
            ]
        elif preferred_engine:
            selected_opportunity = None
        else:
            competitive_pool = engines.build_competitive_pool(
                recent=recent,
                audience_hint=audience_hint,
                seasonal_context=seasonal_context,
                preferred_pillar=preferred_pillar,
                excluded_concepts=excluded_concepts,
                rotation_index=rotation_index,
            )
            if not competitive_pool:
                raise RuntimeError("no viable opportunities generated")
            selected_opportunity = competitive_pool[0]
        engine_name = str((selected_opportunity or {}).get("engine") or preferred_engine or _pick_engine(rotation_index)).upper()
        engine = engines.get_engine(engine_name)

        # 2. Strategic brief
        brief_exclusions = [] if selected_opportunity else excluded_concepts
        brief = _build_engine_brief(
            engine,
            engine_name=engine_name,
            preferred_engine=preferred_engine,
            recent=recent,
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=preferred_pillar,
            excluded_concepts=brief_exclusions,
            rotation_index=rotation_index,
            selected_opportunity_id=str((selected_opportunity or {}).get("opportunity_id") or ""),
        )
        _apply_verified_fact_opportunity(brief, remediation)
        verified_fact_opportunity = remediation.get("verified_fact_opportunity")
        if isinstance(verified_fact_opportunity, dict):
            selected_fact = str(verified_fact_opportunity.get("verified_fact") or "").strip()
            if selected_fact:
                # A factual recovery may state the selected owned fact, but it
                # cannot infer performance or operational consequences from it.
                verified_facts = [selected_fact]
        if competitive_pool:
            brief.opportunity_shortlist = competitive_pool
            brief.rationale.append(f"global_opportunity_competition:selected={selected_opportunity.get('candidate_id', '')}")
        audience_value_only = engine_name == "B" and (
            require_product_free or (
                bool(brief.audience_value)
                and not brief.audience_value.get("abstain")
                and not brief.audience_value.get("product_needed")
            )
        )
        anchored_offering_metadata = bi_offering
        product_narrative: dict[str, Any] = {}
        if engine_name == "B" and brief.audience_value and brief.audience_value.get("product_needed"):
            try:
                product_narrative = living_intelligence.product_narrative_decision(
                    recent.get("campaign_state", {}), brief.audience_value,
                    verified_facts=list((bi_offering or {}).get("verified_facts") or recent.get("product_context", [])),
                    product_name=str((bi_offering or {}).get("name") or ""),
                )
                brief.audience_value["product_narrative"] = product_narrative
            except Exception:
                product_narrative = {}
        if audience_value_only:
            # The BI context may inform upstream audience selection, but cannot
            # reintroduce a product into an explicitly product-free decision.
            bi_offering = None
            verified_facts = []
        # A Council-approved strategy is the parent object for both production
        # branches. The engine may supply structure, never a replacement angle.
        if approved_strategy:
            locked = strategy_lock.lock(approved_strategy, context=approved_strategy)
            brief.audience_segment = locked["audience"]
            brief.angle = locked["angle"]
            brief.topic_path["topic"] = locked["topic"]
            brief.reader_job = locked["reader_job"]
        elif audience_value_only:
            locked = _audience_value_strategy_lock(brief)
        else:
            locked = _runtime_strategy_lock(brief, lean_context, bi_offering, self.data_dir)
        if isinstance(verified_fact_opportunity, dict) and selected_fact:
            locked = {
                **locked,
                "topic": str(verified_fact_opportunity.get("product_name") or locked.get("topic") or "Product details"),
                "angle": brief.angle,
                "customer_moment": brief.curiosity,
                "proof": [selected_fact],
                "claim_limits": "State only the selected verified fact; do not infer runtime, compatibility, safety, performance, or operational outcomes.",
            }

        recovery_context = any(
            remediation.get(key)
            for key in (
                "replacement_candidate", "original_candidate_id", "recovery_mode", "candidate_attempt_id",
                "excluded_concepts", "exclude_engine_a_decision_thesis",
            )
        )
        if recovery_context and not selected_opportunity:
            candidate_text = " ".join(
                str(value or "")
                for value in (
                    brief.question,
                    brief.angle,
                    brief.curiosity,
                    locked.get("customer_moment"),
                    locked.get("human_need"),
                )
            )
            if opportunity_engine.text_is_excluded(candidate_text, excluded_concepts):
                raise RuntimeError("no viable opportunities generated")

        if engine_name == "A" and bi_offering:
            product_narrative = living_intelligence.product_expression_for_engine_a(
                campaign=recent.get("campaign_state", {}),
                reader_job=brief.reader_job,
                question=brief.question or brief.hook,
                human_reality=str(locked.get("customer_moment") or ""),
                practical_value=str(brief.information_gap or brief.angle),
                takeaway=str(brief.angle),
                verified_facts=list(bi_offering.get("verified_facts") or []),
                product_name=str(bi_offering.get("name") or ""),
            )

        creative_packet = creative_cognition.decide(
            strategy=locked, platform=platform, recent=recent, data_dir=self.data_dir
        )
        concept_candidates = creative_intelligence.concept_competition(
            locked,
            creative_packet.get("feed_intelligence") if isinstance(creative_packet.get("feed_intelligence"), dict) else {},
        )
        selected_concept = creative_intelligence.select_concept(
            concept_candidates,
            feed_intelligence=creative_packet.get("feed_intelligence") if isinstance(creative_packet.get("feed_intelligence"), dict) else {},
        )
        creative_packet["concept_competition"] = {
            "candidates": concept_candidates,
            "winner": selected_concept,
        }
        if brief.audience_value and not brief.audience_value.get("abstain"):
            creative_packet["audience_value_platform_expressions"] = {
                platform_name: audience_value.platform_expression(brief.audience_value, platform_name)
                for platform_name in ("facebook", "instagram_static", "instagram_reel", "linkedin")
            }

        # 3. Copy assembly — real Gemini copy when available, deterministic
        # template assembly as the network-free fallback (§15 Copy Architect).
        beats = copy_intelligence.structure_for(brief.genre)
        revision_objectives = _revision_objectives(revision_feedback, locked)
        strict_verified_fact_recovery = isinstance(verified_fact_opportunity, dict) and bool(selected_fact)
        if strict_verified_fact_recovery:
            beat_content = _assemble_verified_fact_recovery_copy(
                brief=brief,
                structure_beats=beats,
                verified_fact=selected_fact,
            )
            llm_beats = None
        else:
            llm_beats = _llm_copy_beats(
                brief, beats, bi_ctx, bi_offering,
                creative_packet["SELECTED_ANSWER"]["copy_logic"],
                revision_objectives,
            )
            beat_content = llm_beats or _assemble_copy(brief=brief, structure_beats=beats)
        decision_insight: dict[str, Any] = {}
        if engine_name == "A" and not remediation.get("exclude_engine_a_decision_thesis"):
            decision_insight = _engine_a_decision_insight(
                product_narrative,
                list((bi_offering or {}).get("verified_facts") or verified_facts or []),
            )
            beat_content = _render_engine_a_decision_beats(
                beat_content,
                product_narrative,
                decision_insight,
            )
        removed_numeric_claims: list[str] = []
        claim_verified_facts = list((bi_offering or {}).get("verified_facts") or []) or _bi_verified_facts(bi_ctx)
        for beat, value in list(beat_content.items()):
            sanitized, removed = claim_intelligence.remove_unsupported_numeric_claims(value, claim_verified_facts)
            beat_content[beat] = sanitized
            removed_numeric_claims.extend(removed)
        copy_generation_method = "llm" if llm_beats else "template_fallback"
        copy_fallback_reason = None if llm_beats else model_router.last_error()
        hook_text = beat_content.get("hook") or beat_content.get("question") or beat_content.get("problem") or ""
        selected_hook = creative_packet.get("selected_copy_concept", {}).get("opening", "")
        if selected_hook and not llm_beats and not strict_verified_fact_recovery:
            hook_text = selected_hook
            beat_content["hook"] = selected_hook
        body_text = " ".join(v for k, v in beat_content.items() if k != "hook" and v)
        takeaway = beat_content.get("takeaway") or beat_content.get("lesson") or beat_content.get("implication") or brief.angle
        anchor = copy_intelligence.extract_memory_anchor(body_text, takeaway=takeaway)
        brief.hook = hook_text
        brief.body_beats = beat_content
        brief.takeaway = takeaway
        brief.memory_anchor = anchor
        selected_cta = "" if audience_value_only else str(product_narrative.get("cta_class") or (locked or {}).get("CTA_strategy") or _DEFAULT_CTA_BY_JOB.get(brief.reader_job, "Learn more"))

        # 4. Visual direction
        necessity = visual_intelligence.visual_necessity_score(
            genre=brief.genre,
            reader_job_config=brief.reader_job_config,
            platform=platform,
            body_word_count=len(body_text.split()),
        )
        must_render = visual_intelligence.visual_required(necessity=necessity)

        semantic_role = visual_intelligence.visual_semantic_role(
            genre_id=brief.genre.get("id", ""),
            reader_job=brief.reader_job,
        )
        v_msg = visual_intelligence.visual_message(
            angle=brief.angle,
            memory_anchor=anchor,
            semantic_role=semantic_role,
        )
        v_msg = (
            f"{v_msg}. Creative thesis: {selected_concept.get('creative_thesis', '')}. "
            f"Composition principle: {creative_packet['SELECTED_ANSWER']['visual_logic']}"
        )
        v_format = visual_intelligence.route_visual_format(
            genre=brief.genre,
            platform=platform,
            body_word_count=len(body_text.split()),
            has_product_asset=bool(bi_offering and bi_offering.get("images")),
        )
        concepts = visual_intelligence.generate_concepts(
            angle=brief.angle,
            memory_anchor=anchor,
            semantic_role=semantic_role,
            genre_id=brief.genre.get("id", ""),
            concept_stems=_llm_concept_stems(brief, anchor),
        )
        top_concept = concepts[0]
        art = visual_intelligence.build_art_direction(
            visual_purpose=semantic_role,
            visual_msg=v_msg,
            visual_format=v_format,
            concept=top_concept,
            primary_subject=(bi_offering.get("name") if bi_offering else brief.topic_path.get("topic", brief.angle)),
            platform=platform,
        )
        composition = creative_packet["layout_grammar"]
        art.composition = "; ".join((composition["alignment"], composition["reading_flow"], composition["spacing_intent"]))
        art.focal_point = composition["primary_focal_point"]
        art.secondary_subjects = [composition["secondary_focal_point"]]
        art.must_include.extend(creative_packet["information_priority"]["MUST_SHOW"])
        positive_prompt, negative_prompt = visual_intelligence.compile_image_prompt(
            art,
            extra_negatives=_bi_visual_prohibitions(bi_ctx),
        )
        v_humanness = visual_intelligence.visual_prompt_humanness(positive_prompt)

        # 5. Text/visual allocation
        alloc = visual_intelligence.allocate_text_visual(
            beats=beats,
            beat_content=beat_content,
            genre=brief.genre,
        )

        # 6. Carousel
        specs = libraries.platform_specs().get(platform, {})
        max_lines = int(specs.get("max_text_lines_per_card", 5))
        max_slides = int(specs.get("carousel_max_slides", 10))
        carousel_pkg: dict[str, Any] | None = None
        if v_format == "carousel" or visual_intelligence.needs_carousel(
            on_image_lines=alloc.on_image, max_lines=max_lines
        ):
            car = carousel_director.build(
                info_structure=brief.genre.get("info_structure", "hook_answer_explanation_example_takeaway"),
                beat_content=beat_content,
                visual_type=v_format if v_format == "carousel" else "carousel",
                visual_direction=v_msg,
            )
            valid, problems = carousel_director.is_valid_carousel(car, max_slides=max_slides)
            carousel_pkg = car.as_dict()
            carousel_pkg["valid"] = valid
            carousel_pkg["problems"] = problems

        # 7. Claim ledger
        source_concepts = {
            str(decision_insight.get("relationship") or ""): "decision_relationship",
            str(decision_insight.get("decision_consequence") or ""): "decision_consequence",
            hook_text: "hook_payoff",
            takeaway: "takeaway",
            anchor: "memory_anchor",
        }
        ledger = claim_intelligence.build_ledger(
            hook_text + " " + body_text,
            verified_facts=verified_facts or [],
            forbidden_claims=_bi_forbidden_claims(bi_ctx),
            source_concepts=source_concepts,
        )
        evidence_readiness = claim_governance.assess(
            ledger,
            hook=hook_text,
            decision_insight=decision_insight,
            takeaway=takeaway,
        )

        # 8. Quality gate
        response_contract = quality_intelligence.expected_response_contract(
            reader_job=brief.reader_job,
            cta_class=selected_cta,
            content_role=str(product_narrative.get("role") or ""),
        )
        q = quality_intelligence.score(
            hook=hook_text,
            body=body_text,
            takeaway=takeaway,
            memory_anchor=anchor,
            visual_concept_description=top_concept.description,
            platform=platform,
            genre=brief.genre,
            reader_job_config=brief.reader_job_config,
            ledger=ledger,
            visual_prompt_humanness=v_humanness,
            caption_visual_relationship=alloc.relationship,
            engine=engine_name,
            brand_voice=_bi_brand_voice(bi_ctx),
            response_contract=response_contract,
        )
        cd = quality_intelligence.creative_director_test(
            strategy_reason=f"engine={engine_name} pillar={brief.pillar.get('id')} genre={brief.genre.get('id')}",
            audience_reason=f"segment={brief.audience_segment} reader_job={brief.reader_job}",
            value_delivered=takeaway or anchor,
            novelty_angle=brief.angle,
            memory_anchor=anchor,
            copy_earns_attention=copy_intelligence.humanness_score(hook_text) >= 0.6,
            visual_communicates=must_render and v_humanness >= 0.7,
            copy_visual_alignment=alloc.relationship != "",
            brand_feels_like_us=True,
            material_claims_accurate=not ledger.unverified_high_risk,
            worth_reader_time=bool(anchor),
        )
        pre_render_gate = creative_intelligence.pre_render_gate(
            concept=selected_concept,
            hook=hook_text,
            body=body_text,
            visual_thesis=v_msg,
            claim_safe=not ledger.unverified_high_risk,
        )
        creative_packet["pre_render_gate"] = pre_render_gate

        # 9. Provider (real Gemini image generation, or template fallback)
        post_id = uuid.uuid4().hex[:12]
        art_dict = art.as_dict()
        art_dict["post_id"] = post_id
        art_dict["cta"] = selected_cta
        art_dict["creative_concept"] = selected_concept
        art_dict["pre_render_gate"] = pre_render_gate
        art_dict["layout_grammar"] = creative_packet["layout_grammar"]
        art_dict["platform_interpretations"] = creative_packet["platform_interpretations"]
        art_dict["information_priority"] = creative_packet["information_priority"]
        art_dict["benefit_translation"] = creative_packet["benefit_translation"]
        if bi_offering:
            art_dict["product_name"] = bi_offering.get("name", "")
            offering_images = bi_offering.get("images") or []
            if offering_images:
                art_dict["product_image_url"] = offering_images[0]
        provider_result = self.provider.generate(
            art_direction=art_dict,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            platform=platform,
        )

        package = PostPackage(
            post_id=post_id,
            engine=engine_name,
            brief=brief.as_dict(),
            copy={
                "hook": hook_text,
                "body_beats": beat_content,
                "body_text": body_text,
                "takeaway": takeaway,
                "memory_anchor": anchor,
                "tone": brief.tone,
                "cta": selected_cta,
                "generation_method": copy_generation_method,
                "fallback_reason": copy_fallback_reason,
                "revision_feedback": list(revision_feedback or []),
                "revision_objectives": revision_objectives,
                "removed_unsupported_numeric_claims": removed_numeric_claims,
                "strategy_lock": locked,
                "product_narrative": product_narrative,
                "decision_insight": decision_insight,
                "response_contract": response_contract,
                "evidence_readiness": evidence_readiness,
                "remediation_context": remediation,
            },
            visual={
                "semantic_role": semantic_role,
                "visual_message": v_msg,
                "visual_format": v_format,
                "layout_logic": creative_packet["SELECTED_ANSWER"]["layout_logic"],
                "visual_logic": creative_packet["SELECTED_ANSWER"]["visual_logic"],
                "copy_grammar": creative_packet["SELECTED_ANSWER"]["copy_logic"],
                "layout_grammar": creative_packet["layout_grammar"],
                "information_priority": creative_packet["information_priority"],
                "benefit_translation": creative_packet["benefit_translation"],
                "creative_concepts": creative_packet["creative_concepts"],
                "platform_interpretations": creative_packet["platform_interpretations"],
                "necessity_score": necessity,
                "required": must_render,
                "art_direction": art.as_dict(),
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "prompt_humanness": v_humanness,
                "signature": visual_intelligence.visual_signature(
                    visual_format=v_format,
                    layout_family=creative_packet["SELECTED_ANSWER"]["reference_id"],
                    focal_position="center",
                    color_family="brand_primary",
                    headline_position="top",
                ),
                "concepts": [{"label": c.label, "description": c.description, "total": c.total} for c in concepts],
                "strategy_lock": locked,
            },
            carousel=carousel_pkg,
            claim_ledger=ledger.as_dict(),
            quality=q.as_dict(),
            creative_director=cd.__dict__,
            text_visual_allocation={
                "on_image": alloc.on_image,
                "in_caption": alloc.in_caption,
                "relationship": alloc.relationship,
            },
            provider_result=provider_result.as_dict(),
            business_context=bi_ctx,
            anchored_offering=anchored_offering_metadata,
            creative_decision_packet=creative_packet,
        )
        if remediation:
            package.copy["remediation_context"] = remediation
        if locked:
            package.creative_director["creative_decision_review"] = {
                "verdict": "PASS" if creative_packet["ACTION"] == "create" else "DO_NOT_PUBLISH",
                "reason": "creative decision has unresolved material objections" if creative_packet["ACTION"] != "create" else "creative decision packet selected a supported expression",
                "decision_packet_action": creative_packet["ACTION"],
            }
            package.creative_director["human_connection_review"] = strategy_lock.human_connection_critique(
                strategy=locked,
                copy=package.copy,
                visual=package.visual,
            )
            package.creative_director["independent_human_connection_review"] = human_connection_review.review(
                strategy=locked, copy=package.copy, visual=package.visual
            )
            package.creative_director["strategy_integrity_review"] = strategy_lock.integrity(
                locked, package.copy, package.visual
            )
            package.creative_director["copy_critic_review"] = quality_intelligence.copy_critic(
                copy=package.copy, strategy=locked, platform=platform
            )
            package.creative_director["visual_critic_review"] = quality_intelligence.visual_critic(
                visual=package.visual, provider_result=package.provider_result, platform=platform
            )

        # 10. Memory
        if record_memory:
            memory_intelligence.append_content_record(
                {
                    "post_id": post_id,
                    "engine": engine_name,
                    "pillar_id": brief.pillar.get("id"),
                    "genre_id": brief.genre.get("id"),
                    "topic": brief.topic_path.get("topic"),
                    "microtopic": brief.topic_path.get("microtopic"),
                    "hook": hook_text,
                    "memory_anchor": anchor,
                    "tone": brief.tone,
                    "cta_type": copy_intelligence.choose_cta_type(
                        genre=brief.genre,
                        reader_job_config=brief.reader_job_config,
                        recent_ctas=recent.get("ctas", []),
                    ),
                    "quality_overall": q.overall,
                    "creative_decision": creative_packet["MEMORY_UPDATE"],
                    "copy_grammar": creative_packet["SELECTED_ANSWER"]["copy_logic"],
                    "benefit_order": creative_packet["information_priority"]["MUST_SHOW"],
                    "emotional_framing": creative_packet["benefit_translation"]["HUMAN_MEANING"],
                    "customer_moment": locked.get("customer_moment", ""),
                    "reader_job": locked.get("reader_job", ""),
                    "audience_value_form": brief.audience_value.get("content_form", ""),
                    "human_reality": brief.audience_value.get("human_reality", ""),
                    "reader_question": brief.audience_value.get("reader_question", ""),
                    "reader_takeaway": brief.audience_value.get("reader_takeaway", ""),
                    "why_it_matters": brief.audience_value.get("why_it_matters", ""),
                    "desired_memory_anchor": brief.audience_value.get("desired_memory_anchor", ""),
                    "practical_value": brief.audience_value.get("practical_value", ""),
                    "reflection_value": brief.audience_value.get("reflection_value", ""),
                    "share_save_value": brief.audience_value.get("share_save_value", ""),
                    "audience_value_product_needed": brief.audience_value.get("product_needed", False),
                    "audience_value_cta_class": brief.audience_value.get("cta_class", ""),
                    "question_answered": brief.audience_value.get("reader_question", ""),
                    "question_created": brief.audience_value.get("unresolved_question", ""),
                    "unresolved_thread": brief.audience_value.get("unresolved_question", ""),
                    "continuity_thread": brief.audience_value.get("continuity_thread", {}),
                    "thread_action": brief.audience_value.get("thread_action", "NONE"),
                    "assumption_challenged": brief.audience_value.get("reflection_value", ""),
                    "campaign_effect": brief.audience_value.get("campaign_effect", "NO_CAMPAIGN"),
                    "campaign_state": recent.get("campaign_state", {}),
                    "audience_state_change": (brief.audience_value.get("idea") or {}).get("audience_state", ""),
                    "product_relevance_change": brief.audience_value.get("product_relevance", "NOT_RELEVANT"),
                    "product_narrative": brief.audience_value.get("product_narrative", {}),
                    "performance_lesson": (brief.audience_value.get("idea") or {}).get("why_now", ""),
                    "performance_lesson_applied": brief.audience_value.get("performance_lesson_applied", ""),
                    "commercial_pressure": "product_present" if bool(bi_offering) else "",
                    "hook_family": creative_packet.get("hook_selection", {}).get("family", ""),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                data_dir=self.data_dir,
            )
            if living_state is not None and brief.audience_value:
                try:
                    living_state["campaign_state"] = living_intelligence.apply_campaign_post(
                        recent.get("campaign_state", {}), brief.audience_value
                    )
                    living_intelligence.save(self.data_dir or memory_intelligence._default_data_dir(), living_state)
                except Exception:
                    pass
            memory_intelligence.append_visual_record(
                {
                    "post_id": post_id,
                    "visual_format": v_format,
                    "visual_signature": package.visual["signature"],
                    "creative_decision": creative_packet["MEMORY_UPDATE"],
                    "layout_grammar": creative_packet["layout_grammar"],
                    "product_role": creative_packet["layout_grammar"]["product_role"],
                    "human_presence": creative_packet["layout_grammar"]["human_role"],
                    "text_density": creative_packet["layout_grammar"]["text_density"],
                    "product_placement": creative_packet["layout_grammar"]["product_placement"],
                    "headline_placement": creative_packet["layout_grammar"]["headline_position"],
                    "art_direction_family": creative_packet["SELECTED_ANSWER"]["reference_id"],
                    "visual_concept": creative_packet["SELECTED_ANSWER"]["creative_concept"],
                    "art_direction": art.as_dict(),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                data_dir=self.data_dir,
            )
            memory_intelligence.append_post_history_record(
                {
                    "post_id": post_id,
                    "engine": engine_name,
                    "platform": platform,
                    "funnel_stage": "CONVERSION" if engine_name == "A" else "EDUCATION",
                    "pillar_id": brief.pillar.get("id"),
                    "genre_id": brief.genre.get("id"),
                    "topic": brief.topic_path.get("topic"),
                    "microtopic": brief.topic_path.get("microtopic"),
                    "hook": hook_text,
                    "hook_type": brief.genre.get("id"),
                    "memory_anchor": anchor,
                    "tone": brief.tone,
                    "quality": q.as_dict(),
                    "claim_ledger": ledger.as_dict(),
                    "anchored_offering": bi_offering,
                    "engagement_metrics": {},
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                data_dir=self.data_dir,
            )

        return package

    # --- Batch --------------------------------------------------------------

    def create_batch(self, *, count: int, platform: str = "instagram_feed", **kw: Any) -> list[PostPackage]:
        rotation_index = int(kw.pop("rotation_index", 0) or 0)
        out: list[PostPackage] = []
        for i in range(count):
            current_rotation = rotation_index + i
            batch_kw = dict(kw)
            if count > 1:
                batch_kw.setdefault("preferred_engine", _pick_engine(current_rotation))
            out.append(self.create_post(rotation_index=current_rotation, platform=platform, **batch_kw))
        return out
