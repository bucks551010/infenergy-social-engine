from __future__ import annotations

import glob
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

BASE_DIR = os.path.dirname(__file__)
BASE_DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DATA_DIR = os.environ.get("DATA_DIR", BASE_DATA_DIR)
MARKETING_DIR = os.path.join(DATA_DIR, "marketing")


FUNNEL_STAGES = ["ATTENTION", "EDUCATION", "DESIRE", "TRUST", "CONVERSION"]

DEFAULT_FUNNEL_CONFIG: dict[str, Any] = {
    "distribution": {
        "ATTENTION": 0.20,
        "EDUCATION": 0.30,
        "DESIRE": 0.25,
        "TRUST": 0.15,
        "CONVERSION": 0.10,
    },
    "stages": {
        "ATTENTION": {
            "objective": "Capture attention and surface a relatable power problem.",
            "approved_cta_types": ["comment", "share", "save"],
            "preferred_content_formats": ["question_post", "myth_bust", "scenario"],
            "prohibited_cta_types": ["hard_sale", "checkout_now"],
            "preferred_hook_styles": ["question", "common_mistake", "local_relevance"],
            "primary_success_metric": "engagement_rate",
        },
        "EDUCATION": {
            "objective": "Teach useful buyer knowledge with practical examples.",
            "approved_cta_types": ["save", "read_more", "compare"],
            "preferred_content_formats": ["checklist", "comparison", "how_to"],
            "prohibited_cta_types": ["hard_sale"],
            "preferred_hook_styles": ["checklist", "myth", "problem_recognition"],
            "primary_success_metric": "saves_and_clicks",
        },
        "DESIRE": {
            "objective": "Connect product value to daily customer outcomes.",
            "approved_cta_types": ["view_product", "learn_more", "compare"],
            "preferred_content_formats": ["use_case", "demonstration", "before_after"],
            "prohibited_cta_types": ["fear_only"],
            "preferred_hook_styles": ["scenario", "comparison", "product_use_case"],
            "primary_success_metric": "product_page_ctr",
        },
        "TRUST": {
            "objective": "Build credibility using verified details and transparent claims.",
            "approved_cta_types": ["review_specs", "see_details", "consult"],
            "preferred_content_formats": ["spec_breakdown", "faq", "authority_post"],
            "prohibited_cta_types": ["aggressive_discount"],
            "preferred_hook_styles": ["business_continuity", "problem_recognition", "demonstration"],
            "primary_success_metric": "qualified_clicks",
        },
        "CONVERSION": {
            "objective": "Drive a single clear next step toward purchase intent.",
            "approved_cta_types": ["shop", "build_setup", "book_call"],
            "preferred_content_formats": ["offer_post", "decision_guide", "direct_cta"],
            "prohibited_cta_types": ["multi_cta", "bait"],
            "preferred_hook_styles": ["comparison", "scenario", "demonstration"],
            "primary_success_metric": "conversion_rate",
        },
    },
}

