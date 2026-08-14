"""Content Opportunity Engine (Master Build §11).

Generates candidate opportunities (pillar + genre + topic_path + angle) and
ranks them across 13 dimensions before picking one. Data-driven, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import audience_intelligence, content_strategy, libraries

_CONCEPT_STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "this", "that", "to", "with", "your"}


def _concept_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(token) > 2 and token not in _CONCEPT_STOP_WORDS}


def concept_is_excluded(candidate: OpportunityCandidate, excluded_concepts: Iterable[str]) -> bool:
    candidate_text = " ".join((str(candidate.topic_path.topic or ""), str(candidate.topic_path.microtopic or ""), str(candidate.topic_path.angle or ""), str(candidate.audience.question or ""), str(candidate.audience.curiosity or "")))
    return text_is_excluded(candidate_text, excluded_concepts)


def text_is_excluded(candidate_text: str, excluded_concepts: Iterable[str]) -> bool:
    candidate_tokens = _concept_tokens(candidate_text)
    for excluded in excluded_concepts:
        excluded_tokens = _concept_tokens(str(excluded))
        if candidate_tokens and excluded_tokens and len(candidate_tokens & excluded_tokens) / min(len(candidate_tokens), len(excluded_tokens)) >= 0.5:
            return True
    return False


@dataclass
class OpportunityCandidate:
    pillar_id: str
    genre_id: str
    topic_path: content_strategy.TopicPath
    audience: audience_intelligence.AudienceSelection
    scores: dict[str, float]
    total: float = 0.0

    def score_summary(self) -> str:
        top = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)[:3]
        return ", ".join(f"{k}={v:.2f}" for k, v in top)


_SCORE_DIMENSIONS = (
    "audience_relevance",
    "information_value",
    "novelty",
    "usefulness",
    "brand_alignment",
    "visual_potential",
    "timeliness",
    "emotional_potential",
    "save_potential",
    "share_potential",
    "discussion_potential",
    "series_fit",
    "platform_fit",
)


def _score_candidate(
    *,
    pillar_id: str,
    genre_id: str,
    genre: dict[str, Any],
    topic_path: content_strategy.TopicPath,
    audience: audience_intelligence.AudienceSelection,
    recent_topics: Iterable[str],
    engine: str,
    seasonal_context: str | None,
) -> dict[str, float]:
    pillars = libraries.pillars()
    p = pillars.get(pillar_id, {})
    scores: dict[str, float] = {}

    # audience_relevance: does the microtopic connect to segment questions/gaps?
    seg_gaps = " ".join(audience.segment.get("information_gaps", [])).lower()
    micro = (topic_path.microtopic or "").lower()
    scores["audience_relevance"] = 0.9 if micro and any(tok in seg_gaps for tok in micro.split()) else 0.55

    # information_value: comes from genre's declared density
    scores["information_value"] = float(genre.get("avg_information_density", 0.5))

    # novelty: penalize repeat topics
    scores["novelty"] = 0.4 if topic_path.topic in set(recent_topics) else 0.85

    # usefulness: reader_job affinity
    useful_jobs = {"HELP_ME", "SAVE_ME_TIME", "SAVE_ME_MONEY", "HELP_ME_AVOID_A_MISTAKE", "PREPARE_ME"}
    scores["usefulness"] = 0.9 if audience.reader_job in useful_jobs else 0.6

    # brand_alignment: engine_fit boost
    scores["brand_alignment"] = 0.85 if engine in p.get("engine_fit", []) else 0.5

    # visual_potential: whether genre has strong visual formats
    v_fits = genre.get("visual_format_preferences", [])
    scores["visual_potential"] = 0.85 if v_fits and v_fits[0] != "no_visual" else 0.35

    # timeliness: seasonal bump
    if seasonal_context and pillar_id in {"preparedness", "emergency_readiness"}:
        scores["timeliness"] = 0.9
    else:
        scores["timeliness"] = 0.55 if p.get("evergreen") else 0.8

    # emotional_potential: whether reader_job has strong typical_emotion
    scores["emotional_potential"] = 0.8 if audience.reader_job_config.get("typical_emotion") else 0.5

    # save/share/discussion: derived from genre CTA preferences
    ctas = set(genre.get("cta_preferences", []))
    scores["save_potential"] = 0.9 if "SAVE" in ctas else 0.4
    scores["share_potential"] = 0.85 if ("SHARE" in ctas or "REFLECT" in ctas) else 0.45
    scores["discussion_potential"] = 0.8 if ("COMMENT" in ctas or "REFLECT" in ctas) else 0.3

    # series_fit: null unless a series applies (orchestrator layer decides)
    scores["series_fit"] = 0.5

    # platform_fit: engine agnostic default; adapters can adjust later
    scores["platform_fit"] = 0.7

    return scores


def generate(
    *,
    engine: str,
    recent_pillars: Iterable[str] = (),
    recent_genres: Iterable[str] = (),
    recent_topics: Iterable[str] = (),
    recent_microtopics: Iterable[str] = (),
    audience_hint: str | None = None,
    seasonal_context: str | None = None,
    preferred_pillar: str | None = None,
    limit: int = 6,
    excluded_concepts: Iterable[str] = (),
) -> list[OpportunityCandidate]:
    """Produce ``limit`` ranked candidates. Highest total_score first."""
    candidates: list[OpportunityCandidate] = []
    all_p = libraries.pillars()
    all_g = libraries.genres()
    recent_topics_list = list(recent_topics)
    recent_p = list(recent_pillars)
    recent_g = list(recent_genres)
    recent_m = list(recent_microtopics)

    eligible_p = content_strategy.eligible_pillars(engine=engine, recent_pillars=recent_p)
    if preferred_pillar and preferred_pillar in all_p:
        eligible_p = {preferred_pillar: all_p[preferred_pillar], **eligible_p}
    if not eligible_p:
        eligible_p = {pid: p for pid, p in all_p.items() if engine in p.get("engine_fit", [])} or all_p

    rot = 0
    for pid, _p in eligible_p.items():
        aud = audience_intelligence.select(
            pillar_id=pid,
            audience_hint=audience_hint,
            seasonal_context=seasonal_context,
            rotation_index=rot,
        )
        tp = content_strategy.pick_topic_path(
            pillar_id=pid,
            recent_microtopics=recent_m,
            rotation_index=rot,
        )
        if tp is None:
            continue

        # Genre from reader_job
        gd = content_strategy.select_genre(
            reader_job=aud.reader_job,
            pillar_id=pid,
            recent_genres=recent_g,
        )
        genre = all_g.get(gd.genre_id, {})

        scores = _score_candidate(
            pillar_id=pid,
            genre_id=gd.genre_id,
            genre=genre,
            topic_path=tp,
            audience=aud,
            recent_topics=recent_topics_list,
            engine=engine,
            seasonal_context=seasonal_context,
        )
        total = sum(scores.values()) / max(1, len(scores))
        candidates.append(
            OpportunityCandidate(
                pillar_id=pid,
                genre_id=gd.genre_id,
                topic_path=tp,
                audience=aud,
                scores=scores,
                total=total,
            )
        )
        rot += 1
        if len(candidates) >= limit * 2:
            break

    # Apply obviousness filter to angles before ranking finalizes
    survivors: list[OpportunityCandidate] = []
    for c in candidates:
        if content_strategy.is_obvious(c.topic_path.angle):
            c.scores["novelty"] = max(0.0, c.scores["novelty"] - 0.4)
            c.total = sum(c.scores.values()) / max(1, len(c.scores))
        survivors.append(c)

    survivors = [candidate for candidate in survivors if not concept_is_excluded(candidate, excluded_concepts)]
    survivors.sort(key=lambda c: c.total, reverse=True)
    return survivors[:limit]
