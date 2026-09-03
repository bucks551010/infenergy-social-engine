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
SOURCE_MARKETING_DIR = os.path.join(BASE_DIR, "..", "data", "marketing")

DEFAULT_WINDOWS = {
    "exact_caption_days": 180,
    "hook_days": 60,
    "product_feature_days": 7,
    "topic_days": 21,
    "cta_days": 14,
}
DEFAULT_DISABLED_SIGNATURES: tuple[str, ...] = ()
DEFAULT_MAX_VIOLATIONS_ALLOWED = 0
DEFAULT_BLOCKING_SIGNATURES: tuple[str, ...] = ("exact_caption",)


def _config_path() -> str:
    return os.path.join(MARKETING_DIR, "anti_repeat_config.json")


def ensure_anti_repeat_config() -> None:
    os.makedirs(MARKETING_DIR, exist_ok=True)
    path = _config_path()
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_WINDOWS, f, indent=2)


def _apply_config(out: dict[str, Any], data: object) -> None:
    if not isinstance(data, dict):
        return
    for key in DEFAULT_WINDOWS:
        try:
            out[key] = int(data.get(key, out[key]))
        except Exception:
            pass
    if "disabled_signatures" in data and isinstance(data["disabled_signatures"], list):
        out["disabled_signatures"] = [str(value) for value in data["disabled_signatures"]]
    if "blocking_signatures" in data and isinstance(data["blocking_signatures"], list):
        out["blocking_signatures"] = [str(value) for value in data["blocking_signatures"]]
    if "max_violations_allowed" in data:
        try:
            out["max_violations_allowed"] = max(0, int(data["max_violations_allowed"]))
        except Exception:
            pass


def load_anti_repeat_windows() -> dict[str, Any]:
    ensure_anti_repeat_config()
    out: dict[str, Any] = {
        **DEFAULT_WINDOWS,
        "disabled_signatures": list(DEFAULT_DISABLED_SIGNATURES),
        "blocking_signatures": list(DEFAULT_BLOCKING_SIGNATURES),
        "max_violations_allowed": DEFAULT_MAX_VIOLATIONS_ALLOWED,
    }
    # Version-controlled policy is the baseline. The persistent Railway volume
    # can override only fields it explicitly defines, so old config files do not
    # silently erase newly deployed controls.
    source_path = os.path.join(SOURCE_MARKETING_DIR, "anti_repeat_config.json")
    paths = [source_path]
    runtime_path = _config_path()
    if os.path.abspath(runtime_path) != os.path.abspath(source_path):
        paths.append(runtime_path)
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                _apply_config(out, json.load(handle))
        except Exception:
            continue
    return out


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


def _previous_calendar_day_posts(posts: list[dict[str, Any]], now_utc: datetime) -> list[dict[str, Any]]:
    previous_date = now_utc.astimezone(timezone.utc).date() - timedelta(days=1)
    return [post for post in posts if (parsed := _parse_dt(post)) is not None and parsed.astimezone(timezone.utc).date() == previous_date]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _opening_sentence(text: str) -> str:
    cleaned = _normalize_text(text)
    if not cleaned:
        return ""
    parts = re.split(r"[\.!?]", cleaned)
    return parts[0].strip() if parts else cleaned


