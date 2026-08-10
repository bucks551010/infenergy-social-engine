"""Tier-1 #2: performance_reflection_agent.

Reads engagement snapshots + post_history and produces winners/losers grouped
by principle_key, archetype_key, funnel_stage, platform, hook_type.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from statistics import mean

from ._base import env_int, utc_now, write_snapshot


def _score(m: dict) -> float:
    if not isinstance(m, dict) or m.get("error"):
        return 0.0
    return float(
        m.get("total_interactions", 0)
        or (m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0) + m.get("reactions", 0))
    )


def _extract(row: dict) -> dict:
    strat = row.get("logical_emotional_strategy") if isinstance(row.get("logical_emotional_strategy"), dict) else {}
    metrics = row.get("engagement_metrics") if isinstance(row.get("engagement_metrics"), dict) else {}
    return {
        "post_id": row.get("post_id"),
        "principle_key": strat.get("principle_key"),
        "archetype_key": strat.get("archetype_key"),
        "funnel_stage": row.get("funnel_stage"),
        "hook_type": row.get("hook_type"),
        "facebook_score": _score(metrics.get("facebook") if isinstance(metrics.get("facebook"), dict) else {}),
        "instagram_score": _score(metrics.get("instagram") if isinstance(metrics.get("instagram"), dict) else {}),
    }


def _group_summary(rows: list[dict], key: str, platform: str) -> list[dict]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        k = r.get(key)
        if not k:
            continue
        score = r.get(f"{platform}_score", 0.0)
        buckets[str(k)].append(float(score))
    summary = [
        {"key": k, "n": len(v), "avg": round(mean(v), 3) if v else 0.0, "total": round(sum(v), 3)}
        for k, v in buckets.items()
    ]
    return sorted(summary, key=lambda r: r["avg"], reverse=True)


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

    limit = env_int("PERFORMANCE_REFLECTION_LIMIT", 200)
    rows = [_extract(r) for r in posts[-limit:] if isinstance(r, dict)]

    dimensions = ("principle_key", "archetype_key", "funnel_stage", "hook_type")
    summary: dict = {"by_dimension": {}}
    for platform in ("facebook", "instagram"):
        summary["by_dimension"][platform] = {
            dim: _group_summary(rows, dim, platform) for dim in dimensions
        }

    winners: list[str] = []
    losers: list[str] = []
    for platform, per_dim in summary["by_dimension"].items():
        for dim, ranked in per_dim.items():
            if len(ranked) >= 2:
                if ranked[0]["n"] >= 2:
                    winners.append(f"{platform}:{dim}:{ranked[0]['key']}")
                if ranked[-1]["n"] >= 2 and ranked[-1]["avg"] < ranked[0]["avg"]:
                    losers.append(f"{platform}:{dim}:{ranked[-1]['key']}")

    payload = {
        "agent": "performance_reflection",
        "time_utc": utc_now(),
        "posts_analyzed": len(rows),
        "winning_patterns": winners,
        "losing_patterns": losers,
        "summary": summary,
    }
    write_snapshot(data_dir, "performance_reflection", payload)
    return payload
