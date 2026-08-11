"""Audience world model + Jobs-to-be-Done (Master Build §5, §6).

Purpose
-------
Given a business objective and light context, decide:
  * which audience segment to serve
  * what the reader's job (JTBD) is
  * which curiosities, questions, misconceptions, information gaps to draw from

The output feeds the content strategy layer downstream. Everything is
data-driven via ``data/social/audience_world.json`` and
``data/social/reader_jobs.json``; no LLM required to run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import libraries


@dataclass
class AudienceSelection:
    segment_id: str
    segment: dict[str, Any]
    reader_job: str
    reader_job_config: dict[str, Any]
    information_gap: str
    curiosity: str
    misconception: str | None
    question: str
    emotional_driver: str
    rationale: list[str] = field(default_factory=list)


def all_segments() -> dict[str, Any]:
    return libraries.audience_segments()


def all_reader_jobs() -> dict[str, Any]:
    return libraries.reader_jobs()


def infer_segment(
    *,
    pillar_id: str | None = None,
    audience_hint: str | None = None,
    seasonal_context: str | None = None,
) -> str:
    """Return the segment_id best matching the given hints.

    Rule-based inference. Falls back to a stable default.
    """
    segs = all_segments()
    if audience_hint:
        hint = audience_hint.lower()
        for sid, seg in segs.items():
            if hint in sid.lower() or hint in seg.get("name", "").lower():
                return sid
        for sid, seg in segs.items():
            keywords = " ".join(seg.get("lifestyle_context", []) + seg.get("goals", [])).lower()
            if any(tok in keywords for tok in hint.split()):
                return sid

    pillar_bias = {
        "portable_power": "mobile_professional",
        "travel_power": "mobile_professional",
        "outdoor_power": "outdoor_enthusiast",
        "preparedness": "preparedness_focused_household",
        "emergency_readiness": "preparedness_focused_household",
        "buying_smarter": "curious_learner",
        "product_education": "curious_learner",
        "science_behind_power": "curious_learner",
        "energy_education": "curious_learner",
        "battery_knowledge": "curious_learner",
    }
    if pillar_id and pillar_id in pillar_bias:
        if pillar_bias[pillar_id] in segs:
            return pillar_bias[pillar_id]

    if seasonal_context and "storm" in seasonal_context.lower():
        if "preparedness_focused_household" in segs:
            return "preparedness_focused_household"

    return next(iter(segs.keys()))


def _select_reader_job(segment: dict[str, Any], pillar_id: str | None) -> str:
    """Pick a JTBD compatible with the segment's emotional drivers."""
    jobs = all_reader_jobs()
    drivers = set(segment.get("emotional_drivers", []))

    # Score each job by driver overlap; prefer jobs whose typical_emotion
    # matches a segment driver.
    scores: list[tuple[str, int]] = []
    for jid, jcfg in jobs.items():
        score = 0
        if jcfg.get("typical_emotion") in drivers:
            score += 3
        # Slight preference toward high-utility jobs for beginner learners
        if segment.get("experience_level") == "beginner" and jid in {"TEACH_ME", "EXPLAIN_THIS"}:
            score += 2
        if segment.get("experience_level") == "advanced_novice" and jid in {"HELP_ME_CHOOSE", "GIVE_ME_A_REFERENCE"}:
            score += 2
        # Nudge based on pillar
        if pillar_id in {"preparedness", "emergency_readiness"} and jid in {"PREPARE_ME", "WARN_ME"}:
            score += 2
        if pillar_id == "buying_smarter" and jid in {"HELP_ME_CHOOSE", "SAVE_ME_MONEY"}:
            score += 2
        scores.append((jid, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[0][0]


def _pick(items: list[Any], index_hint: int = 0) -> Any | None:
    if not items:
        return None
    return items[index_hint % len(items)]


def select(
    *,
    pillar_id: str | None = None,
    audience_hint: str | None = None,
    seasonal_context: str | None = None,
    rotation_index: int = 0,
) -> AudienceSelection:
    """Build a full audience selection.

    ``rotation_index`` allows diverse picks across a batch (a counter or
    hash of recent posts) without introducing randomness.
    """
    segs = all_segments()
    jobs = all_reader_jobs()

    sid = infer_segment(
        pillar_id=pillar_id,
        audience_hint=audience_hint,
        seasonal_context=seasonal_context,
    )
    segment = segs[sid]
    reader_job = _select_reader_job(segment, pillar_id)
    reader_job_cfg = jobs[reader_job]

    info_gap = _pick(segment.get("information_gaps", []), rotation_index)
    curiosity = _pick(segment.get("curiosities", []), rotation_index + 1)
    misconception = _pick(segment.get("misconceptions", []), rotation_index + 2)
    question = _pick(segment.get("questions", []), rotation_index + 3)
    emotion = (segment.get("emotional_drivers") or [reader_job_cfg.get("typical_emotion") or "curiosity"])[0]

    rationale = [
        f"segment inferred from pillar={pillar_id}, audience_hint={audience_hint}",
        f"reader job {reader_job} chosen for driver alignment with {emotion}",
    ]

    return AudienceSelection(
        segment_id=sid,
        segment=segment,
        reader_job=reader_job,
        reader_job_config=reader_job_cfg,
        information_gap=info_gap or "",
        curiosity=curiosity or "",
        misconception=misconception,
        question=question or "",
        emotional_driver=emotion,
        rationale=rationale,
    )
