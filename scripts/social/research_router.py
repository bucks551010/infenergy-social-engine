"""Decision-scoped research routing and lean first-party change detection."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from typing import Any
from urllib.request import urlopen


@dataclass(frozen=True)
class ResearchTask:
    question: str
    why_needed: str
    entity: str
    decision_affected: str
    preferred_source: str
    freshness_requirement: str
    result: str = ""
    sources: tuple[str, ...] = ()
    confidence: float = 0.0
    how_result_changes_strategy: str = ""

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__ | {"sources": list(self.sources)}


def route(*, question: str, why_needed: str, entity: str, decision_affected: str, freshness_requirement: str = "current") -> ResearchTask:
    """Route only questions that can change a named marketing decision."""
    if not all((question.strip(), why_needed.strip(), entity.strip(), decision_affected.strip())):
        raise ValueError("research requires a question, reason, entity, and affected decision")
    text = f"{question} {entity}".lower()
    source = "existing_internal_intelligence"
    if any(term in text for term in ("question", "objection", "language", "misconception")):
        source = "customer_language_research"
    elif any(term in text for term in ("competitor", "alternative", "market")):
        source = "competitor_source"
    elif any(term in text for term in ("spec", "warranty", "manufacturer", "capacity")):
        source = "official_manufacturer_source"
    elif any(term in text for term in ("site", "product page", "cta", "brand")):
        source = "infenergy_first_party_website"
    return ResearchTask(question, why_needed, entity, decision_affected, source, freshness_requirement)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if clean:
            self.parts.append(clean)


def inspect_first_party(url: str, previous_hash: str = "") -> dict[str, Any]:
    """Extract only decision-useful public facts and positioning language."""
    with urlopen(url, timeout=20) as response:  # nosec B310: caller owns allowed first-party URL
        html = response.read().decode("utf-8", errors="replace")
    parser = _Text()
    parser.feed(html)
    text = " ".join(parser.parts)
    digest = sha256(text.encode("utf-8")).hexdigest()
    phrases = [part for part in parser.parts if len(part) > 20][:80]
    return {
        "url": url,
        "content_hash": digest,
        "changed": bool(previous_hash and previous_hash != digest),
        "factual_candidates": [p for p in phrases if any(c.isdigit() for c in p)][:12],
        "marketing_language": [p for p in phrases if not any(c.isdigit() for c in p)][:20],
        "decision_use": "claim verification, brand positioning, or opportunity discovery",
    }