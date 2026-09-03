from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

BASE_DIR = os.path.dirname(__file__)
DEFAULT_PATH = os.path.join(BASE_DIR, "..", "data", "social", "consumer_life_foundation.json")

REQUIRED_WORLD_FIELDS = (
    "id",
    "name",
    "people",
    "places",
    "activities",
    "devices_and_jobs",
)
REQUIRED_MOMENT_FIELDS = (
    "id",
    "world_id",
    "person",
    "setting",
    "activity",
    "devices_and_jobs",
    "friction",
    "disruption",
    "failure",
    "consequence",
    "immediate_action",
    "backup_plan",
    "question",
    "false_assumption",
    "curiosity_payoff",
    "useful_discovery",
    "visual_evidence",
    "compatible_treatments",
    "product_fit",
)
FORBIDDEN_PUBLIC_CATEGORIES = {"verified_education", "technical_education", "product_education"}
SELECTION_DIMENSIONS = (
    "world_id",
    "id",
    "person",
    "setting",
    "activity",
    "friction",
    "consequence",
    "useful_discovery",
    "immediate_action",
)
CAPABILITY_TERMS = {
    "phone_charging": ("phone", "usb", "power bank", "portable charger"),
    "laptop_charging": ("laptop", "usb-c", "pd", "power delivery"),
    "appliance_power": ("refrigerator", "appliance", "pure sine", "power station", "home backup"),
    "tool_power": ("power tool", "tool batteries", "job site", "jobsite"),
    "vehicle_jump_start": ("jump start", "jump starter", "vehicle battery"),
    "tire_inflation": ("inflator", "tire pressure", "air compressor"),
    "lighting": ("light", "lamp", "lantern", "bulb"),
    "outdoor_use": ("camping", "outdoor", "off-grid", "rv"),
    "quiet_operation": ("quiet", "silent", "low noise"),
    "flight_compliant": ("tsa", "flight", "airline", "100wh"),
    "medical_device": ("cpap", "medical device", "medical equipment"),
    "weather_resistant": ("weather", "water resistant", "waterproof", "ip65", "ip67"),
    "simultaneous_charging": ("simultaneous", "multiple devices", "multiple ports", "outlets"),
    "solar_generation": ("solar panel", "solar", "photovoltaic"),
    "water_treatment": ("water filter", "water purifier", "filtration", "purifier bottle"),
    "personal_cooling": ("fan", "cooling", "airflow"),
    "electric_mobility": ("electric bike", "e-bike", "ebike", "pedal assist"),
    "modular_expansion": ("expansion battery", "extra inverter", "modular", "chassis"),
}
PRODUCT_TYPE_CAPABILITIES = {
    "power_bank": {"phone_charging"},
    "power_station": {"phone_charging", "laptop_charging", "appliance_power", "tool_power", "simultaneous_charging"},
    "portable_power": {"phone_charging", "laptop_charging", "appliance_power", "tool_power", "simultaneous_charging"},
    "power_system_bundle": {"phone_charging", "laptop_charging", "appliance_power", "tool_power", "simultaneous_charging", "modular_expansion"},
    "solar_panel": {"solar_generation", "outdoor_use"},
    "power_system_component": {"modular_expansion"},
    "expansion_battery": {"modular_expansion"},
    "vehicle_jump_starter": {"vehicle_jump_start", "tire_inflation", "lighting"},
    "electric_bike": {"electric_mobility"},
    "portable_fan": {"personal_cooling", "lighting", "phone_charging", "outdoor_use"},
    "solar_light": {"lighting", "solar_generation", "outdoor_use"},
    "portable_water_filter": {"water_treatment", "outdoor_use"},
    "preparedness_product": {"phone_charging", "lighting"},
}
WORLD_PRIMARY_CAPABILITIES = {
    "solar_harvesting": ["solar_generation"],
    "water_access": ["water_treatment"],
    "electric_mobility": ["electric_mobility"],
    "modular_power_growth": ["modular_expansion"],
}


def _require_text(record: dict[str, Any], field: str, label: str) -> None:
    if not str(record.get(field) or "").strip():
        raise ValueError(f"{label} requires non-empty {field}")