def check_duplicates(content: dict[str, Any], history: dict[str, Any], windows: dict[str, int] | None = None, now_utc: datetime | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULT_WINDOWS)
    if windows:
        cfg.update(windows)
    disabled_signatures = {str(value).strip().lower() for value in cfg.get("disabled_signatures", [])}

    posts = [p for p in (history.get("posts", []) if isinstance(history, dict) else []) if isinstance(p, dict)]
    # Never-published attempts (validation/quality/duplicate/channel-readiness skips)
    # must not poison future duplicate checks — only compare against posts that were
    # actually published (or attempted live), otherwise a single skip can perpetually
    # block every future run on the same topic/hook/structure.
    posts = [p for p in posts if not str(p.get("status", "")).startswith("skipped")]

    reasons: list[str] = []

    current_time = now_utc or datetime.now(timezone.utc)
    previous_day_posts = _previous_calendar_day_posts(posts, current_time)
    consumer_moment_id = str(content.get("consumer_moment_id") or "").strip()
    consumer_world_id = str(content.get("consumer_world_id") or "").strip()
    consumer_root = content.get("consumer_root") if isinstance(content.get("consumer_root"), dict) else {}
    consumer_moment = consumer_root.get("moment") if isinstance(consumer_root.get("moment"), dict) else {}
    if consumer_moment_id:
        if any(str(post.get("consumer_moment_id") or "") == consumer_moment_id for post in previous_day_posts):
            reasons.append("duplicate_consumer_moment_on_consecutive_day")
        recent_moments = _recent_posts(posts, cfg["topic_days"], current_time)
        if any(str(post.get("consumer_moment_id") or "") == consumer_moment_id for post in recent_moments):
            reasons.append("consumer_moment_saturated_within_window")
    if consumer_world_id:
        recent_worlds = _recent_posts(posts, 7, current_time)
        world_uses = sum(str(post.get("consumer_world_id") or "") == consumer_world_id for post in recent_worlds)
        if world_uses >= 2:
            reasons.append("consumer_world_saturated_within_week")
    recent_consumer_posts = _recent_posts(posts, cfg["topic_days"], current_time)
    consumer_dimensions = {
        dimension: _normalize_text(str(consumer_moment.get(dimension) or content.get(dimension) or ""))
        for dimension in ("person", "setting", "activity", "friction", "consequence", "useful_discovery", "immediate_action")
    }
    visual_evidence = consumer_moment.get("visual_evidence") if isinstance(consumer_moment.get("visual_evidence"), list) else []
    consumer_dimensions["visual_evidence"] = _normalize_text("|".join(str(value) for value in visual_evidence))
    product_moment_pair = _normalize_text(f"{content.get('product_id', '')}:{consumer_moment_id}")
    if product_moment_pair != ":":
        consumer_dimensions["product_moment_pair"] = product_moment_pair
    for dimension, value in consumer_dimensions.items():
        if not value:
            continue
        uses = 0
        for post in recent_consumer_posts:
            previous_root = post.get("consumer_root") if isinstance(post.get("consumer_root"), dict) else {}
            previous_moment = previous_root.get("moment") if isinstance(previous_root.get("moment"), dict) else {}
            if dimension == "visual_evidence":
                previous_values = previous_moment.get("visual_evidence") if isinstance(previous_moment.get("visual_evidence"), list) else []
                previous_value = _normalize_text("|".join(str(item) for item in previous_values))
            elif dimension == "product_moment_pair":
                previous_value = _normalize_text(str(post.get("product_moment_pair") or f"{post.get('product_id', '')}:{post.get('consumer_moment_id', '')}"))
            else:
                previous_value = _normalize_text(str(post.get(dimension) or previous_moment.get(dimension) or ""))
            uses += previous_value == value
        if uses >= (1 if dimension in {"useful_discovery", "immediate_action", "visual_evidence", "product_moment_pair"} else 2):
            reasons.append(f"consumer_{dimension}_saturated_within_window")
    premise_signatures = {
        value for value in (
            str(content.get("topic_hash", "")),
            stable_text_hash(str(content.get("scenario", ""))) if str(content.get("scenario", "")).strip() else "",
            stable_text_hash(str(content.get("educational_lesson", ""))) if str(content.get("educational_lesson", "")).strip() else "",
        ) if value
    }
    if premise_signatures and "topic" not in disabled_signatures:
        for post in previous_day_posts:
            previous_signatures = {
                value for value in (
                    str(post.get("topic_hash", "")),
                    str(post.get("scenario_signature", "")) or (stable_text_hash(str(post.get("scenario", ""))) if str(post.get("scenario", "")).strip() else ""),
                    str(post.get("lesson_signature", "")) or (stable_text_hash(str(post.get("educational_lesson", ""))) if str(post.get("educational_lesson", "")).strip() else ""),
                ) if value
            }
            if premise_signatures.intersection(previous_signatures):
                reasons.append("duplicate_premise_on_consecutive_day")
                break

    # Topic window
    topic_hash = str(content.get("topic_hash", ""))
    if topic_hash and "topic" not in disabled_signatures:
        for p in _recent_posts(posts, cfg["topic_days"], current_time):
            if str(p.get("topic_hash", "")) == topic_hash:
                reasons.append("duplicate_topic_within_window")
                break

    # Hook window
    hook_hash = str(content.get("hook_hash", "") or stable_text_hash(str(content.get("selected_hook", ""))))
    if hook_hash and "hook" not in disabled_signatures:
        for p in _recent_posts(posts, cfg["hook_days"]):
            existing = str(p.get("hook_hash", "") or stable_text_hash(str(p.get("selected_hook", ""))))
            if existing == hook_hash:
                reasons.append("duplicate_hook_within_window")
                break

    # CTA window
    cta_hash = str(content.get("cta_hash", "") or stable_text_hash(str(content.get("selected_cta", ""))))
    if cta_hash and "cta" not in disabled_signatures:
        for p in _recent_posts(posts, cfg["cta_days"]):
            existing = str(p.get("cta_hash", "") or stable_text_hash(str(p.get("selected_cta", ""))))
            if existing == cta_hash:
                reasons.append("duplicate_cta_within_window")
                break

    # Product feature window
    product_key = _normalize_text(f"{content.get('product_id', '')}|{content.get('product_name', '')}|{content.get('product_sku', '')}")
    if product_key != "||" and "product" not in disabled_signatures:
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

    blocking_signatures = {
        str(value).strip().lower()
        for value in cfg.get("blocking_signatures", DEFAULT_BLOCKING_SIGNATURES)
    }
    strict_reasons = [
        reason
        for reason in reasons
        if reason in {"duplicate_premise_on_consecutive_day", "duplicate_consumer_moment_on_consecutive_day"}
        or (reason == "duplicate_exact_caption_within_window" and "exact_caption" in blocking_signatures)
    ]
    configured_reasons = [
        reason
        for reason in reasons
        if reason not in strict_reasons
        and reason.removeprefix("duplicate_").removesuffix("_within_window") in blocking_signatures
    ]
    max_violations_allowed = int(cfg.get("max_violations_allowed", DEFAULT_MAX_VIOLATIONS_ALLOWED))
    blocking_reasons = strict_reasons + (
        configured_reasons if len(configured_reasons) > max_violations_allowed else []
    )
    return {
        "ok": len(blocking_reasons) == 0,
        "reasons": blocking_reasons,
        "observed_reasons": reasons,
        "signatures": {
            "exact_caption_signature": exact_signature,
            "opening_signature": opening_signature,
            "scenario_signature": scenario_signature,
            "lesson_signature": lesson_signature,
            "format_signature": format_signature,
            "structure_signature": structure_signature,
            "consumer_world_id": consumer_world_id,
            "consumer_moment_id": consumer_moment_id,
            **{f"consumer_{key}_signature": stable_text_hash(value) if value else "" for key, value in consumer_dimensions.items()},
        },
        "windows": cfg,
    }
