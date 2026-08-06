from __future__ import annotations

import csv
import glob
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class ProductFact:
    name: str
    sku: str
    categories: list[str]
    metrics: list[str]
    price: str
    image_url: str


def _to_float(value: str) -> float | None:
    try:
        if value is None:
            return None
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        return float(cleaned)
    except Exception:
        return None


def _strip_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text or "", flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_visible_text(html: str) -> str:
    # Remove script/style blocks so we keep only meaningful brand copy.
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html or "", flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = _strip_html(html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_metrics(text: str) -> list[str]:
    pattern = re.compile(
        r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?(?:Wh|mAh|W|kW|V|A|lbs|lb|in|mm|g|hours|hour|%|year|years)\b",
        flags=re.IGNORECASE,
    )
    out: list[str] = []
    seen = set()
    for hit in pattern.findall(text or ""):
        key = hit.lower()
        if key not in seen:
            seen.add(key)
            out.append(hit)
    return out[:8]


def load_products(products_dir: str) -> list[ProductFact]:
    rows: list[ProductFact] = []
    for csv_path in sorted(glob.glob(os.path.join(products_dir, "*.csv"))):
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Published", "").strip() != "1":
                    continue
                name = (row.get("Name") or "").strip()
                if not name:
                    continue
                desc = _strip_html((row.get("Short description") or "") + " " + (row.get("Description") or ""))
                images = [x.strip() for x in (row.get("Images") or "").split(",") if x.strip()]
                categories = [x.strip() for x in (row.get("Categories") or "").split(",") if x.strip()]
                rows.append(
                    ProductFact(
                        name=name,
                        sku=(row.get("SKU") or "").strip(),
                        categories=categories[:5],
                        metrics=_extract_metrics(desc),
                        price=(row.get("Regular price") or "").strip(),
                        image_url=images[0] if images else "",
                    )
                )
    return rows


def fetch_site_text(site_url: str) -> str:
    try:
        resp = requests.get(site_url, timeout=20)
        resp.raise_for_status()
        return _clean_visible_text(resp.text)
    except Exception:
        return ""


def infer_brand_profile(site_url: str, products_dir: str) -> dict[str, Any]:
    site_text = fetch_site_text(site_url)
    products = load_products(products_dir)

    names = [p.name for p in products[:25]]
    category_counter: Counter[str] = Counter()
    metric_counter: Counter[str] = Counter()
    prices: list[float] = []
    for p in products:
        for c in p.categories:
            category_counter[c] += 1
        for m in p.metrics:
            metric_counter[m.lower()] += 1
        f = _to_float(p.price)
        if f is not None and f > 0:
            prices.append(f)

    top_categories = [k for k, _ in category_counter.most_common(8)]
    top_metrics = [k for k, _ in metric_counter.most_common(12)]

    if prices:
        prices_sorted = sorted(prices)
        median = prices_sorted[len(prices_sorted) // 2]
        price_summary = {
            "min": round(min(prices), 2),
            "max": round(max(prices), 2),
            "median": round(median, 2),
            "count": len(prices),
        }
    else:
        price_summary = {"min": None, "max": None, "median": None, "count": 0}

    value_tier = "mid_to_premium"
    if price_summary["median"] is not None:
        med = price_summary["median"]
        if med < 120:
            value_tier = "entry_to_mid"
        elif med > 1200:
            value_tier = "premium"

    keyword_groups = {
        "preparedness": ["outage", "emergency", "backup", "ready", "storm"],
        "independence": ["independence", "freedom", "grid", "resilience"],
        "sustainability": ["solar", "clean energy", "sustainable", "green"],
    }

    lower_site = site_text.lower()
    messaging_signals: dict[str, int] = {}
    for group, words in keyword_groups.items():
        messaging_signals[group] = sum(lower_site.count(w) for w in words)

    site_sentences = [s.strip() for s in re.split(r"[.!?]", site_text) if s.strip()]
    claim_snippets = [
        s for s in site_sentences
        if any(w in s.lower() for w in ("outage", "power", "solar", "independence", "ready", "backup"))
    ][:10]

    # Derived from visible brand language and offer catalog.
    brand_voice = {
        "tone": [
            "confident",
            "protective",
            "practical",
            "mission-driven",
            "urgency with reassurance",
        ],
        "authority_position": "Resilient power and solar readiness advisor focused on outage protection and energy independence.",
        "brand_promises": [
            "Keep homes and devices running during outages",
            "Deliver practical portable and modular power solutions",
            "Guide buyers with clear specs and realistic use cases",
        ],
    }

    demographics = {
        "primary": "Homeowners and families in outage-prone regions",
        "secondary": "Small businesses, travelers, RV/camping users, and remote workers",
        "price_sensitivity": "Mid to premium with value framing around reliability and total cost of downtime",
        "value_tier": value_tier,
    }

    psychographics = {
        "core_drivers": [
            "Fear of power loss and uncertainty",
            "Desire for control and preparedness",
            "Pride in self-reliance and smart buying",
            "Interest in clean energy and sustainability",
        ],
        "objections": [
            "Is this enough power for my needs?",
            "Will it actually work in a real outage?",
            "Is it worth the cost?",
            "Will setup be difficult?",
        ],
        "decision_triggers": [
            "Recent blackout experience",
            "Storm season reminders",
            "Visible side-by-side specs",
            "Warranty and support confidence",
        ],
    }

    visual_identity = {
        "primary_colors": ["#2563eb", "#1e3a8a", "#f8fafc"],
        "look": "clean technical trust aesthetic with blue-led reliability cues",
        "imagery_direction": [
            "family safety during outages",
            "portable power in outdoor scenarios",
            "modular system components with clear labels",
            "before/after lighting contrast",
        ],
    }

    return {
        "site_url": site_url,
        "site_excerpt": site_text[:2500],
        "site_claim_snippets": claim_snippets,
        "product_count": len(products),
        "product_examples": names,
        "price_summary": price_summary,
        "top_categories": top_categories,
        "top_metrics": top_metrics,
        "messaging_signals": messaging_signals,
        "products": [
            {
                "name": p.name,
                "sku": p.sku,
                "categories": p.categories,
                "metrics": p.metrics,
                "price": p.price,
                "image_url": p.image_url,
            }
            for p in products[:40]
        ],
        "brand_voice": brand_voice,
        "demographics": demographics,
        "psychographics": psychographics,
        "visual_identity": visual_identity,
    }


def save_brand_profile(profile: dict[str, Any], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