def _validate_foundation(data: dict[str, Any]) -> None:
    worlds = data.get("worlds")
    moments = data.get("moments")
    if not isinstance(worlds, list) or not worlds:
        raise ValueError("consumer foundation requires worlds")
    if not isinstance(moments, list) or not moments:
        raise ValueError("consumer foundation requires moments")

    world_ids: set[str] = set()
    for world in worlds:
        if not isinstance(world, dict):
            raise ValueError("each consumer world must be an object")
        for field in REQUIRED_WORLD_FIELDS:
            if field in {"people", "places", "activities", "devices_and_jobs"}:
                if not isinstance(world.get(field), list) or not world[field]:
                    raise ValueError(f"consumer world requires non-empty {field}")
            else:
                _require_text(world, field, "consumer world")
        world_id = str(world["id"])
        if world_id in world_ids:
            raise ValueError(f"duplicate consumer world id: {world_id}")
        world_ids.add(world_id)

    moment_ids: set[str] = set()
    for moment in moments:
        if not isinstance(moment, dict):
            raise ValueError("each consumer moment must be an object")
        for field in REQUIRED_MOMENT_FIELDS:
            if field in {"devices_and_jobs", "visual_evidence", "compatible_treatments"}:
                if not isinstance(moment.get(field), list) or not moment[field]:
                    raise ValueError(f"consumer moment requires non-empty {field}")
            elif field == "product_fit":
                if not isinstance(moment.get(field), dict) or not str(moment[field].get("mode") or "").strip():
                    raise ValueError("consumer moment requires product_fit.mode")
            else:
                _require_text(moment, field, "consumer moment")
        moment_id = str(moment["id"])
        if moment_id in moment_ids:
            raise ValueError(f"duplicate consumer moment id: {moment_id}")
        if str(moment["world_id"]) not in world_ids:
            raise ValueError(f"unknown world_id for consumer moment: {moment_id}")
        categories = {str(value).strip().lower() for value in moment.get("public_categories", [])}
        if categories.intersection(FORBIDDEN_PUBLIC_CATEGORIES):
            raise ValueError(f"consumer moment exposes a forbidden public category: {moment_id}")
        moment_ids.add(moment_id)


