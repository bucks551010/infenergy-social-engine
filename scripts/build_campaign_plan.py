from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

ROOT = os.path.dirname(os.path.dirname(__file__))
BASE_DATA_DIR = os.path.join(ROOT, "data")
DATA_DIR = os.environ.get("DATA_DIR", BASE_DATA_DIR)
MARKETING_DIR = os.path.join(DATA_DIR, "marketing")
CAMPAIGNS_DIR = os.path.join(MARKETING_DIR, "campaigns")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _week_start_iso(now_utc: datetime | None = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = monday - timedelta(days=now.weekday())
    return monday.date().isoformat()


def _latest_strategy(output_dir: str) -> dict[str, Any]:
    paths = glob.glob(os.path.join(output_dir, "marketing_strategy_*.json"))
    if not paths:
        paths = glob.glob(os.path.join(output_dir, "marketing_bundle_*.json"))
    if not paths:
        return {}

    latest = max(paths, key=os.path.getmtime)
    with open(latest, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}


def _load_published_products(max_items: int = 8) -> list[dict[str, str]]:
    products_dir = os.path.join(BASE_DATA_DIR, "products")
    out: list[dict[str, str]] = []
    for csv_path in sorted(glob.glob(os.path.join(products_dir, "*.csv"))):
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("Published", "")).strip() != "1":
                    continue
                pid = str(row.get("ID", "")).strip()
                name = str(row.get("Name", "")).strip()
                sku = str(row.get("SKU", "")).strip()
                if not pid and not name:
                    continue
                out.append({"id": pid, "name": name, "sku": sku})
                if len(out) >= max_items:
                    return out
    return out


def _pick_claims(strategy: dict[str, Any]) -> tuple[list[str], list[str]]:
    profile = strategy.get("brand_profile", {}) if isinstance(strategy, dict) else {}
    messaging = profile.get("messaging_signals", []) if isinstance(profile, dict) else []

    normalized: list[str] = []
    if isinstance(messaging, list):
        normalized = [str(x).strip() for x in messaging if str(x).strip()]
    elif isinstance(messaging, dict):
        for k, v in messaging.items():
            text = f"{k}: {v}".strip()
            if text:
                normalized.append(text)
    elif messaging:
        normalized = [str(messaging).strip()]

    approved = [
        "Use only verified product specs from structured product data.",
        "Prefer phrasing like 'up to' and 'in many cases' for outcome language.",
    ]
    for item in normalized[:4]:
        text = str(item).strip()
        if text:
            approved.append(text)

    prohibited = [
        "No fabricated customer testimonials or invented outcome numbers.",
        "Do not claim guaranteed savings or guaranteed runtime.",
        "Do not invent product capacity, wattage, or price.",
    ]
    return approved[:8], prohibited[:8]


def build_campaign_plan(output_dir: str) -> dict[str, Any]:
    os.makedirs(CAMPAIGNS_DIR, exist_ok=True)
    strategy = _latest_strategy(output_dir)

    audience = strategy.get("audience", {}) if isinstance(strategy, dict) else {}
    offer = strategy.get("offer", {}) if isinstance(strategy, dict) else {}
    copy = strategy.get("copy", {}) if isinstance(strategy, dict) else {}
    profile = strategy.get("brand_profile", {}) if isinstance(strategy, dict) else {}

    segments = audience.get("segments", []) if isinstance(audience, dict) else []
    chosen_segment = segments[0].get("name", "Prepared Homeowner") if segments else "Prepared Homeowner"
    customer_problem = "Rising utility costs and uncertainty during outages."
    if segments and isinstance(segments[0], dict):
        pains = segments[0].get("pain_points", [])
        if isinstance(pains, list) and pains:
            customer_problem = str(pains[0]).strip() or customer_problem

    educational_message = "Teach buyers how to match real device needs to verified power specs before purchasing."
    core_message = "Name the device, show the published specification, and tell the reader what to compare next."

    ctas = copy.get("cta_bank", []) if isinstance(copy, dict) else []
    primary_cta = str(ctas[0]).strip() if ctas else "Build your backup-power setup."
    secondary_cta = str(ctas[1]).strip() if len(ctas) > 1 else "Compare the published specifications with your device list."

    products = _load_published_products(max_items=10)
    featured = [p.get("id", "") for p in products[:3] if p.get("id")]
    supporting = [p.get("id", "") for p in products[3:8] if p.get("id")]

    week_start = _week_start_iso()
    campaign_name = f"outage_readiness_{week_start}"
    campaign_id = hashlib.md5(f"{campaign_name}:{week_start}".encode("utf-8")).hexdigest()[:12]

    angles = copy.get("ad_angles", []) if isinstance(copy, dict) else []
    if not isinstance(angles, list) or not angles:
        angles = [
            "Scenario-led education",
            "Verified specs over hype",
            "Preparedness decision clarity",
        ]

    approved_claims, prohibited_claims = _pick_claims(strategy)

    destination_url = os.environ.get("WP_URL", "https://www.infenergypower.com").strip() or "https://www.infenergypower.com"

    campaign = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "week_start": week_start,
        "primary_objective": str(offer.get("positioning_statement", "Drive qualified product-interest actions with useful education.")).strip(),
        "audience_segment": chosen_segment,
        "customer_problem": customer_problem,
        "educational_message": educational_message,
        "featured_product_ids": featured,
        "supporting_product_ids": supporting,
        "core_message": core_message,
        "primary_cta": primary_cta,
        "secondary_cta": secondary_cta,
        "destination_url": destination_url,
        "content_angles": [str(a).strip() for a in angles[:8] if str(a).strip()],
        "approved_claims": approved_claims,
        "prohibited_claims": prohibited_claims,
    }

    out_path = os.path.join(CAMPAIGNS_DIR, f"campaign_{week_start}_{_utc_stamp()}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(campaign, f, indent=2)

    return {"campaign": campaign, "artifact": out_path}


def main() -> None:
    output_dir = os.environ.get("MARKETING_OUTPUT_DIR", os.path.join(DATA_DIR, "marketing"))
    result = build_campaign_plan(output_dir=output_dir)
    print("Structured campaign plan generated.")
    print(json.dumps({"artifact": result.get("artifact")}, indent=2))


if __name__ == "__main__":
    main()
