"""Tier-3 #14: crisis_relevance_agent.

Detects active weather / power-outage crisis signals and produces a
crisis_context payload that generate_posts can use to bias topic and product
selection. Reads CRISIS_FEED_URLS (comma-separated NOAA/weather JSON feeds) —
gracefully falls back to a neutral 'no active crisis' payload otherwise.
"""

from __future__ import annotations

import json
import os
import re

import requests

from ._base import env_int, utc_now, write_snapshot

try:
    from url_safety import is_safe_http_url
except Exception:
    def is_safe_http_url(url: str) -> bool:
        return bool(str(url or "").strip().lower().startswith("http"))


_CRISIS_KEYWORDS = {
    "outage": "power_outage",
    "storm": "storm",
    "hurricane": "hurricane",
    "tropical storm": "tropical_storm",
    "tornado": "tornado",
    "wildfire": "wildfire",
    "heat wave": "heat_wave",
    "heatwave": "heat_wave",
    "blizzard": "blizzard",
    "flood": "flood",
    "ice storm": "ice_storm",
}


def _classify(text: str) -> list[str]:
    low = str(text or "").lower()
    found = []
    for k, tag in _CRISIS_KEYWORDS.items():
        if k in low and tag not in found:
            found.append(tag)
    return found


def _feed_events(url: str, per_feed: int) -> list[dict]:
    if not is_safe_http_url(url):
        return []
    try:
        resp = requests.get(url, timeout=15)
        if not resp.ok:
            return []
        events: list[dict] = []
        content_type = (resp.headers.get("content-type") or "").lower()
        if "json" in content_type:
            data = resp.json()
            features = data.get("features") if isinstance(data, dict) else None
            for feat in (features or [])[:per_feed]:
                props = feat.get("properties") if isinstance(feat, dict) else {}
                headline = str((props or {}).get("headline") or (props or {}).get("event") or "").strip()
                if not headline:
                    continue
                events.append({"headline": headline, "categories": _classify(headline), "source_url": url})
        else:
            titles = re.findall(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", resp.text or "", re.IGNORECASE | re.DOTALL)
            for t in titles[1 : per_feed + 1]:
                clean = re.sub(r"<[^>]+>", "", t).strip()
                if not clean:
                    continue
                cats = _classify(clean)
                if cats:
                    events.append({"headline": clean, "categories": cats, "source_url": url})
        return events
    except Exception:
        return []


def run(data_dir: str) -> dict:
    feeds_raw = os.environ.get("CRISIS_FEED_URLS", "").strip()
    per_feed = env_int("CRISIS_PER_FEED", 10)
    feed_urls = [u.strip() for u in feeds_raw.split(",") if u.strip()]

    all_events: list[dict] = []
    for url in feed_urls:
        all_events.extend(_feed_events(url, per_feed))

    category_counts: dict[str, int] = {}
    for e in all_events:
        for c in e.get("categories", []) or []:
            category_counts[c] = category_counts.get(c, 0) + 1

    top_categories = sorted(category_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    active = bool(top_categories)

    payload = {
        "agent": "crisis_relevance",
        "time_utc": utc_now(),
        "feeds": feed_urls,
        "events_found": len(all_events),
        "active": active,
        "top_categories": top_categories,
        "sample_events": all_events[:20],
    }
    context_path = os.path.join(data_dir, "crisis_context.json")
    with open(context_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    write_snapshot(data_dir, "crisis_relevance", payload)
    return payload


def load_crisis_context(data_dir: str) -> dict:
    path = os.path.join(data_dir, "crisis_context.json")
    if not os.path.exists(path):
        return {"active": False}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active": False}
