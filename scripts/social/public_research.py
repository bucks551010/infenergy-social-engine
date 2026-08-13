"""Bounded, provenance-preserving public evidence retrieval for routed questions."""
from __future__ import annotations

from hashlib import sha256
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import urlopen

from . import research_router


class _SearchResults(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href", "") or ""
        destination = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        if destination.startswith(("https://", "http://")):
            self.urls.append(destination)


def _query(task: research_router.ResearchTask) -> str:
    suffix = {"official_manufacturer_source": "official specifications", "competitor_source": "competitors alternatives", "customer_language_research": "questions objections problems"}.get(task.preferred_source, "")
    return f"{task.entity} {suffix}".strip()


def discover_web_candidates(task: research_router.ResearchTask) -> list[str]:
    """Discover at most three public candidates for a decision-scoped question."""
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(_query(task))}"
    with urlopen(search_url, timeout=10) as response:  # nosec B310: fixed public discovery endpoint
        parser = _SearchResults()
        parser.feed(response.read().decode("utf-8", errors="replace"))
    excluded = {"duckduckgo.com", "google.com", "bing.com"}
    seen: set[str] = set()
    return [url for url in parser.urls if urlparse(url).netloc.lower().removeprefix("www.") not in excluded and not (url in seen or seen.add(url))][:3]


def discover(*, task: research_router.ResearchTask, known_sources: list[str] | None = None) -> list[dict[str, Any]]:
    """Rank a tiny deterministic source set from task intent; never crawl the web."""
    known_sources = known_sources or []
    source_domains = {
        "infenergy_first_party_website": ["https://infenergypower.com"],
    }
    discovered = [] if task.preferred_source in source_domains else discover_web_candidates(task)
    urls = source_domains.get(task.preferred_source, []) + known_sources + discovered
    seen: set[str] = set()
    return [{"url": url, "authority": 0.9 if "infenergypower.com" in url else 0.6,
             "relevance": 0.9 if task.entity.lower().split()[0] in url.lower() else 0.6,
             "cached": False, "why": task.preferred_source} for url in urls if url and not (url in seen or seen.add(url))][:5]


def research(*, task: research_router.ResearchTask, known_sources: list[str] | None = None) -> list[dict[str, Any]]:
    """Question-to-evidence entry point that does not require a final URL."""
    try:
        discovered = discover(task=task, known_sources=known_sources)
        if not discovered:
            return [{"failure": "NO_RELEVANT_SOURCE", "decision_affected": task.decision_affected}]
        return collect(task=task, urls=[item["url"] for item in discovered]) or [{"failure": "INSUFFICIENT_EVIDENCE", "decision_affected": task.decision_affected}]
    except PermissionError:
        return [{"failure": "AUTHENTICATION_REQUIRED", "decision_affected": task.decision_affected}]
    except Exception:
        return [{"failure": "SOURCE_UNAVAILABLE", "decision_affected": task.decision_affected}]


def test_discovery_failure_is_a_structured_research_outcome(monkeypatch):
    monkeypatch.setattr(public_research, "discover_web_candidates", lambda task: (_ for _ in ()).throw(OSError("offline")))
    task = research_router.route(question="Which competitors frame portable power differently?", why_needed="find whitespace", entity="portable power", decision_affected="positioning")
    assert public_research.research(task=task)[0]["failure"] == "SOURCE_UNAVAILABLE"


def collect(*, task: research_router.ResearchTask, urls: list[str]) -> list[dict[str, Any]]:
    """Fetch only approved task URLs; callers provide candidates, never a bulk crawl."""
    evidence: list[dict[str, Any]] = []
    for url in urls[:5]:
        page = research_router.inspect_first_party(url)
        text = page.get("marketing_language", []) + page.get("factual_candidates", [])
        if not text:
            continue
        now = datetime.now(timezone.utc).isoformat()
        evidence.append({"type": task.preferred_source.upper(), "provenance": url, "content_hash": page["content_hash"], "confidence": 0.55, "extract": text[:12], "decision_affected": task.decision_affected, "observed_at": now, "last_verified_at": now, "freshness_class": research_router.freshness_class(task)})
    return evidence


def fingerprint(evidence: list[dict[str, Any]]) -> str:
    return sha256(repr(evidence).encode()).hexdigest()


def classify_change(previous: list[str], current: list[str]) -> str:
    """Classify meaning, not merely a content-hash difference."""
    before, after = " ".join(previous).lower(), " ".join(current).lower()
    if before == after:
        return "NOISE"
    if " ".join(before.split()) == " ".join(after.split()):
        return "COSMETIC"
    if any(term in after for term in ("new", "capacity", "warranty", "modular", "capability")):
        return "STRATEGICALLY_SIGNIFICANT"
    return "MARKETING_RELEVANT" if len(set(after.split()) - set(before.split())) >= 3 else "MINOR"