DEFAULT_CHANNEL_SCHEDULE: dict[str, Any] = {
    "monday": {
        "morning": [
            {"platform": "linkedin", "allowed_funnel_stages": ["EDUCATION", "TRUST"], "enabled": True, "preferred_content_formats": ["authority_post", "faq"]},
        ],
        "midday": [
            {"platform": "facebook", "allowed_funnel_stages": ["ATTENTION", "EDUCATION"], "enabled": True, "preferred_content_formats": ["comparison", "how_to", "question_post"]},
            {"platform": "linkedin", "allowed_funnel_stages": ["EDUCATION", "TRUST"], "enabled": True, "preferred_content_formats": ["authority_post", "faq"]},
        ],
        "evening": [
            {"platform": "instagram", "allowed_funnel_stages": ["ATTENTION", "DESIRE"], "enabled": True, "preferred_content_formats": ["use_case", "carousel"]},
        ],
    },
    "tuesday": {
        "morning": [
            {"platform": "facebook", "allowed_funnel_stages": ["ATTENTION", "EDUCATION"], "enabled": True, "preferred_content_formats": ["question_post", "myth_bust"]},
        ],
        "midday": [
            {"platform": "instagram", "allowed_funnel_stages": ["DESIRE", "EDUCATION"], "enabled": True, "preferred_content_formats": ["use_case", "demonstration"]},
        ],
        "evening": [
            {"platform": "facebook", "allowed_funnel_stages": ["DESIRE", "TRUST"], "enabled": True, "preferred_content_formats": ["scenario", "use_case"]},
        ],
    },
    "wednesday": {
        "morning": [
            {"platform": "linkedin", "allowed_funnel_stages": ["EDUCATION", "TRUST"], "enabled": True, "preferred_content_formats": ["authority_post", "spec_breakdown"]},
        ],
        "midday": [
            {"platform": "facebook", "allowed_funnel_stages": ["ATTENTION", "EDUCATION"], "enabled": True, "preferred_content_formats": ["question_post", "myth_bust"]},
        ],
        "evening": [
            {"platform": "instagram", "allowed_funnel_stages": ["EDUCATION", "DESIRE"], "enabled": True, "preferred_content_formats": ["checklist", "carousel"]},
        ],
    },
    "thursday": {
        "morning": [
            {"platform": "instagram", "allowed_funnel_stages": ["ATTENTION", "DESIRE"], "enabled": True, "preferred_content_formats": ["reel", "use_case"]},
        ],
        "midday": [
            {"platform": "linkedin", "allowed_funnel_stages": ["TRUST", "EDUCATION"], "enabled": True, "preferred_content_formats": ["spec_breakdown", "authority_post"]},
            {"platform": "instagram", "allowed_funnel_stages": ["TRUST", "DESIRE"], "enabled": True, "preferred_content_formats": ["demonstration", "reel"]},
        ],
        "evening": [
            {"platform": "facebook", "allowed_funnel_stages": ["CONVERSION", "TRUST"], "enabled": True, "preferred_content_formats": ["direct_cta", "offer_post"]},
        ],
    },
    "friday": {
        "morning": [
            {"platform": "facebook", "allowed_funnel_stages": ["EDUCATION", "ATTENTION"], "enabled": True, "preferred_content_formats": ["how_to", "comparison"]},
        ],
        "midday": [
            {"platform": "linkedin", "allowed_funnel_stages": ["TRUST", "EDUCATION"], "enabled": True, "preferred_content_formats": ["authority_post", "faq"]},
        ],
        "evening": [
            {"platform": "instagram", "allowed_funnel_stages": ["DESIRE", "CONVERSION"], "enabled": True, "preferred_content_formats": ["carousel", "offer_post"]},
        ],
    },
    "saturday": {
        "morning": [
            {"platform": "instagram", "allowed_funnel_stages": ["ATTENTION", "DESIRE"], "enabled": True, "preferred_content_formats": ["use_case", "carousel"]},
        ],
        "midday": [
            {"platform": "facebook", "allowed_funnel_stages": ["DESIRE", "ATTENTION"], "enabled": True, "preferred_content_formats": ["scenario", "question_post"]},
        ],
        "evening": [],
    },
    "sunday": {
        "morning": [],
        "midday": [
            {"platform": "facebook", "allowed_funnel_stages": ["ATTENTION", "DESIRE"], "enabled": True, "preferred_content_formats": ["question_post", "use_case"]},
        ],
        "evening": [
            {"platform": "linkedin", "allowed_funnel_stages": ["TRUST", "EDUCATION"], "enabled": True, "preferred_content_formats": ["authority_post", "faq"]},
        ],
    },
}


