import os
import sys
import time
import json
import hmac
import mimetypes
import threading
import subprocess
import traceback
from urllib.parse import urlparse, parse_qs
import schedule
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone, timedelta
import glob
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

import run_engine
import generate_posts
import inventory_db
import intelligence_packages
from content_operations import content_detail, daily_index, daily_markdown, daily_status, init_content_operations, operations_readiness, reconcile_confirmed_transactions, reconcile_ready_inventory, reconcile_stale_claims
from campaign_runtime import eligible_channels_for_slot, load_channel_schedule, load_funnel_config, stage_for_slot

RUN_LOCK = threading.Lock()
LAST_RUN = {
    "status": "idle",
    "slot": None,
    "started_at_utc": None,
    "finished_at_utc": None,
    "error": None,
}
STARTED_AT = datetime.now(timezone.utc)
VISUAL_REPO_BOOTSTRAP = {
    "status": "not_run",
    "time_utc": None,
    "summary": {},
    "error": None,
}


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _meta_state_path() -> str:
    return os.path.join(_data_dir(), "marketing", "meta_token_state.json")


def _safe_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _mask_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) <= 12:
        return "********"
    return f"{token[:6]}...{token[-6:]}"


def _load_meta_runtime_from_state() -> tuple[bool, str]:
    path = _meta_state_path()
    if not os.path.exists(path):
        return False, "state_file_not_found"
    try:
        data = _load_json(path, {})
        if not isinstance(data, dict):
            return False, "state_file_invalid"

        keys = [
            "META_LONG_LIVED_USER_TOKEN",
            "META_PAGE_ACCESS_TOKEN",
            "META_PAGE_ID",
            "META_IG_USER_ID",
            "META_TOKEN_EXPIRES_AT_UTC",
            "META_TOKEN_UPDATED_AT_UTC",
        ]
        loaded = 0
        for key in keys:
            value = str(data.get(key, "")).strip()
            if value:
                os.environ[key] = value
                loaded += 1
        if loaded == 0:
            return False, "state_file_has_no_runtime_keys"
        return True, f"loaded_{loaded}_keys"
    except Exception as e:
        return False, f"state_file_load_error:{e}"


def _meta_refresh_secret() -> str:
    return str(os.environ.get("META_REFRESH_TOKEN", "") or os.environ.get("MANUAL_RUN_TOKEN", "")).strip()


def _refresh_meta_tokens() -> tuple[bool, dict]:
    required = {
        "META_APP_ID": str(os.environ.get("META_APP_ID", "")).strip(),
        "META_APP_SECRET": str(os.environ.get("META_APP_SECRET", "")).strip(),
        "META_LONG_LIVED_USER_TOKEN": str(os.environ.get("META_LONG_LIVED_USER_TOKEN", "")).strip(),
        "META_PAGE_ID": str(os.environ.get("META_PAGE_ID", "")).strip(),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        return False, {
            "ok": False,
            "error": "missing_required_env",
            "missing": missing,
        }

    app_id = required["META_APP_ID"]
    app_secret = required["META_APP_SECRET"]
    current_user_token = required["META_LONG_LIVED_USER_TOKEN"]
    page_id = required["META_PAGE_ID"]
    graph_version = str(os.environ.get("META_GRAPH_VERSION", "v20.0")).strip() or "v20.0"
    graph_base = f"https://graph.facebook.com/{graph_version}"

    try:
        exchange = requests.get(
            f"{graph_base}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": current_user_token,
            },
            timeout=30,
        )
        if not exchange.ok:
            return False, {
                "ok": False,
                "error": "exchange_failed",
                "status_code": exchange.status_code,
                "response": exchange.text[:1000],
            }
        exchange_payload = exchange.json() if exchange.content else {}
        new_user_token = str(exchange_payload.get("access_token", "")).strip()
        expires_in = int(exchange_payload.get("expires_in", 0) or 0)
        if not new_user_token:
            return False, {
                "ok": False,
                "error": "exchange_missing_access_token",
            }

        pages = requests.get(
            f"{graph_base}/me/accounts",
            params={
                "fields": "id,name,access_token,tasks,instagram_business_account",
                "access_token": new_user_token,
            },
            timeout=30,
        )
        if not pages.ok:
            return False, {
                "ok": False,
                "error": "me_accounts_failed",
                "status_code": pages.status_code,
                "response": pages.text[:1000],
            }

        rows = (pages.json() or {}).get("data") or []
        page = next((r for r in rows if str(r.get("id", "")).strip() == page_id), None)
        if not page:
            return False, {
                "ok": False,
                "error": "page_not_found",
                "page_id": page_id,
                "managed_pages": [
                    {"id": str(r.get("id", "")), "name": str(r.get("name", ""))}
                    for r in rows
                ],
            }

        new_page_token = str(page.get("access_token", "")).strip()
        if not new_page_token:
            return False, {
                "ok": False,
                "error": "page_token_missing",
                "page_id": page_id,
            }

        resolved_ig_id = ""
        ig_from_page = (page.get("instagram_business_account") or {}).get("id")
        if ig_from_page:
            resolved_ig_id = str(ig_from_page).strip()
        elif os.environ.get("META_IG_USER_ID", "").strip():
            resolved_ig_id = str(os.environ.get("META_IG_USER_ID", "")).strip()

        now_utc = datetime.now(timezone.utc)
        expires_at = ""
        if expires_in > 0:
            expires_at = (now_utc + timedelta(seconds=expires_in)).isoformat()

        os.environ["META_LONG_LIVED_USER_TOKEN"] = new_user_token
        os.environ["META_PAGE_ACCESS_TOKEN"] = new_page_token
        os.environ["META_PAGE_ID"] = page_id
        os.environ["META_TOKEN_UPDATED_AT_UTC"] = now_utc.isoformat()
        if expires_at:
            os.environ["META_TOKEN_EXPIRES_AT_UTC"] = expires_at
        if resolved_ig_id:
            os.environ["META_IG_USER_ID"] = resolved_ig_id

        state_payload = {
            "META_PAGE_ID": page_id,
            "META_IG_USER_ID": resolved_ig_id,
            "META_LONG_LIVED_USER_TOKEN": new_user_token,
            "META_PAGE_ACCESS_TOKEN": new_page_token,
            "META_TOKEN_UPDATED_AT_UTC": now_utc.isoformat(),
            "META_TOKEN_EXPIRES_AT_UTC": expires_at,
            "meta_graph_version": graph_version,
            "updated_at_utc": now_utc.isoformat(),
            "long_user_token_masked": _mask_token(new_user_token),
            "page_token_masked": _mask_token(new_page_token),
        }
        _safe_write_json(_meta_state_path(), state_payload)

        return True, {
            "ok": True,
            "page_id": page_id,
            "ig_user_id": resolved_ig_id,
            "expires_in": expires_in,
            "expires_at_utc": expires_at,
            "updated_at_utc": now_utc.isoformat(),
            "state_file": _meta_state_path(),
            "long_user_token": _mask_token(new_user_token),
            "page_token": _mask_token(new_page_token),
        }
    except Exception as e:
        return False, {
            "ok": False,
            "error": "exception",
            "detail": str(e),
        }


