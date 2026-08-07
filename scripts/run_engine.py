import os
import sys
import time
import json
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))

import generate_posts
import publish_wordpress
import publish_facebook
import publish_instagram
import publish_linkedin
from score_content import score_content
from validate_product_claims import validate_generated_content
from anti_repeat import check_duplicates, load_anti_repeat_windows
from build_utm_url import build_utm_url
from campaign_runtime import (
    eligible_channels_for_slot,
    load_channel_schedule,
    was_recent_channel_success,
)


def _stable_hash(text: str) -> str:
    import hashlib

    normalized = " ".join((text or "").strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _recent_duplicate_platform_caption(
    history: dict,
    platform: str,
    caption: str,
    *,
    days: int,
) -> bool:
    if days <= 0:
        return False
    target = _stable_hash(caption)
    if not target:
        return False

    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - (days * 86400)
    posts = history.get("posts", []) if isinstance(history, dict) else []
    for row in reversed(posts):
        if not isinstance(row, dict):
            continue
        raw = str(row.get("run_started_at_utc") or row.get("published_at") or row.get("date") or "").strip()
        if not raw:
            continue
        try:
            if len(raw) == 10 and "-" in raw:
                dt = datetime.fromisoformat(raw + "T00:00:00+00:00")
            else:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt.timestamp() < cutoff:
            continue

        records = row.get("platform_records", [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            if str(record.get("platform", "")).strip().lower() != platform.lower():
                continue
            status = str(record.get("status", "")).strip().lower()
            if status not in {"published", "dry-run"}:
                continue
            old_sig = str(record.get("caption_signature", "")).strip()
            if old_sig and old_sig == target:
                return True
    return False


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_channel_config() -> dict:
    return {
        "wordpress": _env_flag("ENABLE_WORDPRESS", False),
        "facebook": _env_flag("ENABLE_FACEBOOK", True),
        "instagram": _env_flag("ENABLE_INSTAGRAM", True),
        "linkedin": _env_flag("ENABLE_LINKEDIN", True),
    }


def check_secrets(dry_run: bool, channels: dict) -> None:
    required: list[str] = []
    # AI key is optional because generator has deterministic fallback content.
    if not os.environ.get("GEMINI_API_KEY"):
        print("[WARN] GEMINI_API_KEY is not set. Using deterministic fallback content.")

    if dry_run:
        return

    if channels["wordpress"]:
        required.extend(["WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"])
    if channels["facebook"]:
        required.extend(["META_PAGE_ID", "META_PAGE_ACCESS_TOKEN"])
    if channels["instagram"]:
        required.extend(["META_IG_USER_ID", "META_PAGE_ACCESS_TOKEN"])
    if channels["linkedin"]:
        required.extend(["LINKEDIN_ACCESS_TOKEN"])

    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing required secrets: {', '.join(missing)}")
        sys.exit(1)


def _latest_marketing_strategy_info() -> tuple[str, str]:
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
    marketing_dir = os.path.join(data_dir, "marketing")
    if not os.path.isdir(marketing_dir):
        return "none", "not found"

    files = [
        os.path.join(marketing_dir, f)
        for f in os.listdir(marketing_dir)
        if (
            (f.startswith("marketing_strategy_") or f.startswith("marketing_bundle_"))
            and f.endswith(".json")
        )
    ]
    if not files:
        return "none", "not found"

    latest = max(files, key=os.path.getmtime)
    ts = datetime.fromtimestamp(os.path.getmtime(latest), tz=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    freshness = "fresh" if age_hours <= 48 else "stale"
    return os.path.basename(latest), freshness


def _refresh_linkedin_access_token_if_configured() -> tuple[bool, str]:
    refresh_token = str(os.environ.get("LINKEDIN_REFRESH_TOKEN", "")).strip()
    client_id = str(os.environ.get("LINKEDIN_CLIENT_ID", "")).strip()
    client_secret = str(os.environ.get("LINKEDIN_CLIENT_SECRET", "")).strip()
    if not (refresh_token and client_id and client_secret):
        return False, "refresh_not_configured"

    try:
        resp = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=20,
        )
        if not resp.ok:
            return False, f"refresh_failed_http_{resp.status_code}"
        payload = resp.json() if resp.content else {}
        new_token = str(payload.get("access_token", "")).strip()
        if not new_token:
            return False, "refresh_missing_access_token"
        os.environ["LINKEDIN_ACCESS_TOKEN"] = new_token
        return True, "refreshed"
    except Exception as e:
        return False, f"refresh_exception:{e}"


def _build_phase5_channel_readiness(effective_channels: dict[str, bool], dry_run: bool) -> dict:
    checks: dict[str, dict] = {}

    def mark(platform: str, status: str, reason: str, details: dict | None = None) -> None:
        checks[platform] = {
            "status": status,
            "reason": reason,
            "details": details or {},
        }

    if not effective_channels.get("wordpress", False):
        mark("wordpress", "yellow", "channel_disabled")
    else:
        wp_url = str(os.environ.get("WP_URL", "")).strip()
        wp_user = str(os.environ.get("WP_USERNAME", "")).strip()
        wp_pw = str(os.environ.get("WP_APP_PASSWORD", "")).strip()
        if not (wp_url and wp_user and wp_pw):
            mark("wordpress", "red", "missing_credentials")
        else:
            mark("wordpress", "green", "credentials_present")

    fb_token = str(os.environ.get("META_PAGE_ACCESS_TOKEN", "")).strip()
    if not effective_channels.get("facebook", False):
        mark("facebook", "yellow", "channel_disabled")
    elif not fb_token:
        mark("facebook", "red", "missing_page_access_token")
    else:
        try:
            resp = requests.get(
                "https://graph.facebook.com/v26.0/me/accounts",
                params={"fields": "id,name", "access_token": fb_token},
                timeout=15,
            )
            if resp.ok:
                mark("facebook", "green", "token_valid")
            else:
                mark("facebook", "red", f"token_check_failed_http_{resp.status_code}")
        except Exception as e:
            mark("facebook", "red", f"token_check_exception:{e}")

    if not effective_channels.get("instagram", False):
        mark("instagram", "yellow", "channel_disabled")
    else:
        ig_user = str(os.environ.get("META_IG_USER_ID", "")).strip()
        if not (ig_user and fb_token):
            mark("instagram", "red", "missing_ig_or_page_token")
        else:
            try:
                resp = requests.get(
                    f"https://graph.facebook.com/v26.0/{ig_user}",
                    params={"fields": "id,username", "access_token": fb_token},
                    timeout=15,
                )
                if resp.ok:
                    mark("instagram", "green", "token_valid")
                else:
                    mark("instagram", "red", f"token_check_failed_http_{resp.status_code}")
            except Exception as e:
                mark("instagram", "red", f"token_check_exception:{e}")

    if not effective_channels.get("linkedin", False):
        mark("linkedin", "yellow", "channel_disabled")
    else:
        token = str(os.environ.get("LINKEDIN_ACCESS_TOKEN", "")).strip()
        if not token:
            mark("linkedin", "red", "missing_access_token")
        else:
            try:
                resp = requests.get(
                    "https://api.linkedin.com/v2/userinfo",
                    headers={"Authorization": f"Bearer {token}", "LinkedIn-Version": datetime.now(timezone.utc).strftime("%Y%m")},
                    timeout=15,
                )
                if resp.ok:
                    mark("linkedin", "green", "token_valid")
                elif resp.status_code in (401, 403) and not dry_run:
                    refreshed, reason = _refresh_linkedin_access_token_if_configured()
                    if refreshed:
                        mark("linkedin", "yellow", "token_refreshed_retry_next_call", {"refresh": reason})
                    else:
                        mark("linkedin", "red", f"token_invalid:{reason}")
                else:
                    mark("linkedin", "red", f"token_check_failed_http_{resp.status_code}")
            except Exception as e:
                mark("linkedin", "red", f"token_check_exception:{e}")

    blocking = [p for p, v in checks.items() if str(v.get("status", "")).lower() == "red" and effective_channels.get(p, False)]
    return {
        "checks": checks,
        "blocking_channels": blocking,
        "overall": "pass" if not blocking else "fail",
    }


def _build_phase6_learning(
    *,
    content: dict,
    platform_records: list[dict],
    errors: list[str],
    status: str,
) -> dict:
    published = [r for r in platform_records if str(r.get("status", "")).lower() == "published"]
    failed = [r for r in platform_records if str(r.get("status", "")).lower() == "error"]
    skipped = [r for r in platform_records if str(r.get("status", "")).lower().startswith("skipped")]

    hypotheses = []
    if published:
        hypotheses.append("Replicate angle and CTA framing on next matching funnel stage.")
    if failed:
        hypotheses.append("Run channel-specific failure drill and token validity recheck before next live run.")
    if skipped:
        hypotheses.append("Rebalance scheduling/eligibility constraints to reduce avoidable skips.")

    return {
        "status": status,
        "postmortem": {
            "topic": str(content.get("topic", "")),
            "hook": str(content.get("selected_hook", "")),
            "cta": str(content.get("selected_cta", "")),
            "published_count": len(published),
            "failed_count": len(failed),
            "skipped_count": len(skipped),
            "errors": errors,
        },
        "experiment_plan": {
            "active_hypotheses": hypotheses[:3],
            "next_test": "A/B test hook opening line while keeping CTA constant",
        },
        "attribution": {
            "driver": "creative_and_channel_readiness",
            "notes": "Attribution based on per-platform status and gate outcomes from this run.",
        },
    }


def _apply_phase8_budget(metrics: dict, key: str, elapsed: float, budget: float) -> None:
    metrics.setdefault("durations_sec", {})[key] = round(elapsed, 3)
    if budget > 0 and elapsed > budget:
        metrics.setdefault("warnings", []).append(f"budget_exceeded:{key}:{round(elapsed, 3)}>{budget}")


def _platform_status(
    platform: str,
    effective_channels: dict[str, bool],
    platform_id: str,
    dry_run: bool,
    error_map: dict[str, str],
) -> str:
    if error_map.get(platform):
        return "error"
    if not effective_channels.get(platform, False):
        return "skipped"
    if platform_id in ("", "skipped"):
        return "skipped"
    if dry_run or platform_id == "dry-run":
        return "dry-run"
    return "published"


def _build_platform_history_records(
    content: dict,
    run_started: str,
    effective_channels: dict[str, bool],
    dry_run: bool,
    ids: dict[str, str],
    tracked_links: dict[str, str],
    error_map: dict[str, str],
) -> list[dict]:
    destination_url = str(content.get("destination_url") or "")
    campaign_id = str(content.get("campaign_id") or "")
    post_id = str(content.get("post_id") or "")
    stage = str(content.get("funnel_stage") or "EDUCATION")
    audience = str(content.get("audience_segment") or "")
    product_id = str(content.get("product_id") or "") or None
    topic = str(content.get("topic") or "")
    hook = str(content.get("selected_hook") or "")
    hook_type = str(content.get("selected_hook_type") or "")
    cta = str(content.get("selected_cta") or "")
    quality_score = content.get("quality_score")
    quality_value = float(quality_score) if isinstance(quality_score, (int, float)) else 0.0
    platform_posts = content.get("platform_posts", {}) if isinstance(content.get("platform_posts"), dict) else {}

    records: list[dict] = []
    for platform in ("facebook", "instagram", "linkedin", "wordpress"):
        platform_entry = platform_posts.get(platform, {}) if isinstance(platform_posts.get(platform), dict) else {}
        platform_post_id = str(ids.get(platform, "") or "")
        utm_url = tracked_links.get(platform) if platform in tracked_links else None
        if platform == "wordpress" and not utm_url:
            utm_url = destination_url or None
        records.append(
            {
                "post_id": post_id,
                "platform_post_id": platform_post_id or None,
                "campaign_id": campaign_id,
                "platform": platform,
                "published_at": run_started,
                "funnel_stage": stage,
                "audience_segment": audience,
                "product_id": product_id,
                "topic": topic,
                "hook": hook,
                "hook_type": hook_type,
                "cta": str(platform_entry.get("cta") or cta),
                "content_format": str(platform_entry.get("content_format") or ("blog_post" if platform == "wordpress" else "")),
                "quality_score": quality_value,
                "caption_signature": _stable_hash(str(platform_entry.get("caption") or "")),
                "destination_url": destination_url or None,
                "utm_url": utm_url,
                "status": _platform_status(platform, effective_channels, platform_post_id, dry_run, error_map),
                "error": error_map.get(platform),
            }
        )
    return records


def main() -> None:
    slot = os.environ.get("POST_SLOT", "morning")
    dry_run = os.environ.get("SOCIAL_DRY_RUN", "true").lower() == "true"
    manual_platforms = [
        x.strip().lower()
        for x in os.environ.get("POST_PLATFORMS", "").split(",")
        if x.strip()
    ]
    manual_duplicate_mode = os.environ.get("MANUAL_DUPLICATE_MODE", "exact_only").strip().lower()
    channels = get_channel_config()
    schedule = load_channel_schedule()
    now_utc = datetime.now(timezone.utc)
    effective_channels = dict(channels)
    channel_reasons: dict[str, str] = {}
    runtime_metrics: dict = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "durations_sec": {},
        "warnings": [],
    }
    generation_budget = float(os.environ.get("PHASE8_BUDGET_GENERATION_SEC", "180"))
    publish_budget = float(os.environ.get("PHASE8_BUDGET_PUBLISH_SEC", "120"))
    total_budget = float(os.environ.get("PHASE8_BUDGET_TOTAL_SEC", "420"))
    t_total = time.perf_counter()

    # Compute a stage first so schedule rules can enforce stage eligibility.
    generate_posts.ensure_runtime_data()
    t_preview = time.perf_counter()
    preview_content = generate_posts.generate(slot)
    _apply_phase8_budget(runtime_metrics, "preview_generation", time.perf_counter() - t_preview, generation_budget)
    funnel_stage = str(preview_content.get("funnel_stage", "EDUCATION"))

    eligibility = eligible_channels_for_slot(
        slot=slot,
        funnel_stage=funnel_stage,
        schedule=schedule,
        now_utc=now_utc,
        manual_platforms=manual_platforms,
    )

    for name, enabled in channels.items():
        if not enabled:
            effective_channels[name] = False
            channel_reasons[name] = "disabled_env"
            continue

        allowed, reason = eligibility.get(name, (False, "not_scheduled"))
        effective_channels[name] = bool(allowed)
        channel_reasons[name] = reason

    check_secrets(dry_run=dry_run, channels=effective_channels)
    phase5_readiness = _build_phase5_channel_readiness(effective_channels, dry_run)
    readiness_block_on_red = os.environ.get("CHANNEL_READINESS_BLOCK_ON_RED", "true").strip().lower() in {"1", "true", "yes", "on"}
    strategy_name, strategy_freshness = _latest_marketing_strategy_info()

    print(f"\n=== INF Energy Social Engine ===")
    print(f"Slot: {slot} | Dry run: {dry_run} | UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n")
    print(
        "Channels: "
        f"wordpress={effective_channels['wordpress']} "
        f"facebook={effective_channels['facebook']} "
        f"instagram={effective_channels['instagram']} "
        f"linkedin={effective_channels['linkedin']}\n"
    )
    print(
        "Channel reasons: "
        f"wp={channel_reasons.get('wordpress', '')} "
        f"fb={channel_reasons.get('facebook', '')} "
        f"ig={channel_reasons.get('instagram', '')} "
        f"li={channel_reasons.get('linkedin', '')}\n"
    )
    if manual_platforms:
        print(f"Manual platform override: {manual_platforms}\n")
    print(f"Marketing strategy: {strategy_name} ({strategy_freshness})\n")
    print(f"Phase5 readiness: {json.dumps(phase5_readiness, ensure_ascii=True)}\n")

    if (not dry_run) and readiness_block_on_red and phase5_readiness.get("overall") != "pass":
        print("[SKIP] Channel readiness check failed; blocking live publish")
        history = generate_posts.load_history()
        run_started = datetime.now(timezone.utc).isoformat()
        tracked_links = {"facebook": None, "instagram": None, "linkedin": None, "wordpress": None}
        platform_ids = {"wordpress": "skipped", "facebook": "skipped", "instagram": "skipped", "linkedin": "skipped"}
        platform_records = _build_platform_history_records(
            content=preview_content,
            run_started=run_started,
            effective_channels=effective_channels,
            dry_run=dry_run,
            ids=platform_ids,
            tracked_links=tracked_links,
            error_map={},
        )
        phase6_learning = _build_phase6_learning(
            content=preview_content,
            platform_records=platform_records,
            errors=["channel_readiness_failed"],
            status="skipped_channel_readiness",
        )
        _apply_phase8_budget(runtime_metrics, "total", time.perf_counter() - t_total, total_budget)
        history["posts"].append({
            "post_id": preview_content.get("post_id", ""),
            "platform_post_id": None,
            "campaign_id": preview_content.get("campaign_id", ""),
            "platform": "multi",
            "published_at": run_started,
            "audience_segment": preview_content.get("audience_segment", ""),
            "product_id": preview_content.get("product_id") or None,
            "hook": preview_content.get("selected_hook", ""),
            "cta": preview_content.get("selected_cta", ""),
            "content_format": "multi",
            "destination_url": preview_content.get("destination_url") or None,
            "utm_url": None,
            "error": "channel_readiness_failed",
            "date": preview_content.get("date"),
            "slot": slot,
            "run_started_at_utc": run_started,
            "topic": preview_content.get("topic"),
            "pillar": preview_content.get("pillar"),
            "topic_hash": preview_content.get("topic_hash"),
            "funnel_stage": preview_content.get("funnel_stage", "EDUCATION"),
            "quality_score": preview_content.get("quality_score"),
            "status": "skipped_channel_readiness",
            "channel_reasons": channel_reasons,
            "phase5_channel_readiness": phase5_readiness,
            "phase6_learning": phase6_learning,
            "phase8_runtime": runtime_metrics,
            "platform_records": platform_records,
            "wp_id": "skipped",
            "fb_id": "skipped",
            "ig_id": "skipped",
            "li_id": "skipped",
        })
        history["posts"] = history["posts"][-200:]
        generate_posts.save_history(history)
        print("\n=== Done (skipped) ===\n")
        return

    print("[1/5] Generating content with Gemini...")
    # Phase 8: max two generation attempts with score/validation gating.
    attempts: list[dict] = []
    windows = load_anti_repeat_windows()
    content = preview_content
    t_generation = time.perf_counter()
    for idx in range(2):
        if idx > 0:
            content = generate_posts.generate(slot)

        validation = validate_generated_content(content)
        if content.get("orchestration_blocked"):
            validation = {
                "passed": False,
                "errors": list(validation.get("errors", [])) + ["orchestration_control_plane_blocked"],
                "warnings": list(validation.get("warnings", [])),
            }
        scoring = score_content(content)
        duplicates = check_duplicates(content, generate_posts.load_history(), windows=windows)
        if manual_platforms and manual_duplicate_mode == "allow_all":
            if duplicates.get("reasons"):
                content.setdefault("quality_warnings", []).append("manual_duplicate_mode:allow_all")
            duplicates["reasons"] = []
            duplicates["ok"] = True
        elif manual_platforms and manual_duplicate_mode == "exact_only":
            reasons = [str(r) for r in duplicates.get("reasons", [])]
            exact_reasons = [
                r for r in reasons if r in {"duplicate_exact_caption_within_window", "duplicate_opening_sentence_within_window"}
            ]
            if len(exact_reasons) != len(reasons):
                content.setdefault("quality_warnings", []).append("manual_duplicate_mode:exact_only")
            duplicates["reasons"] = exact_reasons
            duplicates["ok"] = len(exact_reasons) == 0
        content["validation_status"] = "passed" if validation.get("passed") else "failed"
        content["validation_errors"] = validation.get("errors", [])
        content["validation_warnings"] = validation.get("warnings", [])
        content["quality_score"] = scoring.get("total")
        content["quality_component_scores"] = scoring.get("component_scores", {})
        content["duplicate_check"] = duplicates
        content.update(duplicates.get("signatures", {}))

        attempts.append(
            {
                "attempt": idx + 1,
                "score": scoring.get("total"),
                "decision": scoring.get("decision"),
                "validation_passed": validation.get("passed"),
                "validation_errors": validation.get("errors", []),
                "duplicates_ok": duplicates.get("ok"),
                "duplicate_reasons": duplicates.get("reasons", []),
            }
        )

        if validation.get("passed") and scoring.get("total", 0) >= 82 and duplicates.get("ok"):
            break

        # If score is in regenerate range and this is first attempt, try one more time.
        if idx == 0 and scoring.get("decision") == "regenerate_once":
            continue

        # Otherwise stop on second attempt or hard rejection.
        if idx == 1 or scoring.get("decision") == "reject":
            break
    _apply_phase8_budget(runtime_metrics, "generation", time.perf_counter() - t_generation, generation_budget)

    final_validation_ok = content.get("validation_status") == "passed"
    final_score = float(content.get("quality_score") or 0)
    duplicate_ok = bool(content.get("duplicate_check", {}).get("ok", True))

    if (not final_validation_ok) or final_score < 82 or (not duplicate_ok):
        print("[SKIP] Content did not pass validation/quality thresholds; recording skipped run")
        history = generate_posts.load_history()
        run_started = datetime.now(timezone.utc).isoformat()
        tracked_links = {"facebook": None, "instagram": None, "linkedin": None, "wordpress": None}
        platform_ids = {"wordpress": "skipped", "facebook": "skipped", "instagram": "skipped", "linkedin": "skipped"}
        platform_records = _build_platform_history_records(
            content=content,
            run_started=run_started,
            effective_channels=effective_channels,
            dry_run=dry_run,
            ids=platform_ids,
            tracked_links=tracked_links,
            error_map={},
        )
        history["posts"].append({
            "post_id": content.get("post_id", ""),
            "platform_post_id": None,
            "campaign_id": content.get("campaign_id", ""),
            "platform": "multi",
            "published_at": run_started,
            "audience_segment": content.get("audience_segment", ""),
            "product_id": content.get("product_id") or None,
            "hook": content.get("selected_hook", ""),
            "cta": content.get("selected_cta", ""),
            "content_format": "multi",
            "destination_url": content.get("destination_url") or None,
            "utm_url": None,
            "error": "failed_quality_or_validation_or_duplicate",
            "date": content.get("date"),
            "slot": slot,
            "run_started_at_utc": run_started,
            "topic": content.get("topic"),
            "pillar": content.get("pillar"),
            "topic_hash": content.get("topic_hash"),
            "hook_type": content.get("selected_hook_type", ""),
            "funnel_stage": content.get("funnel_stage", "EDUCATION"),
            "quality_score": content.get("quality_score"),
            "quality_component_scores": content.get("quality_component_scores", {}),
            "validation_status": content.get("validation_status"),
            "validation_errors": content.get("validation_errors", []),
            "duplicate_reasons": content.get("duplicate_check", {}).get("reasons", []),
            "exact_caption_signature": content.get("exact_caption_signature", ""),
            "opening_signature": content.get("opening_signature", ""),
            "scenario_signature": content.get("scenario_signature", ""),
            "lesson_signature": content.get("lesson_signature", ""),
            "format_signature": content.get("format_signature", ""),
            "structure_signature": content.get("structure_signature", ""),
            "generation_attempts": attempts,
            "dry_run": dry_run,
            "status": "skipped_validation_or_quality",
            "channel_reasons": channel_reasons,
            "phase5_channel_readiness": phase5_readiness,
            "phase6_learning": _build_phase6_learning(
                content=content,
                platform_records=platform_records,
                errors=["failed_quality_or_validation_or_duplicate"],
                status="skipped_validation_or_quality",
            ),
            "phase8_runtime": runtime_metrics,
            "platform_records": platform_records,
            "wp_id": "skipped",
            "fb_id": "skipped",
            "ig_id": "skipped",
            "li_id": "skipped",
        })
        history["posts"] = history["posts"][-200:]
        _apply_phase8_budget(runtime_metrics, "total", time.perf_counter() - t_total, total_budget)
        generate_posts.save_history(history)
        print("\n=== Done (skipped) ===\n")
        return

    print(f"Topic: {content['topic']}")
    print(
        "Marketing strategy loaded: "
        f"{'yes' if content.get('marketing_strategy_used') or content.get('marketing_bundle_used') else 'no'}"
    )
    print(f"Funnel stage: {content.get('funnel_stage', 'awareness')}")
    print(f"Quality score: {content.get('quality_score', 'n/a')}")
    print(f"Quality components: {content.get('quality_component_scores', {})}")
    print(f"Validation: {content.get('validation_status', 'unknown')}")
    if content.get("validation_errors"):
        print(f"Validation errors: {content.get('validation_errors')}")
    if content.get("quality_warnings"):
        print(f"Quality warnings: {content.get('quality_warnings')}")
    if content.get("product_name"):
        print(f"Product: {content['product_name']} ({content.get('product_sku', 'N/A')})")
    print(f"WP Title: {content['wp_title']}\n")

    errors = []
    error_map: dict[str, str] = {}
    wp_result = {"id": "skipped", "link": os.environ.get("WP_URL", "https://www.infenergypower.com")}
    fb_result = {"id": "skipped"}
    ig_result = {"id": "skipped"}
    li_result = {"id": "skipped"}

    if not any(effective_channels.values()):
        print("[SKIP] No eligible platforms for this slot/stage; recording successful skipped run")
        history = generate_posts.load_history()
        run_started = datetime.now(timezone.utc).isoformat()
        tracked_links = {"facebook": None, "instagram": None, "linkedin": None, "wordpress": None}
        platform_ids = {"wordpress": "skipped", "facebook": "skipped", "instagram": "skipped", "linkedin": "skipped"}
        platform_records = _build_platform_history_records(
            content=content,
            run_started=run_started,
            effective_channels=effective_channels,
            dry_run=dry_run,
            ids=platform_ids,
            tracked_links=tracked_links,
            error_map={},
        )
        history["posts"].append({
            "post_id": content.get("post_id", ""),
            "platform_post_id": None,
            "campaign_id": content.get("campaign_id", ""),
            "platform": "multi",
            "published_at": run_started,
            "audience_segment": content.get("audience_segment", ""),
            "product_id": content.get("product_id") or None,
            "hook": content.get("selected_hook", ""),
            "cta": content.get("selected_cta", ""),
            "content_format": "multi",
            "destination_url": content.get("destination_url") or None,
            "utm_url": None,
            "error": None,
            "date": content["date"],
            "slot": slot,
            "run_started_at_utc": run_started,
            "topic": content["topic"],
            "pillar": content["pillar"],
            "topic_hash": content["topic_hash"],
            "hook_type": content.get("selected_hook_type", ""),
            "funnel_stage": content.get("funnel_stage", "EDUCATION"),
            "quality_score": content.get("quality_score"),
            "quality_component_scores": content.get("quality_component_scores", {}),
            "validation_status": content.get("validation_status"),
            "validation_errors": content.get("validation_errors", []),
            "duplicate_reasons": content.get("duplicate_check", {}).get("reasons", []),
            "exact_caption_signature": content.get("exact_caption_signature", ""),
            "opening_signature": content.get("opening_signature", ""),
            "scenario_signature": content.get("scenario_signature", ""),
            "lesson_signature": content.get("lesson_signature", ""),
            "format_signature": content.get("format_signature", ""),
            "structure_signature": content.get("structure_signature", ""),
            "generation_attempts": attempts,
            "dry_run": dry_run,
            "status": "skipped_no_eligible_platforms",
            "channel_reasons": channel_reasons,
            "phase5_channel_readiness": phase5_readiness,
            "phase6_learning": _build_phase6_learning(
                content=content,
                platform_records=platform_records,
                errors=[],
                status="skipped_no_eligible_platforms",
            ),
            "phase8_runtime": runtime_metrics,
            "platform_records": platform_records,
            "wp_id": "skipped",
            "fb_id": "skipped",
            "ig_id": "skipped",
            "li_id": "skipped",
        })
        history["posts"] = history["posts"][-200:]
        _apply_phase8_budget(runtime_metrics, "total", time.perf_counter() - t_total, total_budget)
        generate_posts.save_history(history)
        print("\n=== Done (skipped) ===\n")
        return

    print("[2/5] WordPress...")
    t_wp = time.perf_counter()
    if effective_channels["wordpress"]:
        try:
            wp_result = publish_wordpress.publish(content, dry_run=dry_run)
        except Exception as e:
            errors.append(f"WordPress: {e}")
            error_map["wordpress"] = str(e)
            print(f"[ERROR] WordPress publish failed: {e}")
    else:
        print("[SKIP] WordPress disabled")
    _apply_phase8_budget(runtime_metrics, "publish_wordpress", time.perf_counter() - t_wp, publish_budget)
    wp_link = wp_result.get("link", os.environ.get("WP_URL", "https://www.infenergypower.com"))
    campaign_name = os.environ.get("UTM_CAMPAIGN_NAME", "infenergy_engine")
    audience_term = str(content.get("audience_segment", "general")).lower().replace(" ", "_")
    content_slug = f"{slot}_{str(content.get('funnel_stage', 'education')).lower()}"
    wp_link_fb = build_utm_url(
        wp_link,
        source="facebook",
        campaign=campaign_name,
        content=content_slug,
        term=audience_term,
    ).get("utm_url", wp_link)
    wp_link_ig = build_utm_url(
        wp_link,
        source="instagram",
        campaign=campaign_name,
        content=content_slug,
        term=audience_term,
    ).get("utm_url", wp_link)
    wp_link_li = build_utm_url(
        wp_link,
        source="linkedin",
        campaign=campaign_name,
        content=content_slug,
        term=audience_term,
    ).get("utm_url", wp_link)
    history = generate_posts.load_history()
    skip_success_hours = int(os.environ.get("SKIP_RECENT_SUCCESS_HOURS", "0"))
    fb_duplicate_days = int(os.environ.get("FB_DUPLICATE_CAPTION_DAYS", "14"))

    print("[3/5] Facebook...")
    t_fb = time.perf_counter()
    if effective_channels["facebook"]:
        if (not dry_run) and was_recent_channel_success(history, "fb", slot, skip_success_hours):
            print("[SKIP] Facebook recent successful publish within configured window")
        elif (
            (not dry_run)
            and not (manual_platforms and manual_duplicate_mode == "allow_all")
            and _recent_duplicate_platform_caption(
            history,
            "facebook",
            str(content.get("fb_caption", "")),
            days=fb_duplicate_days,
        )):
            msg = f"duplicate_facebook_caption_within_{fb_duplicate_days}d"
            errors.append(f"Facebook: {msg}")
            error_map["facebook"] = msg
            print(f"[ERROR] Facebook publish blocked: {msg}")
        else:
            try:
                fb_result = publish_facebook.publish(content, wp_link_fb, dry_run=dry_run)
            except Exception as e:
                errors.append(f"Facebook: {e}")
                error_map["facebook"] = str(e)
                print(f"[ERROR] Facebook publish failed: {e}")
    else:
        print("[SKIP] Facebook disabled")
    _apply_phase8_budget(runtime_metrics, "publish_facebook", time.perf_counter() - t_fb, publish_budget)

    print("[4/5] Instagram...")
    t_ig = time.perf_counter()
    if effective_channels["instagram"]:
        if (not dry_run) and was_recent_channel_success(history, "ig", slot, skip_success_hours):
            print("[SKIP] Instagram recent successful publish within configured window")
        else:
            try:
                content["tracked_link_instagram"] = wp_link_ig
                ig_result = publish_instagram.publish(content, dry_run=dry_run)
            except Exception as e:
                errors.append(f"Instagram: {e}")
                error_map["instagram"] = str(e)
                print(f"[ERROR] Instagram publish failed: {e}")
    else:
        print("[SKIP] Instagram disabled")
    _apply_phase8_budget(runtime_metrics, "publish_instagram", time.perf_counter() - t_ig, publish_budget)

    print("[5/5] LinkedIn...")
    t_li = time.perf_counter()
    if effective_channels["linkedin"]:
        if (not dry_run) and was_recent_channel_success(history, "li", slot, skip_success_hours):
            print("[SKIP] LinkedIn recent successful publish within configured window")
        else:
            try:
                li_result = publish_linkedin.publish(content, wp_link_li, dry_run=dry_run)
            except Exception as e:
                errors.append(f"LinkedIn: {e}")
                error_map["linkedin"] = str(e)
                print(f"[ERROR] LinkedIn publish failed: {e}")
    else:
        print("[SKIP] LinkedIn disabled")
    _apply_phase8_budget(runtime_metrics, "publish_linkedin", time.perf_counter() - t_li, publish_budget)

    # Persist history so the next run picks a fresh topic
    run_started = datetime.now(timezone.utc).isoformat()
    tracked_links = {
        "facebook": wp_link_fb,
        "instagram": wp_link_ig,
        "linkedin": wp_link_li,
        "wordpress": wp_link,
    }
    platform_ids = {
        "wordpress": str(wp_result.get("id", "") or ""),
        "facebook": str(fb_result.get("id", "") or ""),
        "instagram": str(ig_result.get("id", "") or ""),
        "linkedin": str(li_result.get("id", "") or ""),
    }
    platform_records = _build_platform_history_records(
        content=content,
        run_started=run_started,
        effective_channels=effective_channels,
        dry_run=dry_run,
        ids=platform_ids,
        tracked_links=tracked_links,
        error_map=error_map,
    )
    phase6_learning = _build_phase6_learning(
        content=content,
        platform_records=platform_records,
        errors=errors,
        status="success" if not errors else "partial_error",
    )
    _apply_phase8_budget(runtime_metrics, "total", time.perf_counter() - t_total, total_budget)
    history["posts"].append({
        "post_id": content.get("post_id", ""),
        "platform_post_id": None,
        "campaign_id": content.get("campaign_id", ""),
        "platform": "multi",
        "published_at": run_started,
        "audience_segment": content.get("audience_segment", ""),
        "product_id": content.get("product_id") or None,
        "hook": content.get("selected_hook", ""),
        "cta": content.get("selected_cta", ""),
        "content_format": "multi",
        "destination_url": content.get("destination_url") or None,
        "utm_url": None,
        "status": "success",
        "error": " | ".join(errors) if errors else None,
        "date": content["date"],
        "slot": slot,
        "run_started_at_utc": run_started,
        "topic": content["topic"],
        "pillar": content["pillar"],
        "topic_hash": content["topic_hash"],
        "hook_type": content.get("selected_hook_type", ""),
        "hook_hash": content.get("hook_hash", ""),
        "cta_hash": content.get("cta_hash", ""),
        "selected_hook": content.get("selected_hook", ""),
        "selected_cta": content.get("selected_cta", ""),
        "funnel_stage": content.get("funnel_stage", "awareness"),
        "product_name": content.get("product_name", ""),
        "product_sku": content.get("product_sku", ""),
        "quality_score": content.get("quality_score"),
        "quality_component_scores": content.get("quality_component_scores", {}),
        "quality_warnings": content.get("quality_warnings", []),
        "validation_status": content.get("validation_status"),
        "validation_errors": content.get("validation_errors", []),
        "duplicate_reasons": content.get("duplicate_check", {}).get("reasons", []),
        "exact_caption_signature": content.get("exact_caption_signature", ""),
        "opening_signature": content.get("opening_signature", ""),
        "scenario_signature": content.get("scenario_signature", ""),
        "lesson_signature": content.get("lesson_signature", ""),
        "format_signature": content.get("format_signature", ""),
        "structure_signature": content.get("structure_signature", ""),
        "generation_attempts": attempts,
        "dry_run": dry_run,
        "channel_reasons": channel_reasons,
        "phase5_channel_readiness": phase5_readiness,
        "phase6_learning": phase6_learning,
        "phase8_runtime": runtime_metrics,
        "platform_records": platform_records,
        "tracked_links": {
            "facebook": wp_link_fb,
            "instagram": wp_link_ig,
            "linkedin": wp_link_li,
        },
        "wp_id": wp_result.get("id"),
        "fb_id": fb_result.get("id"),
        "ig_id": ig_result.get("id"),
        "li_id": li_result.get("id"),
    })
    history["posts"] = history["posts"][-200:]
    generate_posts.save_history(history)

    if errors:
        raise RuntimeError(" | ".join(errors))

    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
