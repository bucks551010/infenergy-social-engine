"""Tier-3 #11: posting_time_optimizer_agent.

Groups engagement metrics by hour-of-day + day-of-week and produces an
optimal-slot recommendation per platform. Writes an updated channel_schedule
snapshot to data/channel_schedule_recommended.json (does NOT overwrite the
live schedule automatically).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from statistics import mean

from ._base import env_int, utc_now, write_snapshot


def _iso_dt(value: str):
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None


def _score(m: dict) -> float:
    if not isinstance(m, dict) or m.get("error"):
        return 0.0
    return float(
        m.get("total_interactions", 0)
        or (m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0) + m.get("reactions", 0))
    )


def run(data_dir: str) -> dict:
    history_path = os.path.join(data_dir, "post_history.json")
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = {"posts": []}
    posts = history.get("posts") if isinstance(history, dict) else []
    if not isinstance(posts, list):
        posts = []
    lookback = env_int("POSTING_TIME_LOOKBACK", 100)

    per_platform_bucket: dict[str, dict[tuple[int, int], list[float]]] = {
        "facebook": defaultdict(list),
        "instagram": defaultdict(list),
    }
    for row in posts[-lookback:]:
        if not isinstance(row, dict):
            continue
        dt = _iso_dt(str(row.get("published_at", "") or row.get("run_started_at_utc", "")))
        if not dt:
            continue
        metrics = row.get("engagement_metrics") if isinstance(row.get("engagement_metrics"), dict) else {}
        for platform in per_platform_bucket:
            score = _score(metrics.get(platform) if isinstance(metrics.get(platform), dict) else {})
            per_platform_bucket[platform][(dt.weekday(), dt.hour)].append(score)

    recommendations: dict[str, list[dict]] = {}
    for platform, buckets in per_platform_bucket.items():
        ranked = sorted(
            (
                {"weekday": wd, "hour": h, "n": len(v), "avg": round(mean(v), 3) if v else 0.0}
                for (wd, h), v in buckets.items()
            ),
            key=lambda r: (r["avg"], r["n"]),
            reverse=True,
        )
        recommendations[platform] = ranked[:5]

    payload = {
        "agent": "posting_time_optimizer",
        "time_utc": utc_now(),
        "posts_analyzed": min(len(posts), lookback),
        "recommendations_utc": recommendations,
        "note": "recommendations are UTC weekday(0=Mon)+hour; apply manually to channel_schedule.json",
    }

    rec_path = os.path.join(data_dir, "channel_schedule_recommended.json")
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    write_snapshot(data_dir, "posting_time_optimizer", payload)
    return payload
