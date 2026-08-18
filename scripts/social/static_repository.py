"""Read-only boundary for owner-authored Human Truth repository assets."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STATIC_PATHS = (
    REPOSITORY_ROOT / "data" / "marketing" / "founder_brand_manifesto.json",
    REPOSITORY_ROOT / "data" / "marketing" / "funnel_config.json",
    REPOSITORY_ROOT / "data" / "marketing" / "human_truth",
    REPOSITORY_ROOT / "data" / "marketing" / "conversion",
)


def is_static_path(path: str | Path) -> bool:
    candidate = Path(path).resolve()
    for static_path in STATIC_PATHS:
        resolved_static_path = static_path.resolve()
        if candidate == resolved_static_path or resolved_static_path in candidate.parents:
            return True
    return False


def guard_static_write(path: str | Path) -> None:
    if is_static_path(path):
        message = f"static_repository_write_blocked:{Path(path)}"
        logging.error(message)
        raise RuntimeError(message)


def write_living_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Persist system-authored data only after enforcing the static boundary."""
    target = Path(path)
    guard_static_write(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")