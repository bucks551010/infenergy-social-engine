"""Performance memory - Spec Section 27.

Reads data/post_history.json and derives a "what has worked" signal for
the ConversionLogicEngine. Success is measured by (in order of preference):
- engagement metrics if present on the history entry
- content quality_score as a proxy
- CQS total (conversion_quality_score.total) if present
- brief_adherence adherence_pct if present

The engine then uses these winning combinations to bias selection of
logic_law / copy_framework / emotional_driver with a 70/30 exploit/explore
split (see engine.py).
"""

from __future__ import annotations

import json
import os
from typing import Any


def _history_path(data_dir: str | None) -> str:
    base = data_dir or os.environ.get("DATA_DIR") or os.path.join(os.getcwd(), "data")
    return os.path.join(base, "post_history.json")


def load_history(data_dir: str | None = None) -> list[dict]:
    path = _history_path(data_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, dict) and isinstance(data.get("posts"), list):
        return data["posts"]
    if isinstance(data, list):
        return data
    return []


def _entry_score(entry: dict) -> float:
    """Combine any available success signal into a single 0-100 score."""
    if not isinstance(entry, dict):
        return 0.0
    # 1. explicit engagement metrics take priority
    metrics = entry.get("engagement") or entry.get("metrics") or {}
    if isinstance(metrics, dict):
        for key in ("engagement_rate", "success_score", "score"):
            v = metrics.get(key)
            if isinstance(v, (int, float)) and v > 0:
                return float(v) * (100.0 if 0 <= v <= 1 else 1.0)
    # 2. conversion quality score
    cqs = entry.get("conversion_quality_score") or {}
    if isinstance(cqs, dict) and isinstance(cqs.get("total"), (int, float)):
        return float(cqs["total"])
    # 3. brief adherence
    adh = entry.get("conversion_brief_adherence") or {}
    if isinstance(adh, dict) and isinstance(adh.get("adherence_pct"), (int, float)):
        return float(adh["adherence_pct"])
    # 4. standard quality score (0-1 scaled to 0-100)
    q = entry.get("quality_score")
    if isinstance(q, (int, float)):
        return float(q) * (100.0 if 0 <= q <= 1.0 else 1.0)
    return 50.0


def _brief_of(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {}
    b = entry.get("strategic_brief")
    return b if isinstance(b, dict) else {}


def _key_of(entry: dict, field: str) -> str:
    brief = _brief_of(entry)
    if brief.get(field):
        return str(brief[field])
    if entry.get(field):
        return str(entry[field])
    if field == "logic_principle":
        les = entry.get("logical_emotional_strategy") or {}
        if isinstance(les, dict) and les.get("principle_key"):
            return str(les["principle_key"])
    return ""


def summarize(entries: list[dict], min_success: float = 65.0) -> dict[str, Any]:
    """Bucket entries by (logic_principle, copy_framework, emotional_driver_primary,
    audience_id, awareness_stage) and return winners / losers per field.
    """
    fields = ("logic_principle", "copy_framework", "emotional_driver_primary", "audience_id", "awareness_stage")
    tallies: dict[str, dict[str, dict[str, Any]]] = {f: {} for f in fields}
    for entry in entries or []:
        score = _entry_score(entry)
        for f in fields:
            k = _key_of(entry, f)
            if not k:
                continue
            slot = tallies[f].setdefault(k, {"count": 0, "sum": 0.0, "wins": 0, "losses": 0})
            slot["count"] += 1
            slot["sum"] += score
            if score >= min_success:
                slot["wins"] += 1
            else:
                slot["losses"] += 1

    summary: dict[str, Any] = {"fields": {}}
    for f in fields:
        ranked: list[dict[str, Any]] = []
        for k, s in tallies[f].items():
            avg = s["sum"] / max(s["count"], 1)
            ranked.append({
                "value": k,
                "count": s["count"],
                "avg_score": round(avg, 2),
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": round(s["wins"] / max(s["count"], 1), 3),
            })
        ranked.sort(key=lambda x: (x["avg_score"], x["count"]), reverse=True)
        # loser threshold - anything at or below 40 counts as an avoid signal.
        summary["fields"][f] = {
            "top": [r["value"] for r in ranked[:5] if r["avg_score"] >= min_success],
            "avoid": [r["value"] for r in ranked if r["avg_score"] <= 40.0][:5],
            "ranked": ranked[:20],
        }
    summary["sample_size"] = len(entries or [])
    summary["min_success"] = min_success
    return summary


def winning_hints(data_dir: str | None = None, min_success: float = 65.0) -> dict[str, list[str]]:
    """Convenience wrapper - returns {logic_principle:[...], copy_framework:[...], ...}."""
    entries = load_history(data_dir)
    summary = summarize(entries, min_success=min_success)
    return {f: cfg.get("top", []) for f, cfg in summary["fields"].items()}


def losing_hints(data_dir: str | None = None, min_success: float = 65.0) -> dict[str, list[str]]:
    entries = load_history(data_dir)
    summary = summarize(entries, min_success=min_success)
    return {f: cfg.get("avoid", []) for f, cfg in summary["fields"].items()}
