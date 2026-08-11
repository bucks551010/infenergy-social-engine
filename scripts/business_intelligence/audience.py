"""Audience universe + customer moments + transformations.

Master Build §20-§24. Reuses the segments already defined in
``data/social/audience_world.json`` (which the newly-built Social
Intelligence layer depends on) rather than duplicating them, and lifts
them into the richer :class:`AudienceSegment` schema with evidence-tagged
confidence.
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import evidence, paths
from .schemas import AudienceSegment, CustomerMoment, Transformation


# --- Load existing social audience library -----------------------------


def _social_audience_path() -> str:
    return os.path.join(paths.data_dir(), "social", "audience_world.json")


def load_social_audience() -> dict[str, Any]:
    p = _social_audience_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


# --- Build universe -----------------------------------------------------


def build_segments() -> list[AudienceSegment]:
    data = load_social_audience()
    segments_raw = data.get("segments", {}) if isinstance(data, dict) else {}
    out: list[AudienceSegment] = []
    for seg_id, cfg in segments_raw.items():
        out.append(
            AudienceSegment(
                segment_id=seg_id,
                name=cfg.get("name", seg_id.replace("_", " ").title()),
                definition=cfg.get("description", ""),
                experience_level=cfg.get("experience_level", ""),
                lifestyle_context=list(cfg.get("lifestyle_context", [])),
                goals=list(cfg.get("goals", [])),
                problems=list(cfg.get("problems", [])),
                fears=list(cfg.get("fears", [])),
                questions=list(cfg.get("questions", [])),
                curiosities=list(cfg.get("curiosities", [])),
                misconceptions=list(cfg.get("misconceptions", [])),
                information_gaps=list(cfg.get("information_gaps", [])),
                desired_outcomes=list(cfg.get("goals", [])),
                emotional_drivers=list(cfg.get("emotional_drivers", [])),
                purchase_context=list(cfg.get("purchase_context", [])),
                decision_criteria=list(cfg.get("decisions", [])),
                objections=list(cfg.get("objections", [])),
                confidence=0.6,
            )
        )
    return out


# --- Customer moments (§22) ------------------------------------------


_DEFAULT_MOMENTS = [
    {
        "moment_id": "storm_approaching",
        "situation": "A named storm is forecast within 48 hours",
        "trigger": "Weather alert / neighbor conversation",
        "current_thought": "Do I have enough backup for the fridge and phones?",
        "current_emotion": "mild anxiety",
        "friction": "Doesn't know what capacity actually covers her priority loads",
        "desired_change": "A clear, matched-to-need plan before the storm hits",
        "likely_question": "How long will my current battery run my modem, phones, and a lamp?",
        "likely_objection": "I don't want to spend on capacity I'll never use",
        "appropriate_content_job": "load-matching education + practical checklist",
    },
    {
        "moment_id": "camping_trip_prep",
        "situation": "Packing for a weekend camping/RV trip",
        "trigger": "Trip calendar approaching",
        "current_thought": "Which charger keeps my devices going without weighing down the pack?",
        "current_emotion": "practical curiosity",
        "friction": "Compares mAh vs Wh vs W without understanding what matters for their loads",
        "desired_change": "Confidence in a compact, matched charger",
        "likely_question": "What size battery do I actually need for a phone + headlamp + camera?",
        "appropriate_content_job": "spec-to-outcome translation",
    },
    {
        "moment_id": "mid_outage",
        "situation": "Power just went out and is expected to last hours",
        "trigger": "Grid failure",
        "current_thought": "What do I plug in first — and what do I leave off?",
        "current_emotion": "some urgency",
        "friction": "Doesn't know load priorities",
        "desired_change": "A clear priority order + realistic runtime expectation",
        "likely_question": "What's the smart order to plug things in?",
        "appropriate_content_job": "priority guidance + runtime math",
    },
    {
        "moment_id": "browsing_first_backup",
        "situation": "First-time backup-power research; no prior device",
        "trigger": "Recent outage or emergency-kit checklist",
        "current_thought": "Do I need a huge unit or a small one?",
        "current_emotion": "cautious curiosity",
        "friction": "Category confusion — power bank vs power station vs solar generator",
        "desired_change": "A clear mental model",
        "likely_question": "What's the difference between a power bank and a power station?",
        "appropriate_content_job": "category education",
    },
    {
        "moment_id": "cable_clutter_frustration",
        "situation": "Everyday device-charging chaos",
        "trigger": "Nightly plugging routine",
        "current_thought": "There must be a cleaner way to keep everything charged",
        "current_emotion": "mild irritation",
        "friction": "Too many chargers, unclear compatibility",
        "desired_change": "Consolidated charging that fits actual daily loads",
        "likely_question": "Can one charger cover my laptop, phone, and headphones?",
        "appropriate_content_job": "practical decision guide",
    },
]


def build_moments() -> list[CustomerMoment]:
    return [CustomerMoment(**m) for m in _DEFAULT_MOMENTS]


# --- Transformations (§20) --------------------------------------------


_DEFAULT_TRANSFORMATIONS = [
    {
        "transformation_id": "uncertain_to_prepared",
        "current_state": "Uncertain what to do when power fails",
        "friction": "No load plan, no practice, no matched device",
        "desired_state": "Clear plan, matched device, calm response",
        "offering_capability": "Preparedness-first portable and backup power",
        "mechanism": "Battery capacity + AC/USB output matched to priority loads",
        "benefit": "Confidence and continuity during outages",
        "outcome": "Household keeps working through the outage",
        "emotional_meaning": "protection + control",
    },
    {
        "transformation_id": "immobile_to_mobile",
        "current_state": "Devices die whenever off-outlet",
        "friction": "Wrong-sized battery, wrong ports, wrong output",
        "desired_state": "Mobile all-day capability",
        "offering_capability": "Right-sized portable charger with matching PD output",
        "mechanism": "Wh capacity + USB-C PD wattage matched to device",
        "benefit": "No mid-day dead phone or laptop",
        "outcome": "Uninterrupted mobile work / play",
        "emotional_meaning": "freedom + capability",
    },
    {
        "transformation_id": "spec_confused_to_informed",
        "current_state": "Reading mAh/Wh/W as marketing numbers",
        "friction": "Vocabulary mismatch between customer needs and datasheets",
        "desired_state": "Understands what number matches which decision",
        "offering_capability": "Educational content library + per-SKU fit guidance",
        "mechanism": "Plain-language translation of specs to real loads",
        "benefit": "Buys the right device the first time",
        "outcome": "No returns, no regret purchase",
        "emotional_meaning": "confidence + respect",
    },
]


def build_transformations() -> list[Transformation]:
    return [Transformation(**t) for t in _DEFAULT_TRANSFORMATIONS]


# --- Audience-offering fit graph (§24) --------------------------------


def audience_offering_fit(segments: list[AudienceSegment], offerings: list) -> list[dict[str, Any]]:
    """Cheap symbolic mapping: match segments to offerings via
    customer_fit / category / use_case overlap."""
    edges: list[dict[str, Any]] = []
    for seg in segments:
        seg_tokens = " ".join([seg.name] + seg.lifestyle_context + seg.problems).lower()
        for o in offerings:
            score = 0.0
            for aud in o.customer_fit:
                if aud.lower() in seg_tokens or any(t in seg_tokens for t in aud.lower().split()):
                    score += 0.5
            if o.category and o.category.lower() in seg_tokens:
                score += 0.3
            for uc in o.use_cases:
                if uc.lower() in seg_tokens:
                    score += 0.2
            if score > 0:
                edges.append({
                    "segment_id": seg.segment_id,
                    "offering_id": o.offering_id,
                    "score": round(min(1.0, score), 3),
                })
    return edges
