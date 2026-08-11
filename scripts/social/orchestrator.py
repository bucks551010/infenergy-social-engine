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
    memory_intelligence,
    quality_intelligence,
    visual_intelligence,
    visual_provider,
)


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
        self.provider = provider or visual_provider.TemplateRenderProvider()
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
    ) -> PostPackage:
        # 0. Recent state → recency-aware decisions
        recent = memory_intelligence.recent(self.data_dir, limit=20)

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

        # 3. Copy assembly
        beats = copy_intelligence.structure_for(brief.genre)
        beat_content = _assemble_copy(brief=brief, structure_beats=beats)
        hook_text = beat_content.get("hook") or beat_content.get("question") or beat_content.get("problem") or ""
        body_text = " ".join(v for k, v in beat_content.items() if k != "hook" and v)
        takeaway = beat_content.get("takeaway") or beat_content.get("lesson") or beat_content.get("implication") or brief.angle
        anchor = copy_intelligence.extract_memory_anchor(body_text, takeaway=takeaway)
        brief.hook = hook_text
        brief.body_beats = beat_content
        brief.takeaway = takeaway
        brief.memory_anchor = anchor

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
            has_product_asset=False,
        )
        concepts = visual_intelligence.generate_concepts(
            angle=brief.angle,
            memory_anchor=anchor,
            semantic_role=semantic_role,
            genre_id=brief.genre.get("id", ""),
        )
        top_concept = concepts[0]
        art = visual_intelligence.build_art_direction(
            visual_purpose=semantic_role,
            visual_msg=v_msg,
            visual_format=v_format,
            concept=top_concept,
            primary_subject=brief.topic_path.get("topic", brief.angle),
            platform=platform,
        )
        positive_prompt, negative_prompt = visual_intelligence.compile_image_prompt(art)
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

        # 9. Provider (optional visual generation)
        provider_result = self.provider.generate(
            art_direction=art.as_dict(),
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            platform=platform,
        )

        post_id = uuid.uuid4().hex[:12]
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

        return package

    # --- Batch --------------------------------------------------------------

    def create_batch(self, *, count: int, platform: str = "instagram_feed", **kw: Any) -> list[PostPackage]:
        out: list[PostPackage] = []
        for i in range(count):
            out.append(self.create_post(rotation_index=i, platform=platform, **kw))
        return out
