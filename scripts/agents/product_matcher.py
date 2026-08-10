"""Tier-2 #7: product_matcher_agent.

Ranks active products in inventory_db against a given (topic, funnel_stage,
archetype) triple using keyword overlap + engagement-informed reordering when
available.
"""

from __future__ import annotations

import os
import re

from ._base import utc_now, write_snapshot

_ARCHETYPE_KEYWORDS = {
    "mobile_professional": {"power bank", "charger", "usb", "commuter", "everyday", "portable"},
    "preparedness_buyer": {"backup", "outage", "power station", "generator", "emergency", "battery"},
    "outdoor_adventurer": {"solar", "panel", "camping", "travel", "off-grid", "fan", "water", "filter"},
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(t) >= 3}


def _product_text(product: dict) -> str:
    parts = [
        str(product.get("name", "") or ""),
        " ".join(str(c) for c in (product.get("categories") or [])),
        " ".join(str(m) for m in (product.get("metrics") or [])),
        str(product.get("description", "") or ""),
    ]
    return " ".join(parts)


def _score(product: dict, topic: str, archetype_key: str, funnel_stage: str) -> float:
    text = _product_text(product).lower()
    topic_tokens = _tokens(topic)
    matches = sum(1 for t in topic_tokens if t in text)
    arche_keywords = _ARCHETYPE_KEYWORDS.get(archetype_key, set())
    arche_matches = sum(1 for k in arche_keywords if k in text)
    stage_bonus = 0.0
    stage = str(funnel_stage or "").strip().upper()
    if stage == "CONVERSION" and any(t in text for t in ("power station", "bundle", "kit")):
        stage_bonus = 0.5
    return matches + 1.5 * arche_matches + stage_bonus


def run(
    data_dir: str,
    topic: str = "",
    funnel_stage: str = "EDUCATION",
    archetype_key: str = "preparedness_buyer",
    limit: int = 5,
) -> dict:
    products: list[dict] = []
    try:
        import inventory_db  # type: ignore

        inventory_db.init_inventory_db(data_dir)
        snapshot = inventory_db.get_inventory_snapshot(data_dir)
        products = snapshot.get("products", []) if isinstance(snapshot, dict) else []
    except Exception:
        products = []

    ranked = sorted(
        (
            {
                "product_id": p.get("id") or p.get("product_id"),
                "name": p.get("name"),
                "categories": p.get("categories", []),
                "score": round(_score(p, topic, archetype_key, funnel_stage), 3),
            }
            for p in products
            if isinstance(p, dict)
        ),
        key=lambda r: r["score"],
        reverse=True,
    )
    ranked = ranked[: max(1, min(limit, 25))]

    payload = {
        "agent": "product_matcher",
        "time_utc": utc_now(),
        "topic": topic,
        "funnel_stage": funnel_stage,
        "archetype_key": archetype_key,
        "candidates": ranked,
        "top_choice": ranked[0] if ranked else None,
    }
    write_snapshot(data_dir, "product_matcher", payload)
    return payload
