"""Tier-1 #4: topic_intelligence_agent.

Reads env-configured RSS/JSON feeds (TOPIC_RSS_FEEDS, comma-separated) and
appends fresh topical anchors to data/topic_queue.json.

Uses only stdlib (feedparser is not a dep) — parses <item><title> and
<entry><title> via regex from the raw response body.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

import requests

from ._base import env_int, utc_now, write_snapshot

try:
    from url_safety import is_safe_http_url
except Exception:
    def is_safe_http_url(url: str) -> bool:
        return bool(str(url or "").strip().lower().startswith("http"))


_TITLE_RE = re.compile(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.IGNORECASE | re.DOTALL)


def _fetch_titles(url: str, limit: int) -> list[str]:
    if not is_safe_http_url(url):
        return []
    try:
        resp = requests.get(url, timeout=15)
        if not resp.ok:
            return []
        text = resp.text or ""
        titles = _TITLE_RE.findall(text)
        cleaned = []
        for t in titles[1 : limit + 1]:
            t = re.sub(r"<[^>]+>", "", t).strip()
            if 10 <= len(t) <= 180:
                cleaned.append(t)
        return cleaned
    except Exception:
        return []


def run(data_dir: str) -> dict:
    feeds_raw = os.environ.get("TOPIC_RSS_FEEDS", "").strip()
    per_feed = env_int("TOPIC_INTEL_PER_FEED", 5)
    feed_urls = [u.strip() for u in feeds_raw.split(",") if u.strip()]

    queue_path = os.path.join(data_dir, "topic_queue.json")
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
    except Exception:
        queue = {"topics": []}
    if not isinstance(queue, dict):
        queue = {"topics": []}
    topics = queue.get("topics") if isinstance(queue.get("topics"), list) else []
    seen_titles = {str(t.get("title", "")).strip().lower() for t in topics if isinstance(t, dict)}

    imported: list[dict] = []
    for url in feed_urls:
        titles = _fetch_titles(url, per_feed)
        for title in titles:
            if title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            topic = {
                "title": title,
                "pillar": "preparedness_topical",
                "source_url": url,
                "source_host": urlparse(url).hostname or "",
                "fetched_at_utc": utc_now(),
                "topical": True,
            }
            topics.append(topic)
            imported.append(topic)

    queue["topics"] = topics[-500:]
    if imported:
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2, default=str)

    payload = {
        "agent": "topic_intelligence",
        "time_utc": utc_now(),
        "feeds": feed_urls,
        "imported_count": len(imported),
        "imported": imported[:20],
    }
    write_snapshot(data_dir, "topic_intelligence", payload)
    return payload
