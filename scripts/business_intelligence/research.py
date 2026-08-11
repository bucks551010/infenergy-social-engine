"""Research policy + knowledge gaps + hypothesis registry.

Master Build §35-§38.

The current default is ``research_enabled=false`` — the system does not
wander the internet. Knowledge gaps are still tracked so a human (or a
future authorized adapter) can resolve them.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from typing import Any, Iterable

from . import paths
from .schemas import Hypothesis, KnowledgeGap, ResearchPolicy


# --- Policy persistence ------------------------------------------------


def policy_path() -> str:
    return os.path.join(paths.research_dir(), "research_policy.json")


def gaps_path() -> str:
    return os.path.join(paths.research_dir(), "knowledge_gaps.json")


def hypotheses_path() -> str:
    return os.path.join(paths.research_dir(), "hypotheses.json")


DEFAULT_POLICY = ResearchPolicy(
    research_enabled=False,
    allowed_source_types=["technical_datasheet", "manufacturer_spec"],
    preferred_sources=["manufacturer_docs"],
    blocked_sources=["random blogs", "affiliate roundups", "user-generated forums"],
    freshness_requirements={"seasonal": 7, "market": 30, "technical": 180},
    max_research_depth=1,
    high_risk_verification_required=True,
    competitor_research_enabled=False,
    current_event_research_enabled=False,
    technical_research_enabled=True,
    research_cache_ttl_days=14,
)


def load_policy() -> ResearchPolicy:
    p = policy_path()
    if not os.path.isfile(p):
        return DEFAULT_POLICY
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return ResearchPolicy(**data)
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULT_POLICY


def save_policy(policy: ResearchPolicy) -> None:
    with open(policy_path(), "w", encoding="utf-8") as fh:
        json.dump(asdict(policy), fh, indent=2)


# --- Knowledge gaps ----------------------------------------------------


def load_gaps() -> list[KnowledgeGap]:
    p = gaps_path()
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [KnowledgeGap(**g) for g in data.get("gaps", [])]
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_gaps(gaps: Iterable[KnowledgeGap]) -> None:
    with open(gaps_path(), "w", encoding="utf-8") as fh:
        json.dump({"gaps": [asdict(g) for g in gaps]}, fh, indent=2)


def register_gap(
    *,
    domain: str,
    question: str,
    importance: str = "medium",
    reason_needed: str = "",
    downstream_impact: str = "",
    researchable: bool = False,
    owner_input_required: bool = False,
    priority: int = 5,
) -> KnowledgeGap:
    gap = KnowledgeGap(
        gap_id=uuid.uuid4().hex[:12],
        domain=domain,
        question=question,
        importance=importance,
        reason_needed=reason_needed,
        downstream_impact=downstream_impact,
        researchable=researchable,
        owner_input_required=owner_input_required,
        priority=priority,
        status="OPEN",
    )
    existing = load_gaps()
    existing.append(gap)
    save_gaps(existing)
    return gap


def default_infenergy_gaps() -> list[KnowledgeGap]:
    """Seed the standard open questions the profile can't answer from
    current sources alone (§36)."""
    return [
        KnowledgeGap(
            gap_id="gap-target-reputation",
            domain="reputation",
            question="What single sentence do we want a customer to tell another person about Infenergy?",
            importance="high",
            researchable=False,
            owner_input_required=True,
            priority=1,
            status="OPEN",
        ),
        KnowledgeGap(
            gap_id="gap-prohibited-topics",
            domain="content_policy",
            question="Are there topics we explicitly forbid on our social feed (politics, specific weather scare tactics, etc.)?",
            importance="high",
            owner_input_required=True,
            priority=2,
        ),
        KnowledgeGap(
            gap_id="gap-geo-priority",
            domain="market",
            question="Are we prioritizing specific US regions for outage/preparedness messaging?",
            importance="medium",
            owner_input_required=True,
            priority=4,
        ),
        KnowledgeGap(
            gap_id="gap-cert-verification",
            domain="product_specification",
            question="Which specific certifications (UL, FCC, DOE) are actually held per product family?",
            importance="high",
            researchable=True,
            priority=3,
        ),
    ]


def seed_default_gaps() -> None:
    if load_gaps():
        return
    save_gaps(default_infenergy_gaps())


# --- Hypotheses --------------------------------------------------------


def load_hypotheses() -> list[Hypothesis]:
    p = hypotheses_path()
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [Hypothesis(**h) for h in data.get("hypotheses", [])]
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_hypotheses(hyps: Iterable[Hypothesis]) -> None:
    with open(hypotheses_path(), "w", encoding="utf-8") as fh:
        json.dump({"hypotheses": [asdict(h) for h in hyps]}, fh, indent=2)


def register_hypothesis(statement: str, *, domain: str, confidence: float = 0.3) -> Hypothesis:
    h = Hypothesis(
        hypothesis_id=uuid.uuid4().hex[:12],
        statement=statement,
        domain=domain,
        confidence=confidence,
        status="UNTESTED",
    )
    existing = load_hypotheses()
    existing.append(h)
    save_hypotheses(existing)
    return h


def default_infenergy_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(
            hypothesis_id="hyp-preparedness-position",
            statement="Preparedness-first positioning (not survivalist, not commodity) is the strongest differentiator for Infenergy.",
            domain="positioning",
            confidence=0.7,
            supporting_evidence=["founder_manifesto.mission", "catalog category mix"],
            status="WEAK_SIGNAL",
        ),
        Hypothesis(
            hypothesis_id="hyp-audience-parents",
            statement="Working parents in storm-prone regions are the highest-value segment.",
            domain="audience",
            confidence=0.55,
            supporting_evidence=["founder_manifesto.audience_segments"],
            status="UNTESTED",
        ),
        Hypothesis(
            hypothesis_id="hyp-education-first",
            statement="Education-first social content builds trust faster than product-push content in this category.",
            domain="content_strategy",
            confidence=0.6,
            supporting_evidence=["founder_manifesto.tone_rules"],
            status="UNTESTED",
        ),
    ]


def seed_default_hypotheses() -> None:
    if load_hypotheses():
        return
    save_hypotheses(default_infenergy_hypotheses())
