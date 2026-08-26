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

import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import (
    carousel_director,
    claim_governance,
    claim_intelligence,
    copy_intelligence,
    creative_cognition,
    creative_contracts,
    creative_intelligence,
    engines,
    libraries,
    lean_intelligence,
    living_intelligence,
    memory_intelligence,
    model_router,
    quality_intelligence,
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


def _load_bi_creative_context(
    offering_id: str = "",
    *,
    segment_id: str = "",
    moment_id: str = "",
    job: str = "",
) -> dict[str, Any] | None:
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
        return bi_api.compile_creative_context(
            offering_id=offering_id,
            segment_id=segment_id,
            moment_id=moment_id,
            job=job,
        )
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


def _bi_forbidden_claims(ctx: dict[str, Any] | None) -> list[str]:
    if not ctx:
        return []
    return list(ctx.get("forbidden_claims", []))


def _bi_visual_prohibitions(ctx: dict[str, Any] | None) -> list[str]:
    if not ctx:
        return []
    return list((ctx.get("brand_prohibitions") or {}).get("visual", []))


def _constitution_job(reader_job: str) -> str:
    return {
        "TEACH_ME": "teach",
        "HELP_ME": "help_decide",
        "EXPLAIN_THIS": "translate_a_technical_concept",
        "SHOW_ME": "show_a_capability",
        "PREPARE_ME": "help_prepare",
        "HELP_ME_CHOOSE": "help_decide",
        "GIVE_ME_A_REFERENCE": "build_trust",
        "START_A_CONVERSATION": "start_a_conversation",
    }.get(str(reader_job or "").upper(), "")


def _refresh_bi_context_for_strategy(
    *, offering: dict[str, Any] | None, strategy: dict[str, Any], fallback: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not _bi_enabled():
        return fallback
    try:
        from business_intelligence import api as bi_api
        moment_id = bi_api.resolve_human_connection_moment(
            str(strategy.get("customer_moment", "")),
            str(strategy.get("human_need", "")),
            str(strategy.get("angle", "")),
        )
    except Exception:
        return fallback
    return _load_bi_creative_context(
        str((offering or {}).get("offering_id") or (offering or {}).get("sku") or ""),
        segment_id=str(strategy.get("audience", "")),
        moment_id=moment_id,
        job=_constitution_job(str(strategy.get("reader_job", ""))),
    ) or fallback


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


def _bi_brand_voice(ctx: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ctx:
        return None
    return ctx.get("voice") or None


def _recent_product_ids(data_dir: str | None, *, limit: int = 12) -> set[str]:
    if not data_dir:
        return set()
    try:
        with open(memory_intelligence.post_history_path(data_dir), "r", encoding="utf-8") as handle:
            posts = json.load(handle).get("posts", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()
    recent: list[str] = []
    for post in reversed(posts):
        if not isinstance(post, dict) or str(post.get("status", "")).lower().startswith("skipped"):
            continue
        product_id = str(post.get("product_id") or "").strip().lower()
        if product_id and product_id not in recent:
            recent.append(product_id)
        if len(recent) >= limit:
            break
    return set(recent)


def _choose_unused_offering(offerings: list[dict[str, Any]], recent_ids: set[str]) -> dict[str, Any] | None:
    unused = [
        offering for offering in offerings
        if str(offering.get("offering_id") or offering.get("sku") or "").strip().lower() not in recent_ids
    ]
    return secrets.choice(unused or offerings) if offerings else None


def _bi_pick_offering(rotation_index: int, data_dir: str | None = None) -> dict[str, Any] | None:
    """Choose randomly from eligible offerings not used in recent published posts."""
    if not _bi_enabled():
        return None
    try:
        from business_intelligence import api as bi_api
    except ImportError:
        return None
    try:
        profile = bi_api.get_business_profile()
        offerings = profile.get("offerings", []) or []
        if data_dir:
            from social.product_eligibility import filter_evidence_eligible_products

            offerings, _ = filter_evidence_eligible_products(offerings, data_dir)
        if not offerings:
            return None
        recent_ids = _recent_product_ids(data_dir)
        return _choose_unused_offering(offerings, recent_ids)
    except Exception:
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
    benefit_action = benefit
    for prefix, replacement in (("keeps ", "keep "), ("supports ", "support "), ("helps ", "help ")):
        if benefit_action.lower().startswith(prefix):
            benefit_action = replacement + benefit_action[len(prefix):]
            break
    offering_name = str((offering or {}).get("name") or "this product")
    candidate = {
        "audience": brief.audience_segment,
        "customer_moment": moment,
        "human_need": need,
        "human_value": human_value,
        "topic": brief.topic_path.get("topic", ""),
        "angle": brief.angle,
        "hook_promise": f"How does {offering_name} help {benefit_action}?",
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
        candidate["angle"] = f"how does {offering_name} help {benefit_action}"
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
            "Ground the angle/hook/body in this product, not a generic category topic. "
            "Use this commercial progression: lived human moment, current belief, desired belief, "
            "dominant proposition, product fit, mechanism, verified proof, functional transformation, "
            "emotional transformation, ownership or future pacing, honest objection handling, then one CTA. "
            "Do not lead with the product name or a specification list."
        )
    else:
        prompt_parts.append(
            "This is non-product editorial content. Use this organic progression: the person's world, "
            "human reality, tension, curiosity, useful insight, Infenergy perspective, a concrete story or "
            "example, specific participation, and one memorable closing idea. Do not introduce a product, "
            "shopping language, specifications, or a sales CTA."
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
    human_connection = (bi_ctx or {}).get("human_connection") or {}
    moment_world = human_connection.get("moment_world") or {}
    if moment_world:
        creation_logic = human_connection.get("preemptive_creation_logic") or {}
        before_generation = creation_logic.get("before_generation") or {}
        prompt_parts.append(
            "Human decision context: "
            f"person={moment_world.get('person', '')}; "
            f"decision_state={moment_world.get('decision_state', '')}; "
            f"responsibility={moment_world.get('responsibility', '')}; "
            f"capability_goal={moment_world.get('capability_goal', '')}; "
            f"product_role={moment_world.get('product_role', '')}. "
            f"Human Brain movement={(before_generation.get('brain_movement', {}) or {}).get('question', '')}; "
            f"Human Heart result={(before_generation.get('heart_after', {}) or {}).get('question', '')}. "
            "Begin with this lived moment, define the useful movement in thought, and let the earned emotional result follow from it; do not turn it into fear or a forced product pitch."
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


def _editorial_framework(strategy: dict[str, Any], offering: dict[str, Any] | None) -> dict[str, Any]:
    """Expose the locked reasoning sequence that downstream platform editors must preserve."""
    if offering:
        proof = [str(item).strip() for item in (strategy.get("proof") or []) if str(item).strip()]
        return {
            "mode": "commercial",
            "structure": [
                "human_moment", "current_belief", "desired_belief", "dominant_proposition",
                "product_fit", "mechanism", "verified_proof", "functional_transformation",
                "emotional_transformation", "ownership_future_pacing", "objection", "cta",
            ],
            "human_moment": str(strategy.get("customer_moment") or ""),
            "current_belief": str(strategy.get("human_need") or ""),
            "desired_belief": str(strategy.get("angle") or ""),
            "dominant_proposition": str(strategy.get("benefit") or ""),
            "product_fit": str(strategy.get("positioning") or ""),
            "mechanism": str(strategy.get("important_capability") or ""),
            "verified_proof": proof,
            "functional_transformation": str(strategy.get("benefit") or ""),
            "emotional_transformation": str(strategy.get("human_outcome") or ""),
            "ownership_future_pacing": str(strategy.get("human_value") or ""),
            "objection": str(strategy.get("claim_limits") or ""),
            "cta": str(strategy.get("CTA_strategy") or ""),
        }
    return {
        "mode": "organic",
        "structure": [
            "person_world", "human_reality", "tension", "curiosity", "insight",
            "infenergy_perspective", "story", "participation", "memory",
        ],
        "person_world": str(strategy.get("audience") or ""),
        "human_reality": str(strategy.get("customer_moment") or ""),
        "tension": str(strategy.get("human_need") or ""),
        "curiosity": str(strategy.get("hook_promise") or strategy.get("angle") or ""),
        "insight": str(strategy.get("angle") or ""),
        "infenergy_perspective": str(strategy.get("positioning") or ""),
        "story": str(strategy.get("topic") or ""),
        "participation": str(strategy.get("CTA_strategy") or ""),
        "memory": str(strategy.get("desired_memory") or strategy.get("human_outcome") or ""),
    }


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
    if any(item.startswith("human_connection_reader_value_missing:") for item in findings):
        objectives.append(
            "Revise for Reader Value: begin in the locked human moment, give one concrete useful way to think or act, "
            "address the reader rather than leading with the product, and preserve truthful limits."
        )
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
    curiosity = brief.curiosity or brief.information_gap or brief.angle
    misc = brief.misconception or ""
    reality = brief.angle
    q = brief.question or f"What most people miss about {brief.topic_path.get('topic', 'this')}"
    gap = brief.information_gap or brief.curiosity or brief.angle
    gap_text = gap.strip().rstrip(".?!")
    curiosity_text = brief.curiosity.strip().rstrip(".?!")

    templates: dict[str, str] = {
        "hook": q if q.endswith("?") else f"{q}?",
        "answer": f"The published starting point is {gap_text}.",
        "explanation": f"Use {gap_text} to compare the product with the devices and job you need to support.",
        "example": f"Why this matters: {curiosity_text}.",
        "takeaway": "Choose the setup that fits the devices you rely on and the way you actually move through the day.",
        "problem": "Start by checking the assumption against verified product facts." if misc else f"Most people assume {brief.angle}.",
        "why": f"Because {gap}.",
        "what_happens": f"Which leads to {brief.curiosity}.",
        "what_to_do": f"So the practical move is to compare your actual priorities with {gap_text.lower()}.",
        "myth": "A familiar assumption can still be the wrong basis for the decision." if misc else f"Common belief: {brief.angle}.",
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
    creative_request: dict[str, Any] | None = None

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
            "creative_request": self.creative_request,
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
        no_product: bool = False,
    ) -> PostPackage:
        # 0. Recent state → recency-aware decisions
        recent = memory_intelligence.recent(self.data_dir, limit=20)

        # 0b. Optional BI Foundation hydration — only when the caller
        # didn't already specify a value and the flag is on.
        bi_offering = None if no_product else (
            _bi_get_offering(product_id_override) if product_id_override else _bi_pick_offering(rotation_index, self.data_dir)
        )
        bi_ctx = _load_bi_creative_context(
            str((bi_offering or {}).get("offering_id") or (bi_offering or {}).get("sku") or "")
        )
        if product_id_override and not no_product:
            forced_offering = _bi_get_offering(product_id_override)
            if forced_offering:
                bi_offering = forced_offering
                if not preferred_pillar:
                    preferred_pillar = _category_to_pillar(forced_offering.get("category", ""))
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

        # 1. Engine
        engine_name = (preferred_engine or _pick_engine(rotation_index)).upper()
        engine = engines.get_engine(engine_name)

        # 2. Strategic brief
        brief = engine.build(
            recent=recent,
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=preferred_pillar,
            rotation_index=rotation_index,
        )
        # A Council-approved strategy is the parent object for both production
        # branches. The engine may supply structure, never a replacement angle.
        if approved_strategy:
            locked = strategy_lock.lock(approved_strategy, context=approved_strategy)
            brief.audience_segment = locked["audience"]
            brief.angle = locked["angle"]
            brief.topic_path["topic"] = locked["topic"]
            brief.topic_path["subtopic"] = locked["topic"]
            brief.topic_path["microtopic"] = locked["angle"]
            brief.topic_path["angle"] = locked["angle"]
            brief.reader_job = locked["reader_job"]
            brief.information_gap = str(locked.get("important_capability") or locked.get("benefit") or locked["angle"])
            brief.curiosity = str(locked.get("human_need") or locked.get("customer_moment") or locked["angle"])
            brief.question = str(locked.get("hook_promise") or locked["angle"])
            brief.emotional_driver = str(locked.get("human_outcome") or locked.get("human_value") or brief.emotional_driver)
        else:
            locked = _runtime_strategy_lock(brief, lean_context, bi_offering, self.data_dir)

        bi_ctx = _refresh_bi_context_for_strategy(
            offering=bi_offering,
            strategy=locked,
            fallback=bi_ctx,
        )
        human_connection = (bi_ctx or {}).get("human_connection") or {}
        if human_connection:
            locked = dict(locked)
            locked["human_connection"] = human_connection

        brief.audience_segment = locked["audience"]
        brief.angle = locked["angle"]
        brief.topic_path["topic"] = locked["topic"]
        brief.topic_path["subtopic"] = locked["topic"]
        brief.topic_path["microtopic"] = locked["angle"]
        brief.topic_path["angle"] = locked["angle"]
        brief.reader_job = locked["reader_job"]
        brief.information_gap = str(locked.get("important_capability") or locked.get("benefit") or locked["angle"])
        brief.curiosity = str(locked.get("human_need") or locked.get("customer_moment") or locked["angle"])
        brief.question = str(locked.get("hook_promise") or locked["angle"])
        brief.emotional_driver = str(locked.get("human_outcome") or locked.get("human_value") or brief.emotional_driver)

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

        # 3. Copy assembly — real Gemini copy when available, deterministic
        # template assembly as the network-free fallback (§15 Copy Architect).
        beats = copy_intelligence.structure_for(brief.genre)
        revision_objectives = _revision_objectives(revision_feedback, locked)
        llm_beats = _llm_copy_beats(
            brief, beats, bi_ctx, bi_offering,
            creative_packet["SELECTED_ANSWER"]["copy_logic"],
            revision_objectives,
        )
        beat_content = llm_beats or _assemble_copy(brief=brief, structure_beats=beats)
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
        if selected_hook and not llm_beats:
            hook_text = selected_hook
            beat_content["hook"] = selected_hook
        body_text = " ".join(v for k, v in beat_content.items() if k != "hook" and v)
        takeaway = beat_content.get("takeaway") or beat_content.get("lesson") or beat_content.get("implication") or brief.angle
        anchor = copy_intelligence.extract_memory_anchor(body_text, takeaway=takeaway)
        brief.hook = hook_text
        brief.body_beats = beat_content
        brief.takeaway = takeaway
        brief.memory_anchor = anchor
        selected_cta = (locked or {}).get("CTA_strategy") or _DEFAULT_CTA_BY_JOB.get(brief.reader_job, "Learn more")

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
        moment_world = human_connection.get("moment_world") or {}
        if moment_world:
            v_msg += (
                f" Human scene root: {moment_world.get('person', '')} "
                f"in {moment_world.get('decision_state', '')} "
                f"with the question {moment_world.get('human_question', '')}."
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
        v5_directions = visual_intelligence.build_v5_art_directions(
            strategy=locked,
            reader_job=brief.reader_job,
            genre_id=brief.genre.get("id", ""),
            platform=platform,
            offering=bi_offering,
            overlay_text=hook_text,
            recent_scenes=recent.get("v5_scenes", []),
        )
        v5_direction = v5_directions[0] if v5_directions else {}
        if v5_direction:
            positive_prompt = visual_intelligence.compile_v5_scene_prompt(v5_direction)
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
        ledger = claim_intelligence.build_ledger(
            hook_text + " " + body_text,
            verified_facts=verified_facts or [],
            forbidden_claims=_bi_forbidden_claims(bi_ctx),
        )

        # 8. Quality gate
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
        )
        human_truth = quality_intelligence.human_truth_gate(
            hook=hook_text,
            body=body_text,
            takeaway=takeaway,
            strategy=locked,
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
        art_dict["v5_direction_candidates"] = v5_directions
        art_dict["v5_direction"] = v5_direction
        art_dict["v5_scene_prompt"] = positive_prompt if v5_direction else ""
        if bi_offering:
            art_dict["product_name"] = bi_offering.get("name", "")
            offering_images = bi_offering.get("images") or []
            if offering_images:
                art_dict["product_image_url"] = offering_images[0]
        prompt_governance = claim_governance.assess_visual_prompt(
            v5_direction,
            positive_prompt,
            has_product_reference=bool(art_dict.get("product_image_url")),
            verified_facts=list((bi_offering or {}).get("verified_facts") or verified_facts or _bi_verified_facts(bi_ctx)),
            forbidden_claims=_bi_forbidden_claims(bi_ctx),
        ) if v5_direction else {"ready": True, "status": "LEGACY_DIRECTION"}
        v5_fallback_candidates = []
        for candidate in v5_directions[1:]:
            candidate_prompt = visual_intelligence.compile_v5_scene_prompt(candidate)
            candidate_governance = claim_governance.assess_visual_prompt(
                candidate,
                candidate_prompt,
                has_product_reference=bool(art_dict.get("product_image_url")),
                verified_facts=list((bi_offering or {}).get("verified_facts") or verified_facts or _bi_verified_facts(bi_ctx)),
                forbidden_claims=_bi_forbidden_claims(bi_ctx),
            )
            if candidate_governance.get("ready"):
                v5_fallback_candidates.append({
                    "direction": candidate,
                    "prompt": candidate_prompt,
                    "prompt_governance": candidate_governance,
                })
        art_dict["prompt_governance"] = prompt_governance
        art_dict["v5_fallback_candidates"] = v5_fallback_candidates
        art_dict["human_truth_gate"] = human_truth
        art_dict["action"] = str(
            v5_direction.get("action")
            or v5_direction.get("scene")
            or selected_concept.get("what_happens")
            or selected_concept.get("description")
            or top_concept.description
        ).strip()
        visual_communication_plan = visual_intelligence.build_visual_communication_plan(
            strategy=locked,
            art_direction=art_dict,
            final_copy=" ".join((hook_text, body_text, takeaway)),
            platform=platform,
            offering=bi_offering,
            recent=recent,
        )
        art_dict["visual_communication_plan"] = visual_communication_plan
        positive_prompt = (
            f"{positive_prompt}\nCommunication plan: image job: {visual_communication_plan['communication_jobs']['image']}. "
            f"One-second message: {visual_communication_plan['one_second_message']}. "
            f"Visual concept: {', '.join(visual_communication_plan['visual_concept'])}. "
            f"Human behavior: {visual_communication_plan['human_behavior']}. "
            f"Before/current/after: {visual_communication_plan['narrative']['before']} / "
            f"{visual_communication_plan['narrative']['current']} / {visual_communication_plan['narrative']['after']}."
        )[:4000]
        creative_request = creative_contracts.build_creative_request(
            post_id=post_id,
            platform=platform,
            strategy=locked,
            art_direction=art_dict,
            human_truth=human_truth,
            audience_reaction=str(locked.get("desired_audience_reaction") or brief.emotional_driver or anchor),
            format_name=v_format,
        ).as_studio_payload()
        art_dict["creative_request"] = creative_request
        communication_ready = not visual_communication_plan["quality_governance"]["blocking"]
        if pre_render_gate.get("decision") == "CONCEPT_READY" and prompt_governance.get("ready") and human_truth.get("ready") and communication_ready:
            provider_result = self.provider.generate(
                art_direction=art_dict,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                platform=platform,
            )
        else:
            provider_result = visual_provider.VisualResult(
                provider="pre_render_gate",
                kind="none",
                prompt=positive_prompt,
                negative_prompt=negative_prompt,
                provider_meta={
                    "platform": platform,
                    "reason": "pre_render_gate_not_ready",
                    "gate": pre_render_gate,
                    "prompt_governance": prompt_governance,
                    "human_truth_gate": human_truth,
                    "visual_communication_gate": visual_communication_plan["quality_governance"],
                },
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
                "editorial_framework": _editorial_framework(locked, bi_offering),
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
                "v5_direction_candidates": v5_directions,
                "v5_fallback_candidates": v5_fallback_candidates,
                "v5_direction": v5_direction,
                "prompt_governance": prompt_governance,
                "human_truth_gate": human_truth,
                "visual_communication_plan": visual_communication_plan,
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
            anchored_offering=bi_offering,
            creative_decision_packet=creative_packet,
            creative_request=creative_request,
        )
        package.creative_director["human_truth_gate"] = human_truth
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

        if record_memory:
            living_intelligence.record_decision(
                self.data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
                post_id=post_id,
                strategy=locked,
                direction=v5_direction,
                human_truth=human_truth,
                prompt_governance=prompt_governance,
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
                    "hook_family": creative_packet.get("hook_selection", {}).get("family", ""),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                data_dir=self.data_dir,
            )
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
                    "v5_archetype": v5_direction.get("archetype", ""),
                    "v5_scene": v5_direction.get("scene", ""),
                    "v5_light": v5_direction.get("light", {}),
                    "v5_composition": v5_direction.get("composition", {}),
                    "v5_product_presence": v5_direction.get("product_presence", ""),
                    "v5_prompt_governance": prompt_governance.get("status", ""),
                    "creative_route": creative_request["requestedRoute"],
                    "visual_action": creative_request["whatHappens"],
                    "visual_environment": creative_request["story"]["setup"],
                    "visual_hero": creative_request["visualHero"],
                    "characters_used": creative_request["characters"],
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
                    "creative_request": creative_request,
                    "provider_result": provider_result.as_dict(),
                    "engagement_metrics": {},
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                data_dir=self.data_dir,
            )

        return package

    # --- Batch --------------------------------------------------------------

    def create_batch(self, *, count: int, platform: str = "instagram_feed", **kw: Any) -> list[PostPackage]:
        out: list[PostPackage] = []
        for i in range(count):
            out.append(self.create_post(rotation_index=i, platform=platform, **kw))
        return out
