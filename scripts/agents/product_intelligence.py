"""Build reusable, product-specific intelligence dossiers for the creative team."""

from __future__ import annotations

import os
import re
from typing import Any

from ._base import utc_now, write_json, write_snapshot


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _product_type(product: dict) -> str:
    name = str(product.get("name", "") or "").lower()
    categories = " ".join(_clean_list(product.get("categories"))).lower()
    facts = re.sub(r"<[^>]+>", " ", str(product.get("fact_snippet", "") or "")).lower()
    power_station_evidence = any(token in name for token in ("power station", "generator", "inverter")) or any(
        token in categories for token in ("power station", "generator")
    ) or any(token in facts for token in ("home backup powerhouse", "solar generator", "pure sine wave inverter"))

    if "filter" in name or "straw" in name or "water filtration" in categories:
        return "portable_water_filter"
    if "jump starter" in name:
        return "vehicle_jump_starter"
    if "fan" in name:
        return "portable_fan"
    if power_station_evidence:
        return "power_station"
    if "solar" in name or "panel" in name or (("solar" in categories or "panel" in categories) and not power_station_evidence):
        return "solar_panel"
    if any(token in name for token in ("power bank", "powerbank", "charger")):
        return "power_bank"
    return "preparedness_product"


_TYPE_GUIDANCE = {
    "portable_water_filter": {
        "role": "portable water filtration backup",
        "benefits": ["adds clean-water support to emergency and travel kits", "keeps water preparedness compact and portable"],
        "use_cases": ["emergency water kit", "camping and hiking", "vehicle preparedness", "travel backup"],
        "audiences": ["prepared households", "campers and hikers", "travelers building a water-backup plan"],
        "pain_point": "Preparedness kits fail when safe-water backup is treated as an afterthought.",
        "proof_rule": "Use only published filtration, capacity, material, and compatibility details.",
        "cta": "Review the filtration details and add it to the water-backup plan that fits your kit.",
        "hashtags": ["WaterPreparedness", "EmergencyKit", "WaterFiltration", "OutdoorSafety", "Preparedness"],
        "visual": "Show the real filter in a credible clean-water, trail, travel, or emergency-kit use case.",
    },
    "vehicle_jump_starter": {
        "role": "vehicle emergency jump starter",
        "benefits": ["supports roadside readiness", "provides vehicle-start support when a battery fails"],
        "use_cases": ["roadside emergency kit", "daily vehicle carry", "road trips", "garage preparedness"],
        "audiences": ["drivers", "road-trip travelers", "households building vehicle emergency kits"],
        "pain_point": "Roadside emergencies become expensive when the tool in the trunk cannot handle the vehicle.",
        "proof_rule": "Use only published starting-current, battery, compressor, port, and compatibility details.",
        "cta": "Compare the published starting and compatibility details with your vehicle before buying.",
        "hashtags": ["RoadsideReady", "CarEmergencyKit", "JumpStarter", "VehiclePreparedness"],
        "visual": "Show the real jump starter beside a vehicle in a credible roadside or garage scenario.",
    },
    "portable_fan": {
        "role": "portable airflow and charging support",
        "benefits": ["adds portable airflow for outages, camping, and travel", "supports lighting or small-device charging when published features allow"],
        "use_cases": ["camping", "outage comfort", "vehicle and travel kit", "outdoor work"],
        "audiences": ["campers", "families preparing for warm-weather outages", "travelers needing portable airflow"],
        "pain_point": "Heat and still air become a real problem when an outage or campsite has no dependable airflow.",
        "proof_rule": "Use only published runtime, battery, airflow, lighting, and charging details.",
        "cta": "Review the runtime and airflow details against where you plan to use it.",
        "hashtags": ["PortableFan", "CampingGear", "OutageReady", "EmergencyPreparedness"],
        "visual": "Show the real fan providing airflow in a campsite, room, vehicle, or outage setting.",
    },
    "power_station": {
        "role": "backup power station",
        "benefits": ["supports priority devices during outages and off-grid use", "combines portable stored energy with published output options"],
        "use_cases": ["home outage backup", "RV and camping", "mobile work", "emergency preparedness"],
        "audiences": ["households planning outage loads", "RV and camping users", "mobile professionals"],
        "pain_point": "Backup power choices fail when output, runtime, and charging limits are not matched to actual loads.",
        "proof_rule": "Use only published capacity, output, runtime, battery chemistry, port, and charging details.",
        "cta": "Compare the published capacity and output with the devices and runtime you need.",
        "hashtags": ["BackupPower", "PowerStation", "OutageReady", "EmergencyPreparedness"],
        "visual": "Show the real power station connected to a credible priority load in a home, RV, campsite, or mobile-work setting.",
    },
    "solar_panel": {
        "role": "portable solar charging panel",
        "benefits": ["adds off-grid charging support for compatible equipment", "extends charging options when suitable sunlight is available"],
        "use_cases": ["camping and RV charging", "off-grid travel", "compatible power-station charging", "emergency recharging"],
        "audiences": ["power-station owners", "campers and RV users", "off-grid travelers"],
        "pain_point": "A solar panel is useful only when its output and connectors match the equipment it needs to charge.",
        "proof_rule": "Use only published wattage, connector, voltage, efficiency, size, and compatibility details.",
        "cta": "Verify wattage and connector compatibility with your equipment before buying.",
        "hashtags": ["SolarPanel", "OffGridPower", "SolarCharging", "CampingPower"],
        "visual": "Show the real panel deployed in sunlight and connected only to compatible equipment supported by product data.",
    },
    "power_bank": {
        "role": "portable charging backup",
        "benefits": ["keeps compatible daily devices charged away from outlets", "adds compact charging continuity for travel and daily carry"],
        "use_cases": ["daily carry", "commuting", "travel", "small-device outage backup"],
        "audiences": ["commuters", "travelers", "mobile-device users"],
        "pain_point": "A power bank misses the job when its capacity, ports, or charging speed do not match the devices carried.",
        "proof_rule": "Use only published capacity, port, charging-speed, size, and compatibility details.",
        "cta": "Compare capacity, ports, and charging speed with the devices you carry.",
        "hashtags": ["PowerBank", "PortableCharging", "TravelPower", "StayCharged"],
        "visual": "Show the real power bank charging a compatible daily device in a credible travel or commute setting.",
    },
    "preparedness_product": {
        "role": "preparedness product",
        "benefits": ["fills a specific gap in a practical preparedness plan"],
        "use_cases": ["home preparedness", "vehicle kit", "travel kit"],
        "audiences": ["prepared households", "travelers", "outdoor users"],
        "pain_point": "Generic recommendations leave buyers with the wrong tool for the job.",
        "proof_rule": "Use only published product details and verified compatibility information.",
        "cta": "Review the published details against the job this product needs to do.",
        "hashtags": ["Preparedness", "EmergencyKit", "ReadyForAnything"],
        "visual": "Show the real product performing its documented job in a credible use case.",
    },
}


