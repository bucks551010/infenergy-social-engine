from __future__ import annotations

import glob
import json
import os
import re
from typing import Any


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEF_DIR = os.path.join(REPO_ROOT, "data", "product_briefs")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "marketing", "product_consumer_profiles.json")
REASON_WHY = (
    "Infenergy helps people keep everyday life moving when access to power, light, water, comfort, "
    "or mobility becomes uncertain, using practical products matched honestly to the job."
)


BLUEPRINTS: dict[str, dict[str, Any]] = {
    "power_station": {
        "role": "planned portable or backup power for specific household, work, or recreation loads",
        "promise": "Turn an uncertain power need into a load plan grounded in verified capability.",
        "triggers": ["an outage exposed a gap", "a trip needs dependable off-grid power", "work cannot stop when an outlet is unavailable"],
        "criteria": ["required device loads", "verified output and capacity", "port compatibility", "charging options", "size and portability"],
        "objections": ["I do not know what size I need", "I do not want to pay for unused capacity", "I am unsure what it can actually run"],
        "angles": ["build a load priority before buying", "show the moment continuity matters", "translate verified specifications into a realistic job"],
    },
    "power_system_bundle": {
        "role": "a coordinated larger-capacity power configuration for planned backup or off-grid use",
        "promise": "Make a complex system decision understandable by starting with loads, duration, and compatibility.",
        "triggers": ["smaller backup no longer covers the plan", "a household wants broader outage continuity", "an off-grid project needs a complete configuration"],
        "criteria": ["whole load plan", "verified system capacity and output", "component compatibility", "charging configuration", "installation and space needs"],
        "objections": ["The configuration feels complicated", "I am unsure which components belong together", "I need to justify a larger investment"],
        "angles": ["design from the real load list backward", "compare complete configurations by job", "show how compatible parts work as one plan"],
    },
    "expansion_battery": {
        "role": "compatible capacity expansion for an existing modular power system",
        "promise": "Extend a compatible system only when the added capacity serves a defined need.",
        "triggers": ["the existing system needs longer coverage", "the owner wants modular growth", "a repeated outage revealed insufficient duration"],
        "criteria": ["exact base-system compatibility", "verified added capacity", "connection requirements", "space and mobility", "cost versus replacing the system"],
        "objections": ["Will it work with my exact system?", "Is expansion better than replacement?", "How much useful coverage does it add for my loads?"],
        "angles": ["expand around a known load gap", "verify compatibility before capacity", "show modular ownership as a staged plan"],
    },
    "power_system_component": {
        "role": "a purpose-built component for configuring or moving a compatible modular power system",
        "promise": "Solve one system job without implying compatibility that has not been verified.",
        "triggers": ["an existing system needs a specific capability", "mobility or configuration is limiting use", "the owner is planning a modular upgrade"],
        "criteria": ["exact system compatibility", "documented component function", "installation requirements", "mobility or space impact", "what is included"],
        "objections": ["Does this fit my exact model?", "Do I actually need this component?", "What changes after I add it?"],
        "angles": ["name the system constraint first", "show the component performing its documented role", "make compatibility the first decision"],
    },
    "solar_panel": {
        "role": "portable solar input for compatible equipment when useful sunlight is available",
        "promise": "Add an off-grid charging option after wattage, connectors, and equipment fit are verified.",
        "triggers": ["a trip extends beyond wall charging", "an outage plan needs a renewable recharge path", "a power-station owner wants more charging flexibility"],
        "criteria": ["wattage", "connector and voltage compatibility", "verified efficiency", "packed size and weight", "weather limitations"],
        "objections": ["Will it connect to my equipment?", "Will it be practical to carry and deploy?", "What can I expect when sunlight varies?"],
        "angles": ["match the panel to the equipment before the destination", "show a credible deployment", "explain solar as an input option, not a guarantee"],
    },
    "power_bank": {
        "role": "portable charging continuity for the small devices a person depends on away from an outlet",
        "promise": "Keep essential mobile tasks accessible with a charger matched to the device and carry routine.",
        "triggers": ["a phone died during a necessary task", "travel days outlast available outlets", "mobile work depends on charged devices"],
        "criteria": ["device and port compatibility", "verified capacity and output", "carry size and weight", "recharge method", "simultaneous device needs"],
        "objections": ["Will it charge my exact device?", "Is it comfortable to carry every day?", "How is it different from the charger I already own?"],
        "angles": ["connect charge to the task the device enables", "show the one-percent moment without fear", "fit the charger to a real carry routine"],
    },
    "vehicle_jump_starter": {
        "role": "vehicle-readiness support for documented jump-start, inflation, or roadside functions",
        "promise": "Put the right verified roadside capability within reach before a routine drive becomes a delay.",
        "triggers": ["a previous no-start or low-tire event", "a road trip is approaching", "a household is completing a vehicle kit"],
        "criteria": ["vehicle and engine compatibility", "verified starting capability", "inflation specifications", "included accessories", "storage and recharge routine"],
        "objections": ["Will it work with my vehicle?", "Will it still be ready after sitting in the car?", "Can I use each function confidently?"],
        "angles": ["build the vehicle kit around likely delays", "show preparation as care for passengers", "verify vehicle fit before features"],
    },
    "portable_water_filter": {
        "role": "portable treatment support for a documented water source and use case",
        "promise": "Add a practical water option while staying precise about what the product is verified to filter or purify.",
        "triggers": ["a household is building a water backup plan", "a route may not have dependable treated water", "a traveler wants a compact contingency"],
        "criteria": ["verified filtration or purification claims", "supported water sources", "capacity and flow", "replacement or cleaning requirements", "carry format"],
        "objections": ["What exactly does it remove?", "Which water sources are appropriate?", "How do I maintain it correctly?"],
        "angles": ["start with the water scenario", "separate verified treatment from unsupported safety claims", "show the product in a credible kit"],
    },
    "portable_fan": {
        "role": "portable airflow and documented utility features for camping, travel, or temporary comfort",
        "promise": "Bring practical airflow to a specific place where fixed cooling is unavailable.",
        "triggers": ["a warm-weather trip is approaching", "a household wants an outage comfort option", "a tent or vehicle setup needs portable airflow"],
        "criteria": ["verified battery and runtime", "airflow settings", "noise", "size and mounting", "charging and lighting features"],
        "objections": ["Will the airflow matter in my space?", "How long will it operate at the setting I use?", "Is it practical to pack?"],
        "angles": ["show the exact space where airflow changes comfort", "connect comfort to rest and family routine", "use documented runtime only"],
    },
    "solar_light": {
        "role": "portable light for documented outage, camping, or off-grid use",
        "promise": "Keep a familiar space usable after dark with a light matched to the task and charging plan.",
        "triggers": ["an outage left key rooms dark", "a campsite needs task lighting", "a kit lacks an independent light source"],
        "criteria": ["verified brightness and modes", "charging method", "documented runtime", "placement and portability", "weather limitations"],
        "objections": ["Is it bright enough for the task?", "How will I recharge it?", "Where can it be used safely?"],
        "angles": ["connect light to dinner, homework, setup, or navigation", "show one useful illuminated zone", "make charging part of the plan"],
    },
    "electric_bike": {
        "role": "electric mobility for a documented commute, errand, or recreational route",
        "promise": "Match verified bike capability to the rider, route, load, and reason for moving.",
        "triggers": ["a commute feels costly or inconvenient", "local errands need another option", "a rider wants assisted recreation"],
        "criteria": ["verified range conditions", "motor and battery specifications", "rider and cargo limits", "terrain fit", "storage, charging, and local rules"],
        "objections": ["Will the range cover my real route?", "Can it handle my terrain and load?", "Where will I store and charge it?"],
        "angles": ["map a real route before discussing range", "connect mobility to time and access", "show the rider's actual use rather than generic speed"],
    },
    "preparedness_product": {
        "role": "a specific tool filling one documented gap in a practical preparedness plan",
        "promise": "Choose the tool by the job it must do, not by generic emergency language.",
        "triggers": ["a kit review exposed a missing job", "travel or weather changes the plan", "a household wants calm, usable readiness"],
        "criteria": ["documented function", "fit for the intended scenario", "maintenance and storage", "compatibility", "clear usage instructions"],
        "objections": ["Will I actually use this?", "Does another item already cover the job?", "What must I know before relying on it?"],
        "angles": ["organize preparedness by human need", "show the tool doing one verified job", "replace vague readiness with a simple plan"],
    },
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _context_for(audience: str, use_case: str) -> dict[str, str]:
    text = f"{audience} {use_case}".lower()
    profession = ""
    family = ""
    leisure = ""
    if any(term in text for term in ("professional", "commut", "work", "buyer", "owner", "driver")):
        profession = f"Their work or daily responsibilities depend on {use_case} being manageable without avoidable interruption."
    if any(term in text for term in ("household", "family", "home", "prepared", "driver")):
        family = f"They are thinking about how {use_case} affects the people, routines, or shared resources they care for."
    if any(term in text for term in ("camp", "rv", "outdoor", "travel", "recreation", "off-grid", "road-trip")):
        leisure = f"They want {use_case} to support the experience without equipment uncertainty becoming the focus."
    return {
        "profession_context": profession,
        "family_context": family,
        "leisure_context": leisure,
    }


def _choose_use_case(audience: str, use_cases: list[str], index: int) -> str:
    audience_text = audience.lower()
    affinities = {
        "commut": ("commut", "daily", "errand"),
        "travel": ("travel", "vehicle", "road"),
        "camp": ("camp", "outdoor", "off-grid"),
        "rv": ("rv", "camp", "off-grid"),
        "household": ("home", "outage", "backup"),
        "family": ("home", "outage", "vehicle", "comfort"),
        "professional": ("work", "mobile", "device"),
        "driver": ("vehicle", "road", "daily"),
        "power-station owner": ("power-station", "charging", "recharging"),
        "system owner": ("system", "expansion", "configuration"),
        "off-grid": ("off-grid", "solar", "travel"),
        "recreational": ("recreation", "outdoor", "local"),
    }
    terms = {term for key, values in affinities.items() if key in audience_text for term in values}
    terms.update(word for word in re.findall(r"[a-z]+", audience_text) if len(word) > 4)
    audience_stems = {word[:5] for word in re.findall(r"[a-z]+", audience_text) if len(word) > 4}
    scored = []
    for position, use_case in enumerate(use_cases):
        use_text = use_case.lower()
        score = sum(1 for term in terms if term in use_text)
        score += 3 * sum(1 for stem in audience_stems if stem in use_text)
        scored.append((score, -position, use_case))
    best_score, _, best_use_case = max(scored)
    return best_use_case if best_score else use_cases[index % len(use_cases)]


def _persona(brief: dict[str, Any], blueprint: dict[str, Any], audience: str, use_case: str, index: int) -> dict[str, Any]:
    contexts = _context_for(audience, use_case)
    product_name = str(brief.get("name") or "this product")
    problem = str(brief.get("primary_pain_point") or blueprint["objections"][0])
    cta = str(brief.get("recommended_cta") or f"Compare {product_name} with the job you need it to do.")
    return {
        "persona_id": f"{_slug(audience) or 'consumer'}-{index + 1}",
        "name": audience.strip().capitalize(),
        "identity": audience,
        "life_context": f"They are preparing for or actively dealing with {use_case}.",
        **contexts,
        "use_case": use_case,
        "problem": problem,
        "why_it_matters": f"Without a clear fit, {use_case} can become less dependable, more stressful, or more expensive than expected.",
        "emotional_driver": "confidence from having the right capability for a real responsibility",
        "desired_outcome": f"Handle {use_case} with a product whose documented role and limits are understood before it is needed.",
        "product_role": blueprint["role"],
        "purchase_triggers": list(blueprint["triggers"]),
        "decision_criteria": list(blueprint["criteria"]),
        "objections": list(blueprint["objections"]),
        "objection_response": "Answer with verified product facts, compatibility details, and an honest explanation of limitations; never use fear or unsupported certainty.",
        "message_angles": list(blueprint["angles"]),
        "call_to_action": cta,
    }


def build_profile(brief: dict[str, Any]) -> dict[str, Any]:
    product_type = str(brief.get("product_type") or "preparedness_product")
    blueprint = BLUEPRINTS.get(product_type, BLUEPRINTS["preparedness_product"])
    audiences = [str(item) for item in brief.get("best_fit_audiences", []) if str(item).strip()]
    use_cases = [str(item) for item in brief.get("best_fit_use_cases", []) if str(item).strip()]
    if not audiences:
        audiences = ["practical preparedness buyers"]
    if not use_cases:
        use_cases = [str(brief.get("role") or "a documented everyday need")]
    personas = [
        _persona(brief, blueprint, audience, _choose_use_case(audience, use_cases, index), index)
        for index, audience in enumerate(audiences)
    ]
    product_name = str(brief.get("name") or "This product")
    return {
        "schema_version": "1.0",
        "product_id": str(brief.get("product_id") or brief.get("sku") or ""),
        "product_name": product_name,
        "product_type": product_type,
        "market_role": blueprint["role"],
        "positioning_statement": f"{product_name} is positioned as {blueprint['role']}, for people whose real situation matches its verified capabilities.",
        "core_customer_truth": str(brief.get("primary_pain_point") or "The buyer needs product fit, not a generic feature list."),
        "primary_promise": blueprint["promise"],
        "infenergy_reason_why": REASON_WHY,
        "value_pillars": list(brief.get("core_benefits") or []) + ["clear product-to-life fit", "evidence before claims"],
        "purchase_triggers": list(blueprint["triggers"]),
        "decision_criteria": list(blueprint["criteria"]),
        "objections": list(blueprint["objections"]),
        "content_angles": list(blueprint["angles"]),
        "primary_call_to_action": str(brief.get("recommended_cta") or f"Review {product_name} against your exact use case."),
        "content_mandates": [
            "Choose one persona and one lived use case per product-driven post.",
            "Open with the person's situation, responsibility, or desired experience before introducing the product.",
            "Connect a verified capability to a functional outcome and an earned emotional outcome.",
            "Answer one real objection and end with the matched persona call to action.",
            "Connect the story to Infenergy's reason why without repeating a slogan.",
        ],
        "content_boundaries": list(brief.get("forbidden_claims") or []) + [
            "Do not invent demographic details, emergencies, fear, compatibility, runtime, or performance.",
            "Do not combine multiple personas or unrelated use cases in one post.",
        ],
        "personas": personas,
    }


def main() -> None:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(os.path.join(BRIEF_DIR, "*.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            brief = json.load(fh)
        product_id = str(brief.get("product_id") or brief.get("sku") or "").strip()
        if product_id:
            profiles[product_id] = build_profile(brief)
    payload = {
        "schema_version": "1.0",
        "purpose": "Consumer and messaging foundation for every Infenergy product-driven post.",
        "profiles": profiles,
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)
        fh.write("\n")
    print(f"Wrote {len(profiles)} product consumer profiles to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()