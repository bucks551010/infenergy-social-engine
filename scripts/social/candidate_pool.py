"""History-backed rotation and persistent text-candidate pool utilities."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


POOL_FILENAME = "candidate_pool.json"
DEFAULT_TTL_DAYS = 7
DEFAULT_EXPLORATION_FLOOR = 0.25
ROTATION_DIMENSIONS = (
    "product_id",
    "topic",
    "hook_category",
    "scenario",
    "lesson",
    "awareness_level",
    "emotional_driver",
    "copy_structure",
)
_WINDOW_KEYS = {
    "product_id": "product_feature_days",
    "topic": "topic_days",
    "hook_category": "hook_days",
    "scenario": "topic_days",
    "lesson": "topic_days",
    "awareness_level": "hook_days",
    "emotional_driver": "hook_days",
    "copy_structure": "hook_days",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if len(raw) == 10 and "-" in raw:
            return datetime.fromisoformat(raw + "T00:00:00+00:00")
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _history_timestamp(post: dict[str, Any]) -> datetime | None:
    return _parse_datetime(post.get("run_started_at_utc") or post.get("published_at") or post.get("date"))


def _rotation_value(payload: dict[str, Any], dimension: str) -> str:
    if dimension == "hook_category":
        return str(payload.get("hook_category") or payload.get("selected_hook_type") or "").strip()
    if dimension == "lesson":
        return str(payload.get("lesson") or payload.get("educational_lesson") or "").strip()
    if dimension in {"awareness_level", "emotional_driver", "copy_structure"}:
        brief = payload.get("strategic_brief") if isinstance(payload.get("strategic_brief"), dict) else {}
        return str(payload.get(dimension) or brief.get(dimension) or "").strip()
    return str(payload.get(dimension) or "").strip()


def build_rotation_ledger(
    history: dict[str, Any],
    windows: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return last-use timestamps and active cooldown values from publish history."""
    now = now or _utc_now()
    posts = history.get("posts", []) if isinstance(history, dict) else []
    ledger: dict[str, dict[str, str]] = {dimension: {} for dimension in ROTATION_DIMENSIONS}
    unavailable = not isinstance(posts, list)
    for post in posts if isinstance(posts, list) else []:
        if not isinstance(post, dict) or str(post.get("status", "")).startswith("skipped"):
            continue
        timestamp = _history_timestamp(post)
        if not timestamp:
            continue
        for dimension in ROTATION_DIMENSIONS:
            value = _rotation_value(post, dimension)
            if not value:
                continue
            prior = _parse_datetime(ledger[dimension].get(value))
            if prior is None or timestamp > prior:
                ledger[dimension][value] = timestamp.isoformat()

    cooldown_days = {
        dimension: max(0, int(windows.get(window_key, 0) or 0))
        for dimension, window_key in _WINDOW_KEYS.items()
    }
    return {
        "generated_at_utc": now.isoformat(),
        "ledger_unavailable": unavailable,
        "cooldown_days": cooldown_days,
        "last_used_at": ledger,
    }