def build_product_brief(product: dict) -> dict:
    product_type = _product_type(product)
    guidance = _TYPE_GUIDANCE[product_type]
    product_id = str(product.get("id") or product.get("product_id") or product.get("sku") or "").strip()
    name = str(product.get("name", "") or "").strip()
    metrics = _clean_list(product.get("metrics"))
    facts = str(product.get("fact_snippet", "") or "").strip()
    verified_facts = metrics[:4] + ([facts] if facts else [])

    return {
        "product_id": product_id,
        "sku": str(product.get("sku", "") or "").strip(),
        "name": name,
        "product_type": product_type,
        "role": guidance["role"],
        "product_summary": f"{name} is a {guidance['role']} that {guidance['benefits'][0]}.",
        "categories": _clean_list(product.get("categories")),
        "verified_facts": verified_facts,
        "core_benefits": list(guidance["benefits"]),
        "best_fit_use_cases": list(guidance["use_cases"]),
        "best_fit_audiences": list(guidance["audiences"]),
        "primary_pain_point": guidance["pain_point"],
        "proof_rule": guidance["proof_rule"],
        "recommended_cta": guidance["cta"],
        "hashtag_themes": list(guidance["hashtags"]),
        "visual_direction": guidance["visual"],
        "forbidden_claims": [
            "Do not invent specifications, compatibility, runtime, certifications, guarantees, or included accessories.",
            "Do not describe the product as a different product type because of secondary features or broad categories.",
            "Do not use power-device language for water, comfort, safety, or other non-power primary products.",
        ],
        "source_image_url": str(product.get("image_url", "") or "").strip(),
        "updated_at_utc": utc_now(),
    }


