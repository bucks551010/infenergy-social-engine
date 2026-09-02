"""Build the text-only 120-day Infenergy editorial plan.

This module is deliberately side-effect free. It reads verified product messaging,
returns concept briefs, and never queues posts, prepares image prompts, or writes media.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from campaign_runtime import recurring_series_for_slot


DEFAULT_DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data")),
)
MAX_PLAN_DAYS = 120
PROFILE_PATH = os.path.join("marketing", "product_consumer_profiles.json")

HORIZONS = (
    (14, "LOCKED", "Production-ready concepts"),
    (30, "SHAPED", "Approved concepts with adaptable execution"),
    (60, "ADAPTIVE", "Defined stories open to current context"),
    (90, "DIRECTIONAL", "Story arcs and product opportunities"),
    (120, "OPPORTUNITY", "Strategic direction and response reserve"),
)

WEEKLY_ARCS = (
    {
        "name": "The Communication Layer",
        "pillar": "everyday_power",
        "tension": "the phone is charged, but the rest of the communication chain is not",
        "setting": "a family coordinating work, school, and relatives during a neighborhood outage",
        "lesson": "communication continuity includes devices, cables, signal, contacts, and a recharge path",
        "myth": "A charged phone means communication is covered.",
        "drill": "Run a ten-minute communication check with every cable and contact method in the chain.",
    },
    {
        "name": "The First Ten Minutes",
        "pillar": "outage_readiness",
        "tension": "everyone reaches for a different priority when the lights go out",
        "setting": "an ordinary evening interrupted before anyone has settled on the first move",
        "lesson": "light, information, safe movement, and one shared decision come before equipment improvisation",
        "myth": "Prepared people react faster because they own more gear.",
        "drill": "Practice the first ten minutes with the person who did not build the plan leading it.",
    },
    {
        "name": "The Kitchen Clock",
        "pillar": "outage_readiness",
        "tension": "a short outage becomes a food, refrigeration, and decision-timing problem",
        "setting": "a household kitchen where every door opening spends part of the plan",
        "lesson": "refrigeration decisions need measured demand, duration, temperature guidance, and a recovery plan",
        "myth": "Any large battery automatically makes refrigeration handled.",
        "drill": "Write the refrigerator decision tree before opening the door again.",
    },
    {
        "name": "Comfort Without Overpromising",
        "pillar": "preparedness_mindset",
        "tension": "heat, cold, darkness, or noise turns a manageable interruption into fatigue",
        "setting": "one safe room organized around realistic comfort needs and product limits",
        "lesson": "comfort tools matter when their job and boundary are both explicit",
        "myth": "A comfort product is either a complete solution or not worth planning.",
        "drill": "Define one person, one space, one comfort need, one duration, and one fallback.",
    },
    {
        "name": "The Hidden Workday",
        "pillar": "everyday_power",
        "tension": "the laptop looks ready while a smaller dependency quietly ends the workflow",
        "setting": "a mobile professional moving between home, vehicle, shared workspace, and client call",
        "lesson": "power the complete workflow by consequence, not the largest screen",
        "myth": "Remote-work continuity is mostly about laptop battery life.",
        "drill": "Trace one work deliverable from login through delivery and circle every powered dependency.",
    },
    {
        "name": "Care Has a Power Plan",
        "pillar": "community_resilience",
        "tension": "the person providing care is also managing information, timing, transport, and uncertainty",
        "setting": "a caregiver preparing a calm handoff for another trusted adult",
        "lesson": "care continuity needs documented priorities, honest product roles, contacts, and escalation boundaries",
        "myth": "The main caregiver will always be present to run the plan.",
        "drill": "Give the care-power handoff to someone else and record the first point where they need help.",
    },
    {
        "name": "Travel Day, Outlet Optional",
        "pillar": "travel_and_outdoors",
        "tension": "a long travel day exposes the one missing connector, checkpoint, or recharge assumption",
        "setting": "a traveler moving from rideshare to terminal to destination without chasing outlets",
        "lesson": "travel power works when every item prevents a named failure in the actual itinerary",
        "myth": "Packing more charging accessories creates a more complete travel system.",
        "drill": "Empty the charging pouch and make every item name the failure it prevents.",
    },
    {
        "name": "Roadside Readiness",
        "pillar": "travel_and_outdoors",
        "tension": "a vehicle problem becomes harder because power, air, light, and communication were planned separately",
        "setting": "a safe roadside stop where the driver follows a rehearsed sequence rather than improvising",
        "lesson": "road readiness starts with personal safety and a matched, maintained tool chain",
        "myth": "Owning a multi-function roadside tool means the roadside plan is complete.",
        "drill": "Inspect charge, accessories, storage access, instructions, and the safe-use boundary.",
    },
    {
        "name": "Camp Is a System",
        "pillar": "travel_and_outdoors",
        "tension": "sunset arrives with scattered gear, shared needs, and no agreed energy budget",
        "setting": "a campsite transitioning from daylight activity to a calm overnight routine",
        "lesson": "outdoor power should follow the people, conditions, duration, and recharge access of the trip",
        "myth": "Off-grid means unlimited independence from planning.",
        "drill": "Give every packed power item a device, duration, weather condition, and owner.",
    },
    {
        "name": "Solar Is a Verb",
        "pillar": "power_literacy",
        "tension": "the load keeps spending energy while clouds, shade, angle, and time change the input",
        "setting": "one solar setup observed through clear sun, cloud cover, partial shade, and evening",
        "lesson": "solar is a variable recharge process, not an infinity label",
        "myth": "Adding a solar panel makes stored energy endless.",
        "drill": "Build a cloudy-day energy budget and identify the first demand you would reduce.",
    },
    {
        "name": "The Small Business Chain",
        "pillar": "everyday_power",
        "tension": "the visible equipment has power while connectivity, payment, access, or communication fails",
        "setting": "a neighborhood business protecting one customer-critical workflow",
        "lesson": "continuity belongs to the workflow and its weakest required dependency",
        "myth": "Keeping the biggest machine on keeps the business operating.",
        "drill": "Map one customer transaction and mark every point where loss of power stops the next step.",
    },
    {
        "name": "Apartment-Scale Readiness",
        "pillar": "outage_readiness",
        "tension": "limited space, shared infrastructure, noise, and building rules change the available options",
        "setting": "an apartment household building a compact plan around what it can safely control",
        "lesson": "good readiness fits the home, building, mobility, and storage reality of the people using it",
        "myth": "A serious power plan has to look like a garage full of equipment.",
        "drill": "Build one shelf-sized layer for light, communication, information, and a known exit decision.",
    },
    {
        "name": "Weather Before Weather",
        "pillar": "outage_readiness",
        "tension": "the forecast changes faster than the household can charge, shop, communicate, and decide",
        "setting": "the final calm afternoon before severe weather reaches the area",
        "lesson": "forecast triggers turn vague concern into timed, proportionate actions",
        "myth": "Preparedness starts when the warning becomes urgent.",
        "drill": "Set three forecast triggers and assign the exact action each one starts.",
    },
    {
        "name": "The Neighbor Protocol",
        "pillar": "community_resilience",
        "tension": "everyone intends to help, but nobody knows who checks in, when, or with what capability",
        "setting": "two neighboring households agreeing on one contact, time, capability, and boundary",
        "lesson": "specific mutual aid survives stress better than broad promises",
        "myth": "Good neighbors will naturally know what to do when something happens.",
        "drill": "Make one four-line neighbor agreement and ask the other household to repeat it back.",
    },
    {
        "name": "Power and Water Meet",
        "pillar": "community_resilience",
        "tension": "the water plan depends on movement, treatment, information, or equipment that also has constraints",
        "setting": "a household separating stored water, treatment tools, and the decisions that connect them",
        "lesson": "water readiness needs source, treatment, storage, access, maintenance, and honest product boundaries",
        "myth": "Owning a filter is the same thing as having a water plan.",
        "drill": "Trace one day of water from source to safe use and name every assumption.",
    },
    {
        "name": "Read Past the Biggest Number",
        "pillar": "power_literacy",
        "tension": "one headline specification distracts from the constraint that decides fit",
        "setting": "a buyer comparing products against one written load and duration requirement",
        "lesson": "capacity, output, ports, recharge, compatibility, weight, and conditions answer different questions",
        "myth": "The product with the largest number is automatically the stronger choice.",
        "drill": "Compare one product to a written job before comparing it to another product.",
    },
    {
        "name": "The Household Handoff",
        "pillar": "preparedness_mindset",
        "tension": "the plan works only while the person who built it is available",
        "setting": "another household member running the first five minutes without hints",
        "lesson": "labels, plain instructions, known limits, and practice turn private expertise into shared capability",
        "myth": "A plan is tested when its author can run it successfully.",
        "drill": "Let someone else lead the setup and fix the first question they have to ask.",
    },
    {
        "name": "Whole-Home, One Priority at a Time",
        "pillar": "power_literacy",
        "tension": "more capacity creates more possible loads than the plan has honestly prioritized",
        "setting": "a household assigning larger stored energy to a disciplined priority-load sequence",
        "lesson": "larger systems require stronger load rules, ownership, recovery planning, and tested boundaries",
        "myth": "More capacity removes the need to choose.",
        "drill": "Rank household loads by consequence, demand, duration, and recovery path.",
    },
)

ARC_PRODUCT_WEIGHTS = {
    "The Communication Layer": {"power_bank": 10, "preparedness_product": 7, "solar_light": 4},
    "The First Ten Minutes": {"preparedness_product": 10, "solar_light": 8, "power_bank": 6, "portable_fan": 5},
    "The Kitchen Clock": {"power_station": 10, "power_system_bundle": 9, "expansion_battery": 7},
    "Comfort Without Overpromising": {"portable_fan": 10, "solar_light": 8, "power_station": 7, "power_bank": 4},
    "The Hidden Workday": {"power_bank": 10, "power_station": 8, "power_system_bundle": 5},
    "Care Has a Power Plan": {"preparedness_product": 10, "power_bank": 8, "power_station": 7, "portable_fan": 6},
    "Travel Day, Outlet Optional": {"power_bank": 10, "solar_panel": 8, "portable_water_filter": 7, "portable_fan": 6},
    "Roadside Readiness": {"vehicle_jump_starter": 12, "electric_bike": 9, "power_bank": 6, "power_system_component": 5},
    "Camp Is a System": {"solar_panel": 10, "solar_light": 10, "portable_fan": 9, "portable_water_filter": 8, "power_station": 7},
    "Solar Is a Verb": {"solar_panel": 12, "solar_light": 10, "power_system_bundle": 8, "power_station": 6},
    "The Small Business Chain": {"power_station": 10, "power_system_bundle": 9, "power_bank": 6},
    "Apartment-Scale Readiness": {"power_bank": 10, "power_station": 8, "portable_fan": 7, "solar_light": 6},
    "Weather Before Weather": {"preparedness_product": 10, "power_station": 8, "power_system_bundle": 8, "solar_panel": 5},
    "The Neighbor Protocol": {"power_station": 9, "power_system_bundle": 9, "preparedness_product": 8},
    "Power and Water Meet": {"portable_water_filter": 12, "power_station": 7, "power_system_bundle": 7},
    "Read Past the Biggest Number": {"power_system_component": 10, "expansion_battery": 10, "power_station": 8, "power_system_bundle": 8},
    "The Household Handoff": {"preparedness_product": 10, "power_system_component": 8, "power_system_bundle": 8, "power_station": 7},
    "Whole-Home, One Priority at a Time": {"power_system_bundle": 12, "expansion_battery": 10, "power_station": 9},
}


def _load_catalog(data_dir: str) -> list[dict[str, Any]]:
    path = os.path.join(data_dir, PROFILE_PATH)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        raise ValueError("verified product consumer profiles are unavailable")
    catalog: list[dict[str, Any]] = []
    for product_id, raw_profile in profiles.items():
        if not isinstance(raw_profile, dict):
            continue
        product_name = str(raw_profile.get("product_name") or "").strip()
        if not product_name:
            continue
        personas = [item for item in raw_profile.get("personas", []) if isinstance(item, dict)]
        catalog.append({
            "product_id": str(product_id),
            "product_name": product_name,
            "product_type": str(raw_profile.get("product_type") or "solution"),
            "market_role": str(raw_profile.get("market_role") or "").strip(),
            "primary_promise": str(raw_profile.get("primary_promise") or "").strip(),
            "core_customer_truth": str(raw_profile.get("core_customer_truth") or "").strip(),
            "cta": str(raw_profile.get("primary_call_to_action") or "Review the verified product fit."),
            "personas": personas,
        })
    if not catalog:
        raise ValueError("verified product catalog is empty")
    return catalog


def _horizon(day_number: int) -> dict[str, str]:
    for maximum, state, label in HORIZONS:
        if day_number <= maximum:
            return {"state": state, "label": label}
    raise ValueError(f"day number outside planning horizon: {day_number}")


def _arc_terms(arc: dict[str, str]) -> set[str]:
    text = " ".join(str(value).lower() for value in arc.values())
    return {
        word.strip(".,:;!?()")
        for word in text.split()
        if len(word.strip(".,:;!?()")) >= 5
    }


def _text_relevance(values: list[Any], arc: dict[str, str]) -> int:
    text = " ".join(str(value).lower() for value in values if value)
    return sum(1 for term in _arc_terms(arc) if term in text)


def _product_relevance(product: dict[str, Any], arc: dict[str, str]) -> int:
    type_score = ARC_PRODUCT_WEIGHTS.get(arc["name"], {}).get(product["product_type"], 0)
    text_score = _text_relevance([
        product["product_name"],
        product["market_role"],
        product["primary_promise"],
        product["core_customer_truth"],
        *[
            " ".join(str(value) for value in persona.values() if not isinstance(value, (list, dict)))
            for persona in product["personas"]
        ],
    ], arc)
    return (type_score * 100) + text_score


def _assign_products(
    catalog: list[dict[str, Any]],
    start: date,
    days: int,
) -> dict[int, tuple[dict[str, Any], int]]:
    product_offsets = [
        offset
        for offset in range(days)
        if (start + timedelta(days=offset)).weekday() in {1, 2, 4}
    ]
    assignments: dict[int, tuple[dict[str, Any], int]] = {}
    available_offsets = set(product_offsets)
    available_products = set(range(len(catalog)))

    while available_offsets and available_products:
        score, product_index, offset = max(
            (
                _product_relevance(catalog[product_index], WEEKLY_ARCS[(offset // 7) % len(WEEKLY_ARCS)]),
                -product_index,
                -offset,
            )
            for product_index in available_products
            for offset in available_offsets
        )
        product_index = -product_index
        offset = -offset
        assignments[offset] = (catalog[product_index], product_index)
        available_products.remove(product_index)
        available_offsets.remove(offset)

    for offset in sorted(available_offsets):
        arc = WEEKLY_ARCS[(offset // 7) % len(WEEKLY_ARCS)]
        product_index = max(
            range(len(catalog)),
            key=lambda index: (_product_relevance(catalog[index], arc), -index),
        )
        assignments[offset] = (catalog[product_index], product_index)
    return assignments


def _product_context(
    product: dict[str, Any],
    placement: int,
    arc: dict[str, str],
) -> dict[str, str]:
    personas = product["personas"]
    persona = max(
        personas,
        key=lambda item: (
            _text_relevance([
                item.get("name"),
                item.get("life_context"),
                item.get("profession_context"),
                item.get("family_context"),
                item.get("leisure_context"),
                item.get("use_case"),
                item.get("problem"),
                item.get("product_role"),
            ], arc),
            -(personas.index(item) - placement) % len(personas),
        ),
    ) if personas else {}
    return {
        "product_id": product["product_id"],
        "product_name": product["product_name"],
        "product_type": product["product_type"],
        "persona": str(persona.get("name") or "people matching the verified use case"),
        "use_case": str(persona.get("use_case") or product["market_role"] or "a defined readiness need"),
        "product_role": str(persona.get("product_role") or product["market_role"]),
        "customer_truth": str(persona.get("problem") or product["core_customer_truth"]),
        "proof_direction": product["primary_promise"],
        "cta": str(persona.get("call_to_action") or product["cta"]),
    }


def _intervention_concept(
    *,
    current_date: date,
    arc: dict[str, str],
    product: dict[str, str],
    slot: str,
    installment: int,
) -> dict[str, Any]:
    instant = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc)
    series = recurring_series_for_slot(current_date.strftime("%A"), slot, now_utc=instant)
    preferred_format = str(series["preferred_format"])
    format_labels = {
        "cinematic_brand_poster": "Cinematic poster",
        "product_micro_mission_comic": "Product micro-mission comic",
        "educational_story_carousel": "Educational story carousel",
    }
    resolutions = (
        "Infenergy stops the scramble, names the actual dependency, and turns the product into one honest part of the plan.",
        "Infenergy arrives after the first avoidable mistake, resets the priorities, and gives the household a move they can repeat.",
        "Infenergy reveals that the smallest overlooked link was controlling the outcome, then rebuilds the chain around a tested fit.",
        "Infenergy refuses the oversized promise, assigns the product one credible job, and leaves the audience with a practical win.",
    )
    title = f"Infenergy Intervention: {arc['name']}"
    hook = f"They thought the problem was no power. The real problem was {arc['tension']}."
    return {
        "series": series["name"],
        "series_id": series["id"],
        "installment": installment,
        "format": preferred_format,
        "format_label": format_labels[preferred_format],
        "title": title,
        "hook": hook,
        "story": f"Open in {arc['setting']}. Let one believable mistake create tension. {resolutions[(installment - 1) % len(resolutions)]}",
        "takeaway": arc["lesson"].capitalize() + ".",
        "cta": product["cta"],
        "character": "Infenergy",
        "canon_required": True,
    }


def _daily_concept(
    *,
    current_date: date,
    day_number: int,
    arc: dict[str, str],
    product: dict[str, str] | None,
    intervention_number: int,
) -> dict[str, Any]:
    weekday = current_date.weekday()
    base: dict[str, Any]
    slot = "midday"
    if weekday == 0:
        base = {
            "series": "Readiness Myth Lab",
            "format": "educational_carousel",
            "format_label": "Educational carousel",
            "title": f"Myth: {arc['myth']}",
            "hook": f"The expensive mistake in {arc['name'].lower()} is solving the headline instead of the system.",
            "story": f"Challenge the myth with a real scene in {arc['setting']}, then reveal the dependency chain it hides.",
            "takeaway": arc["lesson"].capitalize() + ".",
            "cta": "Save the framework and test it against one real routine.",
        }
    elif weekday == 1:
        if product is None:
            raise ValueError("Tuesday Intervention requires a product")
        base = _intervention_concept(
            current_date=current_date,
            arc=arc,
            product=product,
            slot="midday",
            installment=intervention_number,
        )
    elif weekday == 2:
        if product is None:
            raise ValueError("Wednesday proof story requires a product")
        base = {
            "series": "One Honest Job",
            "format": "product_proof_story",
            "format_label": "Product proof story",
            "title": f"{product['product_name']}: one honest job in {arc['name'].lower()}",
            "hook": product["customer_truth"] or f"A product earns its place only when it fits a named job in {arc['name'].lower()}.",
            "story": f"Start with {product['persona']} handling {product['use_case']}. Show where {product['product_name']} fits, what it does not replace, and which verified detail must carry the proof.",
            "takeaway": product["proof_direction"] or arc["lesson"].capitalize() + ".",
            "cta": product["cta"],
        }
    elif weekday == 3:
        base = {
            "series": "When the Grid Leaves the Room",
            "format": "documentary_micro_story",
            "format_label": "Documentary micro-story",
            "title": f"The moment {arc['name'].lower()} becomes personal",
            "hook": f"The outage did not create the weak point. It removed the convenience that was hiding it: {arc['tension']}.",
            "story": f"Follow one person through {arc['setting']}. Keep the stakes human and specific, then widen from the immediate inconvenience to the system lesson.",
            "takeaway": arc["lesson"].capitalize() + ".",
            "cta": "Name the weak point this story would reveal in your own routine.",
        }
    elif weekday == 4:
        if product is None:
            raise ValueError("Friday Intervention requires a product")
        slot = "morning"
        base = _intervention_concept(
            current_date=current_date,
            arc=arc,
            product=product,
            slot=slot,
            installment=intervention_number,
        )
    elif weekday == 5:
        base = {
            "series": "Saturday Field Test",
            "format": "challenge_carousel",
            "format_label": "Challenge carousel",
            "title": f"This weekend's field test: {arc['name']}",
            "hook": arc["drill"],
            "story": "Turn the drill into four beats: set the condition, let another person attempt it, record the first friction point, and make one repair.",
            "takeaway": "A calm rehearsal produces better evidence than confidence alone.",
            "cta": "Run the test, keep one finding, and schedule the repair.",
        }
    else:
        base = {
            "series": "Power Is Protection",
            "format": "brand_conviction_poster",
            "format_label": "Brand conviction poster",
            "title": f"What {arc['name'].lower()} is really protecting",
            "hook": f"Power is not the outcome. The outcome is staying useful to the people and routines that count on you.",
            "story": f"Close the weekly arc with one quiet human promise inside {arc['setting']}. Make the protected relationship larger than the equipment.",
            "takeaway": arc["lesson"].capitalize() + ".",
            "cta": "Choose the promise first. Build the power plan backward from it.",
        }
    return {
        "date": current_date.isoformat(),
        "day_number": day_number,
        "weekday": current_date.strftime("%A"),
        "slot": slot,
        "week": ((day_number - 1) // 7) + 1,
        "weekly_arc": arc["name"],
        "pillar": arc["pillar"],
        "production_status": "CONCEPT_ONLY",
        "image_status": "NOT_GENERATED",
        "generation_prompts": [],
        "media_assets": [],
        **_horizon(day_number),
        **base,
        "product": product,
    }


def build_120_day_plan(
    *,
    data_dir: str = DEFAULT_DATA_DIR,
    start_date: str | date | None = None,
    days: int = MAX_PLAN_DAYS,
) -> dict[str, Any]:
    """Return an inspectable editorial plan without mutating production state."""
    if days < 1 or days > MAX_PLAN_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_PLAN_DAYS}")
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    start = start or (datetime.now(timezone.utc).date() + timedelta(days=1))
    catalog = _load_catalog(data_dir)
    product_assignments = _assign_products(catalog, start, days)
    entries: list[dict[str, Any]] = []
    intervention_number = 0
    for offset in range(days):
        current_date = start + timedelta(days=offset)
        arc = WEEKLY_ARCS[(offset // 7) % len(WEEKLY_ARCS)]
        product = None
        if offset in product_assignments:
            raw_product, product_placement = product_assignments[offset]
            product = _product_context(raw_product, product_placement, arc)
        if current_date.weekday() in {1, 4}:
            intervention_number += 1
        entries.append(_daily_concept(
            current_date=current_date,
            day_number=offset + 1,
            arc=arc,
            product=product,
            intervention_number=intervention_number,
        ))
    used_product_ids = {
        entry["product"]["product_id"]
        for entry in entries
        if isinstance(entry.get("product"), dict)
    }
    catalog_ids = {product["product_id"] for product in catalog}
    return {
        "status": "TEXT_PREVIEW_READY",
        "mode": "TEXT_ONLY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=days - 1)).isoformat(),
        "days": days,
        "concept_count": len(entries),
        "image_generation_enabled": False,
        "image_count": 0,
        "catalog_size": len(catalog),
        "catalog_products_used": len(used_product_ids),
        "catalog_coverage_complete": catalog_ids.issubset(used_product_ids),
        "format_counts": {
            format_name: sum(1 for entry in entries if entry["format"] == format_name)
            for format_name in sorted({entry["format"] for entry in entries})
        },
        "series_counts": {
            series_name: sum(1 for entry in entries if entry["series"] == series_name)
            for series_name in sorted({entry["series"] for entry in entries})
        },
        "horizons": [
            {"through_day": maximum, "state": state, "label": label}
            for maximum, state, label in HORIZONS
        ],
        "entries": entries,
    }


if __name__ == "__main__":
    print(json.dumps(build_120_day_plan(), ensure_ascii=True, indent=2))