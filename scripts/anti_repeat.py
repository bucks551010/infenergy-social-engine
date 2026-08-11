from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from campaign_runtime import stable_text_hash

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "..", "data"))
MARKETING_DIR = os.path.join(DATA_DIR, "marketing")

DEFAULT_WINDOWS = {
    "exact_caption_days": 180,
    "hook_days": 60,
    "product_feature_days": 7,
    "topic_days": 21,
    "cta_days": 14,
}


def _config_path() -> str:
    return os.path.join(MARKETING_DIR, "anti_repeat_config.json")


def ensure_anti_repeat_config() -> None:
    os.makedirs(MARKETING_DIR, exist_ok=True)
    path = _config_path()
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_WINDOWS, f, indent=2)


def load_anti_repeat_windows() -> dict[str, int]:
    ensure_anti_repeat_config()
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            out = dict(DEFAULT_WINDOWS)
            if isinstance(data, dict):
                for k in DEFAULT_WINDOWS:
                    try:
                        out[k] = int(data.get(k, out[k]))
                    except Exception:
                        pass
            return out
    except Exception:
        return dict(DEFAULT_WINDOWS)


def _parse_dt(post: dict[str, Any]) -> datetime | None:
    raw = str(post.get("run_started_at_utc") or post.get("published_at") or post.get("date") or "").strip()
    if not raw:
        return None
    try:
        if len(raw) == 10 and "-" in raw:
            return datetime.fromisoformat(raw + "T00:00:00+00:00")
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _recent_posts(posts: list[dict[str, Any]], days: int, now_utc: datetime | None = None) -> list[dict[str, Any]]:
    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(0, days))
    out = []
    for p in posts:
        dt = _parse_dt(p)
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            out.append(p)
    return out


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _opening_sentence(text: str) -> str:
    cleaned = _normalize_text(text)
    if not cleaned:
        return ""
    parts = re.split(r"[\.!?]", cleaned)
    return parts[0].strip() if parts else cleaned


def check_duplicates(content: dict[str, Any], history: dict[str, Any], windows: dict[str, int] | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULT_WINDOWS)
    if windows:
        cfg.update(windows)

    posts = [p for p in (history.get("posts", []) if isinstance(history, dict) else []) if isinstance(p, dict)]
    # Never-published attempts (validation/quality/duplicate/channel-readiness skips)
    # must not poison future duplicate checks — only compare against posts that were
    # actually published (or attempted live), otherwise a single skip can perpetually
    # block every future run on the same topic/hook/structure.
    posts = [p for p in posts if not str(p.get("status", "")).startswith("skipped")]

    reasons: list[str] = []

    # Topic window
    topic_hash = str(content.get("topic_hash", ""))
    if topic_hash:
        for p in _recent_posts(posts, cfg["topic_days"]):
            if str(p.get("topic_hash", "")) == topic_hash:
                reasons.append("duplicate_topic_within_window")
                break

    # Hook window
    hook_hash = str(content.get("hook_hash", "") or stable_text_hash(str(content.get("selected_hook", ""))))
    if hook_hash:
        for p in _recent_posts(posts, cfg["hook_days"]):
            existing = str(p.get("hook_hash", "") or stable_text_hash(str(p.get("selected_hook", ""))))
            if existing == hook_hash:
                reasons.append("duplicate_hook_within_window")
                break

    # CTA window
    cta_hash = str(content.get("cta_hash", "") or stable_text_hash(str(content.get("selected_cta", ""))))
    if cta_hash:
        for p in _recent_posts(posts, cfg["cta_days"]):
            existing = str(p.get("cta_hash", "") or stable_text_hash(str(p.get("selected_cta", ""))))
            if existing == cta_hash:
                reasons.append("duplicate_cta_within_window")
                break

    # Product feature window
    product_key = _normalize_text(f"{content.get('product_id', '')}|{content.get('product_name', '')}|{content.get('product_sku', '')}")
    if product_key != "||":
        for p in _recent_posts(posts, cfg["product_feature_days"]):
            existing = _normalize_text(f"{p.get('product_id', '')}|{p.get('product_name', '')}|{p.get('product_sku', '')}")
            if existing == product_key:
                reasons.append("duplicate_product_within_window")
                break

    # Exact caption + opening sentence + scenario/lesson + format/profile signatures
    fb_caption = str(content.get("fb_caption", ""))
    ig_caption = str(content.get("ig_caption", ""))
    li_text = str(content.get("li_text", ""))
    exact_source = "\n".join([_normalize_text(fb_caption), _normalize_text(ig_caption), _normalize_text(li_text)]).strip()
    opening_source = _opening_sentence(fb_caption).strip()
    scenario_source = str(content.get("scenario", "")).strip()
    lesson_source = str(content.get("educational_lesson", "")).strip()

    exact_signature = stable_text_hash(exact_source) if exact_source else ""
    opening_signature = stable_text_hash(opening_source) if opening_source else ""
    scenario_signature = stable_text_hash(scenario_source) if scenario_source else ""
    lesson_signature = stable_text_hash(lesson_source) if lesson_source else ""

    platform_posts = content.get("platform_posts", {}) if isinstance(content.get("platform_posts"), dict) else {}
    format_source = "|".join(
        sorted(
            [
                str(v.get("content_format", "")).strip()
                for v in platform_posts.values()
                if isinstance(v, dict) and str(v.get("content_format", "")).strip()
            ]
        )
    )
    structure_source = "|".join(
        sorted(
            [
                str(v.get("platform", "")).strip() + ":" + str(v.get("visual_direction", "")).strip()
                for v in platform_posts.values()
                if isinstance(v, dict) and str(v.get("platform", "")).strip()
            ]
        )
    )
    format_signature = stable_text_hash(format_source) if format_source else ""
    structure_signature = stable_text_hash(structure_source) if structure_source else ""

    for p in _recent_posts(posts, cfg["exact_caption_days"]):
        old_exact = str(p.get("exact_caption_signature", ""))
        if old_exact and old_exact == exact_signature:
            reasons.append("duplicate_exact_caption_within_window")
            break

    for p in _recent_posts(posts, cfg["hook_days"]):
        if str(p.get("opening_signature", "")) == opening_signature and opening_signature:
            reasons.append("duplicate_opening_sentence_within_window")
            break

    for p in _recent_posts(posts, cfg["hook_days"]):
        if str(p.get("scenario_signature", "")) == scenario_signature and scenario_signature:
            reasons.append("duplicate_customer_scenario_within_window")
            break

    for p in _recent_posts(posts, cfg["hook_days"]):
        if str(p.get("lesson_signature", "")) == lesson_signature and lesson_signature:
            reasons.append("duplicate_educational_lesson_within_window")
            break

    # NOTE: content_format and visual_direction are assigned deterministically per
    # platform/funnel_stage template (not derived from the creative content itself),
    # so format_signature/structure_signature are identical across nearly all posts
    # sharing a funnel stage. They are computed and stored for analytics only — they
    # must never gate publishing, or "same funnel stage" would be treated as
    # "duplicate content" and block almost every post after the first.

    return {
        "ok": len(reasons) == 0,
        "reasons": reasons,
        "signatures": {
            "exact_caption_signature": exact_signature,
            "opening_signature": opening_signature,
            "scenario_signature": scenario_signature,
            "lesson_signature": lesson_signature,
            "format_signature": format_signature,
            "structure_signature": structure_signature,
        },
        "windows": cfg,
    }
