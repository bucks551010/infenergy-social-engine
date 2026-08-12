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
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import (
    carousel_director,
    claim_intelligence,
    copy_intelligence,
    engines,
    libraries,
    lean_intelligence,
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
    ) -> PostPackage:
        # 0. Recent state → recency-aware decisions
        recent = memory_intelligence.recent(self.data_dir, limit=20)

        # 0b. Optional BI Foundation hydration — only when the caller
        # didn't already specify a value and the flag is on.
        bi_offering = _bi_get_offering(product_id_override) if product_id_override else _bi_pick_offering(rotation_index)
        bi_ctx = _load_bi_creative_context(
            str((bi_offering or {}).get("offering_id") or (bi_offering or {}).get("sku") or "")
        )
        if product_id_override:
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
            brief.reader_job = locked["reader_job"]
        else:
            locked = None

        # 3. Copy assembly — real Gemini copy when available, deterministic
        # template assembly as the network-free fallback (§15 Copy Architect).
        beats = copy_intelligence.structure_for(brief.genre)
        llm_beats = _llm_copy_beats(brief, beats, bi_ctx, bi_offering)
        beat_content = llm_beats or _assemble_copy(brief=brief, structure_beats=beats)
        copy_generation_method = "llm" if llm_beats else "template_fallback"
        copy_fallback_reason = None if llm_beats else model_router.last_error()
        hook_text = beat_content.get("hook") or beat_content.get("question") or beat_content.get("problem") or ""
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

        # 9. Provider (real Gemini image generation, or template fallback)
        post_id = uuid.uuid4().hex[:12]
        art_dict = art.as_dict()
        art_dict["post_id"] = post_id
        art_dict["cta"] = selected_cta
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
                "strategy_lock": locked,
            },
            visual={
                "semantic_role": semantic_role,
                "visual_message": v_msg,
                "visual_format": v_format,
                "necessity_score": necessity,
                "required": must_render,
                "art_direction": art.as_dict(),
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "prompt_humanness": v_humanness,
                "signature": visual_intelligence.visual_signature(
                    visual_format=v_format,
                    layout_family="hero" if v_format not in {"carousel", "checklist"} else "list",
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
        )
        if locked:
            package.creative_director["human_connection_review"] = strategy_lock.human_connection_critique(
                strategy=locked,
                copy=package.copy,
                visual=package.visual,
            )
            package.creative_director["independent_human_connection_review"] = human_connection_review.review(
                strategy=locked, copy=package.copy, visual=package.visual
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
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                data_dir=self.data_dir,
            )
            memory_intelligence.append_visual_record(
                {
                    "post_id": post_id,
                    "visual_format": v_format,
                    "visual_signature": package.visual["signature"],
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
        out: list[PostPackage] = []
        for i in range(count):
            out.append(self.create_post(rotation_index=i, platform=platform, **kw))
        return out
