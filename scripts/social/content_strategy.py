"""Content strategy layer (Master Build §7, §8, §9, §10, §12, §13, §14).

Combines:
  * pillar selection with cooldowns
  * genre selection with fatigue avoidance
  * topic-graph traversal (topic → subtopic → microtopic → angle)
  * information gap generation
  * obviousness filter (§13)
  * angle multiplication (§14)
  * series scheduling (§10)

All data-driven; pure Python; no LLM required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import libraries


# -- Pillar selection ---------------------------------------------------------

@dataclass
class PillarDecision:
    pillar_id: str
    pillar: dict[str, Any]
    weight: float
    rationale: list[str] = field(default_factory=list)


def _cooldown_slots() -> int:
    return int(libraries.pillar_defaults().get("cooldown_slots", 3))


def _min_variety_window() -> int:
    return int(libraries.pillar_defaults().get("min_pillar_variety_window", 5))


def eligible_pillars(
    *,
    engine: str | None = None,
    recent_pillars: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    """Return pillars eligible under recency + engine-fit constraints."""
    all_p = libraries.pillars()
    recent = list(recent_pillars)
    cooldown = _cooldown_slots()
    banned = set(recent[-cooldown:])
    out: dict[str, dict[str, Any]] = {}
    for pid, p in all_p.items():
        if pid in banned:
            continue
        if engine and engine not in p.get("engine_fit", []):
            continue
        out[pid] = p
    return out


def select_pillar(
    *,
    engine: str | None = None,
    recent_pillars: Iterable[str] = (),
    preferred: str | None = None,
    seasonal_context: str | None = None,
) -> PillarDecision:
    """Pick the strongest eligible pillar."""
    all_p = libraries.pillars()
    elig = eligible_pillars(engine=engine, recent_pillars=recent_pillars)
    if not elig:
        elig = {k: v for k, v in all_p.items() if not engine or engine in v.get("engine_fit", [])} or all_p

    rationale: list[str] = []
    if preferred and preferred in elig:
        rationale.append(f"preferred pillar {preferred} respected")
        p = elig[preferred]
        return PillarDecision(pillar_id=preferred, pillar=p, weight=p.get("weight", 1.0), rationale=rationale)

    if seasonal_context and "storm" in (seasonal_context or "").lower():
        for candidate in ("emergency_readiness", "preparedness"):
            if candidate in elig:
                rationale.append(f"seasonal '{seasonal_context}' boosts {candidate}")
                return PillarDecision(pillar_id=candidate, pillar=elig[candidate], weight=elig[candidate].get("weight", 1.0), rationale=rationale)

    ranked = sorted(elig.items(), key=lambda kv: kv[1].get("weight", 1.0), reverse=True)
    pid, p = ranked[0]
    rationale.append(f"highest-weight eligible pillar under engine={engine}")
    return PillarDecision(pillar_id=pid, pillar=p, weight=p.get("weight", 1.0), rationale=rationale)


# -- Genre selection ----------------------------------------------------------

@dataclass
class GenreDecision:
    genre_id: str
    genre: dict[str, Any]
    rationale: list[str] = field(default_factory=list)


def select_genre(
    *,
    reader_job: str,
    pillar_id: str | None = None,
    recent_genres: Iterable[str] = (),
    preferred: str | None = None,
) -> GenreDecision:
    """Pick a genre compatible with the reader job and not recently used."""
    all_g = libraries.genres()
    recent = list(recent_genres)
    banned = set(recent[-3:])  # short cooldown for genres

    candidates: dict[str, dict[str, Any]] = {}
    for gid, g in all_g.items():
        if gid in banned:
            continue
        if reader_job in g.get("reader_jobs", []):
            candidates[gid] = g
    if not candidates:
        candidates = {gid: g for gid, g in all_g.items() if reader_job in g.get("reader_jobs", [])}
    if not candidates:
        candidates = dict(all_g)

    rationale: list[str] = []
    if preferred and preferred in candidates:
        rationale.append(f"preferred genre {preferred} respected")
        return GenreDecision(genre_id=preferred, genre=candidates[preferred], rationale=rationale)

    ranked = sorted(candidates.items(), key=lambda kv: kv[1].get("avg_information_density", 0.5), reverse=True)
    gid, g = ranked[0]
    rationale.append(f"highest density genre fitting reader_job={reader_job}")
    return GenreDecision(genre_id=gid, genre=g, rationale=rationale)


# -- Topic graph traversal ----------------------------------------------------

@dataclass
class TopicPath:
    topic: str
    subtopic: str
    microtopic: str
    angle: str
    pillar_id: str
    rationale: list[str] = field(default_factory=list)


def pillar_topics(pillar_id: str) -> list[str]:
    """Return topic ids in the topic_graph matching the pillar."""
    tg = libraries.topic_graph()
    return [tid for tid, t in tg.items() if t.get("pillar") == pillar_id]


def _rotate(seq: list[Any], rotation_index: int) -> Any | None:
    if not seq:
        return None
    return seq[rotation_index % len(seq)]


def pick_topic_path(
    *,
    pillar_id: str,
    recent_microtopics: Iterable[str] = (),
    rotation_index: int = 0,
) -> TopicPath | None:
    """Deterministically pick a topic → subtopic → microtopic → angle."""
    tg = libraries.topic_graph()
    banned = set(recent_microtopics)

    candidates = pillar_topics(pillar_id)
    if not candidates:
        return None

    topic_id = _rotate(candidates, rotation_index)
    topic = tg[topic_id]
    subtopics = list(topic.get("subtopics", {}).items())
    if not subtopics:
        return None
    sub_id, sub = _rotate(subtopics, rotation_index)

    micro_pool = [m for m in sub.get("microtopics", []) if m not in banned]
    if not micro_pool:
        micro_pool = list(sub.get("microtopics", []))
    angle = _rotate(sub.get("angles", []), rotation_index) if sub.get("angles") else ""
    angle_terms = set(str(angle or "").lower().replace("-", " ").split())
    scored_microtopics = sorted(
        micro_pool,
        key=lambda value: len(angle_terms.intersection(str(value).lower().replace("-", " ").split())),
        reverse=True,
    )
    best_micro = scored_microtopics[0] if scored_microtopics else ""
    best_overlap = len(angle_terms.intersection(str(best_micro).lower().replace("-", " ").split()))
    micro = best_micro if best_overlap else (_rotate(micro_pool, rotation_index) if micro_pool else "")

    rationale = [
        f"pillar={pillar_id} → topic={topic_id} → subtopic={sub_id}",
        f"microtopic '{micro}' picked with rotation_index={rotation_index}",
    ]

    return TopicPath(
        topic=topic.get("name", topic_id),
        subtopic=sub_id,
        microtopic=micro or "",
        angle=angle or "",
        pillar_id=pillar_id,
        rationale=rationale,
    )


# -- Information gap engine (§12) --------------------------------------------

def information_gaps_for(segment: dict[str, Any], topic_path: TopicPath | None) -> list[str]:
    """Combine segment-level information gaps with topic-derived questions."""
    seg_gaps = list(segment.get("information_gaps", []))
    if topic_path and topic_path.angle:
        seg_gaps = [topic_path.angle] + seg_gaps
    return [g for g in seg_gaps if g]


# -- Obviousness filter (§13) ------------------------------------------------

_OBVIOUS_PATTERNS = (
    "charge your phone before",
    "buy the biggest",
    "always charge to 100",
    "never let your battery die",
    "backup power is important",
    "safety first",
)


def is_obvious(idea: str) -> bool:
    """Return True if the phrasing looks like content-noise obviousness."""
    if not idea:
        return True
    low = idea.lower()
    return any(pat in low for pat in _OBVIOUS_PATTERNS)


def reject_obviousness(candidates: list[str]) -> list[str]:
    """Filter out obvious candidates; return survivors."""
    return [c for c in candidates if not is_obvious(c)]


# -- Angle multiplier (§14) --------------------------------------------------

def multiply_angles(topic_path: TopicPath, information_gap: str = "") -> list[str]:
    """Produce several legitimate angles for the same topic path."""
    tg = libraries.topic_graph()
    topic = next(
        (t for t in tg.values() if t.get("name", "").lower() == topic_path.topic.lower()),
        None,
    )
    if not topic:
        return [topic_path.angle] if topic_path.angle else []
    sub = topic.get("subtopics", {}).get(topic_path.subtopic, {})
    angles = list(sub.get("angles", []))
    if information_gap and information_gap not in angles:
        angles.append(information_gap)
    return angles


# -- Series scheduling (§10) -------------------------------------------------

def eligible_series(
    *,
    recent_series_by_id: dict[str, int],
    day_index: int,
    genre_id: str | None = None,
) -> list[str]:
    """Return series_ids eligible today under min_gap_days constraints.

    ``recent_series_by_id`` maps series_id → days_since_last_run.
    """
    reg = libraries.series_registry()
    out: list[str] = []
    for sid, cfg in reg.items():
        last = recent_series_by_id.get(sid)
        min_gap = int(cfg.get("min_gap_days", 7))
        if last is not None and last < min_gap:
            continue
        if genre_id and cfg.get("genres") and genre_id not in cfg["genres"]:
            continue
        out.append(sid)
    return out