def weekly_schedule_coverage(schedule: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize weekly opportunity coverage per platform and flag empty day/slot gaps.

    Used to enforce the seven-day planning invariant: every platform should have
    a real opportunity across the week, and empty slots should be visible rather
    than silently discovered at generation time.
    """
    active_schedule = schedule if schedule is not None else load_channel_schedule()
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    slots = ["morning", "midday", "evening"]
    platform_counts = {"facebook": 0, "instagram": 0, "linkedin": 0, "wordpress": 0}
    empty_slots: list[str] = []

    if _is_legacy_schedule(active_schedule):
        return {"platform_counts": platform_counts, "empty_slots": empty_slots, "legacy_schedule": True}

    for day in days:
        day_rules = active_schedule.get(day, {}) if isinstance(active_schedule, dict) else {}
        for slot in slots:
            slot_rules = day_rules.get(slot, []) if isinstance(day_rules, dict) else []
            active_rules = [
                r for r in slot_rules
                if isinstance(r, dict) and bool(r.get("enabled", True)) and _platform_from_rule(r) in platform_counts
            ]
            if not active_rules:
                empty_slots.append(f"{day}:{slot}")
                continue
            for rule in active_rules:
                platform_counts[_platform_from_rule(rule)] += 1

    return {
        "platform_counts": platform_counts,
        "empty_slots": empty_slots,
        "legacy_schedule": False,
        "platforms_with_zero_opportunities": [p for p, c in platform_counts.items() if c == 0 and p != "wordpress"],
    }

DEFAULT_CTA_LIBRARY: dict[str, list[str]] = {
    "ATTENTION": [
        "Comment with your answer.",
        "Share this with someone preparing their household.",
    ],
    "EDUCATION": [
        "Save this checklist.",
        "Read the full comparison.",
    ],
    "DESIRE": [
        "See what this product is designed to support.",
        "Compare available portable-power options.",
    ],
    "TRUST": [
        "Review the verified product details.",
        "See how this solution fits different use cases.",
    ],
    "CONVERSION": [
        "Shop available products.",
        "Build your backup-power setup.",
    ],
}

RISKY_CLAIM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bguarantee(?:d|s)?\b", flags=re.IGNORECASE), "designed"),
    (re.compile(r"\b100%\b", flags=re.IGNORECASE), "up to 100% in some scenarios"),
    (re.compile(r"\bzero risk\b", flags=re.IGNORECASE), "lower risk"),
    (re.compile(r"\binstant(?:ly)?\b", flags=re.IGNORECASE), "quickly"),
]

EXPLICIT_CTA_KEYWORDS: tuple[str, ...] = (
    "shop",
    "buy",
    "build",
    "book",
    "compare",
    "see",
    "review",
    "get",
    "start",
    "message",
    "comment",
    "schedule",
    "call",
    "contact",
    "quote",
    "assessment",
    "checkout",
    "order",
)


@dataclass
class QualityScore:
    score: int
    checks: dict[str, Any]
    warnings: list[str]


def _json_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def _marketing_json_path(filename: str) -> str:
    return os.path.join(MARKETING_DIR, filename)


def _schedule_needs_migration(existing: dict[str, Any]) -> bool:
    """Detect the sparse pre-fix default schedule (no weekends, no morning slot).

    Older deployments already persisted `channel_schedule.json` from the previous
    default, so `not os.path.exists(...)` alone would never refresh it. Auto-heal
    any schedule that is missing full 7-day/3-slot coverage back to the current
    default so every platform gets real weekly opportunities.
    """
    if not isinstance(existing, dict) or not existing:
        return True
    if _is_legacy_schedule(existing):
        return False
    required_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    if not required_days.issubset({str(k).lower() for k in existing.keys()}):
        return True
    for day in required_days:
        day_rules = existing.get(day, {})
        if not isinstance(day_rules, dict) or "morning" not in day_rules:
            return True
    return False


def ensure_campaign_runtime_files() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MARKETING_DIR, exist_ok=True)

    # Preferred location for funnel config (Phase 2): data/marketing/funnel_config.json.
    funnel_marketing_path = _marketing_json_path("funnel_config.json")
    if not os.path.exists(funnel_marketing_path):
        with open(funnel_marketing_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_FUNNEL_CONFIG, f, indent=2)

    # Backward-compatible legacy location for older runtime paths.
    legacy_funnel_path = _json_path("funnel_config.json")
    if not os.path.exists(legacy_funnel_path):
        with open(legacy_funnel_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_FUNNEL_CONFIG, f, indent=2)

    # Preferred location for schedule config (Phase 3): data/marketing/channel_schedule.json.
    schedule_marketing_path = _marketing_json_path("channel_schedule.json")
    if not os.path.exists(schedule_marketing_path):
        with open(schedule_marketing_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CHANNEL_SCHEDULE, f, indent=2)
    else:
        existing = _read_json_or_default(schedule_marketing_path, {})
        if _schedule_needs_migration(existing):
            with open(schedule_marketing_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CHANNEL_SCHEDULE, f, indent=2)

    # Backward-compatible legacy location.
    schedule_path = _json_path("channel_schedule.json")
    if not os.path.exists(schedule_path):
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CHANNEL_SCHEDULE, f, indent=2)
    else:
        existing_legacy = _read_json_or_default(schedule_path, {})
        if _schedule_needs_migration(existing_legacy):
            with open(schedule_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CHANNEL_SCHEDULE, f, indent=2)

    cta_library_path = _marketing_json_path("cta_library.json")
    if not os.path.exists(cta_library_path):
        with open(cta_library_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CTA_LIBRARY, f, indent=2)


def _read_json_or_default(path: str, default: dict[str, Any]) -> dict[str, Any]:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return default


def load_funnel_config() -> dict[str, Any]:
    ensure_campaign_runtime_files()
    primary = _marketing_json_path("funnel_config.json")
    legacy = _json_path("funnel_config.json")
    if os.path.exists(primary):
        return _read_json_or_default(primary, DEFAULT_FUNNEL_CONFIG)
    return _read_json_or_default(legacy, DEFAULT_FUNNEL_CONFIG)


def load_channel_schedule() -> dict[str, Any]:
    ensure_campaign_runtime_files()
    primary = _marketing_json_path("channel_schedule.json")
    legacy = _json_path("channel_schedule.json")
    if os.path.exists(primary):
        return _read_json_or_default(primary, DEFAULT_CHANNEL_SCHEDULE)
    return _read_json_or_default(legacy, DEFAULT_CHANNEL_SCHEDULE)


def load_cta_library() -> dict[str, list[str]]:
    ensure_campaign_runtime_files()
    path = _marketing_json_path("cta_library.json")
    if not os.path.exists(path):
        return dict(DEFAULT_CTA_LIBRARY)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return dict(DEFAULT_CTA_LIBRARY)
            merged = dict(DEFAULT_CTA_LIBRARY)
            for k, v in data.items():
                stage = _normalize_stage(str(k))
                if isinstance(v, list):
                    cleaned = [str(x).strip() for x in v if str(x).strip()]
                    if cleaned:
                        merged[stage] = cleaned
            return merged
    except Exception:
        return dict(DEFAULT_CTA_LIBRARY)


def choose_cta_for_stage(stage: str, preferred: str, cta_library: dict[str, list[str]], recent_cta_hashes: set[str]) -> str:
    normalized = _normalize_stage(stage)
    options = list(cta_library.get(normalized, []))
    if preferred and preferred.strip():
        options.insert(0, preferred.strip())
    cleaned = [x for x in options if x]
    for cta in cleaned:
        if stable_text_hash(cta) not in recent_cta_hashes:
            return cta
    if cleaned:
        return cleaned[0]
    fallback = DEFAULT_CTA_LIBRARY.get(normalized, ["Learn more."])
    return fallback[0]


def cta_is_valid_for_stage(stage: str, cta: str, destination_url: str) -> tuple[bool, str]:
    normalized = _normalize_stage(stage)
    text = (cta or "").strip()
    if not text:
        return False, "cta_missing"
    if "\n" in text:
        return False, "multiple_cta_lines_not_allowed"
    if normalized in ("DESIRE", "TRUST", "CONVERSION") and not (destination_url or "").strip():
        return False, "destination_url_required_for_stage"
    return True, "ok"


def has_explicit_cta_keyword(text: str) -> bool:
    low = str(text or "").lower()
    return any(k in low for k in EXPLICIT_CTA_KEYWORDS)


def _is_legacy_schedule(schedule: dict[str, Any]) -> bool:
    if not isinstance(schedule, dict):
        return False
    keys = {str(k).lower() for k in schedule.keys()}
    return bool(keys.intersection({"facebook", "instagram", "linkedin", "wordpress"}))


def _platform_from_rule(rule: dict[str, Any]) -> str:
    return str(rule.get("platform", "")).strip().lower()


def _stage_from_rule(rule: dict[str, Any]) -> str:
    return _normalize_stage(str(rule.get("stage", "")))


def _stages_from_rule(rule: dict[str, Any]) -> list[str]:
    allowed = rule.get("allowed_funnel_stages")
    if isinstance(allowed, list) and allowed:
        out = [_normalize_stage(str(x)) for x in allowed]
        return [x for x in out if x in FUNNEL_STAGES]
    stage = _stage_from_rule(rule)
    return [stage] if stage else []


def eligible_channels_for_slot(
    slot: str,
    funnel_stage: str,
    schedule: dict[str, Any],
    now_utc: datetime | None = None,
    env: dict[str, str] | None = None,
    manual_platforms: list[str] | None = None,
) -> dict[str, tuple[bool, str]]:
    env_map = env or os.environ
    now = now_utc or datetime.now(timezone.utc)
    day_name = now.strftime("%A").lower()
    stage = _normalize_stage(funnel_stage)

    base = {"wordpress": (False, "not_scheduled"), "facebook": (False, "not_scheduled"), "instagram": (False, "not_scheduled"), "linkedin": (False, "not_scheduled")}

    manual_set = {p.strip().lower() for p in (manual_platforms or []) if p.strip()}
    if manual_set:
        for platform in base:
            base[platform] = (platform in manual_set, "manual_platform_override")
        return base

    if _is_legacy_schedule(schedule):
        for platform in base:
            allowed, reason = should_channel_run(platform, slot, schedule, now_utc=now, env=env_map)
            base[platform] = (allowed, reason)
        return base

    day_rules = schedule.get(day_name, {}) if isinstance(schedule, dict) else {}
    slot_rules = day_rules.get(slot, []) if isinstance(day_rules, dict) else []

    if isinstance(slot_rules, list):
        for raw_rule in slot_rules:
            if not isinstance(raw_rule, dict):
                continue
            platform = _platform_from_rule(raw_rule)
            if platform not in base:
                continue
            enabled = bool(raw_rule.get("enabled", True))
            if not enabled:
                base[platform] = (False, "disabled_in_schedule")
                continue

            allowed_stages = _stages_from_rule(raw_rule)
            if allowed_stages and stage not in allowed_stages:
                base[platform] = (False, f"stage_mismatch:{'|'.join(allowed_stages)}")
                continue

            base[platform] = (True, "schedule_match")

    # Existing per-channel slot overrides still win when present.
    for platform in base:
        override_key = f"ENABLE_{platform.upper()}_SLOTS"
        override = (env_map.get(override_key) or "").strip()
        if override:
            slots = [x.strip().lower() for x in override.split(",") if x.strip()]
            base[platform] = (slot.lower() in slots, f"env_override:{override_key}")

    return base


def _load_latest_json_by_patterns(patterns: list[str]) -> dict[str, Any]:
    paths: list[str] = []
    for pattern in patterns:
        paths.extend(glob.glob(os.path.join(DATA_DIR, pattern)))
        paths.extend(glob.glob(os.path.join(BASE_DATA_DIR, pattern)))
    if not paths:
        return {}
    latest = max(paths, key=os.path.getmtime)
    try:
        with open(latest, "r", encoding="utf-8") as f:
            payload = json.load(f)
            if isinstance(payload, dict):
                return payload
    except Exception:
        return {}
    return {}


def load_latest_weekly_plan() -> dict[str, Any]:
    return _load_latest_json_by_patterns(["marketing/weekly_plan_*.json"])


def recurring_series_for_slot(day: str, slot: str, now_utc: datetime | None = None) -> dict[str, Any]:
    normalized = (day.strip().lower(), slot.strip().lower())
    targets = [("tuesday", "midday"), ("friday", "morning")]
    if normalized not in targets:
        return {}
    formats = ["cinematic_brand_poster", "product_micro_mission_comic", "educational_story_carousel"]
    now = now_utc or datetime.now(timezone.utc)
    occurrence = targets.index(normalized)
    return {
        "id": "infenergy_intervention",
        "name": "Infenergy Intervention",
        "archetype": "character_led_edutainment",
        "cadence": "twice_weekly",
        "preferred_format": formats[(now.isocalendar().week + occurrence) % len(formats)],
        "format_rotation": formats,
        "product_rotation": "least_recently_used_catalog",
        "product_required": True,
        "character_canon_required": True,
        "story_pattern": "avoidable_energy_mistake_to_infenergy_intervention_to_product_enabled_resolution",
        "originality_dimensions": ["scenario", "persona", "tension", "setting", "hook", "product_role", "resolution"],
    }


def select_weekly_sequence(slot: str, now_utc: datetime | None = None) -> dict[str, Any]:
    plan = load_latest_weekly_plan()
    if not plan:
        return {}

    now = now_utc or datetime.now(timezone.utc)
    day_name = now.strftime("%A")
    sequence = plan.get("sequence", [])
    if not isinstance(sequence, list):
        return {}

    for row in sequence:
        if not isinstance(row, dict):
            continue
        if row.get("day") == day_name and row.get("slot") == slot:
            selected = dict(row)
            series = recurring_series_for_slot(day_name, slot, now_utc=now)
            if series:
                selected["series"] = series
            return selected
    return {}


def _normalize_stage(value: str) -> str:
    raw = (value or "").strip().upper()
    aliases = {
        "AWARENESS": "ATTENTION",
        "CONSIDERATION": "EDUCATION",
        "DECISION": "CONVERSION",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in FUNNEL_STAGES else "EDUCATION"


def _distribution_map(config: dict[str, Any]) -> dict[str, float]:
    base = config.get("distribution", {}) if isinstance(config, dict) else {}
    result: dict[str, float] = {}
    for stage in FUNNEL_STAGES:
        try:
            result[stage] = float(base.get(stage, 0.0))
        except Exception:
            result[stage] = 0.0
    total = sum(result.values())
    if total <= 0:
        return {"ATTENTION": 0.20, "EDUCATION": 0.30, "DESIRE": 0.25, "TRUST": 0.15, "CONVERSION": 0.10}
    return {k: v / total for k, v in result.items()}


def allowed_stages_for_slot(
    slot: str,
    schedule: dict[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> list[str]:
    """Return the funnel stages actually schedulable for this weekday/slot.

    Legacy (per-channel) schedules carry no stage constraint, so every stage
    is considered available. Structured schedules restrict the choice to the
    union of `allowed_funnel_stages` (or single `stage`) declared by enabled
    rules for that exact day and slot, so stage selection can never pick a
    stage no scheduled channel is willing to run.
    """
    active_schedule = schedule if schedule is not None else load_channel_schedule()
    if _is_legacy_schedule(active_schedule):
        return list(FUNNEL_STAGES)

    now = now_utc or datetime.now(timezone.utc)
    day_name = now.strftime("%A").lower()
    day_rules = active_schedule.get(day_name, {}) if isinstance(active_schedule, dict) else {}
    slot_rules = day_rules.get(slot, []) if isinstance(day_rules, dict) else []

    stages: set[str] = set()
    if isinstance(slot_rules, list):
        for raw_rule in slot_rules:
            if not isinstance(raw_rule, dict):
                continue
            if not bool(raw_rule.get("enabled", True)):
                continue
            stages.update(_stages_from_rule(raw_rule))

    return sorted(stages) if stages else list(FUNNEL_STAGES)


def select_funnel_stage(
    history: dict[str, Any],
    funnel_config: dict[str, Any] | None = None,
    window: int = 60,
    allowed_stages: list[str] | None = None,
) -> str:
    config = funnel_config or load_funnel_config()
    distribution = _distribution_map(config)
    candidates = [s for s in FUNNEL_STAGES if not allowed_stages or s in allowed_stages]
    if not candidates:
        candidates = list(FUNNEL_STAGES)

    posts = history.get("posts", []) if isinstance(history, dict) else []
    recent = [p for p in posts[-window:] if isinstance(p, dict)]
    if not recent:
        return max(candidates, key=lambda stage: distribution.get(stage, 0.0))

    counts = {stage: 0 for stage in FUNNEL_STAGES}
    for row in recent:
        stage = _normalize_stage(str(row.get("funnel_stage", "")))
        counts[stage] += 1

    total = max(1, sum(counts.values()))
    deficits = []
    for stage in candidates:
        actual = counts[stage] / total
        target = distribution.get(stage, 0.0)
        deficits.append((target - actual, target, stage))

    deficits.sort(reverse=True)
    return deficits[0][2]


def stage_for_slot(
    slot: str,
    history: dict[str, Any] | None = None,
    funnel_config: dict[str, Any] | None = None,
    schedule: dict[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> str:
    allowed = allowed_stages_for_slot(slot, schedule=schedule, now_utc=now_utc)
    return select_funnel_stage(history or {"posts": []}, funnel_config=funnel_config, allowed_stages=allowed)


def should_channel_run(
    channel: str,
    slot: str,
    schedule: dict[str, Any],
    now_utc: datetime | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    env_map = env or os.environ
    override_key = f"ENABLE_{channel.upper()}_SLOTS"
    override = (env_map.get(override_key) or "").strip()
    if override:
        slots = [x.strip().lower() for x in override.split(",") if x.strip()]
        allowed = slot.lower() in slots
        return allowed, f"env_override:{override_key}"

    config = schedule.get(channel, {}) if isinstance(schedule, dict) else {}
    slots = config.get("slots", []) if isinstance(config, dict) else []
    days = config.get("days", []) if isinstance(config, dict) else []

    now = now_utc or datetime.now(timezone.utc)
    weekday = now.weekday()
    slot_ok = slot in slots if isinstance(slots, list) and slots else True
    day_ok = weekday in days if isinstance(days, list) and days else True

    if slot_ok and day_ok:
        return True, "schedule_match"
    return False, "schedule_blocked"


def apply_claim_guardrails(text: str) -> tuple[str, list[str]]:
    updated = text
    replaced: list[str] = []
    for pattern, replacement in RISKY_CLAIM_PATTERNS:
        if pattern.search(updated):
            updated = pattern.sub(replacement, updated)
            replaced.append(pattern.pattern)
    return updated, replaced


def count_numbers(text: str) -> int:
    return len(re.findall(r"\b\d+(?:[\.,]\d+)?\b", text or ""))


def score_generated_content(content: dict[str, Any]) -> QualityScore:
    wp_content = str(content.get("wp_content", ""))
    fb_caption = str(content.get("fb_caption", ""))
    ig_caption = str(content.get("ig_caption", ""))
    li_text = str(content.get("li_text", ""))

    checks: dict[str, Any] = {}
    warnings: list[str] = []
    score = 100

    total_numbers = count_numbers(wp_content) + count_numbers(fb_caption) + count_numbers(ig_caption) + count_numbers(li_text)
    checks["numeric_evidence_count"] = total_numbers
    if total_numbers < 3:
        warnings.append("Low numeric evidence across channels")
        score -= 10

    if len(wp_content) < 1200:
        warnings.append("WordPress body is shorter than target depth")
        score -= 8
    checks["wp_length"] = len(wp_content)

    ig_hashtags = re.findall(r"#[A-Za-z0-9_]+", ig_caption)
    checks["ig_hashtag_count"] = len(ig_hashtags)
    if len(ig_hashtags) < 5:
        warnings.append("Instagram hashtag count below target")
        score -= 6

    cta_source = " ".join(
        [
            str(content.get("selected_cta", "")),
            fb_caption,
            ig_caption,
            li_text,
            wp_content,
        ]
    )
    cta_present = has_explicit_cta_keyword(cta_source)
    checks["cta_present"] = cta_present
    if not cta_present:
        warnings.append("No explicit CTA keyword detected")
        score -= 12

    risky_hits = []
    for field_name, value in (("wp_content", wp_content), ("fb_caption", fb_caption), ("ig_caption", ig_caption), ("li_text", li_text)):
        for pattern, _ in RISKY_CLAIM_PATTERNS:
            if pattern.search(value):
                risky_hits.append({"field": field_name, "pattern": pattern.pattern})
    checks["risky_claim_hits"] = risky_hits
    if risky_hits:
        warnings.append("Risky claims detected and should be softened")
        score -= min(18, 4 * len(risky_hits))

    score = max(0, min(100, score))
    checks["grade"] = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D"
    return QualityScore(score=score, checks=checks, warnings=warnings)


def stable_text_hash(value: str) -> str:
    return hashlib.md5((value or "").encode("utf-8")).hexdigest()


def build_utm_link(base_url: str, source: str, medium: str, campaign: str, content: str) -> str:
    if not base_url:
        return base_url
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign,
            "utm_content": content,
        }
    )
    new_query = urlencode(query)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def was_recent_channel_success(history: dict[str, Any], channel: str, slot: str, within_hours: int) -> bool:
    posts = history.get("posts", []) if isinstance(history, dict) else []
    if not isinstance(posts, list) or within_hours <= 0:
        return False

    now = datetime.now(timezone.utc)
    key = f"{channel}_id"
    for post in reversed(posts[-200:]):
        if not isinstance(post, dict):
            continue
        if post.get("slot") != slot:
            continue
        value = str(post.get(key, ""))
        if value in ("", "skipped", "dry-run"):
            continue
        date_iso = str(post.get("run_started_at_utc") or post.get("date") or "")
        try:
            dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
            age_hours = (now - dt).total_seconds() / 3600.0
            if age_hours <= within_hours:
                return True
        except Exception:
            continue
    return False