def _auto_refresh_meta_if_due() -> tuple[bool, str]:
    enabled = str(os.environ.get("META_AUTO_REFRESH_ENABLED", "true")).strip().lower()
    if enabled in ("0", "false", "no"):
        return False, "auto_refresh_disabled"

    force_every_run = str(os.environ.get("META_REFRESH_EVERY_RUN", "false")).strip().lower()
    if force_every_run in ("1", "true", "yes"):
        ok, payload = _refresh_meta_tokens()
        return ok, payload.get("error", "refresh_failed") if not ok else "refreshed_force_every_run"

    threshold_hours = int(str(os.environ.get("META_REFRESH_THRESHOLD_HOURS", "72") or "72"))
    expires_raw = str(os.environ.get("META_TOKEN_EXPIRES_AT_UTC", "")).strip()
    if not expires_raw:
        ok, payload = _refresh_meta_tokens()
        return ok, payload.get("error", "refreshed_without_known_expiry") if not ok else "refreshed"

    try:
        expiry = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        if expiry - now_utc > timedelta(hours=threshold_hours):
            return False, "not_due"
    except Exception:
        ok, payload = _refresh_meta_tokens()
        return ok, payload.get("error", "refreshed_on_invalid_expiry") if not ok else "refreshed"

    ok, payload = _refresh_meta_tokens()
    return ok, payload.get("error", "refresh_failed") if not ok else "refreshed"


def _load_history(limit: int = 20) -> list[dict]:
    history_path = os.path.join(_data_dir(), "post_history.json")
    history = _load_json(history_path, {"posts": []})
    posts = history.get("posts", []) if isinstance(history, dict) else []
    if not isinstance(posts, list):
        return []
    return posts[-limit:]


def _latest_file(pattern: str) -> str:
    paths = glob.glob(pattern)
    if not paths:
        return ""
    return max(paths, key=os.path.getmtime)


def _load_latest_campaign_plan() -> dict:
    paths = []
    for base in (_data_dir(), os.path.join(os.path.dirname(__file__), "data")):
        paths.extend(glob.glob(os.path.join(base, "marketing", "campaign_plan_*.json")))
    latest = max(paths, key=os.path.getmtime) if paths else ""
    if not latest:
        return {}
    data = _load_json(latest, {})
    if isinstance(data, dict):
        data["_artifact"] = latest
    return data if isinstance(data, dict) else {}


def _load_latest_structured_campaign() -> dict:
    paths = []
    for base in (_data_dir(), os.path.join(os.path.dirname(__file__), "data")):
        paths.extend(glob.glob(os.path.join(base, "marketing", "campaigns", "campaign_*.json")))
    latest = max(paths, key=os.path.getmtime) if paths else ""
    if not latest:
        return {}
    data = _load_json(latest, {})
    if isinstance(data, dict):
        data["_artifact"] = latest
    return data if isinstance(data, dict) else {}


def _quality_summary(posts: list[dict]) -> dict:
    scores = [p.get("quality_score") for p in posts if isinstance(p.get("quality_score"), (int, float))]
    avg = round(sum(scores) / len(scores), 2) if scores else None
    warning_count = sum(len(p.get("quality_warnings", []) or []) for p in posts if isinstance(p, dict))
    return {
        "samples": len(scores),
        "average_quality_score": avg,
        "quality_warning_count": warning_count,
    }


def _quality_report(posts: list[dict]) -> dict:
    scores = [float(p.get("quality_score")) for p in posts if isinstance(p.get("quality_score"), (int, float))]
    rejected = [p for p in posts if isinstance(p, dict) and str(p.get("status", "")).startswith("skipped_")]

    reason_counts: dict[str, int] = {}
    platform_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}

    for p in posts:
        if not isinstance(p, dict):
            continue
        stage = str(p.get("funnel_stage", "")).strip().upper()
        if stage:
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        for platform_record in p.get("platform_records", []) or []:
            if not isinstance(platform_record, dict):
                continue
            platform = str(platform_record.get("platform", "")).strip().lower()
            if platform:
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
            err = str(platform_record.get("error") or "").strip()
            if err:
                reason_counts[err] = reason_counts.get(err, 0) + 1

        for r in p.get("duplicate_reasons", []) or []:
            key = str(r).strip()
            if key:
                reason_counts[key] = reason_counts.get(key, 0) + 1

        for r in p.get("validation_errors", []) or []:
            key = str(r).strip()
            if key:
                reason_counts[key] = reason_counts.get(key, 0) + 1

    recurring = sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "sample_size": len(posts),
        "scores": {
            "count": len(scores),
            "average": round(sum(scores) / len(scores), 2) if scores else None,
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
        },
        "rejected_posts": [
            {
                "post_id": p.get("post_id"),
                "date": p.get("date"),
                "slot": p.get("slot"),
                "status": p.get("status"),
                "duplicate_reasons": p.get("duplicate_reasons", []),
                "validation_errors": p.get("validation_errors", []),
            }
            for p in rejected[-50:]
        ],
        "rejection_reasons": [{"reason": k, "count": v} for k, v in recurring[:30]],
        "recurring_generation_problems": [{"problem": k, "count": v} for k, v in recurring[:15]],
        "platform_distribution": platform_counts,
        "funnel_stage_distribution": stage_counts,
    }


def _parse_preview_params(params: dict) -> dict:
    platform = str(params.get("platform", [""])[0]).strip().lower()
    slot = str(params.get("slot", ["morning"])[0]).strip().lower()
    funnel_stage = str(params.get("funnel_stage", [""])[0]).strip().upper()
    product_id = str(params.get("product_id", [""])[0]).strip()
    pipeline = str(params.get("pipeline", [""])[0]).strip().lower()
    no_product = str(params.get("no_product", ["false"])[0]).strip().lower() in ("1", "true", "yes")
    if slot not in ("morning", "midday", "evening"):
        slot = "morning"
    if platform and platform not in ("facebook", "instagram", "linkedin", "wordpress"):
        platform = ""
    if funnel_stage and funnel_stage not in ("ATTENTION", "EDUCATION", "DESIRE", "TRUST", "CONVERSION"):
        funnel_stage = ""
    if pipeline not in ("legacy", "orchestrator", "best_of", "both"):
        pipeline = ""
    return {
        "platform": platform,
        "slot": slot,
        "funnel_stage": funnel_stage,
        "product_id": product_id,
        "pipeline": pipeline,
        "no_product": no_product,
    }


