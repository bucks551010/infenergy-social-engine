"""Tier-3 #12: ab_variant_orchestrator_agent.

Picks recent posts and generates a single variant per post that swaps EITHER
the formal-logic principle_key OR the audience archetype_key, tagging both
with an experiment_id so downstream engagement rollups can attribute lift.
"""

from __future__ import annotations

import json
import os
import uuid

from ._base import env_int, utc_now, write_snapshot

_PRINCIPLE_ROTATION = [
    "contrapositive",
    "disjunctive_syllogism",
    "double_implication",
    "symmetrical_equivalence",
    "implication_of_result",
]
_ARCHETYPE_ROTATION = ["preparedness_buyer", "mobile_professional", "outdoor_adventurer"]


def _pick_swap(current: str, options: list[str]) -> str:
    if not current:
        return options[0]
    try:
        idx = options.index(current)
        return options[(idx + 1) % len(options)]
    except ValueError:
        return options[0]


def run(data_dir: str, count: int | None = None) -> dict:
    n = int(count if count is not None else env_int("AB_VARIANT_COUNT", 2))
    history_path = os.path.join(data_dir, "post_history.json")
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = {"posts": []}
    posts = history.get("posts") if isinstance(history, dict) else []
    if not isinstance(posts, list):
        posts = []

    experiments: list[dict] = []
    seen_post_ids: set[str] = set()
    for row in reversed(posts):
        if len(experiments) >= n:
            break
        if not isinstance(row, dict):
            continue
        if row.get("status") != "success":
            continue
        post_id = str(row.get("post_id") or "").strip()
        if not post_id or post_id in seen_post_ids:
            continue
        seen_post_ids.add(post_id)

        strat = row.get("logical_emotional_strategy") if isinstance(row.get("logical_emotional_strategy"), dict) else {}
        current_principle = str(strat.get("principle_key", "") or "")
        current_archetype = str(strat.get("archetype_key", "") or "")

        swap_mode = "principle" if len(experiments) % 2 == 0 else "archetype"
        if swap_mode == "principle":
            new_principle = _pick_swap(current_principle, _PRINCIPLE_ROTATION)
            new_archetype = current_archetype
        else:
            new_principle = current_principle
            new_archetype = _pick_swap(current_archetype, _ARCHETYPE_ROTATION)

        experiment_id = f"exp_{uuid.uuid4().hex[:10]}"
        experiments.append(
            {
                "experiment_id": experiment_id,
                "control_post_id": post_id,
                "control_principle_key": current_principle,
                "control_archetype_key": current_archetype,
                "variant_principle_key": new_principle,
                "variant_archetype_key": new_archetype,
                "swap_dimension": swap_mode,
                "product_id": row.get("product_id"),
                "topic": row.get("topic"),
                "created_at_utc": utc_now(),
            }
        )

    experiments_path = os.path.join(data_dir, "experiments", "pending_experiments.json")
    os.makedirs(os.path.dirname(experiments_path), exist_ok=True)
    try:
        with open(experiments_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if not isinstance(existing, dict):
            existing = {"experiments": []}
    except Exception:
        existing = {"experiments": []}
    existing.setdefault("experiments", [])
    existing["experiments"].extend(experiments)
    existing["experiments"] = existing["experiments"][-100:]
    with open(experiments_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, default=str)

    payload = {
        "agent": "ab_variant_orchestrator",
        "time_utc": utc_now(),
        "created": len(experiments),
        "experiments": experiments,
    }
    write_snapshot(data_dir, "ab_variant_orchestrator", payload)
    return payload
