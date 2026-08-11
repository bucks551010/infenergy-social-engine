"""Business identity + why + worldview + brand DNA synthesis.

Master Build §11-§14, §25-§30.

Source of truth (in descending authority):
  1. Owner assertions (``founder_brand_manifesto.json``)
  2. Recent brand profiles (``data/marketing/brand_profile_*.json``)
  3. Documented claims from marketing bundles / strategies
  4. Inferences from the offering catalog + social library

Every derived field is written back as an evidence record with the
correct information type so the Profile assembler + Critic can trace
provenance.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any

from . import evidence, paths
from .schemas import (
    BrandPosture,
    BrandPromise,
    BusinessIdentity,
    BusinessJob,
    BusinessWhy,
    Positioning,
    Reputation,
    VisualDNA,
    VoiceDNA,
    Worldview,
)


# --- Owner-authoritative loaders ---------------------------------------


def load_manifesto() -> dict[str, Any]:
    p = paths.founder_manifesto_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def load_latest_brand_profile() -> dict[str, Any]:
    p = sorted(glob.glob(os.path.join(paths.marketing_dir(), "brand_profile_*.json")))
    if not p:
        return {}
    try:
        with open(p[-1], "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


# --- Synthesis ---------------------------------------------------------


def _first_nonempty(*values: Any) -> Any:
    for v in values:
        if v not in ("", None, [], {}):
            return v
    return ""


def build_identity() -> BusinessIdentity:
    man = load_manifesto()
    bp = load_latest_brand_profile()
    business_profile = man.get("business_profile", {}) if isinstance(man, dict) else {}
    return BusinessIdentity(
        business_name=_first_nonempty(man.get("brand_name"), bp.get("brand_name"), "Infenergy Power"),
        business_description=_first_nonempty(business_profile.get("positioning"), bp.get("positioning_statement")),
        business_type="ecommerce_product_brand",
        industry="Portable power / preparedness",
        subindustries=["Backup power", "Solar power", "Emergency preparedness", "Outdoor/mobile power"],
        business_model="direct-to-consumer product sales + educational content",
        commercial_model="one-time purchase (products); no subscription",
        geographic_relevance="United States (primary)",
        stage="operating",
        primary_category=_first_nonempty(business_profile.get("primary_category"), "Portable power"),
        secondary_categories=list(business_profile.get("what_we_sell", [])),
        what_we_do=list(business_profile.get("what_we_sell", [])),
        what_we_do_not_do=list(business_profile.get("what_we_do_not_position_as", [])),
    )


def build_why() -> BusinessWhy:
    man = load_manifesto()
    origin = man.get("origin_story", {}) if isinstance(man, dict) else {}
    return BusinessWhy(
        reason_for_existence=_first_nonempty(origin.get("why_it_matters"), man.get("mission")),
        foundational_problem=origin.get("problem", ""),
        mission=man.get("mission", ""),
        vision=man.get("vision", ""),
        purpose=origin.get("why_it_matters", ""),
        beliefs=list(man.get("core_values", [])),
        principles=list(man.get("core_values", [])),
        worldview="Preparedness is safety, connection, and control — not fear.",
        desired_customer_impact="Households and mobile users stay powered, safe, and connected when normal systems fail.",
        future_state_we_want_to_help_create="Everyday preparedness that reduces panic and protects routines during power disruption.",
        why_customers_should_matter_to_us="Because power failure creates real safety and continuity risk for real families.",
        why_we_want_people_to_purchase="So they own capable, matched-to-need power before they need it — not during a crisis.",
        why_the_business_deserves_to_exist="Existing power-product sellers commoditize devices; families need product-fit guidance for real scenarios.",
    )


def build_worldview() -> Worldview:
    man = load_manifesto()
    return Worldview(
        market_beliefs=[
            "Most power products are sold on spec sheets, not on how they fit a real outage",
            "Preparedness content is often fear-based instead of practically empowering",
        ],
        customer_deserves=[
            "Straight answers about what to power first",
            "Practical fit guidance, not one-size-fits-all recommendations",
            "Plain-language translation of technical specs",
        ],
        unnecessary_difficulties=[
            "Deciding capacity vs runtime vs port compatibility from raw datasheets",
            "Choosing between overselling ‘survival’ marketing and true preparedness",
        ],
        conventional_agrees_with=[
            "Backup power belongs in homes, backpacks, and glove boxes",
        ],
        conventional_challenges=[
            "Larger is always better — actually, matched-to-need is better",
            "Preparedness has to be fear-driven",
        ],
        enduring_principles=list(man.get("core_values", [])) or [
            "Preparedness without fear-mongering",
            "Product-fit over generic recommendations",
        ],
        supported_progress=[
            "Cleaner off-grid capability",
            "Household resilience during outages",
        ],
        would_never_encourage=[
            "Panic-buying based on hypothetical worst-cases",
            "Overspending on capacity a household will never actually use",
        ],
    )


def build_job() -> BusinessJob:
    return BusinessJob(
        functional_job="Sell matched-to-need portable and backup power devices",
        emotional_job="Help customers feel prepared, capable, and in control",
        educational_job="Teach practical capacity/runtime/port fit for real scenarios",
        decision_support_job="Guide customers to the right device for their actual loads",
        community_job="Build a preparedness-minded community that shares practical knowledge",
        commercial_job="Move customers from browsing to a confident matched purchase",
    )


def build_positioning() -> Positioning:
    bp = load_latest_brand_profile()
    return Positioning(
        market_category="Preparedness-first portable and backup power",
        category_role="Educator + trusted guide (not commodity reseller)",
        competitive_frame="Big-box branded generators; Amazon commodity power banks; ‘survival’ brands",
        direct_alternatives=["Anker", "Jackery", "EcoFlow", "Bluetti", "Generac"],
        indirect_alternatives=["Wall-outlet-only life", "Gas generator only", "Doing nothing"],
        status_quo_alternative="No backup — hope the outage is short",
        primary_position="Preparedness-first portable power for real families, not doomsday marketing",
        secondary_positions=["Practical off-grid capability", "Product-fit coaching"],
        differentiators=[
            "Mission-led preparedness lifestyle without fear-mongering",
            "Product-fit guidance instead of spec-sheet selling",
            "Outcome-focused education for real emergency scenarios",
        ],
        reasons_to_believe=[
            "Founder built the brand after a personal storm outage",
            "Product-brief system tuned to real load matching",
        ],
        positioning_strength=0.7,
        positioning_risks=[
            "Category is crowded and commoditizing",
            "Preparedness framing risks slipping into fear marketing",
        ],
        positioning_whitespace=[
            "Plain-language power education aimed at first-time buyers",
            "Preparedness content that respects the customer",
        ],
    )


def build_promise() -> BrandPromise:
    return BrandPromise(
        promise="Stay powered, prepared, and in control when normal systems fail.",
        business_capability="Curated preparedness-first product catalog with per-SKU fit guidance",
        offering_capability="Matched portable + backup power devices from vetted brands",
        customer_outcome="Household + mobile continuity during outages and off-grid moments",
    )


def build_reputation() -> Reputation:
    return Reputation(
        desired_reputation="The brand that quietly helped my family stay powered — without scaring us into it.",
        desired_associations=["preparedness", "reliability", "practical guidance", "calm", "trusted"],
        desired_emotions=["confidence", "calm", "capability", "protection"],
        desired_customer_language=["prepared", "matched to my need", "ready", "peace of mind"],
        trust_attributes=["transparent specs", "no invented claims", "founder-led"],
        authority_attributes=["real-scenario fit guidance", "load-matching literacy"],
        community_attributes=["preparedness-minded", "practical", "helpful"],
        undesired_associations=["doomsday", "prepper stereotype", "fear-based", "spec-sheet commodity"],
        reputation_risks=["overpromising runtime", "conflating solar power with residential solar installation"],
    )


def build_voice() -> VoiceDNA:
    man = load_manifesto()
    personality = man.get("brand_personality", {}) if isinstance(man, dict) else {}
    return VoiceDNA(
        brand_personality=personality.get("voice_name", "Calm Strength"),
        voice_principles=list(personality.get("tone_rules", [])),
        voice_traits=list(personality.get("traits", [])),
        tone_range=["calm", "confident", "practical", "warm", "urgent-when-justified"],
        sentence_style="short-to-medium; concrete nouns; plain verbs",
        rhythm="steady; occasional pattern-interrupt for emphasis",
        technical_depth="moderate — always translate specs to outcomes",
        humor_policy="light, dry, never at customer expense",
        confidence_level="assured, not arrogant",
        warmth_level="warm, protective",
        authority_level="coach-like",
        directness_level="direct — one clear next step",
        preferred_phrases=["matched to your need", "powered when it matters", "practical fit"],
        prohibited_phrases=[
            "life-saving", "guaranteed", "unbreakable",
            "revolutionize", "game-changer",
            "SHTF", "doomsday", "panic",
        ],
        cliches_to_avoid=["in today's fast-paced world", "unlock the power", "elevate your"],
        claims_language="only what is verified in the catalog or manifesto",
        cta_style="one clear, low-friction step",
        storytelling_style="real-scenario vignette, then practical resolution",
        educational_style="translate the spec into outcome and mechanism",
        community_style="peer-to-peer, no gatekeeping",
        sales_style="confident, product-fit-first",
        platform_variations={
            "instagram": "visual-first; short caption; save-worthy takeaway",
            "facebook": "story-forward; conversation-friendly",
            "linkedin": "authority + educational framing",
        },
    )


def build_visual() -> VisualDNA:
    return VisualDNA(
        brand_colors={"primary": "#0A2540", "secondary": "#1C7C9B", "accent": "#F5A623"},
        accent_palette=["#F5A623", "#2E7D32"],
        neutral_palette=["#F7F8FA", "#E5E9EE", "#333333"],
        heading_font="Inter",
        body_font="Inter",
        typography_behavior="Large, high-contrast headlines; generous negative space; consistent grid",
        spacing_system="8pt baseline; safe padding 64px",
        border_radius="24px",
        icon_style="line, weighted, functional",
        photography_style="honest editorial daylight; real household + outdoor contexts; no fake studios",
        illustration_style="clean vector; brand-color-limited; explanatory",
        graphic_density="low-to-medium; readable at thumb size",
        background_style="neutral, non-cliche",
        shadow_rules="soft, physical, restrained",
        image_tone="calm, capable, honest",
        visual_energy="quiet confidence",
        brand_mood="prepared, warm, in-control",
        product_representation_rules=[
            "Show real product assets when available",
            "Never AI-recreate product ports, buttons, or brand marks",
            "Never invent certification labels",
        ],
        human_representation_rules=[
            "Real household + outdoor scenarios",
            "No exaggerated fear expressions",
            "Diverse, everyday people",
        ],
        composition_preferences=["clear focal point", "generous negative space", "thumb-readable"],
        visual_metaphor_policy="metaphors must relate to actual product function or the customer's real scenario",
        prohibited_visual_patterns=[
            "cyberpunk neon UI",
            "generic smiling stock person",
            "fake certification badges",
            "doomsday/disaster porn",
            "impossible product renders",
        ],
        accessibility_requirements=["min contrast 4.5:1", "min body 28px", "min headline 56px"],
    )


def build_posture() -> BrandPosture:
    return BrandPosture(
        how_the_brand_speaks="calm, direct, practical",
        how_the_brand_teaches="translate spec → outcome → mechanism",
        how_the_brand_sells="fit-first: help them pick the right device",
        how_the_brand_disagrees="respectfully; with the mechanism, not with condescension",
        how_the_brand_handles_uncertainty="says 'we don't know yet' rather than inventing",
        how_the_brand_handles_risk="warns without fear-mongering",
        how_the_brand_handles_customer_questions="answers in plain language + one concrete next step",
        how_the_brand_handles_mistakes="acknowledges + corrects + explains what changed",
        how_the_brand_handles_comparison="honest side-by-side; never fake comparison",
        how_the_brand_handles_urgency="only when a real seasonal or safety trigger justifies it",
    )