def _content_preview(preview_params: dict) -> dict:
    previous_text_only = os.environ.get("POST_TEXT_ONLY")
    previous_bucket_override = os.environ.get("CONTENT_BUCKET_OVERRIDE")
    os.environ["POST_TEXT_ONLY"] = "true"
    if preview_params.get("no_product"):
        os.environ["CONTENT_BUCKET_OVERRIDE"] = "no_product"
    try:
        content = generate_posts.generate(
            preview_params["slot"],
            funnel_stage_override=str(preview_params.get("funnel_stage", "")),
            product_id_override=str(preview_params.get("product_id", "")),
            pipeline_override=str(preview_params.get("pipeline", "")),
        )
    finally:
        if previous_text_only is None:
            os.environ.pop("POST_TEXT_ONLY", None)
        else:
            os.environ["POST_TEXT_ONLY"] = previous_text_only
        if previous_bucket_override is None:
            os.environ.pop("CONTENT_BUCKET_OVERRIDE", None)
        else:
            os.environ["CONTENT_BUCKET_OVERRIDE"] = previous_bucket_override
    platform = preview_params.get("platform", "")
    requested_stage = preview_params.get("funnel_stage", "")
    requested_product_id = preview_params.get("product_id", "")
    notes: list[str] = []

    if requested_stage:
        if str(content.get("funnel_stage", "")).upper() == requested_stage:
            notes.append("funnel_stage_override_applied")
        else:
            notes.append("funnel_stage_override_not_applied")

    if requested_product_id:
        matched = str(content.get("product_id", "")) == requested_product_id
        notes.append("requested_product_matched" if matched else "requested_product_not_matched")

    if platform:
        platform_posts = content.get("platform_posts", {})
        if isinstance(platform_posts, dict):
            selected = platform_posts.get(platform)
            content["platform_posts"] = {platform: selected} if isinstance(selected, dict) else {}

    content["preview_only"] = True
    content["preview_filters"] = preview_params
    content["preview_notes"] = notes
    return content


def _schedule_preview(days: int = 7) -> list[dict]:
    history = _load_json(os.path.join(_data_dir(), "post_history.json"), {"posts": []})
    schedule = load_channel_schedule()
    funnel_config = load_funnel_config()
    now = datetime.now(timezone.utc)
    out: list[dict] = []

    for offset in range(days):
        when = now + timedelta(days=offset)
        day_entry = {
            "date": when.date().isoformat(),
            "weekday": when.strftime("%A").lower(),
            "slots": {},
        }
        for slot in ("morning", "midday", "evening"):
            stage = stage_for_slot(slot, history=history, funnel_config=funnel_config, schedule=schedule, now_utc=when)
            eligibility = eligible_channels_for_slot(
                slot=slot,
                funnel_stage=stage,
                schedule=schedule,
                now_utc=when,
                manual_platforms=[],
            )
            day_entry["slots"][slot] = {
                "funnel_stage": stage,
                "eligible_channels": {
                    name: {"eligible": bool(values[0]), "reason": str(values[1])}
                    for name, values in eligibility.items()
                },
            }
        out.append(day_entry)
    return out


def _authorized(params: dict) -> tuple[bool, int, dict]:
    token = os.environ.get("MANUAL_RUN_TOKEN", "")
    provided = str(params.get("token", [""])[0])
    if not token:
        return False, 403, {"error": "MANUAL_RUN_TOKEN not configured"}
    if not hmac.compare_digest(provided, token):
        return False, 401, {"error": "invalid token"}
    return True, 200, {}


def _uptime_seconds() -> int:
    return int((datetime.now(timezone.utc) - STARTED_AT).total_seconds())


def _last_run_outcome() -> dict:
    return _load_json(os.path.join(_data_dir(), "social", "last_run_outcome.json"), {})


def _candidate_pool_depth() -> int:
    payload = _load_json(os.path.join(_data_dir(), "social", "candidate_pool.json"), {})
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    return sum(1 for candidate in candidates if isinstance(candidate, dict) and candidate.get("status") == "available")


