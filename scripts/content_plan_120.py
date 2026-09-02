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


PROFILE_PATH = os.path.join("marketing", "product_consumer_profiles.json")
COMPANY_KNOWLEDGE_PATH = os.path.join("marketing", "infenergy_company_knowledge.json")
BUNDLED_DATA_CANDIDATES = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data")),
    os.path.abspath(os.path.join(os.getcwd(), "data")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "data")),
)
BUNDLED_DATA_DIR = next(
    (candidate for candidate in BUNDLED_DATA_CANDIDATES if os.path.isfile(os.path.join(candidate, PROFILE_PATH))),
    BUNDLED_DATA_CANDIDATES[0],
)
DEFAULT_DATA_DIR = os.environ.get("DATA_DIR", BUNDLED_DATA_DIR)
MAX_PLAN_DAYS = 120

HORIZONS = (
    (14, "LOCKED", "Production-ready concepts"),
    (30, "SHAPED", "Approved concepts with adaptable execution"),
    (60, "ADAPTIVE", "Defined stories open to current context"),
    (90, "DIRECTIONAL", "Story arcs and product opportunities"),
    (120, "OPPORTUNITY", "Strategic direction and response reserve"),
)

LEGACY_WEEKLY_ARCS = (
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

LEGACY_ARC_PRODUCT_WEIGHTS = {
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

AUDIENCES = {
    "mobile_professional": {
        "name": "Mobile Professional / Digital Nomad",
        "demographic_lens": "Early- and mid-career remote or hybrid workers moving between home, cafes, cars, airports, client sites, and shared workspaces.",
        "psychographic": "Values autonomy, clean systems, momentum, and looking composed; resents wasted time, cable clutter, and planning life around outlets.",
        "desire": "Stay productive and creatively in motion without carrying a repair shop in a backpack.",
        "identity": "The person whose setup is as mobile and intentional as their ambition.",
        "language_style": "Sharp, design-aware, outcome-first, lightly witty",
        "primary_platform": "LinkedIn + Instagram",
    },
    "outdoor_enthusiast": {
        "name": "Outdoor / Adventure Enthusiast",
        "demographic_lens": "Weekend campers, road-trippers, RV and van-life travelers, photographers, festival crews, and outdoor households.",
        "psychographic": "Buys freedom, range, and memorable experiences rather than emergency gear; respects equipment that earns its space and dislikes fragile complexity.",
        "desire": "Stay out longer, pack smarter, and keep the experience feeling effortless.",
        "identity": "The friend who brings capability without turning the trip into a gear lecture.",
        "language_style": "Specific, visual, gear-aware, adventurous",
        "primary_platform": "Instagram + Facebook",
    },
    "caregiver": {
        "name": "Caregiver / Family Continuity Lead",
        "demographic_lens": "Parents, multigenerational households, adult children supporting elders, and the person who quietly carries the family logistics.",
        "psychographic": "Protective and practical; wants relief through clarity, not anxiety, and notices whether a plan can be handed to someone else.",
        "desire": "Keep care, comfort, communication, and household confidence intact when routines get disrupted.",
        "identity": "The calm center of the household, supported by a plan that does not live only in their head.",
        "language_style": "Warm, protective, precise, never sentimentalized",
        "primary_platform": "Facebook + Instagram",
    },
    "small_business_operator": {
        "name": "Small Business Operator",
        "demographic_lens": "Owner-operators, independent professionals, neighborhood retail and service businesses, creators, and lean teams.",
        "psychographic": "Protects momentum, reputation, revenue, and customer trust; thinks in workflows and hates preventable downtime disguised as bad luck.",
        "desire": "Keep the part of the business customers actually experience moving.",
        "identity": "The operator who sees the dependency before it becomes an excuse.",
        "language_style": "Decisive, commercially aware, concrete",
        "primary_platform": "LinkedIn + Facebook",
    },
    "preparedness_buyer": {
        "name": "Modern Preparedness Buyer",
        "demographic_lens": "Renters and homeowners, first-time preparedness shoppers, growing households, and practical buyers comparing compact through whole-home options.",
        "psychographic": "Wants control without fear culture, capability without visual clutter, and proof that a purchase fits real life rather than prepper theater.",
        "desire": "Build a right-sized system that feels considered, livable, and ready enough.",
        "identity": "Prepared, informed, and still living a normal modern life.",
        "language_style": "Confident, culturally current, plainspoken",
        "primary_platform": "Facebook + Instagram",
    },
}


def _episode(
    name: str,
    audience_id: str,
    *,
    territory: str,
    tension: str,
    setting: str,
    cultural_register: str,
    transformation: tuple[str, str],
    takeaway: str,
    cold_open: str,
    product_weights: dict[str, int],
) -> dict[str, Any]:
    return {
        **AUDIENCES[audience_id],
        "name": name,
        "territory": territory,
        "pillar": "modern_personal_energy",
        "audience_id": audience_id,
        "tension": tension,
        "setting": setting,
        "cultural_register": cultural_register,
        "transformation_from": transformation[0],
        "transformation_to": transformation[1],
        "takeaway": takeaway,
        "lesson": takeaway,
        "myth": f"More equipment automatically creates the identity and freedom promised by {name.lower()}.",
        "drill": f"Recreate the lived moment behind {name.lower()} and remove the first point of friction.",
        "cold_open": cold_open,
        "product_weights": product_weights,
    }


WEEKLY_ARCS = (
    _episode("The 3% Society", "mobile_professional", territory="Freedom, Designed", tension="battery percentage has started making decisions the person should be making", setting="an airport gate, rideshare, or client lobby where polished plans suddenly orbit one available outlet", cultural_register="premium travel comedy with quiet main-character confidence", transformation=("outlet_dependent", "portable"), takeaway="A clean mobile-power ritual protects momentum better than last-minute outlet hunting.", cold_open="At 84%, you have plans. At 3%, every outlet has excellent real estate.", product_weights={"power_bank": 12, "power_station": 5}),
    _episode("The Cable Drawer Cinematic Universe", "preparedness_buyer", territory="Prepared, Not Precious", tension="a supposedly complete setup is being held hostage by one mystery connector", setting="a beautiful modern home interrupted by the most chaotic cable drawer in North America", cultural_register="domestic observational comedy shot like a prestige mystery", transformation=("disorganized", "organized"), takeaway="The coolest setup is the one another person can understand in ten seconds.", cold_open="Every home has a cable drawer. Few have protected witness identities this thoroughly.", product_weights={"power_bank": 10, "preparedness_product": 8, "power_system_component": 7}),
    _episode("Soft Life, Hard Backup", "caregiver", territory="Care Without Chaos", tension="the person creating comfort is also carrying every invisible decision", setting="a calm, design-conscious family room prepared around one person, one need, and one honest comfort layer", cultural_register="warm lifestyle editorial with earned softness, not beige perfection", transformation=("overwhelmed", "simplified"), takeaway="Real comfort begins when responsibility is shared and every tool has an honest boundary.", cold_open="Soft life is not pretending nothing will happen. It is refusing to let one person carry the whole plan.", product_weights={"portable_fan": 12, "solar_light": 10, "power_bank": 7, "power_station": 6}),
    _episode("Your Office Has No Address", "mobile_professional", territory="Freedom, Designed", tension="the laptop is ready but the smaller device controlling the workflow is not", setting="a creator moving from cafe to parked car to client site with one deadline and no fixed desk", cultural_register="fast, polished workday documentary with creator-economy fluency", transformation=("frustrated", "confident"), takeaway="Power the workflow in sequence, not the device with the biggest screen.", cold_open="The laptop had 62%. The hotspot had 4%. Guess which one fired the boss.", product_weights={"power_bank": 12, "power_station": 9, "power_system_bundle": 5}),
    _episode("Main Character Range", "outdoor_enthusiast", territory="Range Is a Feeling", tension="freedom ends exactly where an untested assumption begins", setting="a road trip leaving the city with cameras, bikes, maps, and a destination beyond dependable outlets", cultural_register="kinetic road-film energy with gear used as part of the life, not displayed as inventory", transformation=("limited", "flexible"), takeaway="Range comes from matching equipment to the actual route, conditions, and return plan.", cold_open="Main-character energy is knowing where the day can go without asking an outlet for permission.", product_weights={"electric_bike": 12, "power_bank": 9, "solar_panel": 8, "portable_water_filter": 6}),
    _episode("The Family Group Chat Has Infrastructure", "caregiver", territory="Care Without Chaos", tension="everyone is connected until the one person with the plan becomes unreachable", setting="a multigenerational family coordinating school, work, elders, and weather through one very active group chat", cultural_register="recognizable family ensemble comedy with a calm emotional landing", transformation=("uncertain", "in_control"), takeaway="Communication continuity is people, roles, contacts, power, and a backup channel.", cold_open="The family group chat has 47 messages, three thumbs-up reactions, and no agreed first move.", product_weights={"power_bank": 11, "preparedness_product": 9, "power_station": 6}),
    _episode("Weekend Mode: Unplugged, Not Unprepared", "outdoor_enthusiast", territory="Range Is a Feeling", tension="the escape starts feeling like logistics because every device has a different plan", setting="a campsite at golden hour where music, light, airflow, cameras, and phones share one energy budget", cultural_register="aspirational outdoor lifestyle with knowing humor and zero survival cosplay", transformation=("disorganized", "organized"), takeaway="The best off-grid kit disappears into the experience because every item earns its space.", cold_open="You came to disconnect. Your devices arrived with separate demands.", product_weights={"solar_panel": 12, "solar_light": 11, "portable_fan": 10, "portable_water_filter": 8, "power_station": 7}),
    _episode("Roadside Plot Twist", "outdoor_enthusiast", territory="Range Is a Feeling", tension="a minor vehicle issue becomes four problems because safety, air, light, and communication were never designed together", setting="a safe roadside pull-off where one prepared driver moves through a clean sequence without performing heroics", cultural_register="tight thriller grammar resolved with competence instead of spectacle", transformation=("reactive", "prepared"), takeaway="Roadside confidence is a maintained sequence, not a gadget in the trunk.", cold_open="The tire was the plot twist. The dead jump starter was the unnecessary sequel.", product_weights={"vehicle_jump_starter": 14, "electric_bike": 9, "power_bank": 6, "power_system_component": 5}),
    _episode("Camp MVP Energy", "outdoor_enthusiast", territory="Range Is a Feeling", tension="one person brought plenty of gear but nobody assigned light, power, or recharge to the moments that matter", setting="friends transitioning from lake-day chaos to a sharp, relaxed campsite after dark", cultural_register="ensemble adventure comedy with one quietly capable MVP", transformation=("guessing", "informed"), takeaway="Capability looks effortless when the energy budget was decided before sunset.", cold_open="The camp MVP is not the person with the most gear. It is the person whose gear has jobs.", product_weights={"solar_panel": 12, "solar_light": 12, "portable_fan": 10, "portable_water_filter": 9, "power_station": 8}),
    _episode("Sun Chaser Math", "outdoor_enthusiast", territory="Range Is a Feeling", tension="the aesthetic says endless solar while clouds, shade, angle, and active loads keep editing the result", setting="one photogenic solar setup followed from perfect morning light into a very ordinary cloudy afternoon", cultural_register="beautiful expectation-versus-reality storytelling with technical credibility", transformation=("guessing", "informed"), takeaway="Solar freedom gets more believable when weather is included in the math.", cold_open="The sun is free. Your energy budget still needs a manager.", product_weights={"solar_panel": 14, "solar_light": 10, "power_system_bundle": 8, "power_station": 7}),
    _episode("The Business Behind the Business", "small_business_operator", territory="Never Miss the Moment", tension="the visible equipment has power while the tiny dependency customers actually touch goes down", setting="a neighborhood studio, shop, food business, or mobile service protecting one customer-critical transaction", cultural_register="founder-mode case study with editorial restraint and real operational stakes", transformation=("slow", "efficient"), takeaway="Continuity belongs to the customer journey and its weakest required step.", cold_open="The lights were on. The payment screen was not. Customers only noticed one of those facts.", product_weights={"power_station": 12, "power_system_bundle": 11, "power_bank": 7}),
    _episode("Small Space, Serious Energy", "preparedness_buyer", territory="Prepared, Not Precious", tension="traditional preparedness advice assumes a garage, unlimited storage, and permission the customer does not have", setting="a renter-friendly apartment with a shelf-sized system and no tactical-catalog aesthetic", cultural_register="urban design editorial: compact, intentional, visibly livable", transformation=("overwhelmed", "simplified"), takeaway="A serious plan can be compact when it is built around priorities, building rules, and an exit decision.", cold_open="Preparedness does not require a bunker. Sometimes it requires one shelf that makes sense.", product_weights={"power_bank": 11, "power_station": 9, "portable_fan": 8, "solar_light": 7}),
    _episode("Forecast Mode", "preparedness_buyer", territory="Prepared, Not Precious", tension="the forecast is getting louder while the household still has not decided what would change its behavior", setting="a Gulf Coast household checking weather, calendars, charging, food, and family logistics before urgency arrives", cultural_register="weather-app realism with calm, fashion-forward household competence", transformation=("reactive", "prepared"), takeaway="A forecast becomes useful when it triggers a specific, proportionate action.", cold_open="Weather alerts are not a personality test. Decide what each one actually changes.", product_weights={"preparedness_product": 12, "power_station": 10, "power_system_bundle": 9, "solar_panel": 5}),
    _episode("The Block Has a Backup Plan", "caregiver", territory="Care Without Chaos", tension="everyone says call if you need anything but nobody has defined what anything means", setting="neighbors turning a porch hang into a four-line agreement about contacts, check-ins, capabilities, and boundaries", cultural_register="community ensemble warmth with block-party confidence, never staged charity", transformation=("dependent", "prepared"), takeaway="Mutual aid becomes real when help is specific enough to keep.", cold_open="Good neighbors bring more than vibes. They bring a contact, a time, a capability, and a boundary.", product_weights={"power_station": 10, "power_system_bundle": 9, "preparedness_product": 9}),
    _episode("Water Has Main-Character Stakes", "caregiver", territory="Care Without Chaos", tension="the household owns a treatment product but has not connected source, storage, access, maintenance, and power", setting="a multigenerational kitchen mapping one ordinary day of water from source to safe use", cultural_register="clean investigative editorial centered on dignity and care", transformation=("uncertain", "in_control"), takeaway="Water readiness is a system, and the product is only one scene in it.", cold_open="The filter is not the water plan. It is one cast member with a very specific role.", product_weights={"portable_water_filter": 14, "power_station": 7, "power_system_bundle": 7}),
    _episode("Specs With Red Flags", "preparedness_buyer", territory="Prepared, Not Precious", tension="the biggest number is getting all the attention while compatibility and practical constraints decide the relationship", setting="a buyer swiping through product pages like dating profiles, rejecting impressive but mismatched options", cultural_register="smart consumer comedy with premium comparison-show pacing", transformation=("guessing", "informed"), takeaway="Fit lives in the supporting specifications, not the loudest number.", cold_open="A huge watt-hour number is attractive. Ask what it is like in a relationship.", product_weights={"power_system_component": 12, "expansion_battery": 12, "power_station": 10, "power_system_bundle": 10}),
    _episode("Pass the Power", "caregiver", territory="Care Without Chaos", tension="the household system becomes private expertise the second its author leaves the room", setting="another family member taking over the first five minutes while the usual planner stays silent", cultural_register="warm competence challenge with playful family dynamics", transformation=("dependent", "prepared"), takeaway="A household plan becomes real when capability survives the handoff.", cold_open="If the plan begins with 'just ask me,' it is not a plan yet.", product_weights={"preparedness_product": 11, "power_system_component": 10, "power_system_bundle": 9, "power_station": 8}),
    _episode("Big Energy, Better Taste", "preparedness_buyer", territory="Prepared, Not Precious", tension="more capacity is being treated as permission to stop prioritizing", setting="a modern home integrating larger stored energy without turning every outlet into a demand", cultural_register="architectural product editorial with disciplined luxury and no macho excess", transformation=("uncertain", "in_control"), takeaway="The larger the system, the more intentional the priorities, ownership, and recovery plan must become.", cold_open="Big energy is not powering everything. It is knowing exactly what deserves power next.", product_weights={"power_system_bundle": 14, "expansion_battery": 11, "power_station": 10}),
)

ARC_PRODUCT_WEIGHTS = {
    arc["name"]: arc["product_weights"]
    for arc in WEEKLY_ARCS
}

AUDIENCE_PRODUCT_WEIGHTS = {
    "mobile_professional": {"power_bank": 8, "power_station": 5, "preparedness_product": 4},
    "outdoor_enthusiast": {"power_bank": 5, "power_station": 6, "solar_panel": 7, "solar_light": 7, "portable_fan": 7, "portable_water_filter": 6, "vehicle_jump_starter": 6, "electric_bike": 6},
    "caregiver": {"power_bank": 5, "power_station": 7, "power_system_bundle": 7, "preparedness_product": 7, "portable_fan": 6, "portable_water_filter": 6},
    "small_business_operator": {"power_bank": 5, "power_station": 8, "power_system_bundle": 8, "expansion_battery": 6, "power_system_component": 6},
    "preparedness_buyer": {"power_bank": 5, "power_station": 8, "power_system_bundle": 8, "expansion_battery": 7, "power_system_component": 7, "solar_panel": 5, "preparedness_product": 7},
}


def _load_catalog(data_dir: str) -> list[dict[str, Any]]:
    path = os.path.join(data_dir, PROFILE_PATH)
    if not os.path.isfile(path):
        path = os.path.join(BUNDLED_DATA_DIR, PROFILE_PATH)
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


def _load_company_thoughts(data_dir: str) -> tuple[str, list[dict[str, Any]]]:
    paths = [os.path.join(data_dir, COMPANY_KNOWLEDGE_PATH)]
    paths.extend(os.path.join(candidate, COMPANY_KNOWLEDGE_PATH) for candidate in BUNDLED_DATA_CANDIDATES)
    for path in dict.fromkeys(paths):
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        thoughts = [
            thought for thought in payload.get("thought_library", [])
            if isinstance(thought, dict) and thought.get("id") and thought.get("statement")
        ] if isinstance(payload, dict) else []
        thought_by_id = {str(thought["id"]): thought for thought in thoughts}
        messages = []
        for message in payload.get("super_message_library", []) if isinstance(payload, dict) else []:
            if not isinstance(message, dict) or not message.get("id") or not message.get("statement"):
                continue
            support = thought_by_id.get(str(message.get("support_thought_id") or ""))
            if support:
                messages.append({**support, **message, "support_statement": support["statement"]})
        if messages:
            return str(payload.get("knowledge_id") or "infenergy-company-truth"), messages
    raise ValueError("verified Infenergy super messages are unavailable")


def _select_company_thought(
    thoughts: list[dict[str, Any]],
    arc: dict[str, str],
    used_thought_ids: set[str],
) -> dict[str, Any]:
    audience_map = {
        "mobile_professional": "mobile_professional",
        "outdoor_enthusiast": "outdoor",
        "caregiver": "caregiver",
        "small_business_operator": "mobile_professional",
        "preparedness_buyer": "preparedness_builder",
    }
    target_audience = audience_map.get(arc["audience_id"], "working_family")
    available = [thought for thought in thoughts if str(thought["id"]) not in used_thought_ids] or thoughts
    return max(
        available,
        key=lambda thought: (
            8 if thought.get("audience") == target_audience else 0,
            5 if thought.get("pillar") == arc.get("pillar") else 0,
            _text_relevance([
                thought.get("statement"), thought.get("expansion"), thought.get("useful_detail"),
            ], arc),
            -thoughts.index(thought),
        ),
    )


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
    episode_score = ARC_PRODUCT_WEIGHTS.get(arc["name"], {}).get(product["product_type"], 0)
    audience_score = AUDIENCE_PRODUCT_WEIGHTS.get(arc["audience_id"], {}).get(product["product_type"], 0)
    type_score = episode_score + audience_score
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
        "product_micro_mission_comic": "Superhero with text",
        "educational_story_carousel": "Educational story carousel",
    }
    resolutions = (
        "Freeze the scene at the bad assumption. Infenergy enters like the smartest friend in the group chat, names the hidden dependency, and gives the product one honest mission.",
        "Start with a stylish plan going sideways. Infenergy strips away the clutter, keeps what serves the life, and hands control back to the person.",
        "Treat the overlooked dependency like the reveal in a heist film. Infenergy identifies it, matches capability to the moment, and lets competence deliver the payoff.",
        "Open on the oversized flex. Infenergy rejects more-for-more's-sake, chooses the right-sized move, and makes restraint look more powerful than excess.",
    )
    title = f"Infenergy Intervention #{installment}: {arc['name']}"
    hook = arc["cold_open"]
    visible_text = None
    story_comic_contract = {}
    if preferred_format == "product_micro_mission_comic":
        visible_text = {
            "headline": hook,
            "infenergy_line": "Pause. What job does the power actually need to do?",
            "resolution_line": arc["takeaway"],
        }
        story_comic_contract = {
            "delivery_label": "Product Story comic strip",
            "platform": "instagram_story",
            "aspect_ratio": "9:16",
            "canvas_px": {"width": 1080, "height": 1920},
            "canvas_count": 1,
            "panel_count": 3,
            "layout": "single_vertical_comic_strip",
            "product_required": True,
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "product_role": product["product_role"],
            "product_proof_direction": product["proof_direction"],
            "product_reference_required": True,
            "story_sequence": [
                "Panel 1: the human problem and bad assumption interrupt the routine.",
                "Panel 2: Infenergy identifies the hidden energy job and physically uses the verified product for that job.",
                "Panel 3: show the human consequence and honest product boundary; the person owns the resolution.",
            ],
            "delivery_constraints": [
                "one full-bleed 1080 x 1920 image containing three readable comic panels",
                "not a carousel and not three separate images",
                "use the verified product reference without redesigning or inventing features",
                "keep all exact dialogue inside Instagram Story safe areas",
            ],
        }
    return {
        "series": series["name"],
        "series_id": series["id"],
        "installment": installment,
        "format": preferred_format,
        "format_label": format_labels[preferred_format],
        "visible_text": visible_text,
        "title": title,
        "hook": hook,
        "story": f"Cold-open in {arc['setting']}. The consumer wants {arc['desire'].lower()}, but {arc['tension']}. {resolutions[(installment - 1) % len(resolutions)]}",
        "takeaway": arc["takeaway"],
        "cta": product["cta"],
        "character": "Infenergy",
        "character_role": "Culturally fluent capability guide, never a product mascot",
        "canon_required": True,
        **story_comic_contract,
    }


FUNNEL_CYCLE = (
    "ATTENTION", "EDUCATION", "DESIRE", "TRUST", "EDUCATION",
    "DESIRE", "ATTENTION", "EDUCATION", "DESIRE", "CONVERSION",
    "TRUST", "EDUCATION", "DESIRE", "ATTENTION", "TRUST",
    "EDUCATION", "DESIRE", "ATTENTION", "EDUCATION", "CONVERSION",
)

DAY_STRATEGY = {
    0: ("Culture Current", "cultural_observation", "NOTICE", "RECOGNITION", "SHARE"),
    1: ("Infenergy Intervention", "entertainment_franchise", "REFRAME", "CAPABILITY", "EXPLORE"),
    2: ("The Fit Check", "product_lifestyle_proof", "DISTINGUISH", "CONFIDENCE", "COMPARE"),
    3: ("POV: Power Moves", "character_micro_story", "DISCOVER", "CURIOSITY", "RESPOND"),
    4: ("Infenergy Intervention", "entertainment_franchise", "PRIORITIZE", "CONTROL", "EXPLORE"),
    5: ("Try This IRL", "social_challenge", "PLAN", "READINESS", "SAVE"),
    6: ("Energy Is an Identity", "brand_world_statement", "RECONSIDER", "FREEDOM", "FOLLOW"),
}

POST_TYPE_LABELS = {
    "current_event": "Current event / timely response",
    "product_education": "Product education",
    "statement": "Brand statement",
    "humor": "Culture-led humor",
    "framework": "Planning framework",
    "micro_story": "Human micro-story",
    "explainer": "Practical explainer",
    "drill": "IRL drill",
    "myth": "Myth-busting",
}

POST_TYPES_BY_WEEKDAY = {
    0: ("current_event", "humor", "myth"),
    1: ("micro_story", "product_education", "explainer"),
    2: ("product_education", "explainer", "framework"),
    3: ("micro_story", "humor", "current_event"),
    4: ("explainer", "product_education", "micro_story"),
    5: ("drill", "framework", "drill"),
    6: ("statement", "myth", "statement"),
}


def _post_type(day_number: int, weekday: int) -> str:
    week_index = (day_number - 1) // 7
    choices = POST_TYPES_BY_WEEKDAY[weekday]
    return choices[week_index % len(choices)]


def _apply_post_type_treatment(
    base: dict[str, Any],
    post_type: str,
    arc: dict[str, str],
    product: dict[str, str] | None,
) -> dict[str, Any]:
    treated = dict(base)
    product_name = product["product_name"] if product else "the relevant capability"
    if post_type == "current_event":
        treated["title"] = f"Timely Response: {arc['name']}"
        treated["hook"] = "What changed this week, and what does it actually change for this audience?"
        treated["story"] = f"At production time, attach one verified, current source to {arc['tension']}. Separate what happened, what remains unknown, and the one proportionate action that matters to {arc['audience_id'].replace('_', ' ')}. Never invent or pre-write a future event."
    elif post_type == "product_education":
        treated["story"] = f"Teach one verified job for {product_name} inside {arc['setting']}. Show the fit, the operating boundary, and the comparison question a buyer should ask; do not turn the product into the hero or imply it replaces the wider plan."
    elif post_type == "humor":
        treated["title"] = f"The Very Modern Problem: {arc['name']}"
        treated["story"] = f"Write a sharply observed comedy scene in {arc['setting']} where {arc['tension']}. Let recognition earn the laugh, then land on the useful truth: {arc['takeaway']}"
    elif post_type == "framework":
        treated["title"] = f"The 3-Part Framework: {arc['name']}"
        treated["hook"] = "Three decisions. One setup another person can actually use."
        treated["story"] = f"Turn {arc['drill']} into a three-step tool: name the lived priority, identify the first dependency, and choose the smallest capability that closes it. Apply the framework to {product_name} when a product is present."
    elif post_type == "explainer":
        treated["title"] = f"Explain It Like It Matters: {arc['name']}"
        treated["story"] = f"Explain the mechanism behind {arc['tension']} in plain language. Use {product_name} only as a verified example, distinguish capacity from outcome, and end with the decision the audience can now make more confidently."
    elif post_type == "drill":
        treated["title"] = f"60-Second Drill: {arc['name']}"
        treated["hook"] = "Run the handoff before the real moment asks for it."
        treated["story"] = f"Run this rehearsal: {arc['drill']} Give a second person sixty seconds to find the tool, explain its job and limit, and make the first move without coaching. Record the friction, not a performance."
    elif post_type == "myth":
        treated["title"] = f"Myth Check: {arc['name']}"
        treated["hook"] = f"Myth: {arc['myth']}"
        treated["story"] = f"Name why the myth feels attractive, show where it fails inside {arc['setting']}, and replace it with a more useful belief: {arc['takeaway']}"
    return treated


def _daily_concept(
    *,
    current_date: date,
    day_number: int,
    arc: dict[str, str],
    product: dict[str, str] | None,
    intervention_number: int,
    company_knowledge_id: str,
    company_thought: dict[str, Any] | None,
) -> dict[str, Any]:
    weekday = current_date.weekday()
    base: dict[str, Any]
    slot = "midday"
    series, creative_mode, brain_movement, heart_after, natural_response = DAY_STRATEGY[weekday]
    post_type = _post_type(day_number, weekday)
    funnel_stage = FUNNEL_CYCLE[(day_number - 1) % len(FUNNEL_CYCLE)]
    if weekday == 0:
        base = {
            "series": series,
            "format": "culture_carousel",
            "format_label": "Culture-led carousel",
            "title": f"Culture Current: {arc['name']}",
            "hook": arc["cold_open"],
            "story": f"Use {arc['cultural_register']} to decode a behavior this audience instantly recognizes. Begin in {arc['setting']}; move from the joke or observation into the real desire: {arc['desire']}",
            "takeaway": arc["takeaway"],
            "cta": "Send this to the person whose setup has this exact personality.",
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
            "series": series,
            "format": "product_proof_story",
            "format_label": "Lifestyle fit check",
            "title": f"The Fit Check: {product['product_name']} x {arc['name']}",
            "hook": f"The flex is not owning more power. It is carrying exactly what this life asks for.",
            "story": f"Follow {product['persona']} through {product['use_case']} inside {arc['setting']}. Judge {product['product_name']} on three modern-consumer questions: does it fit the routine, earn its space, and support the identity without pretending to replace the whole plan? Use only verified proof: {product['proof_direction']}",
            "takeaway": product["customer_truth"] or arc["takeaway"],
            "cta": product["cta"],
        }
    elif weekday == 3:
        base = {
            "series": series,
            "format": "documentary_micro_story",
            "format_label": "POV micro-story",
            "title": f"POV: The Moment You Felt {arc['transformation_to'].replace('_', ' ').title()}",
            "hook": f"The before: {arc['transformation_from'].replace('_', ' ')}. The after: {arc['transformation_to'].replace('_', ' ')}. The difference was one clear decision.",
            "story": f"Tell a first-person, scene-first story in {arc['setting']}. Show the exact instant the character notices that {arc['tension']}, makes one intelligent move, and starts becoming {arc['identity'].lower()}",
            "takeaway": arc["takeaway"],
            "cta": "What is the one decision that would change this scene for you?",
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
            "series": series,
            "format": "challenge_carousel",
            "format_label": "IRL challenge carousel",
            "title": f"Try This IRL: {arc['name']}",
            "hook": f"Can your setup deliver the feeling it advertises? Ten minutes. No shopping. No pretending.",
            "story": f"Build a social challenge around {arc['setting']}. Ask the audience to recreate the moment, name what they assumed, remove the first friction point, and share the one change that made the setup feel more {arc['transformation_to'].replace('_', ' ')}.",
            "takeaway": "Modern preparedness is tested capability, not an equipment aesthetic.",
            "cta": "Save the challenge, run it this weekend, and post the one thing you changed.",
        }
    else:
        if company_thought is None:
            raise ValueError("Sunday company quote requires a verified Infenergy thought")
        statement = str(company_thought["statement"])
        base = {
            "series": "Infenergy Company Voice",
            "format": "infenergy_company_quote_visual",
            "format_label": "Infenergy quote in the scene",
            "delivery_label": "Single-frame integrated typography",
            "title": statement,
            "hook": statement,
            "story": f"{company_thought.get('expansion', '')} {company_thought.get('useful_detail', '')}".strip(),
            "takeaway": statement,
            "cta": str(company_thought.get("action") or company_thought.get("prompt") or "Choose one useful next step."),
            "character": "Infenergy",
            "character_role": "Infenergy physically acts on the sourced company truth; never pose beside a quote card.",
            "canon_required": True,
            "platform": "instagram",
            "aspect_ratio": "4:5",
            "canvas_px": {"width": 1080, "height": 1350},
            "canvas_count": 1,
            "layout": "single_frame_integrated_typography",
            "integrated_typography": True,
            "exact_visible_text": [statement],
            "typography_material": "scene-authentic physical material",
            "infenergy_action": f"Infenergy physically changes, powers, repairs, carries, enters, or redirects the exact words {statement} as part of the environment.",
            "verbatim_company_quote": True,
            "company_source": {
                "knowledge_id": company_knowledge_id,
                "message_id": str(company_thought["id"]),
                "support_thought_id": str(company_thought["support_thought_id"]),
                "statement": statement,
                "audience": str(company_thought.get("audience") or ""),
                "pillar": str(company_thought.get("pillar") or ""),
            },
            "support_statement": str(company_thought.get("support_statement") or ""),
            "source_expansion": str(company_thought.get("expansion") or ""),
            "source_useful_detail": str(company_thought.get("useful_detail") or ""),
            "source_prompt": str(company_thought.get("prompt") or ""),
            "delivery_constraints": [
                "one full-bleed 1080 x 1350 image",
                "the sourced statement appears exactly once with no additional visible copy",
                "Infenergy physically interacts with the exact words as part of one cohesive scene",
                "no quote card, static pose, carousel, product claim, or generic superhero redesign",
            ],
        }
    base = _apply_post_type_treatment(base, post_type, arc, product)
    return {
        "date": current_date.isoformat(),
        "day_number": day_number,
        "weekday": current_date.strftime("%A"),
        "slot": slot,
        "week": ((day_number - 1) // 7) + 1,
        "weekly_arc": arc["name"],
        "creative_territory": arc["territory"],
        "pillar": arc["pillar"],
        "audience_id": arc["audience_id"],
        "audience_name": AUDIENCES[arc["audience_id"]]["name"],
        "demographic_lens": arc["demographic_lens"],
        "psychographic": arc["psychographic"],
        "consumer_desire": arc["desire"],
        "identity_signal": arc["identity"],
        "transformation": {
            "from": arc["transformation_from"],
            "to": arc["transformation_to"],
        },
        "cultural_register": arc["cultural_register"],
        "human_reality": arc["tension"],
        "brain_movement": brain_movement,
        "heart_after": heart_after,
        "human_value": arc["desire"],
        "content_job": creative_mode,
        "post_type": post_type,
        "post_type_label": POST_TYPE_LABELS[post_type],
        "funnel_stage": funnel_stage,
        "primary_platform": arc["primary_platform"],
        "platform_treatment": f"Lead on {arc['primary_platform']} in a {arc['language_style'].lower()} voice; preserve the lived moment before adapting length.",
        "natural_response": natural_response,
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
    company_knowledge_id, company_thoughts = _load_company_thoughts(data_dir)
    product_assignments = _assign_products(catalog, start, days)
    entries: list[dict[str, Any]] = []
    intervention_number = 0
    used_thought_ids: set[str] = set()
    for offset in range(days):
        current_date = start + timedelta(days=offset)
        arc = WEEKLY_ARCS[(offset // 7) % len(WEEKLY_ARCS)]
        product = None
        if offset in product_assignments:
            raw_product, product_placement = product_assignments[offset]
            product = _product_context(raw_product, product_placement, arc)
        if current_date.weekday() in {1, 4}:
            intervention_number += 1
        company_thought = None
        if current_date.weekday() == 6:
            company_thought = _select_company_thought(company_thoughts, arc, used_thought_ids)
            used_thought_ids.add(str(company_thought["id"]))
        entries.append(_daily_concept(
            current_date=current_date,
            day_number=offset + 1,
            arc=arc,
            product=product,
            intervention_number=intervention_number,
            company_knowledge_id=company_knowledge_id,
            company_thought=company_thought,
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
        "date_coverage": {
            "expected_days": days,
            "planned_days": len({entry["date"] for entry in entries}),
            "continuous": all(
                entry["date"] == (start + timedelta(days=index)).isoformat()
                for index, entry in enumerate(entries)
            ),
        },
        "post_type_taxonomy": POST_TYPE_LABELS,
        "post_type_counts": {
            post_type: sum(1 for entry in entries if entry["post_type"] == post_type)
            for post_type in POST_TYPE_LABELS
        },
        "format_counts": {
            format_name: sum(1 for entry in entries if entry["format"] == format_name)
            for format_name in sorted({entry["format"] for entry in entries})
        },
        "superhero_with_text_count": sum(
            1 for entry in entries if entry["format"] == "product_micro_mission_comic"
        ),
        "weekly_company_quote_count": sum(
            1 for entry in entries if entry["format"] == "infenergy_company_quote_visual"
        ),
        "company_super_message_bank_count": len(company_thoughts),
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