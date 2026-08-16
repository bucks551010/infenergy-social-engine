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


def opportunity_fingerprint(candidate: dict[str, Any]) -> dict[str, str]:
    """Keep the strategic identity of a blocked attempt separate from its copy."""
    return {
        "product_id": str(candidate.get("product_id") or ""),
        "question": str(candidate.get("question") or ""),
        "angle": str(candidate.get("angle") or ""),
        "human_reality": str(candidate.get("human_reality") or ""),
        "decision_thesis": str(candidate.get("decision_thesis") or ""),
        "reader_job": str(candidate.get("reader_job") or ""),
        "product_role": str(candidate.get("product_role") or ""),
        "evidence_dependency": str(candidate.get("evidence_dependency") or ""),
    }


def _fingerprint_tokens(candidate: dict[str, Any]) -> set[str]:
    aliases = {"compatible": "fit", "compatibility": "fit", "device": "fit", "capacity": "reserve", "battery": "reserve", "travel": "trip", "outlets": "outlet"}
    ignored = {"before", "after", "which", "their", "this", "that", "with", "from", "your", "published"}
    words = " ".join(str(value or "").lower() for value in opportunity_fingerprint(candidate).values()).split()
    return {aliases.get(word.strip(".,;:?!"), word.strip(".,;:?!")) for word in words if len(word.strip(".,;:?!")) > 3 and word.strip(".,;:?!") not in ignored}


def select_replacement(
    shortlist: list[dict[str, Any]],
    *,
    excluded_product_ids: set[str] | None = None,
    excluded_concepts: set[str] | None = None,
    blocked_human_realities: set[str] | None = None,
    blocked_fingerprint: dict[str, Any] | None = None,
    max_claim_burden_level: int | None = None,
    required_content_mode_change: bool = False,
    blocked_content_mode: str = "",
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Choose Candidate B in rank order, recording compact skip evidence."""
    excluded_product_ids = {str(value) for value in excluded_product_ids or set()}
    excluded_concepts = {str(value).lower() for value in excluded_concepts or set() if value}
    blocked_human_realities = {str(value).lower() for value in blocked_human_realities or set() if value}
    blocked_tokens = _fingerprint_tokens(blocked_fingerprint or {})
    considered: list[dict[str, str]] = []
    for candidate in sorted(shortlist, key=lambda item: int(item.get("rank", 0))):
        rank = int(candidate.get("rank", 0))
        if rank <= 1:
            continue
        product_id = str(candidate.get("product_id") or "")
        text = " ".join(str(candidate.get(key) or "") for key in ("topic", "question", "angle")).lower()
        human_reality = str(candidate.get("human_reality") or "").lower()
        candidate_tokens = _fingerprint_tokens(candidate)
        claim_burden_level = int(candidate.get("claim_burden_level", 0) or 0)
        content_mode = str(candidate.get("content_mode") or "").upper()
        reason = ""
        if product_id and product_id in excluded_product_ids:
            reason = "duplicate_product_within_window"
        elif max_claim_burden_level is not None and claim_burden_level > max_claim_burden_level:
            reason = "claim_burden_too_high"
        elif required_content_mode_change and blocked_content_mode and content_mode == blocked_content_mode:
            reason = "blocked_content_mode"
        elif any(concept in text for concept in excluded_concepts):
            reason = "blocked_semantic_concept"
        elif human_reality and human_reality in blocked_human_realities:
            reason = "blocked_human_reality"
        elif blocked_tokens and len(blocked_tokens & candidate_tokens) / max(1, min(len(blocked_tokens), len(candidate_tokens))) >= 0.35:
            reason = "blocked_opportunity_fingerprint"
        if reason:
            considered.append({"rank": str(rank), "result": "skipped", "reason": reason})
            continue
        considered.append({"rank": str(rank), "result": "selected", "reason": "highest_ranked_viable"})
        return candidate, considered
    return None, considered


def verified_fact_opportunities(
    *,
    product_id: str,
    product_name: str,
    verified_facts: list[str],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Build a small no-model field whose thesis is limited to owned facts."""
    opportunities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fact in verified_facts:
        normalized = " ".join(str(fact or "").split())
        key = normalized.lower()
        if len(normalized) < 8 or key in seen:
            continue
        seen.add(key)
        rank = len(opportunities) + 1
        opportunities.append({
            "rank": rank,
            "candidate_id": f"verified-fact:{product_id}:{rank}",
            "product_id": product_id,
            "product_name": product_name,
            "verified_fact": normalized,
            "question": f"Which published detail matters when comparing {product_name}?",
            "angle": f"{product_name} lists {normalized}. Keep that published detail visible when reviewing the product.",
            "human_reality": "comparing published product details",
            "reader_job": "SAVE_ME_TIME",
            "decision_thesis": f"Published product detail: {normalized}",
            "content_mode": "VERIFIED_FACT_PRODUCT_EDUCATION",
            "claim_burden_level": 0,
            "opportunity_score": round(0.92 - ((rank - 1) * 0.03), 2),
        })
        if len(opportunities) >= limit:
            break
    return opportunities