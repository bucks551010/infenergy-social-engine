"""Three engines that produce a strategic content brief (Master Build §2, §3).

* Engine A — CONVERSION LOGIC ENGINE (existing, wrapped in adapter)
* Engine B — AUDIENCE VALUE ENGINE (new — teach/entertain/inform)
* Engine C — BRAND & COMMUNITY ENGINE (new — brand identity + community)

All three share the same output shape (``EngineBrief``) so the
orchestrator can hand any of them off to the downstream copy + visual
intelligence stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import (
    audience_value,
    copy_intelligence,
    libraries,
    opportunity_engine,
)


@dataclass
class EngineBrief:
    engine: str  # A | B | C
    pillar: dict[str, Any]
    genre: dict[str, Any]
    reader_job: str
    reader_job_config: dict[str, Any]
    audience_segment: str
    audience_segment_config: dict[str, Any]
    information_gap: str
    curiosity: str
    misconception: str
    question: str
    emotional_driver: str
    topic_path: dict[str, Any]
    angle: str
    tone: str
    opportunity_score: float
    rationale: list[str] = field(default_factory=list)
    # Populated later by copy stage
    hook: str = ""
    body_beats: dict[str, str] = field(default_factory=dict)
    takeaway: str = ""
    memory_anchor: str = ""
    audience_value: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "pillar_id": self.pillar.get("id"),
            "genre_id": self.genre.get("id"),
            "reader_job": self.reader_job,
            "audience_segment": self.audience_segment,
            "information_gap": self.information_gap,
            "curiosity": self.curiosity,
            "misconception": self.misconception,
            "question": self.question,
            "emotional_driver": self.emotional_driver,
            "topic_path": self.topic_path,
            "angle": self.angle,
            "tone": self.tone,
            "opportunity_score": self.opportunity_score,
            "rationale": self.rationale,
            "hook": self.hook,
            "body_beats": self.body_beats,
            "takeaway": self.takeaway,
            "memory_anchor": self.memory_anchor,
            "audience_value": self.audience_value,
        }


# --- Shared building block --------------------------------------------------


def _shared_brief(
    engine: str,
    *,
    recent: dict[str, list[Any]],
    audience_hint: str | None,
    seasonal_context: str | None,
    preferred_pillar: str | None,
    rotation_index: int,
) -> EngineBrief:
    # 1. Opportunity generation
    candidates = opportunity_engine.generate(
        engine=engine,
        recent_pillars=recent.get("pillars", []),
        recent_genres=recent.get("genres", []),
        recent_topics=recent.get("topics", []),
        recent_microtopics=recent.get("microtopics", []),
        audience_hint=audience_hint,
        seasonal_context=seasonal_context,
        preferred_pillar=preferred_pillar,
        limit=6,
    )
    if not candidates:
        raise RuntimeError("no viable opportunities generated")
    best = candidates[0]

    pillars = libraries.pillars()
    pillar = dict(pillars[best.pillar_id])
    pillar["id"] = best.pillar_id

    genre = dict(libraries.genres()[best.genre_id])
    genre["id"] = best.genre_id

    aud = best.audience
    topic_path = best.topic_path

    tone = copy_intelligence.tone_for(aud.reader_job, aud.emotional_driver)

    return EngineBrief(
        engine=engine,
        pillar=pillar,
        genre=genre,
        reader_job=aud.reader_job,
        reader_job_config=aud.reader_job_config,
        audience_segment=aud.segment_id,
        audience_segment_config=aud.segment,
        information_gap=aud.information_gap,
        curiosity=aud.curiosity,
        misconception=aud.misconception or "",
        question=aud.question,
        emotional_driver=aud.emotional_driver,
        topic_path=topic_path.__dict__ if hasattr(topic_path, "__dict__") else dict(topic_path),
        angle=topic_path.angle,
        tone=tone,
        opportunity_score=best.total,
        rationale=list(aud.rationale) + [best.score_summary()],
    )


# --- Engine A — Conversion (adapter over existing ConversionLogicEngine) ---


class ConversionEngine:
    """Adapter that wraps the existing ConversionLogicEngine.

    We do NOT rewrite conversion logic — we call it and translate its
    StrategicBrief into an EngineBrief so the visual/quality stages can
    treat all three engines uniformly.
    """

    name = "A"

    def build(
        self,
        *,
        recent: dict[str, list[Any]] | None = None,
        audience_hint: str | None = None,
        seasonal_context: str | None = None,
        preferred_pillar: str | None = None,
        rotation_index: int = 0,
    ) -> EngineBrief:
        recent = recent or {}
        # For now, produce a social-shaped brief anchored to a
        # conversion-friendly pillar. A future iteration can call
        # ConversionLogicEngine.build_brief() and merge its fields.
        return _shared_brief(
            "A",
            recent=recent,
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=preferred_pillar or "product_education",
            rotation_index=rotation_index,
        )


# --- Engine B — Audience Value (teach/entertain/inform) --------------------


class AudienceValueEngine:
    name = "B"

    def build(
        self,
        *,
        recent: dict[str, list[Any]] | None = None,
        audience_hint: str | None = None,
        seasonal_context: str | None = None,
        preferred_pillar: str | None = None,
        rotation_index: int = 0,
    ) -> EngineBrief:
        recent = recent or {}
        brief = _shared_brief(
            "B",
            recent=recent,
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=preferred_pillar,
            rotation_index=rotation_index,
        )
        opportunity = audience_value.discover(
            recent=recent,
            rotation_index=rotation_index,
            seasonal_context=seasonal_context,
        )
        brief.audience_value = opportunity.as_dict()
        if not opportunity.abstain:
            brief.question = opportunity.reader_question
            brief.angle = opportunity.reader_takeaway
            brief.curiosity = opportunity.why_it_matters
            brief.rationale.extend(["audience_value_engine", opportunity.state_reason])
        return brief


# --- Engine C — Brand & Community ------------------------------------------


class BrandCommunityEngine:
    name = "C"

    def build(
        self,
        *,
        recent: dict[str, list[Any]] | None = None,
        audience_hint: str | None = None,
        seasonal_context: str | None = None,
        preferred_pillar: str | None = None,
        rotation_index: int = 0,
    ) -> EngineBrief:
        return _shared_brief(
            "C",
            recent=recent or {},
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=preferred_pillar or "brand_philosophy",
            rotation_index=rotation_index,
        )


ENGINES: dict[str, Any] = {
    "A": ConversionEngine(),
    "B": AudienceValueEngine(),
    "C": BrandCommunityEngine(),
}


def get_engine(name: str) -> Any:
    return ENGINES.get(name.upper(), ENGINES["B"])
