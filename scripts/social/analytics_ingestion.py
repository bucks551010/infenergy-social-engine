"""Incremental, platform-aware performance observation from published IDs."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests


def collect_meta(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch only metrics Graph returns for existing Facebook/Instagram IDs."""
    token = os.environ.get("META_PAGE_ACCESS_TOKEN", "").strip()
    if not token:
        return []
    observations: list[dict[str, Any]] = []
    for platform, key in (("facebook", "fb_id"), ("instagram", "ig_id")):
        post_id = str(record.get(key, "") or "").strip()
        if not post_id or post_id in {"skipped", "dry-run"}:
            continue
        response = requests.get(f"https://graph.facebook.com/v26.0/{post_id}/insights", params={"access_token": token}, timeout=20)
        if not response.ok:
            continue
        metrics: dict[str, float] = {}
        for item in (response.json() or {}).get("data", []):
            name = str(item.get("name", ""))
            values = item.get("values") or []
            if values and isinstance(values[0], dict) and isinstance(values[0].get("value"), (int, float)):
                metrics[name] = float(values[0]["value"])
        observations.append({"platform_post_id": post_id, "platform": platform, "published_at": record.get("published_at", ""), "metrics": metrics, "collected_at": datetime.now(timezone.utc).isoformat()})
    return observations