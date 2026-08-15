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
    recovery,
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
    opportunity_shortlist: list[dict[str, Any]] = field(default_factory=list)
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
            "opportunity_shortlist": self.opportunity_shortlist,
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
    excluded_concepts: list[str] | None,
    rotation_index: int,
    selected_opportunity_id: str = "",
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
        excluded_concepts=excluded_concepts or [],
        limit=6,
    )
    if not candidates:
        raise RuntimeError("no viable opportunities generated")
    shortlist = [
        {**recovery.compact_candidate(candidate, rank), "engine": engine}
        for rank, candidate in enumerate(candidates, start=1)
    ]
    best = next(
        (candidate for candidate, compact in zip(candidates, shortlist) if compact["opportunity_id"] == selected_opportunity_id),
        candidates[0],
    )

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
        opportunity_shortlist=shortlist,
    )


def _opportunity_record(candidate: opportunity_engine.OpportunityCandidate, *, engine: str, recent: dict[str, list[Any]]) -> dict[str, Any]:
    """Describe a cheap strategic option before it is allowed to create copy or media."""
    compact = recovery.compact_candidate(candidate, 0)
    audience = candidate.audience
    path = candidate.topic_path
    candidate_text = " ".join((path.topic, path.microtopic, path.angle, audience.question, audience.curiosity))
    product_centered = engine == "A"
    content_mode = {
        "A": "PRODUCT_FIT",
        "B": "DECISION_SUPPORT",
        "C": "BRAND_PERSPECTIVE",
    }.get(engine, "AUDIENCE_VALUE")
    technical_terms = {"capacity", "output", "connection", "compatibility", "stored energy", "specification"}
    depends_on_category_fact = engine == "B" and any(term in candidate_text.lower() for term in technical_terms)
    claim_burden_level = 1 if product_centered else 2 if depends_on_category_fact else 0
    evidence_burden = "REQUIRES_PRODUCT_EVIDENCE" if claim_burden_level == 1 else "LOW"
    commercial_intensity = "PRODUCT_LIGHT" if product_centered else "NONE"
    truth_penalty = 0.22 if product_centered else 0.14 if claim_burden_level == 2 else 0.0
    audience_bonus = 0.12 if engine == "B" else 0.0
    publishability = {
        "status": "PASS",
        "central_message_identifiable": bool(path.angle),
        "truth_basis": "verified_product_facts" if claim_burden_level == 1 else "owner_approved_decision_guidance" if claim_burden_level == 2 else "brand_perspective_or_planning_prompt",
        "claim_burden_level": claim_burden_level,
        "evidence_available": claim_burden_level < 3,
        "freshness_acceptable": float(candidate.scores.get("novelty", 0.0)) >= 0.5,
        "audience_value_meaningful": float(candidate.scores.get("usefulness", 0.65)) >= 0.55,
        "platform_fit_plausible": float(candidate.scores.get("platform_fit", 0.7)) >= 0.5,
        "visual_concept_possible": float(candidate.scores.get("visual_potential", 0.7)) >= 0.5,
    }
    return {
        **compact,
        "candidate_id": f"{engine}:{compact['opportunity_id']}",
        "engine": engine,
        "audience": audience.segment_id,
        "human_reality": audience.curiosity,
        "situation": audience.information_gap,
        "what_matters": path.angle,
        "core_question": audience.question,
        "core_answer": path.angle,
        "one_big_idea": path.angle,
        "reader_job": audience.reader_job,
        "content_job": candidate.genre_id,
        "content_mode": content_mode,
        "product_relevance": "EARNED_BY_EVIDENCE" if product_centered else "NOT_REQUIRED",
        "product_id": "",
        "product_role": "DECISION_SUPPORT" if product_centered else "NONE",
        "commercial_intensity": commercial_intensity,
        "expected_response": audience.reader_job,
        "campaign_fit": "ELIGIBLE",
        "known_evidence_burden": evidence_burden,
        "claim_burden_level": claim_burden_level,
        "publishability_precheck": publishability,
        "recent_semantic_similarity": round(1.0 - float(candidate.scores.get("novelty", 0.0)), 3),
        "recent_product_pressure": len(recent.get("product_roles", [])),
        "likely_platform_fit": round(float(candidate.scores.get("platform_fit", 0.0)), 3),
        "reason_it_may_deserve_publication": candidate.score_summary(),
        "prequalification_text": candidate_text,
        "global_score": round(float(candidate.total) - truth_penalty + audience_bonus, 4),
    }