def build_team_handoff(
    brief: dict,
    *,
    topic: str = "",
    funnel_stage: str = "EDUCATION",
    audience_segment: str = "",
    selected_hook: str = "",
    selected_cta: str = "",
) -> dict:
    stage = str(funnel_stage or "EDUCATION").strip().upper()
    stage_angle = {
        "ATTENTION": "Lead with the product-specific problem and make the cost of a poor fit concrete.",
        "EDUCATION": "Teach buyers which verified details determine fit for this product type.",
        "DESIRE": "Connect the documented use case to a practical, believable outcome.",
        "TRUST": "Reduce purchase risk with transparent facts, limits, and compatibility guidance.",
        "CONVERSION": "Make the next product-specific buying step simple and concrete.",
    }.get(stage, "Translate verified product facts into a practical next step.")
    cta = str(selected_cta or "").strip() or str(brief.get("recommended_cta", ""))
    proof_points = _clean_list(brief.get("verified_facts"))

    return {
        "agent": "product_intelligence",
        "product_brief": brief,
        "product_summary": brief.get("product_summary", ""),
        "best_fit_audiences": _clean_list(brief.get("best_fit_audiences")) + ([f"Primary audience segment: {audience_segment}"] if audience_segment else []),
        "core_benefits": _clean_list(brief.get("core_benefits")),
        "proof_points": proof_points,
        "sales_angle": stage_angle,
        "preferred_vocabulary": [brief.get("role", ""), *brief.get("best_fit_use_cases", [])],
        "emotional_outcomes": ["confidence in product fit", "clarity about the product's job", "preparedness grounded in verified facts"],
        "messaging_devices": ["one product, one primary job", "fact to use case to outcome", "state compatibility limits clearly"],
        "sales_copy_seed": " ".join(part for part in (selected_hook, brief.get("primary_pain_point", ""), brief.get("product_summary", ""), cta) if part),
        "handoff": {
            "copywriter": [
                f"Primary product type: {brief.get('product_type', '')}",
                f"Primary job: {brief.get('role', '')}",
                f"Use cases: {brief.get('best_fit_use_cases', [])}",
                f"Use only these facts: {proof_points}",
                f"CTA direction: {cta}",
            ],
            "visual_director": [brief.get("visual_direction", ""), "Use the supplied real product image; do not synthesize a replacement product."],
            "platform_editor": ["Preserve the primary product job on every platform.", f"Keep the content native to this topic: {topic}"],
            "product_truth": [brief.get("proof_rule", ""), *brief.get("forbidden_claims", [])],
        },
    }


def _load_product(data_dir: str, product_id: str) -> dict | None:
    try:
        import inventory_db  # type: ignore

        inventory_db.init_inventory_db(data_dir)
        products = inventory_db.fetch_products(data_dir)
    except Exception:
        return None
    requested = str(product_id or "").strip().lower()
    for product in products:
        if not isinstance(product, dict):
            continue
        identifiers = (product.get("id"), product.get("product_id"), product.get("sku"), product.get("name"))
        if requested and any(str(value or "").strip().lower() == requested for value in identifiers):
            return product
    return None


def rebuild_catalog(data_dir: str) -> dict:
    try:
        import inventory_db  # type: ignore

        inventory_db.init_inventory_db(data_dir)
        products = inventory_db.fetch_products(data_dir)
    except Exception as exc:
        return {"agent": "product_intelligence", "error": "inventory_unavailable", "detail": str(exc)[:300]}

    written: list[dict] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        brief = build_product_brief(product)
        safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", brief.get("product_id") or brief.get("sku") or brief.get("name") or "product").strip("-")
        path = os.path.join(data_dir, "product_briefs", f"{safe_id}.json")
        write_json(path, brief)
        written.append({"product_id": brief.get("product_id", ""), "name": brief.get("name", ""), "product_type": brief.get("product_type", ""), "brief_path": path})

    payload = {
        "agent": "product_intelligence",
        "mode": "catalog_rebuild",
        "products_scanned": len(products),
        "briefs_written": len(written),
        "products": written,
        "time_utc": utc_now(),
    }
    write_snapshot(data_dir, "product_intelligence", payload)
    return payload


def run(
    data_dir: str,
    product_id: str = "",
    topic: str = "",
    funnel_stage: str = "EDUCATION",
    audience_segment: str = "",
    selected_hook: str = "",
    selected_cta: str = "",
    product: dict | None = None,
) -> dict:
    if str(product_id or "").strip().lower() in {"all", "*"}:
        return rebuild_catalog(data_dir)
    selected_product = product if isinstance(product, dict) else _load_product(data_dir, product_id)
    if not selected_product:
        return {"agent": "product_intelligence", "error": "product_not_found", "product_id": product_id}

    brief = build_product_brief(selected_product)
    safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", brief.get("product_id") or brief.get("sku") or brief.get("name") or "product").strip("-")
    brief_path = os.path.join(data_dir, "product_briefs", f"{safe_id}.json")
    write_json(brief_path, brief)
    payload = build_team_handoff(
        brief,
        topic=topic,
        funnel_stage=funnel_stage,
        audience_segment=audience_segment,
        selected_hook=selected_hook,
        selected_cta=selected_cta,
    )
    payload["brief_path"] = brief_path
    payload["time_utc"] = utc_now()
    write_snapshot(data_dir, "product_intelligence", payload)
    return payload