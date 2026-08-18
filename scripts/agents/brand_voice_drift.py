"""Tier-2 #8: brand_voice_drift_agent.

Compares recent captions against banned phrases + brand voice signature from
the founder manifesto and produces a drift score with per-caption findings.
"""

from __future__ import annotations

import json
import os
import re

from ._base import env_int, utc_now, write_snapshot


def _load_manifesto(data_dir: str) -> dict:
    path = os.path.join(data_dir, "marketing", "founder_brand_manifesto.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_captions(data_dir: str, limit: int) -> list[dict]:
    path = os.path.join(data_dir, "post_history.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        return []
    posts = history.get("posts") if isinstance(history, dict) else []
    if not isinstance(posts, list):
        return []
    tail = posts[-limit:]
    out: list[dict] = []
    for row in tail:
        if not isinstance(row, dict):
            continue
        for key, platform in (("fb_caption", "facebook"), ("ig_caption", "instagram"), ("li_text", "linkedin")):
            text = str(row.get(key, "") or "").strip()
            if text:
                out.append({"post_id": row.get("post_id"), "platform": platform, "text": text})
    return out


def _manifesto_drift_rules(manifesto: dict) -> tuple[list[str], set[str]]:
    guardrails = manifesto.get("guardrails", {}) if isinstance(manifesto.get("guardrails"), dict) else {}
    business_profile = manifesto.get("business_profile", {}) if isinstance(manifesto.get("business_profile"), dict) else {}
    banned_values = list(manifesto.get("banned_phrases", [])) + list(guardrails.get("disallowed_claim_patterns", []))
    banned = list(dict.fromkeys(str(value).strip().lower() for value in banned_values if str(value).strip()))
    positioning = str(manifesto.get("positioning") or business_profile.get("positioning") or "").lower()
    return banned, set(re.findall(r"[a-z0-9]+", positioning))


def run(data_dir: str) -> dict:
    limit = env_int("BRAND_DRIFT_LOOKBACK", 20)
    manifesto = _load_manifesto(data_dir)
    banned, positioning_tokens = _manifesto_drift_rules(manifesto)

    captions = _load_captions(data_dir, limit)
    per_caption: list[dict] = []
    total_hits = 0
    for c in captions:
        low = c["text"].lower()
        hits = [b for b in banned if b in low]
        token_overlap = len(positioning_tokens.intersection(re.findall(r"[a-z0-9]+", low))) if positioning_tokens else 0
        drift = bool(hits)
        if hits:
            total_hits += len(hits)
        per_caption.append(
            {
                "post_id": c["post_id"],
                "platform": c["platform"],
                "banned_hits": hits,
                "positioning_overlap": token_overlap,
                "drift": drift,
            }
        )

    n = max(1, len(captions))
    drift_ratio = round(sum(1 for x in per_caption if x["drift"]) / n, 3)
    payload = {
        "agent": "brand_voice_drift",
        "time_utc": utc_now(),
        "captions_analyzed": len(captions),
        "banned_phrase_count": len(banned),
        "total_banned_hits": total_hits,
        "drift_ratio": drift_ratio,
        "drift_status": "green" if drift_ratio < 0.1 else "yellow" if drift_ratio < 0.25 else "red",
        "per_caption": per_caption[-30:],
    }
    write_snapshot(data_dir, "brand_voice_drift", payload)
    return payload
