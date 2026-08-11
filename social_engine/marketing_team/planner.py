from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone
from typing import Any

from scripts.campaign_runtime import DEFAULT_CHANNEL_SCHEDULE, DEFAULT_FUNNEL_CONFIG


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_latest_strategy(output_dir: str) -> dict[str, Any]:
    paths = glob.glob(os.path.join(output_dir, "marketing_strategy_*.json"))
    if not paths:
        # Backward compatibility with older artifacts.
        paths = glob.glob(os.path.join(output_dir, "marketing_bundle_*.json"))
    if not paths:
        return {}

    latest = max(paths, key=os.path.getmtime)
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)


def _weekly_slots() -> list[dict[str, str]]:
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    slots = ["morning", "midday", "evening"]
    return [{"day": day, "slot": slot} for day in days for slot in slots]


def _content_goal(slot: str) -> str:
    if slot == "morning":
        return "education"
    if slot == "midday":
        return "proof"
    return "conversion"


def build_weekly_plan(output_dir: str) -> dict[str, Any]:
    strategy = _load_latest_strategy(output_dir)
    if not strategy:
        raise FileNotFoundError("No marketing strategy found. Run scripts/run_marketing_team.py first.")

    profile = strategy.get("brand_profile", {})
    audience = strategy.get("audience", {})
    copy = strategy.get("copy", {})
    offer = strategy.get("offer", {})

    segments = audience.get("segments", [])
    hooks = copy.get("social_hooks", [])
    ctas = copy.get("cta_bank", [])
    offers = offer.get("core_offers", [])
    categories = profile.get("top_categories", [])
    ad_angles = copy.get("ad_angles", [])
    segments = audience.get("segments", [])
    experiments = strategy.get("experiments", {}).get("experiments", [])

    if not hooks:
        hooks = ["What fails first in your home during an outage?"]
    if not ctas:
        ctas = ["Get your free power readiness assessment"]
    if not offers:
        offers = ["Device-by-device runtime planning"]
    if not categories:
        categories = ["Portable Power"]
    if not ad_angles:
        ad_angles = ["Fear-to-control framing"]

    sequence = []
    slots = _weekly_slots()
    used = set()
    for i, slot_info in enumerate(slots):
        segment = segments[i % max(1, len(segments))] if segments else {}
        hook = hooks[i % len(hooks)]
        if hook in used:
            hook = hooks[(i + 1) % len(hooks)]
        used.add(hook)

        sequence.append(
            {
                "day": slot_info["day"],
                "slot": slot_info["slot"],
                "theme": categories[i % len(categories)],
                "segment": segment.get("name", "Prepared Buyer"),
                "hook": hook,
                "offer_angle": offers[i % len(offers)],
                "primary_cta": ctas[i % len(ctas)],
                "ad_angle": ad_angles[i % len(ad_angles)],
                "content_type": _content_goal(slot_info["slot"]),
                "proof_requirement": "Include one measurable spec or scenario metric",
                "kpi_target": "engagement" if slot_info["slot"] != "evening" else "conversion",
            }
        )

    campaign_arcs = [
        {
            "name": "Outage Readiness Week",
            "primary_objective": "Increase preparedness consult bookings",
            "hero_offer": ctas[0],
            "narrative": [
                "Day 1-2: expose hidden outage risk",
                "Day 3-4: prove spec-to-outcome mapping",
                "Day 5-7: convert with clear next-step CTA",
            ],
        },
        {
            "name": "Portable Power Lifestyle Week",
            "primary_objective": "Increase product-fit consults for home, travel, and outdoor use",
            "hero_offer": offers[0],
            "narrative": [
                "Day 1-2: everyday device dependence and risk",
                "Day 3-4: practical setup pathways for families and mobile users",
                "Day 5-7: conversion push with concrete next steps",
            ],
        },
    ]

    test_queue = [
        {
            "experiment": e.get("name", "Experiment"),
            "hypothesis": e.get("hypothesis", ""),
            "window": "7 days",
        }
        for e in experiments[:3]
    ]

    plan = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_strategy_generated_at": strategy.get("generated_at_utc"),
        "objective": "Run a structured weekly growth sprint with education-proof-conversion sequencing and measurable tests.",
        "campaign_arcs": campaign_arcs,
        "test_queue": test_queue,
        "ops_guardrails": [
            "Never repeat identical hooks on consecutive posts",
            "Every post has one proof element and one clear CTA",
            "Evening slots prioritize conversion CTAs",
        ],
        "sequence": sequence,
        "campaign_plan": {
            "name": "infenergy_weekly_growth_sprint",
            "funnel": DEFAULT_FUNNEL_CONFIG,
            "channel_schedule": DEFAULT_CHANNEL_SCHEDULE,
            "quality_targets": {
                "minimum_quality_score": 78,
                "required_numeric_evidence_per_post": 1,
                "max_risky_claim_hits": 0,
            },
            "publishing_rules": {
                "skip_recent_success_hours": 0,
                "anti_repeat_topic_window": 60,
                "anti_repeat_hook_window": 30,
                "anti_repeat_cta_window": 30,
            },
        },
    }

    stamp = _utc_stamp()
    out_json = os.path.join(output_dir, f"weekly_plan_{stamp}.json")
    out_md = os.path.join(output_dir, f"weekly_plan_{stamp}.md")
    campaign_json = os.path.join(output_dir, f"campaign_plan_{stamp}.json")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    with open(campaign_json, "w", encoding="utf-8") as f:
        json.dump(plan["campaign_plan"], f, indent=2)

    lines = ["# INF Energy Weekly Marketing Plan", "", f"Generated: {plan['generated_at_utc']}", ""]
    lines.append("## Objective")
    lines.append(plan["objective"])
    lines.append("")
    lines.append("## Campaign Arcs")
    for arc in campaign_arcs:
        lines.append(f"- {arc['name']}: {arc['primary_objective']}")
    lines.append("")
    lines.append("## Test Queue")
    for test in test_queue:
        lines.append(f"- {test['experiment']}: {test['hypothesis']}")
    lines.append("")
    lines.append("## Sequence")
    for item in sequence:
        lines.append(
            f"- {item['day']} {item['slot']}: [{item['content_type']}] {item['theme']} | Segment: {item['segment']} | Hook: {item['hook']} | Angle: {item['ad_angle']} | CTA: {item['primary_cta']}"
        )

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    plan["artifacts"] = {
        "weekly_plan_json": out_json,
        "weekly_plan_md": out_md,
        "campaign_plan_json": campaign_json,
    }
    return plan