def select_least_recently_used(
    candidates: list[dict[str, Any]],
    dimension: str,
    ledger: dict[str, Any],
    *,
    value_key: str | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Select an eligible LRU candidate, falling back to full-pool LRU on exhaustion."""
    now = now or _utc_now()
    value_key = value_key or dimension
    last_used = ledger.get("last_used_at", {}).get(dimension, {}) if isinstance(ledger, dict) else {}
    cooldown_days = int((ledger.get("cooldown_days", {}) if isinstance(ledger, dict) else {}).get(dimension, 0) or 0)
    cutoff = now - timedelta(days=max(0, cooldown_days))

    cleaned = [candidate for candidate in candidates if isinstance(candidate, dict) and str(candidate.get(value_key) or "").strip()]
    eligible: list[dict[str, Any]] = []
    for candidate in cleaned:
        used_at = _parse_datetime(last_used.get(str(candidate.get(value_key)).strip()))
        if used_at is None or used_at < cutoff:
            eligible.append(candidate)

    pool = eligible or cleaned
    selected = min(
        pool,
        key=lambda candidate: _parse_datetime(last_used.get(str(candidate.get(value_key)).strip())) or datetime.min.replace(tzinfo=timezone.utc),
        default=None,
    )
    return selected, {
        "dimension": dimension,
        "pool_size": len(cleaned),
        "excluded_count": len(cleaned) - len(eligible),
        "selected": str(selected.get(value_key) or "") if selected else "",
        "selection_reason": "eligible_lru" if eligible else "rotation_exhausted_lru_fallback",
        "rotation_exhausted": bool(cleaned and not eligible),
    }


class CandidatePool:
    def __init__(self, data_dir: str, *, ttl_days: int = DEFAULT_TTL_DAYS) -> None:
        self.path = os.path.join(data_dir, "social", POOL_FILENAME)
        self.ttl_days = max(1, int(ttl_days))

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {"candidates": []}
        except (OSError, ValueError, json.JSONDecodeError):
            return {"candidates": []}

    def _save(self, payload: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(prefix="candidate_pool_", suffix=".json", dir=os.path.dirname(self.path))
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2)
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _expire(self, payload: dict[str, Any], now: datetime) -> bool:
        changed = False
        cutoff = now - timedelta(days=self.ttl_days)
        for candidate in payload.get("candidates", []):
            if not isinstance(candidate, dict) or candidate.get("status") != "available":
                continue
            created_at = _parse_datetime(candidate.get("created_at"))
            if created_at is not None and created_at < cutoff:
                candidate["status"] = "expired"
                candidate["expired_at"] = now.isoformat()
                changed = True
        return changed

    def add(
        self,
        content: dict[str, Any],
        *,
        rotation: dict[str, Any],
        batch_gate_results: dict[str, Any],
        selection_lane: str = "proven",
    ) -> dict[str, Any]:
        now = _utc_now()
        payload = self._load()
        self._expire(payload, now)
        candidate = {
            "candidate_id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "status": "available",
            "content": content,
            "rotation_selected": rotation,
            "batch_gate_results": batch_gate_results,
            "selection_lane": "exploration" if selection_lane == "exploration" else "proven",
        }
        payload.setdefault("candidates", []).append(candidate)
        self._save(payload)
        return candidate

    def available(self) -> list[dict[str, Any]]:
        now = _utc_now()
        payload = self._load()
        if self._expire(payload, now):
            self._save(payload)
        return [candidate for candidate in payload.get("candidates", []) if isinstance(candidate, dict) and candidate.get("status") == "available"]

    def select_for_publication(self, *, exploration_floor: float = DEFAULT_EXPLORATION_FLOOR) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Select LRU content while preserving a bounded exploration allocation."""
        floor = min(0.5, max(0.0, float(exploration_floor)))
        payload = self._load()
        now = _utc_now()
        if self._expire(payload, now):
            self._save(payload)
            payload = self._load()

        available = [candidate for candidate in payload.get("candidates", []) if isinstance(candidate, dict) and candidate.get("status") == "available"]
        available.sort(key=lambda candidate: str(candidate.get("created_at") or ""))
        exploratory = [candidate for candidate in available if candidate.get("selection_lane") == "exploration"]
        events = [event for event in payload.get("selection_events", []) if isinstance(event, dict)]
        exploration_count = sum(1 for event in events if event.get("selection_lane") == "exploration")
        exploration_rate = exploration_count / len(events) if events else 0.0
        reserve_due = bool(exploratory and exploration_rate < floor)
        selected = (exploratory if reserve_due else available)
        candidate = selected[0] if selected else None
        lane = str(candidate.get("selection_lane") or "proven") if candidate else ""
        telemetry = {
            "selection_lane": lane,
            "selection_reason": "exploration_reserve" if reserve_due else "least_recently_created",
            "exploration_floor": floor,
            "exploration_rate_before": round(exploration_rate, 3),
            "available_exploration_candidates": len(exploratory),
        }
        if candidate:
            events.append({
                "candidate_id": candidate.get("candidate_id", ""),
                "selection_lane": lane,
                "selected_at": now.isoformat(),
            })
            payload["selection_events"] = events[-100:]
            self._save(payload)
        return candidate, telemetry

    def consume(self, candidate_id: str, *, published_at: str | None = None) -> bool:
        payload = self._load()
        for candidate in payload.get("candidates", []):
            if isinstance(candidate, dict) and candidate.get("candidate_id") == candidate_id and candidate.get("status") == "available":
                candidate["status"] = "consumed"
                candidate["consumed_at"] = published_at or _utc_now().isoformat()
                self._save(payload)
                return True
        return False

    def quarantine(self, candidate_id: str, *, reason: str = "", quarantined_at: str | None = None) -> bool:
        """Mark a candidate as quarantined so it won't be re-selected.

        Use this when a candidate fails a gate (e.g., duplicate check) but wasn't
        published. Without quarantine, the candidate remains "available" and gets
        re-selected indefinitely, causing the same failure repeatedly.
        """
        payload = self._load()
        for candidate in payload.get("candidates", []):
            if isinstance(candidate, dict) and candidate.get("candidate_id") == candidate_id and candidate.get("status") == "available":
                candidate["status"] = "quarantined"
                candidate["quarantined_at"] = quarantined_at or _utc_now().isoformat()
                candidate["quarantine_reason"] = reason or "unspecified"
                self._save(payload)
                return True
        return False

    def depth(self) -> int:
        return len(self.available())