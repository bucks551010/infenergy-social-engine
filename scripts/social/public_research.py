"""Bounded, provenance-preserving public evidence retrieval for routed questions."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from . import research_router


def collect(*, task: research_router.ResearchTask, urls: list[str]) -> list[dict[str, Any]]:
    """Fetch only approved task URLs; callers provide candidates, never a bulk crawl."""
    evidence: list[dict[str, Any]] = []
    for url in urls[:5]:
        page = research_router.inspect_first_party(url)
        text = page.get("marketing_language", []) + page.get("factual_candidates", [])
        if not text:
            continue
        evidence.append({"type": task.preferred_source.upper(), "provenance": url, "content_hash": page["content_hash"], "confidence": 0.55, "extract": text[:12], "decision_affected": task.decision_affected})
    return evidence


def fingerprint(evidence: list[dict[str, Any]]) -> str:
    return sha256(repr(evidence).encode()).hexdigest()