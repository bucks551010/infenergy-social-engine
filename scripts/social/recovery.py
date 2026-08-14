"""Bounded, fail-closed recovery policy for one publishing opportunity."""

from __future__ import annotations

from typing import Any


PRESENTATION_REPAIRABLE = "PRESENTATION_REPAIRABLE"
STRATEGY_REPLACEMENT_REQUIRED = "STRATEGY_REPLACEMENT_REQUIRED"
CREATIVE_REPAIRABLE = "CREATIVE_REPAIRABLE"
NON_CONTENT_SYSTEM_FAILURE = "NON_CONTENT_SYSTEM_FAILURE"

_PRESENTATION_MARKERS = ("final_presentation_not_ready", "caption", "platform_format")
_STRATEGY_MARKERS = (
    "duplicate", "research_required", "unsupported", "semantic", "stale",
    "campaign_conflict", "human_connection_review_do_not_publish",
)
_CREATIVE_MARKERS = ("visual", "artifact", "aspect_ratio", "render")
_SYSTEM_MARKERS = ("token", "credential", "publisher", "http_", "runtime", "railway")


def classify_failure(reasons: list[str]) -> str:
    """Classify a failure conservatively; strategy always wins over cosmetics."""
    normalized = [str(reason or "").lower() for reason in reasons]
    if any(marker in reason for reason in normalized for marker in _SYSTEM_MARKERS):
        return NON_CONTENT_SYSTEM_FAILURE
    if any(marker in reason for reason in normalized for marker in _STRATEGY_MARKERS):
        return STRATEGY_REPLACEMENT_REQUIRED
    if any(marker in reason for reason in normalized for marker in _CREATIVE_MARKERS):
        return CREATIVE_REPAIRABLE
    if normalized and all(any(marker in reason for marker in _PRESENTATION_MARKERS) for reason in normalized):
        return PRESENTATION_REPAIRABLE
    return STRATEGY_REPLACEMENT_REQUIRED


def compact_candidate(candidate: Any, rank: int) -> dict[str, Any]:
    """Persist only run-scoped opportunity metadata, never generation payloads."""
    topic_path = getattr(candidate, "topic_path", None)
    audience = getattr(candidate, "audience", None)
    scores = getattr(candidate, "scores", {}) or {}
    return {
        "rank": rank,
        "opportunity_id": f"{getattr(candidate, 'pillar_id', '')}:{getattr(candidate, 'genre_id', '')}:{getattr(topic_path, 'microtopic', '')}",
        "engine": "",
        "pillar": getattr(candidate, "pillar_id", ""),
        "genre": getattr(candidate, "genre_id", ""),
        "topic": getattr(topic_path, "topic", ""),
        "question": getattr(audience, "question", ""),
        "angle": getattr(topic_path, "angle", ""),
        "human_reality": getattr(audience, "curiosity", ""),
        "reader_job": getattr(audience, "reader_job", ""),
        "opportunity_score": round(float(getattr(candidate, "total", 0) or 0), 4),
        "semantic_score": round(float(scores.get("novelty", 0) or 0), 4),
    }


def select_replacement(
    shortlist: list[dict[str, Any]],
    *,
    excluded_product_ids: set[str] | None = None,
    excluded_concepts: set[str] | None = None,
    blocked_human_realities: set[str] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Choose Candidate B in rank order, recording compact skip evidence."""
    excluded_product_ids = {str(value) for value in excluded_product_ids or set()}
    excluded_concepts = {str(value).lower() for value in excluded_concepts or set() if value}
    blocked_human_realities = {str(value).lower() for value in blocked_human_realities or set() if value}
    considered: list[dict[str, str]] = []
    for candidate in sorted(shortlist, key=lambda item: int(item.get("rank", 0))):
        rank = int(candidate.get("rank", 0))
        if rank <= 1:
            continue
        product_id = str(candidate.get("product_id") or "")
        text = " ".join(str(candidate.get(key) or "") for key in ("topic", "question", "angle")).lower()
        human_reality = str(candidate.get("human_reality") or "").lower()
        reason = ""
        if product_id and product_id in excluded_product_ids:
            reason = "duplicate_product_within_window"
        elif any(concept in text for concept in excluded_concepts):
            reason = "blocked_semantic_concept"
        elif human_reality and human_reality in blocked_human_realities:
            reason = "blocked_human_reality"
        if reason:
            considered.append({"rank": str(rank), "result": "skipped", "reason": reason})
            continue
        considered.append({"rank": str(rank), "result": "selected", "reason": "highest_ranked_viable"})
        return candidate, considered
    return None, considered