def build_competitive_pool(
    *,
    recent: dict[str, list[Any]] | None = None,
    audience_hint: str | None = None,
    seasonal_context: str | None = None,
    preferred_pillar: str | None = None,
    excluded_concepts: list[str] | None = None,
    rotation_index: int = 0,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Rank up to six cheap cross-engine opportunities before expensive work.

    The records are structured from existing libraries only. They are not copy,
    prompts, images, or model calls; downstream generation receives one winner.
    """
    recent = recent or {}
    excluded = excluded_concepts or []
    records: list[dict[str, Any]] = []
    engine_pillars = {"A": "product_education", "B": preferred_pillar, "C": "brand_philosophy"}
    for engine in ("A", "B", "C"):
        candidates = opportunity_engine.generate(
            engine=engine,
            recent_pillars=recent.get("pillars", []),
            recent_genres=recent.get("genres", []),
            recent_topics=recent.get("topics", []),
            recent_microtopics=recent.get("microtopics", []),
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=engine_pillars[engine],
            excluded_concepts=excluded,
            limit=2,
        )
        for candidate in candidates[:2]:
            record = _opportunity_record(candidate, engine=engine, recent=recent)
            if opportunity_engine.text_is_excluded(record["prequalification_text"], excluded):
                continue
            if record["recent_semantic_similarity"] >= 0.75:
                continue
            records.append(record)

    records.sort(key=lambda item: (float(item["global_score"]), -int(item["claim_burden_level"])), reverse=True)
    retained: list[dict[str, Any]] = []
    seen_opportunities: set[str] = set()
    for record in records:
        opportunity_id = str(record["opportunity_id"])
        if opportunity_id in seen_opportunities:
            continue
        seen_opportunities.add(opportunity_id)
        retained.append(record)
        if len(retained) >= limit:
            break
    for rank, record in enumerate(retained, start=1):
        record["rank"] = rank
        record.pop("prequalification_text", None)
    return retained


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
        excluded_concepts: list[str] | None = None,
        rotation_index: int = 0,
        selected_opportunity_id: str = "",
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
            excluded_concepts=excluded_concepts,
            rotation_index=rotation_index,
            selected_opportunity_id=selected_opportunity_id,
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
        excluded_concepts: list[str] | None = None,
        rotation_index: int = 0,
        selected_opportunity_id: str = "",
    ) -> EngineBrief:
        recent = recent or {}
        brief = _shared_brief(
            "B",
            recent=recent,
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=preferred_pillar,
            excluded_concepts=excluded_concepts,
            rotation_index=rotation_index,
            selected_opportunity_id=selected_opportunity_id,
        )
        if not selected_opportunity_id:
            opportunity = audience_value.discover(
                recent=recent,
                rotation_index=rotation_index,
                seasonal_context=seasonal_context,
            )
            brief.audience_value = opportunity.as_dict()
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
        excluded_concepts: list[str] | None = None,
        rotation_index: int = 0,
        selected_opportunity_id: str = "",
    ) -> EngineBrief:
        return _shared_brief(
            "C",
            recent=recent or {},
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            preferred_pillar=preferred_pillar or "brand_philosophy",
            excluded_concepts=excluded_concepts,
            rotation_index=rotation_index,
            selected_opportunity_id=selected_opportunity_id,
        )


ENGINES: dict[str, Any] = {
    "A": ConversionEngine(),
    "B": AudienceValueEngine(),
    "C": BrandCommunityEngine(),
}


def get_engine(name: str) -> Any:
    return ENGINES.get(name.upper(), ENGINES["B"])
