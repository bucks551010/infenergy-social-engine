"""Bounded, provenance-preserving public evidence retrieval for routed questions."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from . import research_router


def discover(*, task: research_router.ResearchTask, known_sources: list[str] | None = None) -> list[dict[str, Any]]:
    """Rank a tiny deterministic source set from task intent; never crawl the web."""
    known_sources = known_sources or []
    source_domains = {
        "infenergy_first_party_website": ["https://infenergypower.com"],
        "official_manufacturer_source": [],
        "competitor_source": [],
        "customer_language_research": [],
    }
    urls = source_domains.get(task.preferred_source, []) + known_sources
    seen: set[str] = set()
    return [{"url": url, "authority": 0.9 if "infenergypower.com" in url else 0.6,
             "cached": False, "why": task.preferred_source} for url in urls if url and not (url in seen or seen.add(url))][:5]


def research(*, task: research_router.ResearchTask, known_sources: list[str] | None = None) -> list[dict[str, Any]]:
    """Question-to-evidence entry point that does not require a final URL."""
    discovered = discover(task=task, known_sources=known_sources)
    return collect(task=task, urls=[item["url"] for item in discovered])


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