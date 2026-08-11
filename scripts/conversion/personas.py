"""Persona lookup — Spec Section 6."""

from __future__ import annotations

from typing import Any

from .libraries import personas


def all_persona_ids() -> list[str]:
    return list(personas().keys())


def get(persona_id: str) -> dict[str, Any]:
    lib = personas()
    return lib.get(persona_id, lib["preparedness_buyer"])


def infer_from_product_and_stage(
    product_type: str | None,
    funnel_stage: str,
    fallback: str = "preparedness_buyer",
) -> str:
    """Heuristic mapping until product intelligence exposes a persona directly."""
    product_type = (product_type or "").lower()
    if product_type in ("small_business_operator", "power_system_bundle", "power_system_component"):
        return "small_business_operator"
    if product_type in ("electric_bike",):
        return "outdoor_enthusiast"
    if product_type in ("portable_water_filter", "solar_light", "portable_fan"):
        return "outdoor_enthusiast"
    if product_type in ("vehicle_jump_starter", "power_bank"):
        return "mobile_professional"
    if product_type in ("expansion_battery", "power_station", "preparedness_product"):
        return "preparedness_buyer"
    return fallback


def audience_keywords(persona_id: str) -> list[str]:
    p = get(persona_id)
    kws = []
    for key in ("primary_problem", "secondary_problem", "desired_outcome", "context"):
        v = p.get(key, "")
        for word in v.replace(",", " ").split():
            w = word.strip().lower()
            if len(w) >= 4:
                kws.append(w)
    return list(dict.fromkeys(kws))[:12]
