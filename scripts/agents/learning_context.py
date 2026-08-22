"""Read-only operational learning shared across agents and generation paths."""

from __future__ import annotations

from typing import Any

from ._base import latest_snapshot
from .learning_ingestion import load_recent_lessons


def _names(rows: Any, limit: int = 8) -> list[str]:
    values: list[str] = []
    for row in rows if isinstance(rows, list) else []:
        value = row[0] if isinstance(row, (list, tuple)) and row else row
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)
    return values[:limit]


def load_operational_learning(data_dir: str) -> dict[str, Any]:
    """Combine verified recent lessons without allowing them to replace company truth."""
    recent = load_recent_lessons(data_dir)
    reflection = latest_snapshot(data_dir, "performance_reflection") or {}
    winners = _names(reflection.get("winning_patterns"), 12)
    losers = _names(reflection.get("losing_patterns"), 12)
    winning_hooks = _names(recent.get("winning_hooks"), 8)
    losing_hooks = _names(recent.get("losing_hooks"), 8)
    warnings = _names(recent.get("top_warnings"), 8)
    errors = _names(recent.get("top_errors"), 8)
    return {
        "contract_version": "infenergy-operational-learning-v1",
        "authority": "advisory_below_canonical_company_and_product_truth",
        "evidence_rules": [
            "Apply patterns only within the platform, funnel stage, archetype, or hook dimension named by the evidence.",
            "Reuse the principle behind a winner, never its exact wording or visual execution.",
            "Treat missing or sparse evidence as unknown, not as permission to invent a rule.",
        ],
        "winning_patterns": winners,
        "losing_patterns": losers,
        "winning_hook_examples": winning_hooks,
        "losing_hook_examples": losing_hooks,
        "quality_warnings_to_resolve": warnings,
        "validation_errors_to_prevent": errors,
        "sources": {
            "recent_lessons_time_utc": str(recent.get("time_utc") or ""),
            "performance_reflection_time_utc": str(reflection.get("time_utc") or ""),
            "posts_analyzed": max(
                int(recent.get("posts_analyzed") or 0),
                int(reflection.get("posts_analyzed") or 0),
            ),
        },
    }