def load_consumer_foundation(path: str = DEFAULT_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("consumer foundation must be an object")
    data = _materialize_reviewed_patterns(data)
    _validate_foundation(data)
    return data


def _world_item(world: dict[str, Any], field: str, index: int) -> str:
    values = world.get(field) if isinstance(world.get(field), list) else []
    return str(values[index % len(values)]) if values else ""


def _capabilities_for_world(world: dict[str, Any]) -> list[str]:
    primary = WORLD_PRIMARY_CAPABILITIES.get(str(world.get("id") or ""))
    if primary:
        return list(primary)
    evidence = _normalized(" ".join(str(value) for value in world.get("devices_and_jobs", [])))
    matches = [capability for capability, terms in CAPABILITY_TERMS.items() if any(term in evidence for term in terms)]
    return matches[:2]


def _materialize_reviewed_patterns(data: dict[str, Any]) -> dict[str, Any]:
    expanded = deepcopy(data)
    moments = [moment for moment in expanded.get("moments", []) if isinstance(moment, dict)]
    worlds_by_id = {
        str(world.get("id") or ""): world
        for world in expanded.get("worlds", [])
        if isinstance(world, dict)
    }
    for moment in moments:
        product_fit = moment.get("product_fit") if isinstance(moment.get("product_fit"), dict) else {}
        world = worlds_by_id.get(str(moment.get("world_id") or ""), {})
        capabilities = [] if product_fit.get("mode") == "none" else _capabilities_for_world(world)
        product_fit.setdefault("required_capabilities", capabilities)
        product_fit.setdefault("requirements", [f"verified evidence supporting {capability}" for capability in capabilities])
        product_fit.setdefault("no_fit_when", "The product lacks verified evidence for every required capability")
        moment["product_fit"] = product_fit
    existing_ids = {str(moment.get("id") or "") for moment in moments}
    patterns = (
        ("handoff", "Only one person knows the final handoff", "The next person cannot complete the routine without calling for help", "Put the handoff beside the tool and have another person complete it once"),
        ("timing", "The normal time window closes earlier than expected", "A manageable task becomes an avoidable last-minute interruption", "Protect the final required step before spending time or power on optional ones"),
        ("location", "The routine moves to a place where the usual support is unavailable", "Working equipment becomes unusable because the real setting was never tested", "Test the entire chain once in the place where it must actually work"),
        ("shared_knowledge", "The plan lives in one person's memory", "Silence or absence is mistaken for a completed plan", "Give every critical action an owner, a backup owner, and a visible status"),
        ("recovery", "The first attempt fails and nobody has named the recovery step", "People repeat the same failed action while the useful window shrinks", "Decide the stop condition and the next workable method before beginning"),
    )
    for world in expanded.get("worlds", []):
        if not isinstance(world, dict):
            continue
        world_id = str(world.get("id") or "")
        capabilities = _capabilities_for_world(world)
        for index, (pattern_id, friction, consequence, discovery) in enumerate(patterns):
            moment_id = f"{world_id}_{pattern_id}"
            if moment_id in existing_ids:
                continue
            person = _world_item(world, "people", index)
            setting = _world_item(world, "places", index)
            activity = _world_item(world, "activities", index)
            device_job = _world_item(world, "devices_and_jobs", index)
            action = f"For {activity}, {discovery[0].lower() + discovery[1:]}"
            moments.append({
                "id": moment_id,
                "world_id": world_id,
                "person": person,
                "setting": setting,
                "activity": activity,
                "devices_and_jobs": [device_job],
                "friction": friction,
                "disruption": f"During {activity}, {friction[0].lower() + friction[1:]}",
                "failure": f"The routine assumes {device_job} will remain available without a tested handoff or recovery step",
                "consequence": consequence,
                "immediate_action": action,
                "backup_plan": f"Write the alternate way to finish {activity} and keep it with the items used at {setting}",
                "question": f"What exact handoff lets {person} finish {activity} at {setting}?",
                "false_assumption": f"If each item works separately, {activity} will work as a complete routine",
                "curiosity_payoff": f"The overlooked dependency is not the biggest device; it is the transition that lets {activity} finish",
                "useful_discovery": f"{discovery} in this {activity} routine",
                "visual_evidence": [f"{person} actively {activity} at {setting}", device_job, action],
                "compatible_treatments": ["POV micro-story", "three-step checklist", "comic strip", "documentary still"],
                "product_fit": {
                    "mode": "optional" if capabilities else "none",
                    "required_capabilities": capabilities,
                    "requirements": [f"verified evidence supporting {capability}" for capability in capabilities],
                    "no_fit_when": "The product lacks verified evidence for every required capability or distracts from the human practice",
                },
                "public_categories": [world_id.replace("_", " "), "practical routine"],
            })
            existing_ids.add(moment_id)
    expanded["moments"] = moments
    return expanded


def select_consumer_root(
    *,
    current_date: str | date,
    slot: str = "midday",
    preferred_world_id: str = "",
    preferred_moment_id: str = "",
    product_required: bool = False,
    product: dict[str, Any] | None = None,
    sequence: int = 0,
    history: list[dict[str, Any]] | None = None,
    winning_hints: dict[str, list[str]] | None = None,
    losing_hints: dict[str, list[str]] | None = None,
    path: str = DEFAULT_PATH,
) -> dict[str, Any]:
    data = load_consumer_foundation(path)
    worlds = {str(world["id"]): world for world in data["worlds"]}
    candidates = [
        moment for moment in data["moments"]
        if (not preferred_world_id or str(moment["world_id"]) == preferred_world_id)
        and (not preferred_moment_id or str(moment["id"]) == preferred_moment_id)
    ]
    if product_required:
        candidates = [moment for moment in candidates if moment["product_fit"]["mode"] != "none"]
    if product is not None:
        compatible = [moment for moment in candidates if assess_product_compatibility(moment, product)["compatible"]]
        candidates = compatible
    if not candidates:
        raise ValueError(f"no consumer moments for world: {preferred_world_id}")
    date_key = current_date.isoformat() if isinstance(current_date, date) else str(current_date)
    selected = deepcopy(max(
        candidates,
        key=lambda moment: _selection_score(
            moment,
            history=history or [],
            winning_hints=winning_hints or {},
            losing_hints=losing_hints or {},
            tie_key=f"{date_key}|{slot}|{sequence}",
        ),
    ))
    world = deepcopy(worlds[str(selected["world_id"])])
    return {
        "schema_version": str(data.get("schema_version") or "consumer-life.v1"),
        "root_id": f"{world['id']}:{selected['id']}",
        "world_id": str(world["id"]),
        "moment_id": str(selected["id"]),
        "world": world,
        "moment": selected,
        "consumer_receipt": {
            "who": selected["person"],
            "where": selected["setting"],
            "doing": selected["activity"],
            "friction": selected["friction"],
            "consequence": selected["consequence"],
            "useful_discovery": selected["useful_discovery"],
            "immediate_action": selected["immediate_action"],
            "product_fit_mode": selected["product_fit"]["mode"],
        },
        "selection_receipt": _selection_receipt(selected, history or [], winning_hints or {}, losing_hints or {}),
    }


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _history_value(entry: dict[str, Any], dimension: str) -> str:
    aliases = {"id": "consumer_moment_id"}
    direct = entry.get(aliases.get(dimension, dimension))
    if direct:
        return _normalized(direct)
    root = entry.get("consumer_root") if isinstance(entry.get("consumer_root"), dict) else {}
    moment = root.get("moment") if isinstance(root.get("moment"), dict) else {}
    return _normalized(root.get(dimension) or moment.get(dimension))


def _entry_score(entry: dict[str, Any]) -> float:
    engagement = entry.get("engagement") if isinstance(entry.get("engagement"), dict) else {}
    for value in (engagement.get("success_score"), engagement.get("engagement_rate")):
        if isinstance(value, (int, float)):
            return float(value) * (100 if 0 <= value <= 1 else 1)
    quality = entry.get("conversion_quality_score") if isinstance(entry.get("conversion_quality_score"), dict) else {}
    value = quality.get("total", entry.get("quality_score", 50))
    return float(value) if isinstance(value, (int, float)) else 50.0


def _selection_receipt(
    moment: dict[str, Any],
    history: list[dict[str, Any]],
    winning_hints: dict[str, list[str]],
    losing_hints: dict[str, list[str]],
) -> dict[str, Any]:
    dimension_uses = {
        dimension: sum(_history_value(entry, dimension) == _normalized(moment.get(dimension)) for entry in history)
        for dimension in SELECTION_DIMENSIONS
    }
    return {
        "history_sample_size": len(history),
        "dimension_uses": dimension_uses,
        "winning_dimensions_applied": sorted(key for key, values in winning_hints.items() if _normalized(moment.get(key)) in {_normalized(value) for value in values}),
        "losing_dimensions_avoided": sorted(key for key, values in losing_hints.items() if _normalized(moment.get(key)) not in {_normalized(value) for value in values}),
    }


def _selection_score(
    moment: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    winning_hints: dict[str, list[str]],
    losing_hints: dict[str, list[str]],
    tie_key: str,
) -> tuple[float, int]:
    score = 100.0
    for dimension in SELECTION_DIMENSIONS:
        value = _normalized(moment.get(dimension))
        matches = [entry for entry in history if _history_value(entry, dimension) == value and value]
        score -= len(matches) * (28.0 if dimension == "id" else 3.0)
        if matches:
            score += (sum(_entry_score(entry) for entry in matches) / len(matches) - 50.0) * 0.08
        winners = {_normalized(item) for item in winning_hints.get(dimension, [])}
        losers = {_normalized(item) for item in losing_hints.get(dimension, [])}
        score += 8.0 if value and value in winners else 0.0
        score -= 20.0 if value and value in losers else 0.0
    digest = hashlib.sha256(f"{tie_key}|{moment['id']}".encode("utf-8")).hexdigest()
    return score, int(digest[:12], 16)


def assess_product_compatibility(moment: dict[str, Any], product: dict[str, Any] | None) -> dict[str, Any]:
    product_fit = moment.get("product_fit") if isinstance(moment.get("product_fit"), dict) else {}
    mode = str(product_fit.get("mode") or "none")
    if product is None:
        return {"compatible": mode in {"none", "optional"}, "mode": mode, "product_id": "", "matched_capabilities": [], "failed_requirements": [] if mode in {"none", "optional"} else ["product_required"]}
    product_id = str(product.get("id") or product.get("product_id") or product.get("sku") or "")
    if mode == "none":
        return {"compatible": False, "mode": mode, "product_id": product_id, "matched_capabilities": [], "failed_requirements": ["product_not_allowed_for_moment"]}
    evidence_parts = [
        product.get("product_type"), product.get("name"), product.get("fact_snippet"), product.get("proof_rule"),
        *(product.get("categories") or []), *(product.get("metrics") or []), *(product.get("verified_facts") or []),
        *(product.get("core_benefits") or []), *(product.get("best_fit_use_cases") or []),
    ]
    evidence = _normalized(" ".join(str(part) for part in evidence_parts if part))
    required = [str(value) for value in product_fit.get("required_capabilities", [])]
    type_capabilities = PRODUCT_TYPE_CAPABILITIES.get(str(product.get("product_type") or "").strip().lower(), set())
    matched = [
        capability for capability in required
        if capability in type_capabilities or any(term in evidence for term in CAPABILITY_TERMS.get(capability, (capability.replace("_", " "),)))
    ]
    failed = [capability for capability in required if capability not in matched]
    if not evidence:
        failed.append("verified_product_evidence_missing")
    compatible = not failed and mode in {"optional", "eligible", "restricted"}
    return {
        "compatible": compatible,
        "mode": mode,
        "product_id": product_id,
        "matched_capabilities": matched,
        "failed_requirements": failed,
        "decision": "product_fit" if compatible else "no_product_fit",
        "no_fit_reason": "verified requirements not satisfied" if failed else "",
    }


def assess_copy_fidelity(content: dict[str, Any]) -> dict[str, Any]:
    root = content.get("consumer_root") if isinstance(content.get("consumer_root"), dict) else {}
    receipt = root.get("consumer_receipt") if isinstance(root.get("consumer_receipt"), dict) else {}
    platform_posts = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
    texts = [str(content.get(key) or "") for key in ("wp_content", "fb_caption", "ig_caption", "li_text")]
    texts.extend(str(package.get("caption") or "") for package in platform_posts.values() if isinstance(package, dict))
    public_text = _normalized(" ".join(texts))
    checks: dict[str, bool] = {}
    for field in ("who", "where", "doing", "friction", "useful_discovery", "immediate_action"):
        expected = _normalized(receipt.get(field))
        significant = [word for word in expected.split() if len(word) >= 5]
        checks[field] = bool(expected) and (
            expected in public_text
            or bool(significant) and sum(word in public_text for word in significant) >= max(1, min(3, len(significant) // 3))
        )
    missing = [field for field, passed in checks.items() if not passed]
    return {"passed": not missing, "checks": checks, "missing": missing}


def validate_consumer_receipt(content: dict[str, Any]) -> dict[str, Any]:
    root = content.get("consumer_root") if isinstance(content.get("consumer_root"), dict) else {}
    receipt = content.get("consumer_receipt") if isinstance(content.get("consumer_receipt"), dict) else {}
    errors: list[str] = []
    if str(root.get("schema_version") or "") != "consumer-life.v1":
        errors.append("missing_consumer_life_schema")
    for field in ("root_id", "world_id", "moment_id"):
        if not str(root.get(field) or "").strip():
            errors.append(f"missing_consumer_{field}")
    for field in ("who", "where", "doing", "friction", "consequence", "useful_discovery", "immediate_action", "product_fit_mode"):
        if not str(receipt.get(field) or "").strip():
            errors.append(f"missing_consumer_receipt_{field}")
    if root and receipt and receipt != root.get("consumer_receipt"):
        errors.append("consumer_receipt_root_mismatch")
    moment = root.get("moment") if isinstance(root.get("moment"), dict) else {}
    product_fit = moment.get("product_fit") if isinstance(moment.get("product_fit"), dict) else {}
    if str(product_fit.get("mode") or "") == "none" and any(
        str(content.get(field) or "").strip() for field in ("product_id", "product_name", "product_sku")
    ):
        errors.append("product_forbidden_for_consumer_moment")
    compatibility = content.get("product_compatibility") if isinstance(content.get("product_compatibility"), dict) else {}
    if any(str(content.get(field) or "").strip() for field in ("product_id", "product_name", "product_sku")) and compatibility.get("compatible") is False:
        errors.append("product_incompatible_with_consumer_moment")
    return {"passed": not errors, "errors": errors, "root_id": str(root.get("root_id") or "")}
