"""Lean social-marketing context derived from existing product and audience data.

This module deliberately compiles a small, task-specific object instead of
adding another exhaustive product database. It establishes the relationship
chain required before content generation:

offering -> compatible audience -> customer moment -> human value -> pillar.
"""

from __future__ import annotations

from typing import Any

from . import libraries


_CATEGORY_PILLARS = {
    "electric bike": "electric_mobility",
    "electric bikes": "electric_mobility",
    "e-bike": "electric_mobility",
    "ebike": "electric_mobility",
    "portable power": "portable_power",
    "emergency power": "portable_power",
    "power bank": "portable_power",
    "travel power": "portable_power",
    "phone power banks": "portable_power",
    "solar": "solar",
}

_AUDIENCE_ALIASES = {
    "commuter": "mobile_professional",
    "commuters": "mobile_professional",
    "traveler": "mobile_professional",
    "travelers": "mobile_professional",
    "mobile-device user": "mobile_professional",
    "mobile-device users": "mobile_professional",
    "mobile professional": "mobile_professional",
    "outdoor enthusiast": "outdoor_enthusiast",
    "outdoor enthusiasts": "outdoor_enthusiast",
    "household": "preparedness_focused_household",
    "households": "preparedness_focused_household",
    "small business": "small_business_operator",
}


def _text(values: Any) -> str:
    if isinstance(values, list):
        return " ".join(str(value) for value in values)
    return str(values or "")


def pillar_for_offering(offering: dict[str, Any] | None) -> str:
    """Choose the narrowest available social pillar from category/type text."""
    source = " ".join(
        (
            _text((offering or {}).get("category")),
            _text((offering or {}).get("categories")),
            _text((offering or {}).get("product_type")),
        )
    ).lower()
    for token, pillar in _CATEGORY_PILLARS.items():
        if token in source and pillar in libraries.pillars():
            return pillar
    return ""


def audience_for_offering(offering: dict[str, Any] | None, pillar_id: str = "") -> str:
    """Resolve a social audience only from explicit offering fit, then pillar."""
    segments = libraries.audience_segments()
    fits = (offering or {}).get("customer_fit") or (offering or {}).get("best_fit_audiences") or []
    for raw in fits:
        normalized = _AUDIENCE_ALIASES.get(str(raw).strip().lower())
        if normalized in segments:
            return normalized
    pillar_defaults = {
        "portable_power": "mobile_professional",
        "electric_mobility": "mobile_professional",
        "preparedness": "preparedness_focused_household",
    }
    return pillar_defaults.get(pillar_id, "")


def compile_product_social_intelligence(offering: dict[str, Any] | None) -> dict[str, Any]:
    """Return the compact Tier-A context needed for normal social decisions.

    Unknown operational/compliance fields are named as research-on-demand gaps,
    not treated as generation blockers.
    """
    offering = offering or {}
    pillar_id = pillar_for_offering(offering)
    audience_id = audience_for_offering(offering, pillar_id)
    segments = libraries.audience_segments()
    audience = segments.get(audience_id, {})
    use_cases = list(offering.get("use_cases") or offering.get("best_fit_use_cases") or [])
    benefits = list(offering.get("functional_benefits") or offering.get("core_benefits") or [])
    problems = list(offering.get("problems_addressed") or [])
    primary_problem = problems[0] if problems else ""
    moments = list(audience.get("purchase_context") or audience.get("lifestyle_context") or [])
    human_values = list(audience.get("emotional_drivers") or [])
    questions = list(audience.get("questions") or [])
    unknowns: list[str] = []
    if not offering.get("product_url"):
        unknowns.append("canonical_product_url")
    if not offering.get("verified_facts"):
        unknowns.append("approved_product_facts")
    if not offering.get("images"):
        unknowns.append("primary_visual_asset")

    return {
        "identity": {
            "product_id": offering.get("offering_id") or offering.get("sku") or "",
            "sku": offering.get("sku") or "",
            "product_name": offering.get("name") or "",
            "canonical_product_type": offering.get("product_type") or offering.get("category") or "",
            "category": offering.get("category") or "",
            "product_url": offering.get("product_url") or "",
            "availability": offering.get("stock_status") or "",
            "price_for_accuracy_only": offering.get("price"),
            "primary_assets": list(offering.get("images") or [])[:3],
        },
        "understanding": {
            "plain_english_description": offering.get("description_clean") or offering.get("product_summary") or "",
            "important_capabilities": list(offering.get("verified_facts") or [])[:5],
            "important_features": list(offering.get("features") or [])[:5],
            "primary_use_cases": use_cases[:3],
            "secondary_use_cases": use_cases[3:6],
        },
        "human_value": {
            "primary_audience": audience_id,
            "customer_moments": moments[:3],
            "problems": problems[:3],
            "desires": list(audience.get("goals") or [])[:3],
            "benefits": benefits[:3],
            "human_meaning": human_values[:3],
        },
        "marketing": {
            "customer_questions": questions[:4],
            "misconceptions": list(audience.get("misconceptions") or [])[:3],
            "objections": list(audience.get("objections") or [])[:3],
            "approved_marketing_claims": list(offering.get("verified_facts") or [])[:5],
            "content_opportunities": list(offering.get("content_opportunities") or [])[:5],
            "visual_opportunities": list(offering.get("images") or [])[:2],
            "cta": offering.get("recommended_cta") or "Learn more",
        },
        "relationships": {
            "pillar_id": pillar_id,
            "audience_id": audience_id,
            "customer_moment": moments[0] if moments else "",
            "human_value": human_values[0] if human_values else "",
            "primary_problem": primary_problem,
        },
        "truth": {
            "forbidden_claims": list(offering.get("forbidden_claims") or []),
            "sources": list(offering.get("evidence_refs") or []),
            "important_unknowns": unknowns,
        },
    }


def research_needed(context: dict[str, Any], *, decision: str, required_fact: str = "") -> dict[str, Any]:
    """Create a research-on-demand task only when a decision truly needs it."""
    unknowns = set((context.get("truth") or {}).get("important_unknowns") or [])
    needed = bool(required_fact and required_fact in unknowns)
    return {
        "needed": needed,
        "decision": decision,
        "required_fact": required_fact,
        "why": "required by this decision" if needed else "current core context is sufficient",
        "source_order": ["business_website", "official_manufacturer", "approved_owner_input"],
    }