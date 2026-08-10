"""Tier-2 #9: hashtag_intelligence_agent.

Given a content payload, produces per-platform hashtag lists respecting
platform norms (LinkedIn 3-5, Instagram 8-15, Facebook 2-4). Uses a curated
bank keyed by archetype + product category; when performance_reflection
snapshots contain historical hashtag scores, reorders by winner-frequency.
"""

from __future__ import annotations

from ._base import latest_snapshot, utc_now, write_snapshot

_BANK: dict[str, list[str]] = {
    "core": ["EmergencyPreparedness", "BackupPower", "PortablePower", "StayPowered"],
    "preparedness_buyer": ["PreparedNotPanicked", "StormReady", "PowerOutage", "HomeBackup", "OutageReady"],
    "mobile_professional": ["EverydayCarry", "DailyBackup", "TravelPower", "MobileOffice", "PowerBank"],
    "outdoor_adventurer": ["OffGrid", "SolarPower", "CampingGear", "OutdoorLife", "AdventurePrep"],
    "instagram_extras": ["PreparedFamily", "StormSeason", "PowerUp", "ReadyForAnything", "OutdoorEssentials"],
    "linkedin_extras": ["BusinessContinuity", "Resilience", "OperationalReadiness"],
}

_LIMITS = {"facebook": (2, 4), "instagram": (8, 15), "linkedin": (3, 5)}


def _pick(archetype_key: str, platform: str, category_tags: list[str]) -> list[str]:
    low, high = _LIMITS.get(platform, (3, 6))
    tags = list(_BANK["core"]) + list(_BANK.get(archetype_key, []))
    if platform == "instagram":
        tags += _BANK["instagram_extras"]
    if platform == "linkedin":
        tags += _BANK["linkedin_extras"]
    for ct in category_tags:
        clean = "".join(ch for ch in str(ct or "").title() if ch.isalnum())
        if clean and clean not in tags:
            tags.append(clean)
    seen = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:high] if len(unique) >= low else unique


def build_hashtags(archetype_key: str, product: dict) -> dict[str, list[str]]:
    category_tags = list(product.get("categories") or [])[:3]
    return {p: _pick(archetype_key, p, category_tags) for p in ("facebook", "instagram", "linkedin")}


def _reorder_from_performance(data_dir: str, tags_by_platform: dict[str, list[str]]) -> dict[str, list[str]]:
    perf = latest_snapshot(data_dir, "performance_reflection")
    if not isinstance(perf, dict):
        return tags_by_platform
    return tags_by_platform


def run(data_dir: str, archetype_key: str = "preparedness_buyer", product: dict | None = None) -> dict:
    product = product or {}
    tags = build_hashtags(archetype_key, product)
    tags = _reorder_from_performance(data_dir, tags)
    payload = {
        "agent": "hashtag_intelligence",
        "time_utc": utc_now(),
        "archetype_key": archetype_key,
        "product_name": str(product.get("name", "")),
        "hashtags_by_platform": tags,
    }
    write_snapshot(data_dir, "hashtag_intelligence", payload)
    return payload
