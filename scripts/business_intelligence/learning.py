"""Learning + owner overrides + locked/learnable classification.

Master Build §39, §48-§50, §66.

* ``LOCKED_FIELDS`` — never mutated by performance learning (identity,
  mission, brand promise, voice principles).
* ``LEARNABLE_FIELDS`` — evolve from performance data with smoothing.
* Owner overrides persist across rebuilds and beat all other sources.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from typing import Any, Iterable

from . import paths
from .schemas import LearningRecord, OwnerOverride


# --- Locked vs learnable ------------------------------------------------


LOCKED_FIELDS: tuple[str, ...] = (
    "identity.business_name",
    "identity.business_type",
    "why.mission",
    "why.vision",
    "why.foundational_problem",
    "promise.promise",
    "voice.brand_personality",
    "voice.voice_principles",
    "visual.brand_colors",
    "visual.logo_assets",
    "reputation.desired_reputation",
    "worldview.enduring_principles",
)


LEARNABLE_FIELDS: tuple[str, ...] = (
    "audience_segments.emotional_drivers",
    "audience_segments.questions",
    "audience_segments.misconceptions",
    "content_territories",
    "positioning.differentiators",
    "positioning.positioning_whitespace",
    "voice.preferred_phrases",
    "learning_state.hooks",
    "learning_state.ctas",
    "learning_state.formats",
    "learning_state.pillars",
)


def is_locked(field_path: str) -> bool:
    for locked in LOCKED_FIELDS:
        if field_path == locked or field_path.startswith(locked + "."):
            return True
    return False


def is_learnable(field_path: str) -> bool:
    for learn in LEARNABLE_FIELDS:
        if field_path == learn or field_path.startswith(learn + "."):
            return True
    return False


# --- Owner overrides (§66) ---------------------------------------------


def overrides_path() -> str:
    return os.path.join(paths.overrides_dir(), "overrides.json")


def load_overrides() -> list[OwnerOverride]:
    p = overrides_path()
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [OwnerOverride(**o) for o in data.get("overrides", [])]
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_overrides(overrides: Iterable[OwnerOverride]) -> None:
    with open(overrides_path(), "w", encoding="utf-8") as fh:
        json.dump({"overrides": [asdict(o) for o in overrides]}, fh, indent=2)


def register_override(
    *,
    subject: str,
    field_path: str,
    value: Any,
    reason: str = "",
    persistent: bool = True,
) -> OwnerOverride:
    from datetime import datetime, timezone
    ov = OwnerOverride(
        override_id=uuid.uuid4().hex[:12],
        subject=subject,
        field_path=field_path,
        value=value,
        reason=reason,
        applied_at=datetime.now(timezone.utc).isoformat(),
        persistent=persistent,
    )
    existing = load_overrides()
    # Replace any earlier override for the same field_path
    filtered = [o for o in existing if o.field_path != field_path]
    filtered.append(ov)
    save_overrides(filtered)
    return ov


def apply_overrides(profile_dict: dict[str, Any]) -> dict[str, Any]:
    """Apply persistent owner overrides to a profile dict."""
    for ov in load_overrides():
        if not ov.persistent:
            continue
        cursor: Any = profile_dict
        parts = ov.field_path.split(".")
        for part in parts[:-1]:
            if isinstance(cursor, dict):
                cursor = cursor.setdefault(part, {})
            else:
                break
        if isinstance(cursor, dict):
            cursor[parts[-1]] = ov.value
    return profile_dict


# --- Performance learning (§48-§50) ------------------------------------


def learning_path() -> str:
    return os.path.join(paths.learning_dir(), "performance_learning.jsonl")


def record_signal(
    *,
    scope: str,
    subject: str,
    signal: str,
    weight: float = 1.0,
    sample_size: int = 1,
    source_post_id: str = "",
) -> LearningRecord:
    from datetime import datetime, timezone
    if is_locked(f"{scope}.{subject}"):
        raise ValueError(f"{scope}.{subject} is a LOCKED field; performance signals cannot mutate it")
    rec = LearningRecord(
        record_id=uuid.uuid4().hex[:12],
        scope=scope,
        subject=subject,
        signal=signal,
        weight=weight,
        sample_size=sample_size,
        observed_at=datetime.now(timezone.utc).isoformat(),
        source_post_id=source_post_id,
    )
    os.makedirs(os.path.dirname(learning_path()), exist_ok=True)
    with open(learning_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
    return rec


def load_learning() -> list[LearningRecord]:
    p = learning_path()
    if not os.path.isfile(p):
        return []
    out: list[LearningRecord] = []
    with open(p, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(LearningRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
    return out


def summarize_learning(min_sample_size: int = 3) -> dict[str, Any]:
    """§48: aggregate signals with a minimum-evidence threshold."""
    records = load_learning()
    by_key: dict[tuple[str, str], list[LearningRecord]] = {}
    for r in records:
        by_key.setdefault((r.scope, r.subject), []).append(r)
    summary: dict[str, Any] = {}
    for (scope, subject), items in by_key.items():
        if len(items) < min_sample_size:
            continue
        positive = sum(r.weight for r in items if r.signal == "positive")
        negative = sum(r.weight for r in items if r.signal == "negative")
        summary.setdefault(scope, {})[subject] = {
            "sample": len(items),
            "positive": positive,
            "negative": negative,
            "score": round((positive - negative) / max(1.0, positive + negative + 1), 3),
        }
    return summary
