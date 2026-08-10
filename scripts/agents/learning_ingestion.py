"""Tier-1 #3: learning_ingestion_agent.

Reads phase6_learning + validation_errors + quality_warnings from recent posts,
distills them into `recent_lessons` consumed by generate_posts._run_phase2_creative_stack.
"""

from __future__ import annotations

import json
import os
from collections import Counter

from ._base import env_int, utc_now, write_snapshot


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

    lookback = env_int("LEARNING_LOOKBACK_POSTS", 50)
    tail = posts[-lookback:]

    error_counter: Counter = Counter()
    warning_counter: Counter = Counter()
    status_counter: Counter = Counter()
    winning_hooks: list[str] = []
    losing_hooks: list[str] = []

    for row in tail:
        if not isinstance(row, dict):
            continue
        for e in row.get("validation_errors", []) or []:
            error_counter[str(e)] += 1
        for w in row.get("quality_warnings", []) or []:
            warning_counter[str(w)] += 1
        status_counter[str(row.get("status", ""))] += 1
        metrics = row.get("engagement_metrics") if isinstance(row.get("engagement_metrics"), dict) else {}
        fb = metrics.get("facebook") if isinstance(metrics.get("facebook"), dict) else {}
        ig = metrics.get("instagram") if isinstance(metrics.get("instagram"), dict) else {}
        score = float(fb.get("total_interactions", 0) or 0) + float(ig.get("total_interactions", 0) or 0)
        hook = str(row.get("hook", "") or "").strip()
        if hook and score >= 5:
            winning_hooks.append(hook)
        elif hook and score == 0 and row.get("status") == "success":
            losing_hooks.append(hook)

    lessons_path = os.path.join(data_dir, "learning", "recent_lessons.json")
    payload = {
        "agent": "learning_ingestion",
        "time_utc": utc_now(),
        "posts_analyzed": len(tail),
        "top_errors": error_counter.most_common(10),
        "top_warnings": warning_counter.most_common(10),
        "status_distribution": status_counter.most_common(),
        "winning_hooks": winning_hooks[-15:],
        "losing_hooks": losing_hooks[-15:],
    }

    os.makedirs(os.path.dirname(lessons_path), exist_ok=True)
    with open(lessons_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    write_snapshot(data_dir, "learning_ingestion", payload)
    return payload


def load_recent_lessons(data_dir: str) -> dict:
    path = os.path.join(data_dir, "learning", "recent_lessons.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