def _operational_intelligence_snapshot() -> dict:
    """Expose only operational facts with a local source; never infer provider budgets."""
    try:
        from social.living_intelligence import operational_status
        living = operational_status(_data_dir())
        state = _load_json(os.path.join(_data_dir(), "social", "living_intelligence.json"), {})
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__}
    target_depth = int(os.environ.get("CANDIDATE_POOL_TARGET_DEPTH", "6"))
    token_expiry = str(os.environ.get("META_TOKEN_EXPIRES_AT_UTC", "") or os.environ.get("META_TOKEN_EXPIRES_AT", "")).strip()
    token_status = {"status": "UNAVAILABLE", "value": None}
    if token_expiry:
        try:
            expiry = datetime.fromisoformat(token_expiry.replace("Z", "+00:00"))
            expiry = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
            days_remaining = (expiry - datetime.now(timezone.utc)).total_seconds() / 86400
            token_status = {
                "status": "EXPIRED" if days_remaining < 0 else "WARNING_RENEW_WITHIN_7_DAYS" if days_remaining <= 7 else "HEALTHY",
                "value": token_expiry,
                "days_remaining": round(days_remaining, 2),
            }
        except ValueError:
            token_status = {"status": "INVALID_TIMESTAMP", "value": token_expiry}
    return {
        "status": "READY",
        "pool": {"available": _candidate_pool_depth(), "target": target_depth, "refill_needed": _candidate_pool_depth() < target_depth},
        "seasonal_lookahead": state.get("seasonal_lookahead", []),
        "visual_novelty": state.get("visual_novelty", {}),
        "exploration": state.get("exploration", {}),
        "token_expiry": token_status,
        "gemini": {"configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()), "budget_status": "UNAVAILABLE_NO_SUPPORTED_BILLING_SOURCE"},
        "living": living,
    }


def _env_is_true(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _production_readiness_snapshot() -> dict:
    data_dir = _data_dir()
    init_content_operations(data_dir)
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    channel_flags = run_engine.get_channel_config()
    publisher_configuration = {
        "facebook": bool(os.environ.get("META_PAGE_ID", "").strip() and os.environ.get("META_PAGE_ACCESS_TOKEN", "").strip()),
        "instagram": bool(os.environ.get("META_IG_USER_ID", "").strip() and os.environ.get("META_PAGE_ACCESS_TOKEN", "").strip()),
        "linkedin": bool(os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()),
    }
    overrides = {
        name: str(os.environ.get(name, "")).strip()
        for name in (
            "POST_PLATFORMS",
            "POST_PRODUCT_ID_OVERRIDE",
            "POST_FUNNEL_STAGE_OVERRIDE",
            "POST_PIPELINE_OVERRIDE",
            "MANUAL_DUPLICATE_MODE",
            "CHANNEL_READINESS_BLOCK_ON_RED",
            "SKIP_RECENT_SUCCESS_HOURS",
        )
    }
    return {
        "time_utc": _utc_now(),
        "global": {
            "dry_run": str(os.environ.get("SOCIAL_DRY_RUN", "true")).lower() == "true",
            "shadow_mode": _env_is_true("SOCIAL_SHADOW_MODE", False),
            "run_lock_active": RUN_LOCK.locked(),
            "scheduler_jobs_registered": len(schedule.jobs),
        },
        "channels": channel_flags,
        "platform_configuration_present": publisher_configuration,
        "linkedin_target_configuration": {
            "explicit_target_present": bool(os.environ.get("LINKEDIN_ORGANIZATION_URN", "").strip() or os.environ.get("LINKEDIN_AUTHOR_URN", "").strip()),
            "automatic_resolution_available": bool(os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()),
        },
        "gemini": {
            "api_key_present": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
            "text_model": str(os.environ.get("GEMINI_MODEL", "")).strip() or "provider_default",
            "image_model": str(os.environ.get("GEMINI_IMAGE_MODEL", "")).strip() or "gemini-2.5-flash-image",
        },
        "data": {
            "path": data_dir,
            "exists": os.path.isdir(data_dir),
            "writable": os.access(data_dir, os.W_OK),
            "history_present": os.path.isfile(os.path.join(data_dir, "post_history.json")),
            "receipts_present": os.path.isfile(os.path.join(data_dir, "social", "publish_receipts.json")),
        },
        "content_supply": {
            "today": daily_status(data_dir, today),
            "tomorrow": daily_status(data_dir, tomorrow),
        },
        "intelligence_packages": intelligence_packages.package_coverage(data_dir),
        "operations_readiness": operations_readiness(
            data_dir,
            lead_hours=int(os.environ.get("CONTENT_READINESS_LEAD_HOURS", "2")),
            publisher_ready={platform: channel_flags.get(platform, False) and publisher_configuration[platform] for platform in publisher_configuration},
            dispatcher_active=any(
                getattr(job.job_func, "func", None) is _start_dispatch_thread
                for job in schedule.jobs
            ),
        ),
        "overrides": overrides,
    }


def _run_script(script_name: str) -> tuple[bool, str]:
    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
    script_path = os.path.join(scripts_dir, script_name)
    try:
        runtime_data_dir = _data_dir()
        runtime_marketing_dir = os.path.join(runtime_data_dir, "marketing")
        env = os.environ.copy()
        env.setdefault("DATA_DIR", runtime_data_dir)
        env.setdefault("MARKETING_OUTPUT_DIR", runtime_marketing_dir)
        completed = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.dirname(__file__),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode == 0:
            return True, output[-3000:]
        return False, output[-3000:]
    except Exception as e:
        return False, str(e)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auto_bootstrap_visual_repo() -> dict:
    global VISUAL_REPO_BOOTSTRAP
    try:
        summary = inventory_db.bootstrap_visual_repo_from_env(_data_dir())
        VISUAL_REPO_BOOTSTRAP = {
            "status": "ok",
            "time_utc": _utc_now(),
            "summary": summary,
            "error": None,
        }
    except Exception as e:
        VISUAL_REPO_BOOTSTRAP = {
            "status": "error",
            "time_utc": _utc_now(),
            "summary": {},
            "error": str(e),
        }
    return VISUAL_REPO_BOOTSTRAP


def _start_slot_thread(
    slot: str,
    force_live: bool = False,
    force_dry_run: bool = False,
    shadow_mode: bool = False,
    platforms_override: str = "",
    duplicate_mode: str = "",
    readiness_block_override: str = "",
    product_id_override: str = "",
    no_product: bool = False,
    funnel_stage_override: str = "",
    pipeline_override: str = "",
) -> bool:
    if RUN_LOCK.locked():
        return False

    thread = threading.Thread(
        target=run_slot,
        kwargs={
            "slot": slot,
            "force_live": force_live,
            "force_dry_run": force_dry_run,
            "shadow_mode": shadow_mode,
            "platforms_override": platforms_override,
            "duplicate_mode": duplicate_mode,
            "readiness_block_override": readiness_block_override,
            "product_id_override": product_id_override,
            "no_product": no_product,
            "funnel_stage_override": funnel_stage_override,
            "pipeline_override": pipeline_override,
        },
        daemon=True,
    )
    thread.start()
    return True


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/media/"):
            file_name = os.path.basename(parsed.path[len("/media/"):]).strip()
            if not file_name:
                body = b'{"error":"missing media file"}'
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            media_path = os.path.join(_data_dir(), "public_media", file_name)
            if not os.path.exists(media_path) or not os.path.isfile(media_path):
                body = b'{"error":"media not found"}'
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            with open(media_path, "rb") as f:
                payload = f.read()
            mime, _ = mimetypes.guess_type(media_path)
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path in ("/", "/health", "/healthz"):
            payload = {
                "status": "ok",
                "service": "infenergy-social-engine",
                "time_utc": _utc_now(),
                "uptime_seconds": _uptime_seconds(),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/status":
            recent_posts = _load_history(limit=10)
            payload = {
                "status": "ok",
                "service": "infenergy-social-engine",
                "time_utc": _utc_now(),
                "uptime_seconds": _uptime_seconds(),
                "last_run": LAST_RUN,
                "candidate_pool_depth": _candidate_pool_depth(),
                "dry_run": os.environ.get("SOCIAL_DRY_RUN", "true"),
                "shadow_mode": os.environ.get("SOCIAL_SHADOW_MODE", "false"),
                "recent_quality": _quality_summary(recent_posts),
                "visual_repo_bootstrap": VISUAL_REPO_BOOTSTRAP,
                "operational_intelligence": _operational_intelligence_snapshot(),
                "production_readiness": _production_readiness_snapshot(),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path in ("/content-operations/status", "/content-operations/detail", "/content-operations/daily"):
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path.endswith("/daily"):
                requested_date = str(params.get("date", [""])[0]).strip() or None
                body = daily_markdown(_data_dir(), requested_date).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path.endswith("/detail"):
                decision_id = str(params.get("decision_id", [""])[0]).strip()
                payload = content_detail(_data_dir(), decision_id) if decision_id else {"error": "decision_id_required"}
                response_code = 200 if payload and "error" not in payload else 400
            else:
                requested_date = str(params.get("date", [""])[0]).strip() or None
                payload = daily_index(_data_dir(), requested_date)
                response_code = 200
            body = json.dumps(payload, ensure_ascii=True, default=str).encode("utf-8")
            self.send_response(response_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/gemini-visual-repo-bootstrap":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            bootstrap = _auto_bootstrap_visual_repo()
            payload = {
                "status": "ok" if bootstrap.get("status") == "ok" else "error",
                "time_utc": _utc_now(),
                "bootstrap": bootstrap,
                "repo": inventory_db.fetch_gemini_style_references(_data_dir(), active_only=False, limit=500),
                "settings": inventory_db.fetch_visual_generation_settings(_data_dir()),
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if bootstrap.get("status") == "ok" else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/agents/list":
            from agents.dispatcher import available_agents  # local import to avoid startup cost

            body = json.dumps({"status": "ok", "agents": available_agents()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/agents/conference":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            from business_intelligence import api as bi_api

            result = bi_api.run_agent_conference()
            body = json.dumps(result, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/agents/run":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            from agents.dispatcher import run_agent

            name = str(params.get("name", [""])[0]).strip()
            if not name:
                body = json.dumps({"error": "missing_name"}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            result = run_agent(name, _data_dir(), params)
            code = 400 if isinstance(result, dict) and "error" in result else 200
            body = json.dumps(result, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/history":
            params = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit", ["20"])[0])
            except (TypeError, ValueError):
                limit = 20
            limit = max(1, min(200, limit))
            posts = _load_history(limit=limit)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "count": len(posts),
                "posts": posts,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/campaign":
            plan = _load_latest_campaign_plan()
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "campaign": plan,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/campaign-current":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            campaign = _load_latest_structured_campaign()
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "campaign": campaign,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/content-preview":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            preview_params = _parse_preview_params(params)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "preview": _content_preview(preview_params),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/schedule-preview":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "days": _schedule_preview(days=7),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/production-readiness":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = json.dumps({"status": "ok", "readiness": _production_readiness_snapshot()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/quality-report":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            limit = int(params.get("limit", ["200"])[0])
            limit = max(10, min(500, limit))
            posts = _load_history(limit=limit)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "report": _quality_report(posts),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/inventory-db":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            sync_result = generate_posts.sync_inventory_database(force=False)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "sync": sync_result,
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
                "brand_profile": generate_posts.load_brand_profile(),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/inventory-sync":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            force = str(params.get("force", ["false"])[0]).strip().lower() in ("1", "true", "yes", "on")
            sync_result = generate_posts.sync_inventory_database(force=force)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "force": force,
                "sync": sync_result,
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/brand-profile-apply":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            result = generate_posts.apply_conference_brand_profile()
            payload = {
                "status": "ok" if result.get("ok") else "error",
                "time_utc": _utc_now(),
                "applied": bool(result.get("ok")),
                "brand_profile": result.get("brand_profile", {}),
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if result.get("ok") else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/selling-ideology":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "selling_ideology": generate_posts.load_selling_ideology(),
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/selling-ideology-apply":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            result = generate_posts.apply_conference_selling_ideology()
            payload = {
                "status": "ok" if result.get("ok") else "error",
                "time_utc": _utc_now(),
                "applied": bool(result.get("ok")),
                "selling_ideology": result.get("selling_ideology", {}),
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if result.get("ok") else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/gemini-visual-repo":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            refs = inventory_db.fetch_gemini_style_references(_data_dir(), active_only=False, limit=500)
            settings = inventory_db.fetch_visual_generation_settings(_data_dir())
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "repo": refs,
                "settings": settings,
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/gemini-visual-repo-seed":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            seeded = inventory_db.seed_gemini_style_idea_repo(_data_dir())
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "seed": seeded,
                "repo": inventory_db.fetch_gemini_style_references(_data_dir(), active_only=False, limit=500),
                "settings": inventory_db.fetch_visual_generation_settings(_data_dir()),
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/gemini-visual-repo-apply":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            refs_json_raw = str(params.get("refs_json", [""])[0] or "").strip()
            active_style_keys_csv = str(params.get("active_style_keys", [""])[0] or "").strip()
            override_url = str(params.get("override_url", [""])[0] or "").strip()

            refs_payload = []
            if refs_json_raw:
                try:
                    parsed_refs = json.loads(refs_json_raw)
                    if isinstance(parsed_refs, list):
                        refs_payload = parsed_refs
                except Exception:
                    refs_payload = []

            upserted = inventory_db.upsert_gemini_style_references(_data_dir(), refs_payload) if refs_payload else 0
            active_style_keys = [k.strip() for k in active_style_keys_csv.split(",") if k.strip()]

            existing_settings = inventory_db.fetch_visual_generation_settings(_data_dir())
            inventory_db.upsert_visual_generation_settings(
                _data_dir(),
                {
                    "active_style_keys": active_style_keys or existing_settings.get("active_style_keys", []),
                    "visual_product_image_override_url": override_url or str(existing_settings.get("visual_product_image_override_url", "")),
                },
            )

            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "upserted": upserted,
                "repo": inventory_db.fetch_gemini_style_references(_data_dir(), active_only=False, limit=500),
                "settings": inventory_db.fetch_visual_generation_settings(_data_dir()),
                "snapshot": inventory_db.get_inventory_snapshot(_data_dir()),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/run-marketing":
            token = os.environ.get("MANUAL_RUN_TOKEN", "")
            params = parse_qs(parsed.query)
            provided = params.get("token", [""])[0]
            if not token:
                body = b'{"error":"MANUAL_RUN_TOKEN not configured"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if provided != token:
                body = b'{"error":"invalid token"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            ok, output = _run_script("run_marketing_team.py")
            payload = {
                "ok": ok,
                "message": "marketing team run complete" if ok else "marketing team run failed",
                "time_utc": _utc_now(),
                "output_tail": output,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/run-weekly":
            token = os.environ.get("MANUAL_RUN_TOKEN", "")
            params = parse_qs(parsed.query)
            provided = params.get("token", [""])[0]
            if not token:
                body = b'{"error":"MANUAL_RUN_TOKEN not configured"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if provided != token:
                body = b'{"error":"invalid token"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            ok, output = _run_script("run_marketing_weekly.py")
            campaign_ok, campaign_output = _run_script("build_campaign_plan.py")
            current_campaign = _load_latest_structured_campaign()
            overall_ok = bool(ok and campaign_ok)
            payload = {
                "ok": overall_ok,
                "message": "weekly planner run complete" if overall_ok else "weekly planner run failed",
                "time_utc": _utc_now(),
                "output_tail": output,
                "campaign_build_ok": campaign_ok,
                "campaign_output_tail": campaign_output,
                "campaign_current": current_campaign,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if overall_ok else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/run-now":
            token = os.environ.get("MANUAL_RUN_TOKEN", "")
            params = parse_qs(parsed.query)
            provided = params.get("token", [""])[0]
            slot = params.get("slot", ["morning"])[0]
            force_live = params.get("live", ["false"])[0].lower() in ("1", "true", "yes")
            force_dry_run = params.get("dry_run", ["false"])[0].lower() in ("1", "true", "yes")
            shadow_mode = params.get("shadow", ["false"])[0].lower() in ("1", "true", "yes")
            platforms_override = params.get("platforms", [""])[0]
            duplicate_mode = params.get("duplicate_mode", [""])[0].strip().lower()
            readiness_block_override = params.get("readiness_block", [""])[0].strip().lower()
            product_id_override = params.get("product_id", [""])[0].strip()
            no_product = params.get("no_product", ["false"])[0].strip().lower() in ("1", "true", "yes")
            funnel_stage_override = params.get("funnel_stage", [""])[0].strip().upper()
            pipeline_override = params.get("pipeline", [""])[0].strip().lower()
            if duplicate_mode and duplicate_mode not in ("strict", "exact_only", "allow_all"):
                duplicate_mode = ""
            if readiness_block_override and readiness_block_override not in ("true", "false", "1", "0", "yes", "no"):
                readiness_block_override = ""
            if funnel_stage_override and funnel_stage_override not in ("ATTENTION", "EDUCATION", "TRUST", "DESIRE", "CONVERSION"):
                funnel_stage_override = ""
            if pipeline_override in ("both", "combined", "compare"):
                pipeline_override = "best_of"
            if pipeline_override and pipeline_override not in ("legacy", "orchestrator", "best_of"):
                pipeline_override = ""
            if slot not in ("morning", "midday", "evening"):
                slot = "morning"

            if not token:
                body = b'{"error":"MANUAL_RUN_TOKEN not configured"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if provided != token:
                body = b'{"error":"invalid token"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            started = _start_slot_thread(
                slot,
                force_live=force_live,
                force_dry_run=force_dry_run,
                platforms_override=platforms_override,
                duplicate_mode=duplicate_mode,
                readiness_block_override=readiness_block_override,
                product_id_override=product_id_override,
                no_product=no_product,
                funnel_stage_override=funnel_stage_override,
                pipeline_override=pipeline_override,
                shadow_mode=shadow_mode,
            )
            payload = {
                "accepted": started,
                "slot": slot,
                "force_live": force_live,
                "force_dry_run": force_dry_run,
                "shadow_mode": shadow_mode,
                "platforms": platforms_override,
                "duplicate_mode": duplicate_mode or "env_default",
                "readiness_block": readiness_block_override or "env_default",
                "product_id": product_id_override or "auto",
                "no_product": no_product,
                "funnel_stage": funnel_stage_override or "auto",
                "pipeline": pipeline_override or "env_default",
                "message": "run started" if started else "run already in progress",
                "time_utc": _utc_now(),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(202 if started else 409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/delete-post":
            token = os.environ.get("MANUAL_RUN_TOKEN", "")
            params = parse_qs(parsed.query)
            provided = params.get("token", [""])[0]
            platform = params.get("platform", [""])[0].strip().lower()
            post_id = params.get("post_id", [""])[0].strip()

            if not token:
                body = b'{"error":"MANUAL_RUN_TOKEN not configured"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if provided != token:
                body = b'{"error":"invalid token"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if platform not in ("facebook", "instagram", "linkedin") or not post_id:
                body = b'{"error":"platform must be facebook|instagram|linkedin and post_id is required"}'
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            payload = {"platform": platform, "post_id": post_id, "time_utc": _utc_now()}
            try:
                if platform == "facebook":
                    import publish_facebook
                    result = publish_facebook.delete(post_id)
                elif platform == "instagram":
                    import publish_instagram
                    result = publish_instagram.delete(post_id)
                else:
                    import publish_linkedin
                    result = publish_linkedin.delete(post_id)
                payload["success"] = True
                payload["result"] = result
                status = 200
            except Exception as e:
                payload["success"] = False
                payload["error"] = str(e)
                status = 502

            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/refresh-meta":
            params = parse_qs(parsed.query)
            provided = str(params.get("token", [""])[0]).strip()
            secret = _meta_refresh_secret()

            if not secret:
                payload = {"error": "META_REFRESH_TOKEN or MANUAL_RUN_TOKEN not configured"}
                body = json.dumps(payload).encode("utf-8")
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if provided != secret:
                payload = {"error": "invalid token"}
                body = json.dumps(payload).encode("utf-8")
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            ok, payload = _refresh_meta_tokens()
            payload["time_utc"] = _utc_now()
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Health endpoint listening on 0.0.0.0:{port}")


def run_slot(
    slot: str,
    force_live: bool = False,
    force_dry_run: bool = False,
    shadow_mode: bool = False,
    platforms_override: str = "",
    duplicate_mode: str = "",
    readiness_block_override: str = "",
    product_id_override: str = "",
    no_product: bool = False,
    funnel_stage_override: str = "",
    pipeline_override: str = "",
) -> None:
    with RUN_LOCK:
        LAST_RUN["status"] = "running"
        LAST_RUN["slot"] = slot
        LAST_RUN["started_at_utc"] = _utc_now()
        LAST_RUN["finished_at_utc"] = None
        LAST_RUN["error"] = None

        print(f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] Starting {slot} run...")
        # A scheduled slot convenes an informed decision before generation; the
        # heartbeat itself never publishes or generates copy.
        try:
            from social.living_intelligence import heartbeat
            heartbeat(_data_dir(), level="LIGHT_HEARTBEAT", website_url=os.environ.get("FIRST_PARTY_SITE_URL", ""))
        except Exception as exc:
            print(f"[INTELLIGENCE] heartbeat unavailable: {exc}")
        previous_dry_run = os.environ.get("SOCIAL_DRY_RUN", "true")
        previous_platforms = os.environ.get("POST_PLATFORMS", "")
        previous_duplicate_mode = os.environ.get("MANUAL_DUPLICATE_MODE", "")
        previous_readiness_block = os.environ.get("CHANNEL_READINESS_BLOCK_ON_RED", "")
        previous_product_override = os.environ.get("POST_PRODUCT_ID_OVERRIDE", "")
        previous_bucket_override = os.environ.get("CONTENT_BUCKET_OVERRIDE", "")
        previous_funnel_stage_override = os.environ.get("POST_FUNNEL_STAGE_OVERRIDE", "")
        previous_pipeline_override = os.environ.get("POST_PIPELINE_OVERRIDE", "")
        previous_shadow_mode = os.environ.get("SOCIAL_SHADOW_MODE", "")
        previous_pool_runtime = os.environ.get("CANDIDATE_POOL_RUNTIME_ENABLED", "")
        os.environ["POST_SLOT"] = slot
        os.environ["POST_PLATFORMS"] = platforms_override
        os.environ["CANDIDATE_POOL_RUNTIME_ENABLED"] = "false"
        if duplicate_mode:
            os.environ["MANUAL_DUPLICATE_MODE"] = duplicate_mode
        if readiness_block_override:
            os.environ["CHANNEL_READINESS_BLOCK_ON_RED"] = "true" if readiness_block_override in ("1", "true", "yes") else "false"
        if product_id_override:
            os.environ["POST_PRODUCT_ID_OVERRIDE"] = product_id_override
        if no_product:
            os.environ["CONTENT_BUCKET_OVERRIDE"] = "no_product"
        if funnel_stage_override:
            os.environ["POST_FUNNEL_STAGE_OVERRIDE"] = funnel_stage_override
        if pipeline_override:
            os.environ["POST_PIPELINE_OVERRIDE"] = pipeline_override
        if force_live:
            os.environ["SOCIAL_DRY_RUN"] = "false"
        elif force_dry_run:
            os.environ["SOCIAL_DRY_RUN"] = "true"
        if shadow_mode:
            os.environ["SOCIAL_SHADOW_MODE"] = "true"

        _auto_bootstrap_visual_repo()

        refresh_ok, refresh_reason = _auto_refresh_meta_if_due()
        if refresh_ok:
            print("[META] Token refresh completed before run")
        elif refresh_reason not in ("not_due", "auto_refresh_disabled"):
            print(f"[META] Token refresh skipped/failed: {refresh_reason}")
        try:
            timeout_sec = int(os.environ.get("RUN_SLOT_TIMEOUT_SEC", "900"))
            scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
            run_engine_path = os.path.join(scripts_dir, "run_engine.py")
            env = os.environ.copy()

            completed = subprocess.run(
                [sys.executable, run_engine_path],
                cwd=os.path.dirname(__file__),
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_sec,
                check=False,
            )

            output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
            if output:
                print(output[-4000:])

            if completed.returncode != 0:
                outcome = _last_run_outcome()
                if outcome.get("slot") == slot and outcome.get("status") == "published":
                    LAST_RUN["status"] = "published"
                    LAST_RUN["error"] = f"partial_platform_failure: {output[-1500:]}"
                    return
                raise RuntimeError(f"run_engine exit={completed.returncode} output_tail={output[-1500:]}")

            outcome = _last_run_outcome()
            if outcome.get("slot") == slot and outcome.get("status") in {"published", "blocked_no_publish", "skipped_no_eligible_platforms"}:
                LAST_RUN["status"] = outcome["status"]
                LAST_RUN["error"] = str(outcome.get("detail") or "") or None
            else:
                LAST_RUN["status"] = "generation_failed"
                LAST_RUN["error"] = "run_engine_completed_without_outcome"
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else str(e.stdout or "")
            stderr = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else str(e.stderr or "")
            partial = f"{stdout}\n{stderr}".strip()
            LAST_RUN["status"] = "generation_failed"
            LAST_RUN["error"] = f"run_timeout_after_{timeout_sec}s"
            if partial:
                print(partial[-4000:])
            print(f"[ERROR] {slot} run timed out after {timeout_sec}s")
        except BaseException as e:
            LAST_RUN["status"] = "generation_failed"
            LAST_RUN["error"] = str(e)
            print(f"[ERROR] {slot} run failed: {e}")
            traceback.print_exc()
        finally:
            os.environ["SOCIAL_DRY_RUN"] = previous_dry_run
            os.environ["POST_PLATFORMS"] = previous_platforms
            if previous_duplicate_mode:
                os.environ["MANUAL_DUPLICATE_MODE"] = previous_duplicate_mode
            elif "MANUAL_DUPLICATE_MODE" in os.environ:
                del os.environ["MANUAL_DUPLICATE_MODE"]
            if previous_readiness_block:
                os.environ["CHANNEL_READINESS_BLOCK_ON_RED"] = previous_readiness_block
            elif "CHANNEL_READINESS_BLOCK_ON_RED" in os.environ:
                del os.environ["CHANNEL_READINESS_BLOCK_ON_RED"]
            if previous_product_override:
                os.environ["POST_PRODUCT_ID_OVERRIDE"] = previous_product_override
            elif "POST_PRODUCT_ID_OVERRIDE" in os.environ:
                del os.environ["POST_PRODUCT_ID_OVERRIDE"]
            if previous_bucket_override:
                os.environ["CONTENT_BUCKET_OVERRIDE"] = previous_bucket_override
            elif "CONTENT_BUCKET_OVERRIDE" in os.environ:
                del os.environ["CONTENT_BUCKET_OVERRIDE"]
            if previous_funnel_stage_override:
                os.environ["POST_FUNNEL_STAGE_OVERRIDE"] = previous_funnel_stage_override
            elif "POST_FUNNEL_STAGE_OVERRIDE" in os.environ:
                del os.environ["POST_FUNNEL_STAGE_OVERRIDE"]
            if previous_pipeline_override:
                os.environ["POST_PIPELINE_OVERRIDE"] = previous_pipeline_override
            elif "POST_PIPELINE_OVERRIDE" in os.environ:
                del os.environ["POST_PIPELINE_OVERRIDE"]
            if previous_shadow_mode:
                os.environ["SOCIAL_SHADOW_MODE"] = previous_shadow_mode
            elif "SOCIAL_SHADOW_MODE" in os.environ:
                del os.environ["SOCIAL_SHADOW_MODE"]
            if previous_pool_runtime:
                os.environ["CANDIDATE_POOL_RUNTIME_ENABLED"] = previous_pool_runtime
            elif "CANDIDATE_POOL_RUNTIME_ENABLED" in os.environ:
                del os.environ["CANDIDATE_POOL_RUNTIME_ENABLED"]
            LAST_RUN["finished_at_utc"] = _utc_now()


# All times in UTC — currently mapped to Central Time (CT)
# 8am CT = 13:00 UTC | 12pm CT = 17:00 UTC | 6pm CT = 23:00 UTC
# Change POST_SCHEDULE_MORNING/MIDDAY/EVENING env vars to override
morning_utc = os.environ.get("POST_SCHEDULE_MORNING", "13:00")
midday_utc  = os.environ.get("POST_SCHEDULE_MIDDAY",  "17:00")
evening_utc = os.environ.get("POST_SCHEDULE_EVENING", "23:00")
intelligence_light_utc = os.environ.get("INTELLIGENCE_SCHEDULE_LIGHT", "11:00")
intelligence_standard_utc = os.environ.get("INTELLIGENCE_SCHEDULE_STANDARD", "03:00")
intelligence_deep_utc = os.environ.get("INTELLIGENCE_SCHEDULE_DEEP", "02:00")


def run_intelligence_heartbeat(level: str) -> None:
    """Scheduled observation is independent from and incapable of publishing."""
    from social.living_intelligence import heartbeat
    result = heartbeat(_data_dir(), level=level, website_url=os.environ.get("FIRST_PARTY_SITE_URL", ""), publication_records=_load_history(limit=200))
    print(f"[INTELLIGENCE] {level}: {len(result.get('observations', []))} observations")


def run_candidate_batch() -> None:
    ok, output = _run_script("build_candidate_pool.py")
    status = "ok" if ok else "failed"
    print(f"[CANDIDATE_POOL] {status}: {output[-1000:]}")


def run_intelligence_enrichment() -> None:
    try:
        coverage = intelligence_packages.compile_packages(_data_dir())
        print(f"[ENRICHMENT] packages={len(coverage['packages'])} reserve={coverage['ready_reserve_available']} counts={coverage['counts']}")
    except Exception as exc:
        print(f"[ENRICHMENT] failed: {type(exc).__name__}: {exc}")


def _scheduled_at(content_date, value: str) -> str:
    normalized = value if len(value.split(":")) == 3 else f"{value}:00"
    return f"{content_date.isoformat()}T{normalized}+00:00"


def run_content_factory() -> None:
    """Fill missing today/tomorrow slots independently from publication clocks."""
    if not RUN_LOCK.acquire(blocking=False):
        print("[FACTORY] Deferred because another content operation is active")
        return
    try:
        data_dir = _data_dir()
        init_content_operations(data_dir)
        reconciled = reconcile_ready_inventory(data_dir)
        if reconciled:
            print(f"[FACTORY] Reopened {len(reconciled)} stale ready packages: {reconciled}")
        stale_claims = reconcile_stale_claims(data_dir)
        if stale_claims:
            print(f"[FACTORY] Recovered {len(stale_claims)} stale claims: {stale_claims}")
        confirmed = reconcile_confirmed_transactions(data_dir)
        if confirmed:
            print(f"[FACTORY] Reconciled {len(confirmed)} confirmed transactions: {confirmed}")
        today = datetime.now(timezone.utc).date()
        horizon = [today, today + timedelta(days=1)]
        slot_times = {"morning": morning_utc, "midday": midday_utc, "evening": evening_utc}
        scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
        run_engine_path = os.path.join(scripts_dir, "run_engine.py")
        for content_date in horizon:
            snapshot = daily_status(data_dir, content_date)
            existing = {item["slot"]: item["status"] for item in snapshot.get("slots", [])}
            for slot in ("morning", "midday", "evening"):
                if existing.get(slot) in {"READY", "DUE", "CLAIMED", "PUBLISHING", "PUBLISHED", "EXTERNAL_ACTION_REQUIRED"}:
                    continue
                env = os.environ.copy()
                env.update({
                    "DATA_DIR": data_dir,
                    "POST_SLOT": slot,
                    "POST_CONTENT_DATE": content_date.isoformat(),
                    "CONTENT_FACTORY_ONLY": "true",
                    "CONTENT_OPERATIONS_ENABLED": "true",
                    "SOCIAL_DRY_RUN": "false",
                    "SOCIAL_SHADOW_MODE": "false",
                    "POST_PLATFORMS": "",
                })
                completed = subprocess.run(
                    [sys.executable, run_engine_path],
                    cwd=os.path.dirname(__file__),
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=int(os.environ.get("CONTENT_FACTORY_SLOT_TIMEOUT_SEC", "900")),
                    check=False,
                )
                output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
                print(f"[FACTORY] {content_date} {slot}: exit={completed.returncode} {output[-1000:]}")
    except Exception as exc:
        print(f"[FACTORY] error: {type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        RUN_LOCK.release()


def dispatch_scheduled_slot(slot: str) -> None:
    """Run the boring dispatcher; it never generates or rewrites content."""
    if not RUN_LOCK.acquire(blocking=False):
        print(f"[DISPATCH] {slot} deferred because another content operation is active")
        return
    try:
        scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
        env = os.environ.copy()
        env["DATA_DIR"] = _data_dir()
        completed = subprocess.run(
            [sys.executable, os.path.join(scripts_dir, "dispatch_outbox.py")],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            env=env,
            timeout=int(os.environ.get("DISPATCH_TIMEOUT_SEC", "360")),
            check=False,
        )
        output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
        print(f"[DISPATCH] {slot}: exit={completed.returncode} {output[-2000:]}")
    finally:
        RUN_LOCK.release()


def _start_factory_thread() -> None:
    threading.Thread(target=run_content_factory, daemon=True, name="content-factory").start()


def _start_dispatch_thread(slot: str) -> None:
    threading.Thread(target=dispatch_scheduled_slot, args=(slot,), daemon=True, name=f"dispatch-{slot}").start()


def register_scheduled_jobs() -> None:
    schedule.clear()
    schedule.every().day.at(morning_utc).do(_start_dispatch_thread, "morning")
    schedule.every().day.at(midday_utc).do(_start_dispatch_thread, "midday")
    schedule.every().day.at(evening_utc).do(_start_dispatch_thread, "evening")
    schedule.every(5).minutes.do(_start_dispatch_thread, "due_sweep")
    schedule.every(30).minutes.do(_start_factory_thread)
    schedule.every(6).hours.do(run_intelligence_enrichment)
    schedule.every().day.at(intelligence_light_utc).do(run_intelligence_heartbeat, "LIGHT_HEARTBEAT")
    schedule.every().day.at("10:00").do(run_candidate_batch)
    schedule.every().monday.at(intelligence_standard_utc).do(run_intelligence_heartbeat, "STANDARD_HEARTBEAT")
    schedule.every().sunday.at(intelligence_deep_utc).do(run_intelligence_heartbeat, "DEEP_HEARTBEAT")

def main() -> None:
    register_scheduled_jobs()

    start_health_server()

    loaded, load_reason = _load_meta_runtime_from_state()
    if loaded:
        print(f"Loaded Meta runtime state from disk ({load_reason})")
    else:
        print(f"Meta runtime state load: {load_reason}")

    bootstrap = _auto_bootstrap_visual_repo()
    if bootstrap.get("status") == "ok":
        print(f"Visual repo bootstrap ok: {bootstrap.get('summary', {})}")
    else:
        print(f"Visual repo bootstrap failed: {bootstrap.get('error')}")

    run_intelligence_enrichment()

    print("=== INF Energy Social Engine — Railway Worker ===")
    print(f"Scheduled (UTC): morning={morning_utc}  midday={midday_utc}  evening={evening_utc}")
    print(f"Dry run: {os.environ.get('SOCIAL_DRY_RUN', 'true')}")
    print("Manual run endpoint: /run-now?slot=morning&token=... (requires MANUAL_RUN_TOKEN)")
    print("Meta refresh endpoint: /refresh-meta?token=... (uses META_REFRESH_TOKEN or MANUAL_RUN_TOKEN)")
    print("Waiting for next scheduled run...\n")

    _start_factory_thread()

    if os.environ.get("RUN_ON_STARTUP", "false").lower() == "true":
        print("RUN_ON_STARTUP=true, launching startup run for morning slot")
        _start_slot_thread("morning")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
