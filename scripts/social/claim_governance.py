"""Evidence readiness for material claims at the final publication boundary."""

from __future__ import annotations

import re
from typing import Any

from . import claim_intelligence


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z]{4,}", str(text or "").lower())}


def _overlaps(claim_text: str, dependency_text: str) -> bool:
    claim_tokens = _tokens(claim_text)
    dependency_tokens = _tokens(dependency_text)
    return len(claim_tokens & dependency_tokens) >= 2


_CONCEPT_TERMS = {
    "capability": {"available", "output", "power", "wattage", "source", "support"},
    "reserve": {"capacity", "reserve", "stored", "energy", "endurance", "runtime"},
    "fit": {"fit", "compatibility", "compatible", "feasibility", "requirement", "require"},
    "dependency": {"determines", "determine", "establishes", "established", "before", "after", "only", "whether"},
    "workflow": {"workflow", "execution", "throughput", "cleanup", "exception", "review"},
    "resolution": {"response", "acknowledge", "resolution", "resolved", "outcome", "closed"},
}


def _concepts(text: str) -> set[str]:
    tokens = _tokens(text)
    return {
        concept
        for concept, terms in _CONCEPT_TERMS.items()
        if tokens & terms
    }


def _semantically_supports_dependency(claim_text: str, dependency_text: str) -> bool:
    claim_concepts = _concepts(claim_text)
    dependency_concepts = _concepts(dependency_text)
    shared = claim_concepts & dependency_concepts
    return "dependency" in shared and bool(shared - {"dependency"})


def _centrality(claim: claim_intelligence.Claim, *, hook: str, decision_insight: dict[str, Any], takeaway: str) -> str:
    if claim.risk == claim_intelligence.HIGH_RISK:
        return "CENTRAL"
    if set(claim.source_concept_ids) & {
        "decision_relationship", "decision_consequence", "hook_payoff",
        "core_answer", "primary_product_argument", "takeaway",
        "memory_anchor", "cta_justification",
    }:
        return "CENTRAL"
    dependencies = " ".join(
        str(decision_insight.get(key) or "")
        for key in ("relationship", "why_relationship_matters", "decision_consequence", "practical_check")
    )
    if _semantically_supports_dependency(claim.claim_text, dependencies):
        return "CENTRAL"
    return "INCIDENTAL"


def assess(
    ledger: claim_intelligence.ClaimLedger,
    *,
    hook: str,
    decision_insight: dict[str, Any] | None = None,
    takeaway: str = "",
) -> dict[str, Any]:
    """Return compact evidence readiness; high-risk policy remains independently fail-closed."""
    insight = decision_insight if isinstance(decision_insight, dict) else {}
    needs: list[dict[str, Any]] = []
    audited: list[dict[str, Any]] = []
    for claim in ledger.claims:
        centrality = _centrality(claim, hook=hook, decision_insight=insight, takeaway=takeaway)
        research_required = claim.provenance == "UNVERIFIED_INFERENCE" and claim.risk == claim_intelligence.MEDIUM_RISK
        record = {
            "claim": claim.claim_text,
            "risk": claim.risk,
            "claim_type": claim.claim_type,
            "centrality": centrality,
            "research_status": "RESEARCH_REQUIRED" if research_required else claim.verification_status.upper(),
            "evidence_available": claim.provenance,
        }
        audited.append(record)
        if centrality == "CENTRAL" and research_required:
            needs.append({
                **record,
                "research_question": f"What reliable evidence substantiates: {claim.claim_text}",
                "claim_to_verify": claim.claim_text,
                "why_needed": "The claim carries the post's core decision method or payoff.",
                "acceptable_source_type": "manufacturer technical documentation or authoritative independent technical guidance",
                "decision_if_unverified": "revise_or_research_required",
            })
    if ledger.unverified_high_risk:
        return {"ready": False, "status": "HIGH_RISK_UNVERIFIED", "claims": audited, "research_needs": needs}
    if needs:
        return {"ready": False, "status": "RESEARCH_REQUIRED", "claims": audited, "research_needs": needs}
    return {"ready": True, "status": "READY", "claims": audited, "research_needs": []}