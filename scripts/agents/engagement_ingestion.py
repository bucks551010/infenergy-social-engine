"""Tier-1 #1: engagement_ingestion_agent.

Polls Meta Graph API (page + Instagram) for insights on each post published in
the last 14 days and writes an `engagement_metrics` dict back onto each history
row plus a rollup snapshot.

Degrades gracefully when tokens are missing or an individual post returns an
error (partial ingestion is better than no ingestion).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from ._base import env_int, utc_now, write_snapshot

GRAPH_BASE = "https://graph.facebook.com/v26.0"


def _iso_to_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _fb_metrics(post_id: str, page_token: str) -> dict:
    if not post_id or post_id in {"skipped", "dry-run"} or not page_token:
        return {}
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/{post_id}",
            params={
                "fields": "likes.summary(true),comments.summary(true),shares,reactions.summary(true)",
                "access_token": page_token,
            },
            timeout=15,
        )
        if not resp.ok:
            return {"error": f"http_{resp.status_code}"}
        data = resp.json() or {}
        return {
            "likes": int(((data.get("likes") or {}).get("summary") or {}).get("total_count", 0) or 0),
            "comments": int(((data.get("comments") or {}).get("summary") or {}).get("total_count", 0) or 0),
            "reactions": int(((data.get("reactions") or {}).get("summary") or {}).get("total_count", 0) or 0),
            "shares": int((data.get("shares") or {}).get("count", 0) or 0),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def _ig_metrics(media_id: str, page_token: str) -> dict:
    if not media_id or media_id in {"skipped", "dry-run"} or not page_token:
        return {}
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/{media_id}/insights",
            params={
                "metric": "reach,likes,comments,shares,total_interactions",
                "access_token": page_token,
            },
            timeout=15,
        )
        if not resp.ok:
            return {"error": f"http_{resp.status_code}"}
        data = resp.json() or {}
        out: dict[str, int] = {}
        for row in data.get("data", []) or []:
            name = str(row.get("name", "")).strip()
            values = row.get("values") or []
            if not name or not values:
                continue
            out[name] = int(values[0].get("value", 0) or 0)
        return out
    except Exception as e:
        return {"error": str(e)[:200]}


def _score(m: dict) -> float:
    if not isinstance(m, dict) or m.get("error"):
        return 0.0
    return float(
        m.get("total_interactions", 0)
        or (m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0) + m.get("reactions", 0))
    )


def run(data_dir: str, lookback_days: int | None = None) -> dict:
    lookback = int(lookback_days if lookback_days is not None else env_int("ENGAGEMENT_LOOKBACK_DAYS", 14))
    page_token = os.environ.get("META_PAGE_ACCESS_TOKEN", "").strip()

    history_path = os.path.join(data_dir, "post_history.json")
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = {"posts": []}

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback)
    updated = 0
    per_post: list[dict] = []
    posts = history.get("posts") if isinstance(history, dict) else None
    if not isinstance(posts, list):
        posts = []

    for row in posts:
        if not isinstance(row, dict):
            continue
        published = _iso_to_dt(str(row.get("published_at", "") or row.get("run_started_at_utc", "")))
        if published and published < cutoff:
            continue

        fb_id = str(row.get("fb_id", "") or "").strip()
        ig_id = str(row.get("ig_id", "") or "").strip()
        fb_metrics = _fb_metrics(fb_id, page_token) if fb_id else {}
        ig_metrics = _ig_metrics(ig_id, page_token) if ig_id else {}
        metrics = {
            "fetched_at_utc": utc_now(),
            "facebook": fb_metrics,
            "instagram": ig_metrics,
            "linkedin": {"error": "not_implemented"} if str(row.get("li_id", "")).strip() not in {"", "skipped", "dry-run"} else {},
        }
        row["engagement_metrics"] = metrics
        updated += 1
        per_post.append(
            {
                "post_id": row.get("post_id"),
                "published_at": row.get("published_at"),
                "principle_key": (row.get("logical_emotional_strategy") or {}).get("principle_key")
                if isinstance(row.get("logical_emotional_strategy"), dict)
                else None,
                "archetype_key": (row.get("logical_emotional_strategy") or {}).get("archetype_key")
                if isinstance(row.get("logical_emotional_strategy"), dict)
                else None,
                "funnel_stage": row.get("funnel_stage"),
                "facebook_score": _score(fb_metrics),
                "instagram_score": _score(ig_metrics),
            }
        )

    if updated:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2, default=str)

    payload = {
        "agent": "engagement_ingestion",
        "time_utc": utc_now(),
        "lookback_days": lookback,
        "posts_scanned": len(posts),
        "posts_updated": updated,
        "page_token_present": bool(page_token),
        "per_post": per_post,
    }
    write_snapshot(data_dir, "engagement_ingestion", payload)
    return payload
