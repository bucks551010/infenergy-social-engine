"""Resolve the role-aware visual requirements for social publication."""

from __future__ import annotations

from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def requirements(content: dict[str, Any], visual_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return presentation requirements from strategy before catalog fallbacks."""
    copy = _mapping(content.get("copy"))
    strategy = _mapping(content.get("strategy_lock")) or _mapping(copy.get("strategy_lock"))
    offering = _mapping(content.get("anchored_offering"))
    brief = _mapping(content.get("strategic_brief"))
    shortlist = brief.get("opportunity_shortlist") if isinstance(brief.get("opportunity_shortlist"), list) else []
    winner = _mapping(shortlist[0]) if shortlist else {}
    plan = _mapping(visual_plan) or _mapping(content.get("visual_plan"))

    relevance = _first_text(
        strategy.get("product_relevance"),
        offering.get("product_relevance"),
        content.get("product_relevance"),
        winner.get("product_relevance"),
    ).upper()
    raw_role = _first_text(
        strategy.get("product_role"),
        offering.get("product_role"),
        content.get("product_role"),
        winner.get("product_role"),
    ).upper()
    aliases = {"DECISION_SUPPORT": "SUPPORTING", "SUPPORTING_PROOF": "SUPPORTING"}
    role = aliases.get(raw_role, raw_role)
    positioning = str(strategy.get("positioning") or "").strip().lower()
    if relevance == "NOT_RELEVANT" or "product-free" in positioning:
        relevance = "NOT_RELEVANT"
        role = "NONE"
    elif not role:
        attached_product = _first_text(
            content.get("product_id"),
            offering.get("offering_id"),
            offering.get("sku"),
        )
        role = "PRIMARY" if attached_product else "NONE"

    overlay_requested = any(
        value is True
        for value in (
            plan.get("product_overlay_required"),
            strategy.get("product_overlay_required"),
            _mapping(plan.get("presentation_contract")).get("product_overlay_required"),
        )
    )
    product_presence_required = role in {"PRIMARY", "FIT_DEMONSTRATION"}
    return {
        "product_relevance": relevance or ("RELEVANT" if role != "NONE" else "NOT_RELEVANT"),
        "product_role": role,
        "visual_required": True,
        "ai_visual_required": True,
        "product_presence_required": product_presence_required,
        "product_reference_required": product_presence_required,
        "product_fidelity_applicable": role != "NONE",
        "product_overlay_required": role != "NONE" and overlay_requested,
    }