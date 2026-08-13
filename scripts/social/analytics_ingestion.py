"""Incremental, platform-aware performance observation from published IDs."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests


DEFAULT_WINDOWS_HOURS = (24, 168, 720)


def configured_windows() -> tuple[int, ...]:
    """Read three non-negative observation windows without making deployment config fragile."""
    raw = os.environ.get("ANALYTICS_WINDOWS_HOURS", "").strip()
    if not raw:
        return DEFAULT_WINDOWS_HOURS
    try:
        values = tuple(int(value.strip()) for value in raw.split(","))
    except ValueError:
        return DEFAULT_WINDOWS_HOURS
    return values if len(values) == 3 and all(value >= 0 for value in values) and tuple(sorted(values)) == values else DEFAULT_WINDOWS_HOURS


def due(record: dict[str, Any], *, now: datetime | None = None, windows_hours: tuple[int, ...] | None = None) -> str | None:
    """Return the next observation stage without treating absent metrics as zero."""
    windows_hours = windows_hours or configured_windows()
    raw = str(record.get("published_at") or "").replace("Z", "+00:00")
    try:
        published = datetime.fromisoformat(raw)
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    age = (now - (published if published.tzinfo else published.replace(tzinfo=timezone.utc))).total_seconds() / 3600
    collected = {str(item.get("window", "")) for item in record.get("analytics_observations", [])}
    for label, threshold in zip(("EARLY", "INTERMEDIATE", "MATURE"), windows_hours):
        if age >= threshold and label not in collected:
            return label
    return None


def collect_meta(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch only metrics Graph returns for existing Facebook/Instagram IDs."""
    token = os.environ.get("META_PAGE_ACCESS_TOKEN", "").strip()
    if not token:
        return [{"status": "AUTHENTICATION_REQUIRED", "platform": platform} for platform, key in (("facebook", "fb_id"), ("instagram", "ig_id")) if record.get(key)]
    observations: list[dict[str, Any]] = []
    for platform, key in (("facebook", "fb_id"), ("instagram", "ig_id")):
        post_id = str(record.get(key, "") or "").strip()
        if not post_id or post_id in {"skipped", "dry-run"}:
            continue
        response = requests.get(f"https://graph.facebook.com/v26.0/{post_id}/insights", params={"access_token": token}, timeout=20)
        if not response.ok:
            observations.append({"platform_post_id": post_id, "platform": platform, "status": "SOURCE_UNAVAILABLE", "http_status": response.status_code, "collected_at": datetime.now(timezone.utc).isoformat()})
            continue
        metrics: dict[str, float] = {}
        for item in (response.json() or {}).get("data", []):
            name = str(item.get("name", ""))
            values = item.get("values") or []
            if values and isinstance(values[0], dict) and isinstance(values[0].get("value"), (int, float)):
                metrics[name] = float(values[0]["value"])
        observations.append({"platform_post_id": post_id, "platform": platform, "published_at": record.get("published_at", ""), "raw_observation": {"metrics": metrics}, "derived_metrics": {}, "collected_at": datetime.now(timezone.utc).isoformat()})
    return observations