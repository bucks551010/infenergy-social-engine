from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone
from typing import Any


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_latest_bundle(output_dir: str) -> dict[str, Any]:
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


def build_weekly_plan(output_dir: str) -> dict[str, Any]:
    bundle = _load_latest_bundle(output_dir)
    if not bundle:
        raise FileNotFoundError("No marketing bundle found. Run scripts/run_marketing_team.py first.")

    profile = bundle.get("brand_profile", {})
    audience = bundle.get("audience", {})
    copy = bundle.get("copy", {})
    offer = bundle.get("offer", {})

    segments = audience.get("segments", [])
    hooks = copy.get("social_hooks", [])
    ctas = copy.get("cta_bank", [])
    offers = offer.get("core_offers", [])
    categories = profile.get("top_categories", [])

    if not hooks:
        hooks = ["What fails first in your home during an outage?"]
    if not ctas:
        ctas = ["Get your free power readiness assessment"]
    if not offers:
        offers = ["Device-by-device runtime planning"]
    if not categories:
        categories = ["Portable Power"]

    sequence = []
    slots = _weekly_slots()
    for i, slot_info in enumerate(slots):
        segment = segments[i % max(1, len(segments))] if segments else {}
        sequence.append(
            {
                "day": slot_info["day"],
                "slot": slot_info["slot"],
                "theme": categories[i % len(categories)],
                "segment": segment.get("name", "Prepared Buyer"),
                "hook": hooks[i % len(hooks)],
                "offer_angle": offers[i % len(offers)],
                "primary_cta": ctas[i % len(ctas)],
                "content_type": "education" if slot_info["slot"] == "morning" else ("proof" if slot_info["slot"] == "midday" else "cta"),
            }
        )

    plan = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_bundle_generated_at": bundle.get("generated_at_utc"),
        "objective": "Rotate categories and audience segments across 7-day, 3-slot cadence with strong hooks and single-CTA assets.",
        "sequence": sequence,
    }

    stamp = _utc_stamp()
    out_json = os.path.join(output_dir, f"weekly_plan_{stamp}.json")
    out_md = os.path.join(output_dir, f"weekly_plan_{stamp}.md")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    lines = ["# INF Energy Weekly Marketing Plan", "", f"Generated: {plan['generated_at_utc']}", ""]
    lines.append("## Objective")
    lines.append(plan["objective"])
    lines.append("")
    lines.append("## Sequence")
    for item in sequence:
        lines.append(
            f"- {item['day']} {item['slot']}: [{item['content_type']}] {item['theme']} | Segment: {item['segment']} | Hook: {item['hook']} | CTA: {item['primary_cta']}"
        )

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    plan["artifacts"] = {"weekly_plan_json": out_json, "weekly_plan_md": out_md}
    return plan
