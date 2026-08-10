"""Tier-3 #15: cross_post_recycler_agent.

Picks top-engagement posts from the last N days and stages a recycled variant
targeting a different archetype after a cool-down period, so winning content
compounds. Writes to data/recycling/queue.json for consumption by the run
engine on future runs (not automatically republished — human/agent approval
required).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta

from ._base import env_int, utc_now, write_snapshot


_ARCHETYPE_ROTATION = ["preparedness_buyer", "mobile_professional", "outdoor_adventurer"]


def _iso(value: str):
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


def _next_archetype(current: str) -> str:
    if not current:
        return _ARCHETYPE_ROTATION[0]
    try:
        idx = _ARCHETYPE_ROTATION.index(current)
        return _ARCHETYPE_ROTATION[(idx + 1) % len(_ARCHETYPE_ROTATION)]
    except ValueError:
        return _ARCHETYPE_ROTATION[0]


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

    lookback_days = env_int("RECYCLER_LOOKBACK_DAYS", 45)
    cooldown_days = env_int("RECYCLER_COOLDOWN_DAYS", 30)
    top_n = env_int("RECYCLER_TOP_N", 3)
    min_score = env_int("RECYCLER_MIN_SCORE", 10)

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)

    scored: list[tuple[float, dict]] = []
    for row in posts:
        if not isinstance(row, dict):
            continue
        published = _iso(row.get("published_at", "") or row.get("run_started_at_utc", ""))
        if not published or published < cutoff or published > cooldown_cutoff:
            continue
        metrics = row.get("engagement_metrics") if isinstance(row.get("engagement_metrics"), dict) else {}
        total = _score(metrics.get("facebook") if isinstance(metrics.get("facebook"), dict) else {}) + _score(
            metrics.get("instagram") if isinstance(metrics.get("instagram"), dict) else {}
        )
        if total < min_score:
            continue
        scored.append((total, row))

    scored.sort(key=lambda t: t[0], reverse=True)
    picks = scored[:top_n]

    queued: list[dict] = []
    for total, row in picks:
        strat = row.get("logical_emotional_strategy") if isinstance(row.get("logical_emotional_strategy"), dict) else {}
        queued.append(
            {
                "recycle_id": f"rec_{uuid.uuid4().hex[:10]}",
                "source_post_id": row.get("post_id"),
                "source_score": total,
                "product_id": row.get("product_id"),
                "topic": row.get("topic"),
                "source_principle_key": strat.get("principle_key"),
                "source_archetype_key": strat.get("archetype_key"),
                "target_archetype_key": _next_archetype(str(strat.get("archetype_key", "") or "")),
                "created_at_utc": utc_now(),
                "status": "queued",
            }
        )

    queue_path = os.path.join(data_dir, "recycling", "queue.json")
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
        if not isinstance(queue, dict):
            queue = {"queue": []}
    except Exception:
        queue = {"queue": []}
    queue.setdefault("queue", [])
    queue["queue"].extend(queued)
    queue["queue"] = queue["queue"][-50:]
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2, default=str)

    payload = {
        "agent": "cross_post_recycler",
        "time_utc": utc_now(),
        "candidates_considered": len(scored),
        "queued": len(queued),
        "picks": queued,
    }
    write_snapshot(data_dir, "cross_post_recycler", payload)
    return payload
