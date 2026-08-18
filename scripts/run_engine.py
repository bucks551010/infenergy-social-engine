import os
import sys
import time
import json
import shutil
import hashlib
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))

import generate_posts
import publish_wordpress
import publish_facebook
import publish_instagram
import publish_linkedin
from score_content import score_content
from social.candidate_pool import CandidatePool
from social.publish_decision import decide as decide_publication
from social import claim_governance
from social.claim_intelligence import build_ledger, remove_unsupported_numeric_claims
from social import strategy_lock as strategy_lock_intelligence
from social import memory_intelligence
from social import creative_intelligence
from social_visuals import review_rendered_visual
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


def _write_run_outcome(status: str, *, slot: str, detail: str = "") -> None:
    path = os.path.join(generate_posts.DATA_DIR, "social", "last_run_outcome.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "status": status,
                "slot": slot,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "detail": detail,
            },
            handle,
            ensure_ascii=True,
        )
    os.replace(temporary_path, path)


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
    fb_page_id = str(os.environ.get("META_PAGE_ID", "")).strip()
    if not effective_channels.get("facebook", False):
        mark("facebook", "yellow", "channel_disabled")
    elif not fb_token:
        mark("facebook", "red", "missing_page_access_token")
    elif not fb_page_id:
        mark("facebook", "red", "missing_page_id")
    else:
        try:
            resp = requests.get(
                f"https://graph.facebook.com/v26.0/{fb_page_id}",
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


def _conversion_learning_fields(content: dict) -> dict:
    """Shared history-record fields that feed the Phase E performance memory loop.

    Every post_history.json append site must include these so future runs can
    read back strategic_brief / CQS / brief_adherence for winning/losing hints.
    """
    brief = content.get("strategic_brief") if isinstance(content.get("strategic_brief"), dict) else {}
    return {
        "strategic_brief": content.get("strategic_brief"),
        "logic_principle": brief.get("logic_principle", ""),
        "copy_framework": brief.get("copy_framework", ""),
        "conversion_quality_score": content.get("conversion_quality_score"),
        "conversion_brief_adherence": content.get("conversion_brief_adherence"),
        "conversion_variant_id": content.get("conversion_variant_id", ""),
    }


def _generation_diagnostics(content: dict) -> dict:
    """Persist the evidence required to explain a rejected or published run."""
    return {
        "copy": content.get("copy", {}),
        "orchestrator_quality": content.get("orchestrator_quality", {}),
        "claim_ledger": content.get("claim_ledger", {}),
        "creative_director": content.get("creative_director", {}),
        "copy_generation_method": content.get("copy_generation_method", ""),
        "copy_fallback_reason": content.get("copy_fallback_reason"),
        "visual_generation": (content.get("generated_visuals") or {}).get("visual_generation", {}),
        "platform_posts": content.get("platform_posts", {}),
        "creative_decision_packet": content.get("creative_decision_packet", {}),
        "publish_decision": content.get("publish_decision", {}),
    }


def _evidence_readiness(content: dict) -> dict:
    """Assess material claims at the final boundary using only supplied evidence."""
    copy = content.get("copy") if isinstance(content.get("copy"), dict) else {}
    existing = copy.get("evidence_readiness") or content.get("evidence_readiness")
    if isinstance(existing, dict):
        return existing
    text = " ".join(str(content.get(key, "")) for key in ("fb_caption", "ig_caption", "li_text", "wp_content"))
    verified_facts = list(content.get("product_metrics", []) or [])
    product_facts = str(content.get("product_facts", "") or "")
    if product_facts:
        verified_facts.append(product_facts)
    ledger = build_ledger(text, verified_facts=verified_facts)
    readiness = claim_governance.assess(ledger, hook=str(content.get("selected_hook", "")))
    content["claim_ledger"] = ledger.as_dict()
    content["evidence_readiness"] = readiness
    return readiness


def _evidence_safe_remediation_feedback(content: dict) -> list[str]:
    """Request one verified-facts-only replacement after a governance block."""
    product = str(content.get("product_name") or content.get("product_id") or "the product")
    return [
        "The prior candidate is blocked by central unsupported reasoning. Do not restate, soften, or remove metadata from that claim.",
        f"Choose a materially new, single-situation angle for {product} using only verified product facts already supplied to the generator.",
        "Express feature to function to practical use to human value without asserting compatibility, runtime, safety, outage performance, or other unverified consequences.",
        "Keep one natural human situation, a useful verified-fact takeaway, and an earned CTA. Abstain if no such angle is available.",
    ]


def _publish_receipts_path() -> str:
    root = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
    return os.path.join(root, "social", "publish_receipts.json")


def _load_publish_receipts() -> dict:
    try:
        with open(_publish_receipts_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) and isinstance(data.get("receipts"), list) else {"receipts": []}
    except (OSError, json.JSONDecodeError):
        return {"receipts": []}


def _save_publish_receipts(state: dict) -> None:
    path = _publish_receipts_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(temporary, path)


def _receipt_key(content: dict, platform: str) -> str:
    return f"{platform}:{str(content.get('post_id') or '')}"


def _successful_publish_receipt(content: dict, platform: str) -> dict:
    key = _receipt_key(content, platform)
    state = _load_publish_receipts()
    return next((item for item in state["receipts"] if item.get("key") == key and item.get("publisher_status") == "published"), {})


def _receipt_external_id(receipt: dict) -> str:
    return str(receipt.get("external_post_id") or receipt.get("facebook_post_id") or receipt.get("instagram_media_id") or receipt.get("linkedin_post_id") or "").strip()


def _persist_publish_receipt(content: dict, *, platform: str, external_post_id: str, run_id: str, container_id: str = "") -> dict:
    state = _load_publish_receipts()
    key = _receipt_key(content, platform)
    reel = content.get("instagram_reel") if isinstance(content.get("instagram_reel"), dict) else {}
    receipt = {
        "key": key,
        "platform": platform,
        "post_id": str(content.get("post_id") or ""),
        "external_post_id": external_post_id,
        "facebook_post_id": external_post_id if platform == "facebook" else "",
        "instagram_media_id": external_post_id if platform == "instagram" else "",
        "linkedin_post_id": external_post_id if platform == "linkedin" else "",
        "container_id": container_id if platform == "instagram" else "",
        "media_type": str(((content.get("platform_posts") or {}).get("instagram") or {}).get("media_type") or "IMAGE") if platform == "instagram" else "IMAGE",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source_candidate_id": str((content.get("generated_visuals") or {}).get("source_visual_candidate_id") or content.get("post_id") or ""),
        "artifact_path": str(reel.get("reel_artifact_path") or (content.get("generated_visuals") or {}).get(platform) or ""),
        "reel_artifact_path": str(reel.get("reel_artifact_path") or ""),
        "cover_path": str(reel.get("cover_path") or ""),
        "final_freeze_frame_path": str(reel.get("final_freeze_frame_path") or ""),
        "strategy_version": (_strategy_lock_for_revision(content) or {}).get("strategy_version"),
        "run_id": run_id,
        "publisher_status": "published",
        "provider_response_status": "success",
        "postprocess_status": "pending",
    }
    state["receipts"] = [item for item in state["receipts"] if item.get("key") != key] + [receipt]
    _save_publish_receipts(state)
    return receipt


def _pending_publish_receipt(content: dict, *, platform: str, run_id: str) -> bool:
    """Persist intent before an irreversible platform call.

    A later run refuses to repeat an unresolved intent because the prior call
    may have succeeded after the process crashed.
    """
    state = _load_publish_receipts()
    key = _receipt_key(content, platform)
    existing = next((item for item in state["receipts"] if item.get("key") == key), {})
    if existing.get("publisher_status") == "pending":
        return False
    receipt = {
        "key": key,
        "platform": platform,
        "post_id": str(content.get("post_id") or ""),
        "run_id": run_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "publisher_status": "pending",
        "provider_response_status": "not_called",
        "postprocess_status": "pending",
    }
    state["receipts"] = [item for item in state["receipts"] if item.get("key") != key] + [receipt]
    _save_publish_receipts(state)
    return True


def _persist_reconciled_publish_receipt(*, platform: str, external_post_id: str, published_at: str, run_started: str) -> dict:
    """Record a confirmed external publish without inventing missing candidate data."""
    state = _load_publish_receipts()
    receipt = {
        "key": f"{platform}:external:{external_post_id}",
        "platform": platform,
        "post_id": "",
        "facebook_post_id": external_post_id if platform == "facebook" else "",
        "published_at": published_at,
        "source_candidate_id": "",
        "artifact_path": "",
        "strategy_version": None,
        "run_id": run_started,
        "publisher_status": "published",
        "provider_response_status": "confirmed_external_success",
        "postprocess_status": "published_persistence_error",
        "reconciled": True,
    }
    state["receipts"] = [item for item in state["receipts"] if item.get("key") != receipt["key"]] + [receipt]
    _save_publish_receipts(state)
    return receipt


def _mark_publish_postprocess_error(content: dict, platform: str, error: Exception) -> None:
    state = _load_publish_receipts()
    key = _receipt_key(content, platform)
    for receipt in state["receipts"]:
        if receipt.get("key") == key:
            receipt["postprocess_status"] = "published_persistence_error"
            receipt["postprocess_error"] = f"{type(error).__name__}:{error}"
    _save_publish_receipts(state)


def _mark_publish_postprocess_complete(content: dict, platform: str) -> None:
    state = _load_publish_receipts()
    key = _receipt_key(content, platform)
    for receipt in state["receipts"]:
        if receipt.get("key") == key:
            receipt["postprocess_status"] = "complete"
    _save_publish_receipts(state)


def _reconcile_publish_receipt(receipt: dict) -> bool:
    """Append a minimal, honest recovery row for a receipt missing aggregate history."""
    facebook_id = str(receipt.get("facebook_post_id") or "").strip()
    post_id = str(receipt.get("post_id") or "").strip()
    if not facebook_id:
        return False
    history = generate_posts.load_history()
    posts = history.get("posts", []) if isinstance(history.get("posts"), list) else []
    if any(str(row.get("fb_id") or "") == facebook_id for row in posts if isinstance(row, dict)):
        return False
    posts.append({
        "post_id": post_id,
        "fb_id": facebook_id,
        "status": "published_persistence_recovered",
        "published_at": receipt.get("published_at"),
        "run_started_at_utc": receipt.get("run_id"),
        "date": str(receipt.get("published_at") or "")[:10],
        "platform_records": [{
            "platform": "facebook",
            "platform_post_id": facebook_id,
            "status": "published",
            "published_at": receipt.get("published_at"),
            "error": None,
        }],
        "recovery": {
            "source": "durable_publish_receipt",
            "aggregate_history_previously_failed": True,
            "recovered_fields": [item for item, value in {
                "post_id": post_id,
                "fb_id": facebook_id,
                "published_at": receipt.get("published_at"),
                "artifact_path": receipt.get("artifact_path"),
                "strategy_version": receipt.get("strategy_version"),
            }.items() if value not in (None, "")],
            "artifact_path": receipt.get("artifact_path"),
            "strategy_version": receipt.get("strategy_version"),
        },
    })
    history["posts"] = posts[-200:]
    generate_posts.save_history(history)
    return True


def _normalize_history_content(content: dict, *, run_started: str) -> dict:
    """Normalize legacy and orchestrator payloads at the history boundary only."""
    normalized = dict(content)
    timestamp = str(content.get("date") or content.get("created_at") or content.get("run_started_at_utc") or run_started)
    normalized["date"] = timestamp[:10]
    normalized["topic"] = str(content.get("topic") or ((content.get("strategic_brief") or {}).get("topic_path") or {}).get("topic") or "")
    normalized["pillar"] = str(content.get("pillar") or ((content.get("strategic_brief") or {}).get("pillar_id") or ""))
    normalized["topic_hash"] = str(content.get("topic_hash") or _stable_hash(normalized["topic"]))
    return normalized


def _visual_strategy_fingerprint(content: dict) -> str:
    strategy = _strategy_lock_for_revision(content)
    visual_plan = content.get("visual_plan") if isinstance(content.get("visual_plan"), dict) else {}
    payload = {
        "product_id": content.get("product_id"),
        "angle": strategy.get("angle"),
        "visual_objective": strategy.get("visual_objective"),
        "visual_plan": visual_plan,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _can_carry_forward_visuals(visuals: dict, content: dict, effective_channels: dict[str, bool]) -> bool:
    if not visuals or visuals.get("strategy_fingerprint") != _visual_strategy_fingerprint(content):
        return False
    reviews = visuals.get("artifact_reviews") if isinstance(visuals.get("artifact_reviews"), dict) else {}
    for platform in ("facebook", "instagram", "linkedin"):
        if not effective_channels.get(platform):
            continue
        review = reviews.get(platform) if isinstance(reviews.get(platform), dict) else {}
        artifact_path = str(review.get("artifact_path") or visuals.get(platform) or "")
        if str(review.get("verdict", "")).upper() != "PASS" or not artifact_path:
            return False
    return True


def _attach_platform_quality(content: dict, scoring: dict) -> None:
    posts = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
    results = scoring.get("platform_results") if isinstance(scoring.get("platform_results"), dict) else {}
    for platform, result in results.items():
        if isinstance(posts.get(platform), dict):
            posts[platform]["quality_score"] = result.get("total")
            posts[platform]["quality_verdict"] = result


def _conversion_quality_score(content: dict) -> float | None:
    score = content.get("conversion_quality_score")
    if not isinstance(score, dict) or score.get("total") is None:
        return None
    try:
        return float(score["total"])
    except (TypeError, ValueError):
        return None


def _quarantine_failed_pooled_candidate(candidate_pool: CandidatePool, content: dict, *, reason: str) -> bool:
    """Remove a failed pooled candidate before a retry replaces it with fresh content."""
    candidate_id = str(content.get("candidate_id") or "")
    if not candidate_id:
        return False
    return candidate_pool.quarantine(candidate_id, reason=reason or "validation_or_quality_failure")

def _strategy_integrity_errors(content: dict) -> list[str]:
    review = (content.get("creative_director") or {}).get("strategy_integrity_review", {})
    if str(review.get("verdict", "")).upper() == "MATERIAL_DRIFT":
        return ["strategy_integrity_material_drift"]
    human_review = (content.get("creative_director") or {}).get("independent_human_connection_review", {})
    human_verdict = str(human_review.get("verdict", "")).upper()
    if human_verdict == "DO_NOT_PUBLISH":
        return ["human_connection_review_do_not_publish"]
    if human_verdict in {"REVISE_COPY", "REVISE_BOTH", "REVISE_VISUAL"}:
        failures = [str(item) for item in human_review.get("reader_value_failures", []) if str(item)]
        detail = ",".join(failures) if failures else "review_failed"
        return [f"human_connection_review_{human_verdict.lower()}:{detail}"]
    if human_verdict == "CHANGE_ANGLE":
        return ["human_connection_review_change_angle"]
    human_truth = (content.get("creative_director") or {}).get("human_truth_gate", {})
    if isinstance(human_truth, dict) and not human_truth.get("ready", True):
        failures = ",".join(str(item) for item in human_truth.get("failures", []) if str(item))
        return [f"human_truth_gate_rejected:{failures or 'reader_value'}"]
    return []


def _strategy_lock_for_revision(content: dict) -> dict:
    copy = content.get("copy") if isinstance(content.get("copy"), dict) else {}
    trace = content.get("decision_trace") if isinstance(content.get("decision_trace"), dict) else {}
    lock = copy.get("strategy_lock") or trace.get("strategy_lock")
    return dict(lock) if isinstance(lock, dict) else {}


def _revision_feedback(content: dict, decision: dict) -> list[str]:
    """Convert existing critic output into auditable, bounded revision instructions."""
    findings = [str(reason) for reason in decision.get("reasons", []) if str(reason)]
    quality = content.get("orchestrator_quality") if isinstance(content.get("orchestrator_quality"), dict) else {}
    findings.extend(str(reason) for reason in quality.get("reasons", []) if str(reason))
    reviews = content.get("final_platform_copy_reviews") if isinstance(content.get("final_platform_copy_reviews"), dict) else {}
    for review in reviews.values():
        if isinstance(review, dict):
            findings.extend(str(issue) for issue in review.get("issues", []) if str(issue))
    creative = content.get("creative_director") if isinstance(content.get("creative_director"), dict) else {}
    human_review = creative.get("independent_human_connection_review") if isinstance(creative.get("independent_human_connection_review"), dict) else {}
    reader_value_failures = [str(item) for item in human_review.get("reader_value_failures", []) if str(item)]
    if reader_value_failures:
        findings.append("human_connection_reader_value_missing:" + ",".join(reader_value_failures))
    for key in ("copy_critic_review", "visual_critic_review"):
        review = creative.get(key) if isinstance(creative.get(key), dict) else {}
        findings.extend(str(issue) for issue in review.get("issues", []) if str(issue))
    return list(dict.fromkeys(findings))


_RETRYABLE_CONTENT_PREFIXES = (
    "runtime_",
    "capacity_not_verified:",
    "wattage_not_verified:",
    "numeric_claim_not_verified:",
    "price_claim_",
    "price_mismatch:",
    "compatibility_not_verified",
    "testimonial_or_customer_claim_unverified",
    "human_connection_review_revise_",
    "human_connection_reader_value_missing:",
)
_RETRYABLE_CONTENT_FINDINGS = {
    "runtime_quality_below_regeneration_floor",
    "orchestrator_critic_requires_revision",
    "orchestrator_critic_below_regeneration_floor",
    "candidate_needs_regeneration",
    "humanness below bar",
    "primary_benefit_not_explicit",
    "generic_or_ai_like_language",
    "hook-payoff mismatch",
}
_RETRYABLE_DUPLICATE_PREFIX = "duplicate_"
_TERMINAL_FINDINGS = {
    "product_url_missing",
    "product_unavailable_or_out_of_stock",
    "image_candidate_mismatch",
    "orchestration_control_plane_blocked",
    "strategy_integrity_material_drift",
    "human_connection_review_do_not_publish",
    "human_connection_review_change_angle",
}


def _retryability_classification(decision: dict, findings: list[str]) -> str:
    """Fail closed: only known content corrections may consume another attempt."""
    reasons = {str(item) for item in decision.get("reasons", []) if str(item)} | {str(item) for item in findings if str(item)}
    if any(reason in _TERMINAL_FINDINGS for reason in reasons):
        return "TERMINAL"
    if reasons and all(reason.startswith(_RETRYABLE_DUPLICATE_PREFIX) for reason in reasons):
        return "RETRYABLE_CONTENT"
    if any(reason in _RETRYABLE_CONTENT_FINDINGS or reason.startswith(_RETRYABLE_CONTENT_PREFIXES) for reason in reasons):
        return "RETRYABLE_CONTENT"
    return "TERMINAL"


def _duplicate_conflict_requires_fresh_product(findings: list[str]) -> bool:
    """A product-window conflict cannot be repaired while retaining its product lock."""
    return "duplicate_product_within_window" in {str(finding) for finding in findings}


def _duplicate_conflict_requires_fresh_strategy(findings: list[str]) -> bool:
    """Any duplicate retry must release its locked strategy so content can vary."""
    return any(str(finding).startswith(_RETRYABLE_DUPLICATE_PREFIX) for finding in findings)


def _enforce_candidate_claim_boundary(content: dict) -> list[str]:
    """Remove only unsupported unit-bearing numeric sentences before validation."""
    verified_facts = list(content.get("product_metrics") or [])
    product_facts = str(content.get("product_facts") or "").strip()
    if product_facts:
        verified_facts.append(product_facts)
    removed: list[str] = []

    def sanitize(mapping: dict, key: str) -> None:
        value = mapping.get(key)
        if not isinstance(value, str) or not value.strip():
            return
        sanitized, corrections = remove_unsupported_numeric_claims(value, verified_facts)
        mapping[key] = sanitized
        removed.extend(corrections)

    for field in ("wp_content", "fb_caption", "ig_caption", "li_text", "selected_hook"):
        sanitize(content, field)
    copy = content.get("copy")
    if isinstance(copy, dict):
        for field in ("hook", "body_text", "takeaway"):
            sanitize(copy, field)
        beats = copy.get("body_beats")
        if isinstance(beats, dict):
            for field in list(beats):
                sanitize(beats, field)
        copy["removed_unsupported_numeric_claims"] = list(dict.fromkeys(
            list(copy.get("removed_unsupported_numeric_claims") or []) + removed
        ))
    posts = content.get("platform_posts")
    if isinstance(posts, dict):
        for post in posts.values():
            if isinstance(post, dict):
                sanitize(post, "caption")
    return list(dict.fromkeys(removed))


def _revision_scope(content: dict) -> str:
    creative = content.get("creative_director") if isinstance(content.get("creative_director"), dict) else {}
    visual_review = creative.get("visual_critic_review") if isinstance(creative.get("visual_critic_review"), dict) else {}
    return "copy_and_visual" if str(visual_review.get("verdict", "")).upper() == "REVISE" else "copy"


def _cognitive_diagnosis(content: dict, *, strategy: dict, removed_claims: list[str], findings: list[str]) -> dict:
    """Route repair to the smallest owner that can resolve the fresh evidence."""
    copy = content.get("copy") if isinstance(content.get("copy"), dict) else {}
    coherence = strategy_lock_intelligence.post_sanitization_coherence(
        strategy,
        hook=str(copy.get("hook") or content.get("selected_hook") or ""),
        body=str(copy.get("body_text") or content.get("fb_caption") or ""),
        removed_claims=removed_claims,
    )
    failure_level = "COPY_EXECUTION"
    repair_owner = "Copy Intelligence"
    repair_scope = "copy"
    action = "CONTINUE_LOCAL_REPAIR"
    reason_codes = list(findings)
    if coherence["verdict"] == "STRATEGY_RECONSIDERATION_REQUIRED":
        failure_level = "STRATEGY_EVIDENCE_MISMATCH"
        repair_owner = "Strategy Intelligence"
        repair_scope = "angle_and_hook_promise"
        action = "RECONSIDER_ANGLE"
        reason_codes.append(coherence["reason"])
    elif any("visual" in finding.lower() for finding in findings):
        failure_level = "VISUAL_EXECUTION"
        repair_owner = "Visual Intelligence"
        repair_scope = "visual"
    elif any("not_verified" in finding or "unsupported" in finding for finding in findings):
        failure_level = "CLAIM_UNSUPPORTED"
        repair_owner = "Claim Intelligence"
        repair_scope = "claim_and_copy"
    terminal = any(finding in _TERMINAL_FINDINGS for finding in findings)
    if terminal:
        failure_level = "TERMINAL_SAFETY_FAILURE"
        repair_owner = "Governance"
        repair_scope = "none"
        action = "ABSTAIN"
    return {
        "failure_level": failure_level,
        "evidence": coherence["evidence"],
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "confidence": 0.95 if failure_level in {"STRATEGY_EVIDENCE_MISMATCH", "TERMINAL_SAFETY_FAILURE"} else 0.8,
        "repair_owner": repair_owner,
        "repair_scope": repair_scope,
        "preserve_fields": ["product", "audience", "customer_moment", "benefit", "claim_limits"],
        "reconsider_fields": ["angle", "hook_promise"] if action == "RECONSIDER_ANGLE" else [],
        "terminal_or_repairable": "terminal" if terminal else "repairable",
        "coherence": coherence,
        "metacognition": {"action": action, "attempt_budget_remaining": None},
    }


def _safe_reconsidered_angle(strategy: dict) -> tuple[str, str]:
    benefit = str(strategy.get("benefit") or "verified product-fit guidance")
    moment = str(strategy.get("customer_moment") or "when an outlet is unavailable")
    return (
        f"Use verified product facts to assess whether it supports {benefit}",
        f"What verified product facts help with {benefit} {moment}?",
    )


def _issue_key(issue: str) -> str:
    value = str(issue or "")
    return value.split(":", 1)[0]


def _issue_closure(historical_feedback: list[str], current_findings: list[str]) -> list[dict]:
    current_keys = {_issue_key(issue) for issue in current_findings}
    return [
        {
            "issue": issue,
            "status": "unresolved" if _issue_key(issue) in current_keys else "resolved",
        }
        for issue in historical_feedback
    ]


def _candidate_audit(content: dict) -> dict:
    copy = content.get("copy") if isinstance(content.get("copy"), dict) else {}
    posts = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
    facebook = posts.get("facebook") if isinstance(posts.get("facebook"), dict) else {}
    return {
        "post_id": content.get("post_id"),
        "hook": copy.get("hook") or content.get("selected_hook"),
        "body": copy.get("body_text"),
        "cta": copy.get("cta") or content.get("selected_cta"),
        "facebook_copy": facebook.get("caption") or content.get("fb_caption"),
        "claim_ledger": content.get("claim_ledger", {}),
        "revision_objectives": copy.get("revision_objectives", []),
        "removed_unsupported_numeric_claims": copy.get("removed_unsupported_numeric_claims", []),
    }


def _shadow_decision_record(content: dict) -> dict:
    """Owner-readable explanation from existing decision artifacts, never hidden reasoning."""
    strategy = (content.get("copy") or {}).get("strategy_lock") or content.get("strategic_brief") or {}
    creative = content.get("creative_director") or {}
    packet = content.get("creative_decision_packet") or {}
    return {
        "why_this_post_exists": content.get("topic", ""),
        "who_it_is_for": strategy.get("audience") or content.get("audience_segment", ""),
        "human_moment": strategy.get("customer_moment", ""),
        "customer_need": strategy.get("human_need", ""),
        "positioning": strategy.get("positioning", ""),
        "non_price_edge": strategy.get("non_price_edge", {}),
        "selected_angle": strategy.get("angle", ""),
        "copy_intent": (content.get("copy") or {}).get("takeaway", ""),
        "visual_intent": (content.get("visual") or {}).get("visual_objective", ""),
        "creative_concept": (packet.get("SELECTED_ANSWER") or {}).get("creative_concept", ""),
        "copy_approach": (packet.get("selected_copy_concept") or {}).get("approach", ""),
        "hook_selection": packet.get("hook_selection", {}),
        "feed_intelligence": packet.get("feed_intelligence", {}),
        "platform_interpretations": packet.get("platform_interpretations", {}),
        "originality_verdict": packet.get("originality_review", {}),
        "claim_limits": strategy.get("claim_limits", ""),
        "human_connection_verdict": creative.get("independent_human_connection_review", {}),
        "strategy_integrity_verdict": creative.get("strategy_integrity_review", {}),
        "final_publish_decision": content.get("publish_decision", {}),
    }


def _shadow_platform_records(content: dict, run_started: str, effective_channels: dict[str, bool]) -> list[dict]:
    records = _build_platform_history_records(
        content=content,
        run_started=run_started,
        effective_channels={name: False for name in effective_channels},
        dry_run=False,
        ids={"wordpress": "skipped", "facebook": "skipped", "instagram": "skipped", "linkedin": "skipped"},
        tracked_links={"facebook": None, "instagram": None, "linkedin": None, "wordpress": None},
        error_map={},
        channel_reasons={name: "shadow_mode_no_external_publication" for name in effective_channels},
    )
    for record in records:
        record["status"] = "shadow_not_published"
        record["error"] = "shadow_mode_no_external_publication"
    return records


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


def _resolve_primary_publish_image_url(content: dict, dry_run: bool) -> str:
    """Resolve one primary image URL with square-first priority for social placements."""

    def _public_base_url() -> str:
        candidates = [
            os.environ.get("PUBLIC_BASE_URL", ""),
            os.environ.get("SOCIAL_ENGINE_BASE_URL", ""),
            os.environ.get("RAILWAY_STATIC_URL", ""),
        ]
        railway_domain = str(os.environ.get("RAILWAY_PUBLIC_DOMAIN", "") or "").strip()
        if railway_domain:
            candidates.append(f"https://{railway_domain}")
        for raw in candidates:
            base = str(raw or "").strip().rstrip("/")
            if base.startswith("http"):
                return base
        return ""

    def _host_local_media(local_path: str) -> str:
        if not (local_path and os.path.exists(local_path) and os.path.isfile(local_path)):
            return ""
        base = _public_base_url()
        if not base:
            return ""

        data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
        public_dir = os.path.join(data_dir, "public_media")
        os.makedirs(public_dir, exist_ok=True)

        ext = os.path.splitext(local_path)[1].lower() or ".png"
        post_id = str(content.get("post_id", "") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        digest = hashlib.sha1(local_path.encode("utf-8")).hexdigest()[:10]
        file_name = f"{post_id}_{digest}{ext}"
        target_path = os.path.join(public_dir, file_name)
        shutil.copyfile(local_path, target_path)
        return f"{base}/media/{file_name}"

    candidate_paths: list[str] = []
    generated_visuals = content.get("generated_visuals") or {}
    if isinstance(generated_visuals, dict):
        # Prefer square-first assets because IG and most FB feed placements render best from square images.
        for key in ("instagram", "facebook", "linkedin"):
            raw_path = str(generated_visuals.get(key, "") or "").strip()
            if raw_path and os.path.exists(raw_path):
                candidate_paths.append(raw_path)

    # WordPress is out of scope for social publishing; host local media directly.
    for path in candidate_paths:
        try:
            hosted_url = _host_local_media(path)
            if hosted_url.startswith("http"):
                return hosted_url
        except Exception as e:
            print(f"[Image] Warning: failed to host generated visual locally: {e}")

    # Fallback to product/candidate imagery when generated visuals are unavailable.
    product_image = str(content.get("product_image_url", "") or "").strip()
    if product_image and os.path.exists(product_image) and os.path.isfile(product_image):
        hosted_url = _host_local_media(product_image)
        if hosted_url.startswith("http"):
            return hosted_url
    if product_image.startswith("http"):
        return product_image
    for c in content.get("product_image_candidates", []) or []:
        candidate = str(c or "").strip()
        if candidate and os.path.exists(candidate) and os.path.isfile(candidate):
            hosted_url = _host_local_media(candidate)
            if hosted_url.startswith("http"):
                return hosted_url
        if candidate.startswith("http"):
            return candidate
    for c in content.get("category_image_candidates", []) or []:
        candidate = str(c or "").strip()
        if candidate and os.path.exists(candidate) and os.path.isfile(candidate):
            hosted_url = _host_local_media(candidate)
            if hosted_url.startswith("http"):
                return hosted_url
        if candidate.startswith("http"):
            return candidate
    return ""


def _live_visual_gate_errors(content: dict, effective_channels: dict[str, bool], dry_run: bool) -> list[str]:
    if dry_run:
        return []

    requested = [name for name in ("facebook", "instagram", "linkedin") if effective_channels.get(name)]
    if not requested:
        return []

    visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
    render_engines = visuals.get("render_engines") if isinstance(visuals.get("render_engines"), dict) else {}
    overlays = visuals.get("product_overlay_applied") if isinstance(visuals.get("product_overlay_applied"), dict) else {}
    require_gemini = os.environ.get("LIVE_REQUIRE_GEMINI_VISUAL", "true").strip().lower() in {"1", "true", "yes", "on"}
    approved_render_engines = {"gemini", "approved_product_photo"}
    has_anchored_product = bool(str(content.get("product_id") or "").strip())
    require_product = has_anchored_product and os.environ.get("LIVE_REQUIRE_PRODUCT_VISUAL", "true").strip().lower() in {"1", "true", "yes", "on"}

    errors: list[str] = []
    if require_product and str(visuals.get("product_specific_source_present", "false")).lower() != "true":
        errors.append("product_specific_image_source_missing")
    for platform in requested:
        if not str(visuals.get(platform, "")).strip():
            errors.append(f"{platform}_visual_missing")
        if require_gemini and str(render_engines.get(platform, "")) not in approved_render_engines:
            errors.append(f"{platform}_visual_not_gemini")
        if require_product and overlays.get(platform) is not True:
            errors.append(f"{platform}_product_overlay_missing")
    instagram_post = ((content.get("platform_posts") or {}).get("instagram") or {})
    if effective_channels.get("instagram") and str(instagram_post.get("media_type") or "").upper() == "REEL":
        reel = content.get("instagram_reel") if isinstance(content.get("instagram_reel"), dict) else {}
        reel_qa_failed = False
        for qa_name in ("technical_qa", "motion_qa", "freeze_qa", "final_frame_qa", "cover_qa"):
            if str((reel.get(qa_name) or {}).get("status") or "").upper() != "PASS":
                reel_qa_failed = True
                errors.append(f"instagram_reel_{qa_name}_failed")
        presentation = instagram_post.get("presentation") if isinstance(instagram_post.get("presentation"), dict) else {}
        if str(presentation.get("presentation_critic") or "").upper() != "PASS":
            if reel_qa_failed:
                errors.append("instagram_reel_platform_presentation_failed")
            else:
                instagram_post["media_type"] = "STATIC"
                instagram_post["media_fallback_reason"] = "reel_platform_presentation_failed"
                decision = content.get("instagram_media_decision")
                if isinstance(decision, dict):
                    decision["selected_format"] = "STATIC"
    return errors


def _final_presentation_errors(content: dict, effective_channels: dict[str, bool]) -> list[str]:
    """Require the stored final public caption to pass presentation QA before publishing."""
    packages = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
    errors: list[str] = []
    for platform in ("facebook", "instagram", "linkedin"):
        if not effective_channels.get(platform):
            continue
        package = packages.get(platform) if isinstance(packages.get(platform), dict) else {}
        qa = package.get("final_caption_qa") if isinstance(package.get("final_caption_qa"), dict) else {}
        if qa.get("status") != "PRESENTATION_READY":
            errors.append(f"{platform}_final_presentation_not_ready")
    return errors


def _artifact_visual_errors_by_platform(content: dict, effective_channels: dict[str, bool]) -> dict[str, list[str]]:
    """Return saved-artifact QA failures for active social channels only."""
    visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
    reviews = visuals.get("artifact_reviews") if isinstance(visuals.get("artifact_reviews"), dict) else {}
    errors: dict[str, list[str]] = {}
    for platform in ("facebook", "instagram", "linkedin"):
        if not effective_channels.get(platform):
            continue
        review = reviews.get(platform) if isinstance(reviews.get(platform), dict) else {}
        if str(review.get("verdict", "")).upper() != "PASS":
            issues = review.get("issues") if isinstance(review.get("issues"), list) else ["artifact_review_missing"]
            errors[platform] = [str(issue) for issue in issues] or ["artifact_review_missing"]
    return errors


def _v5_semantic_visual_errors(content: dict, effective_channels: dict[str, bool]) -> list[str]:
    """Block a rendered V5 image only on an explicit semantic QA failure."""
    visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
    generation = visuals.get("visual_generation") if isinstance(visuals.get("visual_generation"), dict) else {}
    errors: list[str] = []
    for platform in ("facebook", "instagram", "linkedin"):
        if not effective_channels.get(platform):
            continue
        metadata = generation.get(platform) if isinstance(generation.get(platform), dict) else {}
        report = metadata.get("v5_qa") if isinstance(metadata.get("v5_qa"), dict) else {}
        if not report:
            continue
        flags = [name for name in ("has_text", "has_fake_products", "busy_copy_zone", "off_brand") if report.get(name) is True]
        if report.get("acceptable") is False:
            flags.append("unacceptable")
        if flags:
            errors.append(f"{platform}_v5_semantic_qa:{','.join(sorted(set(flags)))}")
    return errors


def _ensure_final_artifact_qa(content: dict, effective_channels: dict[str, bool]) -> dict[str, dict]:
    """Inspect the actual generated artifact before either governance or shadow stop."""
    if not any(effective_channels.get(platform) for platform in ("facebook", "instagram", "linkedin")):
        return {}
    visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
    if not visuals:
        visuals = generate_posts.generate_visuals(content, visual_plan=content.get("visual_plan"))
        content["generated_visuals"] = visuals
    reviews = visuals.get("artifact_reviews") if isinstance(visuals.get("artifact_reviews"), dict) else {}
    for platform in ("facebook", "instagram", "linkedin"):
        if effective_channels.get(platform):
            existing_review = reviews.get(platform) if isinstance(reviews.get(platform), dict) else {}
            artifact_path = str(visuals.get(platform) or existing_review.get("artifact_path") or "")
            reviews[platform] = review_rendered_visual(artifact_path, platform)
    visuals["artifact_reviews"] = reviews
    content["artifact_visual_qa"] = reviews
    return reviews


def _record_material_strategy_lessons(content: dict, strategy: dict) -> list[dict]:
    red_team = strategy.get("strategy_red_team") if isinstance(strategy.get("strategy_red_team"), dict) else {}
    if str(red_team.get("verdict", "")).upper() != "CHANGE_ANGLE":
        return []
    product_id = str(content.get("product_id") or "")
    records: list[dict] = []
    for requirement in red_team.get("evidence_requirements", []):
        lesson = {
            "product_id": product_id,
            "condition": f"{requirement}_angle_without_verified_evidence",
            "action": "challenge_angle_or_require_evidence",
            "evidence": list(red_team.get("challenge_evidence") or []),
            "source_decision": "CHANGE_ANGLE",
            "source_strategy_version": strategy.get("strategy_version"),
            "lesson": f"Require verified {requirement} evidence or choose a different angle.",
        }
        memory_intelligence.append_strategy_lesson(lesson)
        records.append(lesson)
    return records


def _build_platform_history_records(
    content: dict,
    run_started: str,
    effective_channels: dict[str, bool],
    dry_run: bool,
    ids: dict[str, str],
    tracked_links: dict[str, str],
    error_map: dict[str, str],
    skip_reason_map: dict[str, str] | None = None,
    channel_reasons: dict[str, str] | None = None,
    include_wordpress_audit: bool = False,
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
    platforms = ("facebook", "instagram", "linkedin", "wordpress") if include_wordpress_audit else ("facebook", "instagram", "linkedin")
    for platform in platforms:
        platform_entry = platform_posts.get(platform, {}) if isinstance(platform_posts.get(platform), dict) else {}
        platform_post_id = str(ids.get(platform, "") or "")
        utm_url = tracked_links.get(platform) if platform in tracked_links else None
        if platform == "wordpress" and not utm_url:
            utm_url = destination_url or None
        status = _platform_status(platform, effective_channels, platform_post_id, dry_run, error_map)
        error_value = error_map.get(platform)
        if not error_value:
            error_value = str((skip_reason_map or {}).get(platform, "") or "").strip() or None
        if not error_value and status == "skipped":
            reason = str((channel_reasons or {}).get(platform, "") or "").strip()
            if reason:
                error_value = reason
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
                "status": status,
                "error": error_value,
            }
        )
    return records


def main() -> None:
    slot = os.environ.get("POST_SLOT", "morning")
    dry_run = os.environ.get("SOCIAL_DRY_RUN", "true").lower() == "true"
    shadow_mode = _env_flag("SOCIAL_SHADOW_MODE", False)
    product_id_override = os.environ.get("POST_PRODUCT_ID_OVERRIDE", "").strip()
    funnel_stage_override = os.environ.get("POST_FUNNEL_STAGE_OVERRIDE", "").strip().upper()
    pipeline_override = os.environ.get("POST_PIPELINE_OVERRIDE", "").strip().lower()
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
    # WordPress is legacy-only and cannot participate in social readiness or publication.
    effective_channels["wordpress"] = False
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
    candidate_pool = CandidatePool(generate_posts.DATA_DIR)
    pool_enabled = _env_flag("CANDIDATE_POOL_RUNTIME_ENABLED", False)
    pooled_candidate: dict | None = None
    pool_selection: dict = {"selection_reason": "runtime_pool_disabled"}
    if pool_enabled:
        pool_floor = max(1, int(os.environ.get("CANDIDATE_POOL_MIN_DEPTH", "2")))
        if candidate_pool.depth() < pool_floor:
            from build_candidate_pool import build_pool

            refill = build_pool(target_depth=max(pool_floor, int(os.environ.get("CANDIDATE_POOL_TARGET_DEPTH", "6"))))
            runtime_metrics["candidate_pool_refill"] = refill
        pooled_candidate, pool_selection = candidate_pool.select_for_publication(
            exploration_floor=float(os.environ.get("CANDIDATE_POOL_EXPLORATION_FLOOR", "0.25")),
        )
    t_preview = time.perf_counter()
    if pooled_candidate and isinstance(pooled_candidate.get("content"), dict):
        preview_content = dict(pooled_candidate["content"])
        preview_content["candidate_id"] = pooled_candidate.get("candidate_id", "")
        preview_content["candidate_created_at"] = pooled_candidate.get("created_at", "")
        preview_content["rotation_selected"] = pooled_candidate.get("rotation_selected", {})
        preview_content["batch_gate_results"] = pooled_candidate.get("batch_gate_results", {})
        preview_content["pool_selection"] = pool_selection
    else:
        preview_content = generate_posts.generate(
            slot,
            funnel_stage_override=funnel_stage_override,
            product_id_override=product_id_override,
            pipeline_override=pipeline_override,
        )
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
        if name == "wordpress":
            channel_reasons[name] = "out_of_scope"
            continue
        if not enabled:
            effective_channels[name] = False
            channel_reasons[name] = "disabled_env"
            continue

        allowed, reason = eligibility.get(name, (False, "not_scheduled"))
        effective_channels[name] = bool(allowed)
        channel_reasons[name] = reason

    platform_selection = preview_content.get("platform_selection") if isinstance(preview_content.get("platform_selection"), dict) else {}
    for platform in ("facebook", "instagram", "linkedin"):
        selection = platform_selection.get(platform) if isinstance(platform_selection.get(platform), dict) else {}
        if effective_channels.get(platform) and selection.get("selected") is False:
            effective_channels[platform] = False
            channel_reasons[platform] = "strategy_platform_not_appropriate"

    phase5_readiness = _build_phase5_channel_readiness(effective_channels, dry_run)
    for platform in phase5_readiness.get("blocking_channels", []):
        effective_channels[platform] = False
        readiness_reason = (phase5_readiness.get("checks", {}).get(platform, {}) or {}).get("reason", "readiness_failed")
        channel_reasons[platform] = f"channel_readiness:{readiness_reason}"
    check_secrets(dry_run=dry_run or shadow_mode, channels=effective_channels)
    strategy_name, strategy_freshness = _latest_marketing_strategy_info()

    print(f"\n=== INF Energy Social Engine ===")
    print(f"Slot: {slot} | Dry run: {dry_run} | Shadow mode: {shadow_mode} | UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n")
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
    if product_id_override:
        print(f"Manual product override: {product_id_override}\n")
    if funnel_stage_override:
        print(f"Manual funnel-stage override: {funnel_stage_override}\n")
    print(f"Marketing strategy: {strategy_name} ({strategy_freshness})\n")
    print(f"Phase5 readiness: {json.dumps(phase5_readiness, ensure_ascii=True)}\n")

    print("[1/5] Generating content with Gemini...")
    # Phase 8: up to three generation attempts with score/validation gating.
    attempts: list[dict] = []
    windows = load_anti_repeat_windows()
    content = preview_content
    locked_strategy: dict = {}
    locked_product_id = product_id_override
    pending_feedback: list[str] = []
    pending_scope = "copy"
    prior_generated_visuals: dict = {}
    previous_decision: str | None = None
    previous_current_findings: list[str] = []
    t_generation = time.perf_counter()
    for idx in range(3):
        if idx > 0:
            content = generate_posts.generate(
                slot,
                funnel_stage_override=funnel_stage_override,
                product_id_override=locked_product_id,
                pipeline_override=pipeline_override,
                approved_strategy=locked_strategy or None,
                revision_feedback=pending_feedback,
            )
            if pending_scope == "copy" and _can_carry_forward_visuals(prior_generated_visuals, content, effective_channels):
                content["generated_visuals"] = prior_generated_visuals
                content["revision_reused_components"] = ["generated_visuals"]

        claim_corrections = _enforce_candidate_claim_boundary(content)
        validation = validate_generated_content(content)
        hard_block = str(os.environ.get("ORCHESTRATION_HARD_BLOCK", "false")).strip().lower() in {"1", "true", "yes", "on"}
        if content.get("orchestration_blocked"):
            if hard_block:
                validation = {
                    "passed": False,
                    "errors": list(validation.get("errors", [])) + ["orchestration_control_plane_blocked"],
                    "warnings": list(validation.get("warnings", [])),
                }
            else:
                validation = {
                    "passed": bool(validation.get("passed", False)),
                    "errors": list(validation.get("errors", [])),
                    "warnings": list(validation.get("warnings", [])) + ["orchestration_control_plane_soft_fail"],
                }

        strict_runtime_claims = str(os.environ.get("STRICT_RUNTIME_CLAIMS", "false")).strip().lower() in {"1", "true", "yes", "on"}
        if manual_platforms and manual_duplicate_mode == "allow_all" and not strict_runtime_claims:
            runtime_errors = [e for e in list(validation.get("errors", [])) if str(e) == "runtime_claim_not_supported"]
            if runtime_errors:
                kept_errors = [e for e in list(validation.get("errors", [])) if str(e) != "runtime_claim_not_supported"]
                validation = {
                    "passed": len(kept_errors) == 0,
                    "errors": kept_errors,
                    "warnings": list(validation.get("warnings", [])) + ["runtime_claim_not_supported_soft_fail"],
                }
        scoring = score_content(content, requested_platforms=manual_platforms)
        _attach_platform_quality(content, scoring)
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
        generated_visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
        generated_visuals["source_visual_candidate_id"] = str(generated_visuals.get("source_visual_candidate_id") or content.get("post_id") or "")
        generated_visuals["strategy_fingerprint"] = _visual_strategy_fingerprint(content)
        content["generated_visuals"] = generated_visuals

        # Conversion Logic Engine rule (spec section 23): below 80 CQS, automatically
        # attempt improvement before publishing rather than accepting a "warning"-only gate.
        cqs_total = _conversion_quality_score(content)
        publish_decision = decide_publication(
            legacy_score=scoring,
            validation=validation,
            duplicates=duplicates,
            conversion_quality_score=cqs_total,
            orchestrator_quality=content.get("orchestrator_quality"),
            evidence_readiness=_evidence_readiness(content),
        )
        content["publish_decision"] = publish_decision
        current_strategy = _strategy_lock_for_revision(content)
        if not locked_strategy and current_strategy:
            locked_strategy = current_strategy
        if not locked_product_id:
            locked_product_id = str(content.get("product_id") or "")
        material_lessons = _record_material_strategy_lessons(content, current_strategy or locked_strategy)
        critic_feedback = _revision_feedback(content, publish_decision)
        revision_scope = _revision_scope(content)
        historical_feedback = list(pending_feedback)
        issue_closure = _issue_closure(historical_feedback, critic_feedback)
        retryability = _retryability_classification(publish_decision, critic_feedback)
        diagnosis = _cognitive_diagnosis(
            content,
            strategy=current_strategy or locked_strategy,
            removed_claims=claim_corrections,
            findings=critic_feedback,
        )
        diagnosis["metacognition"]["attempt_budget_remaining"] = 2 - idx

        attempts.append(
            {
                "attempt": idx + 1,
                "score": scoring.get("total"),
                "decision": publish_decision["decision"],
                "validation_passed": validation.get("passed"),
                "validation_errors": validation.get("errors", []),
                "duplicates_ok": duplicates.get("ok"),
                "duplicate_reasons": duplicates.get("reasons", []),
                "conversion_quality_score": cqs_total,
                "orchestrator_critic_score": publish_decision.get("orchestrator_critic_score"),
                "previous_decision": previous_decision,
                "previous_current_findings": previous_current_findings,
                "retryability_classification": retryability,
                "historical_feedback": historical_feedback,
                "current_candidate_findings": critic_feedback,
                "claim_corrections": claim_corrections,
                "issue_closure": issue_closure,
                "revision_scope": revision_scope,
                "cognitive_diagnosis": diagnosis,
                "material_strategy_lessons": material_lessons,
                "strategy_lock": locked_strategy,
                "visual_generation": generated_visuals.get("visual_generation", {}),
                "candidate": _candidate_audit(content),
            }
        )

        metacognitive_review = creative_intelligence.metacognitive_review(attempts)
        diagnosis["metacognition"].update(metacognitive_review)
        attempts[-1]["cognitive_diagnosis"] = diagnosis
        content["creative_concept_escalation"] = metacognitive_review

        if publish_decision["publishable"]:
            break

        if idx == 0:
            duplicate_reasons = content.get("duplicate_check", {}).get("reasons", [])
            quarantine_reason = ",".join(str(reason) for reason in duplicate_reasons) if duplicate_reasons else "validation_or_quality_failure"
            if _quarantine_failed_pooled_candidate(candidate_pool, content, reason=quarantine_reason):
                print(f"[POOL] Quarantined failed candidate before retry: {str(content.get('candidate_id'))[:8]}...")

        # Manual live override path: if operator explicitly requests allow_all, swap to a known-safe
        # product/stage combo for one retry so publishing can proceed.
        if (
            idx == 0
            and manual_platforms
            and manual_duplicate_mode == "allow_all"
            and not validation.get("passed")
            and (not product_id_override)
            and (not funnel_stage_override)
        ):
            content = generate_posts.generate(
                slot,
                funnel_stage_override="ATTENTION",
                product_id_override="INF-9792",
                pipeline_override=pipeline_override,
            )
            validation = validate_generated_content(content)
            strict_runtime_claims = str(os.environ.get("STRICT_RUNTIME_CLAIMS", "false")).strip().lower() in {"1", "true", "yes", "on"}
            if not strict_runtime_claims:
                kept_errors = [e for e in list(validation.get("errors", [])) if str(e) != "runtime_claim_not_supported"]
                validation = {
                    "passed": len(kept_errors) == 0,
                    "errors": kept_errors,
                    "warnings": list(validation.get("warnings", [])) + ["runtime_claim_not_supported_soft_fail"],
                }
            scoring = score_content(content, requested_platforms=manual_platforms)
            _attach_platform_quality(content, scoring)
            duplicates = check_duplicates(content, generate_posts.load_history(), windows=windows)
            if manual_duplicate_mode == "allow_all":
                duplicates["reasons"] = []
                duplicates["ok"] = True
            content["validation_status"] = "passed" if validation.get("passed") else "failed"
            content["validation_errors"] = validation.get("errors", [])
            content["validation_warnings"] = validation.get("warnings", [])
            content["quality_score"] = scoring.get("total")
            content["quality_component_scores"] = scoring.get("component_scores", {})
            content["duplicate_check"] = duplicates
            content.update(duplicates.get("signatures", {}))
            publish_decision = decide_publication(
                legacy_score=scoring,
                validation=validation,
                duplicates=duplicates,
                conversion_quality_score=cqs_total,
                orchestrator_quality=content.get("orchestrator_quality"),
                evidence_readiness=_evidence_readiness(content),
            )
            content["publish_decision"] = publish_decision
            attempts.append(
                {
                    "attempt": idx + 1,
                    "score": scoring.get("total"),
                    "decision": "manual_safe_retry",
                    "validation_passed": validation.get("passed"),
                    "validation_errors": validation.get("errors", []),
                    "duplicates_ok": duplicates.get("ok"),
                    "duplicate_reasons": duplicates.get("reasons", []),
                }
            )
            if publish_decision["publishable"]:
                break

        # A critic-directed revision is bounded to three candidates total.
        if idx < 2 and scoring.get("decision") != "reject" and (
            publish_decision["decision"] in {"revise", "regenerate"}
            or (publish_decision["decision"] == "do_not_publish" and retryability == "RETRYABLE_CONTENT")
        ):
            pending_feedback = critic_feedback or ["Improve the candidate so it meets the existing critic threshold."]
            pending_scope = diagnosis["repair_scope"] if diagnosis["repair_scope"] != "angle_and_hook_promise" else "strategy"
            if diagnosis["metacognition"]["action"] == "RECONSIDER_ANGLE" and locked_strategy:
                new_angle, new_hook = _safe_reconsidered_angle(locked_strategy)
                locked_strategy = strategy_lock_intelligence.reconsider_angle(
                    locked_strategy,
                    reason=str(diagnosis["coherence"]["reason"]),
                    evidence=list(diagnosis["evidence"]),
                    new_angle=new_angle,
                    new_hook_promise=new_hook,
                )
                pending_feedback = list(dict.fromkeys(pending_feedback + [
                    "Use the reopened verified-facts angle. Do not restore removed runtime, efficiency, or appliance compatibility claims.",
                ]))
                prior_generated_visuals = {}
            else:
                prior_generated_visuals = dict(content.get("generated_visuals") or {})
            if _duplicate_conflict_requires_fresh_strategy(critic_feedback):
                # A retry using the locked product necessarily repeats the product-window conflict.
                if _duplicate_conflict_requires_fresh_product(critic_feedback):
                    locked_product_id = ""
                locked_strategy = {}
                prior_generated_visuals = {}
            previous_decision = str(publish_decision["decision"])
            previous_current_findings = list(critic_feedback)
            continue

        if publish_decision["decision"] == "do_not_publish":
            break

        # Otherwise stop on final attempt or hard rejection.
        if idx == 2 or scoring.get("decision") == "reject":
            break
    _apply_phase8_budget(runtime_metrics, "generation", time.perf_counter() - t_generation, generation_budget)

    final_validation_ok = content.get("validation_status") == "passed"
    final_score = float(content.get("quality_score") or 0)
    duplicate_ok = bool(content.get("duplicate_check", {}).get("ok", True))
    deferred_visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
    if deferred_visuals.get("deferred"):
        content["generated_visuals"] = generate_posts.generate_visuals(content, visual_plan=content.get("visual_plan"))
        content["image_generation_attempts"] = int(content.get("image_generation_attempts", 0) or 0) + 1
    _ensure_final_artifact_qa(content, effective_channels)
    artifact_errors = _artifact_visual_errors_by_platform(content, effective_channels)
    for platform, issues in artifact_errors.items():
        effective_channels[platform] = False
        channel_reasons[platform] = f"artifact_visual_qa:{','.join(issues)}"
    visual_gate_errors = _live_visual_gate_errors(content, effective_channels, dry_run or shadow_mode)
    visual_gate_errors.extend(_strategy_integrity_errors(content))
    visual_gate_errors.extend(_v5_semantic_visual_errors(content, effective_channels))
    visual_gate_errors.extend(_final_presentation_errors(content, effective_channels))
    content["artifact_visual_qa"] = (content.get("generated_visuals") or {}).get("artifact_reviews", {})
    content["artifact_visual_qa_failures"] = artifact_errors
    if visual_gate_errors:
        content["validation_status"] = "failed"
        content["validation_errors"] = list(content.get("validation_errors", [])) + visual_gate_errors
        content.setdefault("quality_warnings", []).append("live_visual_gate_blocked")
        final_validation_ok = False

    final_cqs_total = _conversion_quality_score(content)
    if final_cqs_total is not None and final_cqs_total < 80:
        content.setdefault("quality_warnings", []).append(f"cqs_below_target_after_retries:{final_cqs_total}")
        print(f"[QUALITY] Published with Conversion Quality Score {final_cqs_total} after exhausting retries (target 80).")

    final_decision = decide_publication(
        legacy_score=scoring,
        validation={"passed": final_validation_ok, "errors": content.get("validation_errors", [])},
        duplicates=content.get("duplicate_check", {}),
        conversion_quality_score=final_cqs_total,
        orchestrator_quality=content.get("orchestrator_quality"),
        visual_errors=visual_gate_errors,
        evidence_readiness=_evidence_readiness(content),
    )
    content["publish_decision"] = final_decision
    if not final_decision["publishable"] and not shadow_mode:
        print("[SKIP] Content did not pass validation/quality thresholds; recording skipped run")
        # Quarantine pooled candidates that failed so they won't be re-selected indefinitely
        candidate_id = str(content.get("candidate_id") or "")
        if candidate_id:
            dup_reasons = content.get("duplicate_check", {}).get("reasons", [])
            quarantine_reason = ",".join(str(r) for r in dup_reasons) if dup_reasons else "validation_or_quality_failure"
            if _quarantine_failed_pooled_candidate(candidate_pool, content, reason=quarantine_reason):
                print(f"[POOL] Quarantined candidate {candidate_id[:8]}... reason={quarantine_reason}")
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
            "product_name": content.get("product_name", ""),
            "product_sku": content.get("product_sku", ""),
            "product_image_url": content.get("product_image_url", ""),
            "generated_visuals": content.get("generated_visuals", {}),
            "visual_plan": content.get("visual_plan", {}),
            "copy_generation_source": content.get("copy_generation_source", "unknown"),
            "quality_score": content.get("quality_score"),
            "quality_component_scores": content.get("quality_component_scores", {}),
            **_generation_diagnostics(content),
            **_conversion_learning_fields(content),
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
        _write_run_outcome("blocked_no_publish", slot=slot, detail="failed_quality_or_validation_or_duplicate")
        print("\n=== Done (skipped) ===\n")
        return

    if shadow_mode:
        history = generate_posts.load_history()
        run_started = datetime.now(timezone.utc).isoformat()
        platform_records = _shadow_platform_records(content, run_started, effective_channels)
        _apply_phase8_budget(runtime_metrics, "total", time.perf_counter() - t_total, total_budget)
        history["posts"].append({
            "post_id": content.get("post_id", ""), "platform": "multi", "published_at": run_started,
            "date": content.get("date"), "slot": slot, "run_started_at_utc": run_started,
            "topic": content.get("topic"), "audience_segment": content.get("audience_segment", ""),
            "funnel_stage": content.get("funnel_stage", "EDUCATION"),
            "product_id": content.get("product_id") or None, "quality_score": content.get("quality_score"),
            "quality_component_scores": content.get("quality_component_scores", {}),
            **_generation_diagnostics(content), **_conversion_learning_fields(content),
            "validation_status": content.get("validation_status"), "validation_errors": content.get("validation_errors", []),
            "duplicate_reasons": content.get("duplicate_check", {}).get("reasons", []),
            "generation_attempts": attempts, "dry_run": dry_run, "shadow_mode": True,
            "artifact_visual_qa": content.get("artifact_visual_qa", {}),
            "status": "shadow_completed", "decision_record": _shadow_decision_record(content),
            "channel_reasons": channel_reasons, "phase5_channel_readiness": phase5_readiness,
            "phase6_learning": _build_phase6_learning(content=content, platform_records=platform_records, errors=[], status="shadow_completed"),
            "phase8_runtime": runtime_metrics, "platform_records": platform_records,
            "wp_id": "shadow", "fb_id": "shadow", "ig_id": "shadow", "li_id": "shadow",
        })
        history["posts"] = history["posts"][-200:]
        generate_posts.save_history(history)
        print("[SHADOW] Decision recorded; no publisher or external media host was invoked")
        print("\n=== Done (shadow) ===\n")
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
    skip_reason_map: dict[str, str] = {}
    wp_result = {"id": "skipped", "link": os.environ.get("WP_URL", "https://www.infenergypower.com")}
    fb_result = {"id": "skipped"}
    ig_result = {"id": "skipped"}
    li_result = {"id": "skipped"}

    primary_publish_image_url = _resolve_primary_publish_image_url(content, dry_run=dry_run)
    if primary_publish_image_url:
        content["primary_publish_image_url"] = primary_publish_image_url
        print(f"[Image] Shared primary image URL resolved: {primary_publish_image_url}")
    else:
        print("[Image] Shared primary image URL not resolved; publishers will use local fallbacks")

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
            skip_reason_map={},
            channel_reasons=channel_reasons,
            include_wordpress_audit=True,
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
            "date": content.get("date") or run_started[:10],
            "slot": slot,
            "run_started_at_utc": run_started,
            "topic": content.get("topic", ""),
            "pillar": content.get("pillar", ""),
            "topic_hash": content.get("topic_hash", ""),
            "hook_type": content.get("selected_hook_type", ""),
            "funnel_stage": content.get("funnel_stage", "EDUCATION"),
            "quality_score": content.get("quality_score"),
            "quality_component_scores": content.get("quality_component_scores", {}),
            **_conversion_learning_fields(content),
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
        _write_run_outcome("skipped_no_eligible_platforms", slot=slot, detail="no_eligible_platforms")
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
        existing_receipt = _successful_publish_receipt(content, "facebook") if not dry_run else {}
        if existing_receipt:
            fb_result = {"id": _receipt_external_id(existing_receipt), "reused_receipt": True}
            print(f"[SKIP] Facebook already published: {fb_result['id']}")
        elif (not dry_run) and was_recent_channel_success(history, "fb", slot, skip_success_hours):
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
                facebook_post_id = str(fb_result.get("id") or "").strip()
                if facebook_post_id and facebook_post_id not in {"dry-run", "skipped"}:
                    _persist_publish_receipt(
                        content,
                        platform="facebook",
                        external_post_id=facebook_post_id,
                        run_id=str(runtime_metrics["started_at_utc"]),
                    )
            except Exception as e:
                errors.append(f"Facebook: {e}")
                error_map["facebook"] = str(e)
                print(f"[ERROR] Facebook publish failed: {e}")
    else:
        print("[SKIP] Facebook disabled")
    _apply_phase8_budget(runtime_metrics, "publish_facebook", time.perf_counter() - t_fb, publish_budget)

    ig_wait_after_fb_seconds = int(os.environ.get("IG_WAIT_AFTER_FB_SECONDS", "8"))
    if effective_channels["facebook"] and effective_channels["instagram"] and ig_wait_after_fb_seconds > 0:
        print(f"[Instagram] Waiting {ig_wait_after_fb_seconds}s after Facebook step completion")
        time.sleep(ig_wait_after_fb_seconds)

    print("[4/5] Instagram...")
    t_ig = time.perf_counter()
    if effective_channels["instagram"]:
        existing_receipt = _successful_publish_receipt(content, "instagram") if not dry_run else {}
        if existing_receipt:
            ig_result = {"id": _receipt_external_id(existing_receipt), "reused_receipt": True}
            print(f"[SKIP] Instagram already published: {ig_result['id']}")
        elif (not dry_run) and was_recent_channel_success(history, "ig", slot, skip_success_hours):
            print("[SKIP] Instagram recent successful publish within configured window")
        else:
            try:
                content["tracked_link_instagram"] = wp_link_ig
                ig_result = publish_instagram.publish(content, dry_run=dry_run)
                instagram_media_id = str(ig_result.get("id") or "").strip()
                if instagram_media_id and instagram_media_id not in {"dry-run", "skipped"}:
                    _persist_publish_receipt(
                        content,
                        platform="instagram",
                        external_post_id=instagram_media_id,
                        container_id=str(ig_result.get("container_id") or ""),
                        run_id=str(runtime_metrics["started_at_utc"]),
                    )
                if str(ig_result.get("id", "")).strip().lower() == "skipped":
                    ig_reason = str(ig_result.get("reason", "")).strip()
                    if ig_reason:
                        skip_reason_map["instagram"] = ig_reason
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
        existing_receipt = _successful_publish_receipt(content, "linkedin") if not dry_run else {}
        if existing_receipt:
            li_result = {"id": _receipt_external_id(existing_receipt), "reused_receipt": True}
            print(f"[SKIP] LinkedIn already published: {li_result['id']}")
        elif (not dry_run) and not _pending_publish_receipt(content, platform="linkedin", run_id=str(runtime_metrics["started_at_utc"])):
            msg = "linkedin_publish_pending_reconciliation"
            errors.append(f"LinkedIn: {msg}")
            error_map["linkedin"] = msg
            print(f"[ERROR] LinkedIn publish blocked: {msg}")
        elif (not dry_run) and was_recent_channel_success(history, "li", slot, skip_success_hours):
            print("[SKIP] LinkedIn recent successful publish within configured window")
        else:
            try:
                li_result = publish_linkedin.publish(content, wp_link_li, dry_run=dry_run)
                linkedin_post_id = str(li_result.get("id") or "").strip()
                if linkedin_post_id and linkedin_post_id not in {"dry-run", "skipped"}:
                    _persist_publish_receipt(
                        content,
                        platform="linkedin",
                        external_post_id=linkedin_post_id,
                        run_id=str(runtime_metrics["started_at_utc"]),
                    )
            except Exception as e:
                errors.append(f"LinkedIn: {e}")
                error_map["linkedin"] = str(e)
                print(f"[ERROR] LinkedIn publish failed: {e}")
    else:
        print("[SKIP] LinkedIn disabled")
    _apply_phase8_budget(runtime_metrics, "publish_linkedin", time.perf_counter() - t_li, publish_budget)

    # Persist history so the next run picks a fresh topic
    run_started = datetime.now(timezone.utc).isoformat()
    content = _normalize_history_content(content, run_started=run_started)
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
        skip_reason_map=skip_reason_map,
        channel_reasons=channel_reasons,
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
        "status": "success" if not errors else "partial_error",
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
        "product_image_url": content.get("product_image_url", ""),
        "generated_visuals": content.get("generated_visuals", {}),
        "visual_plan": content.get("visual_plan", {}),
        "primary_publish_image_url": content.get("primary_publish_image_url", ""),
        "copy_generation_source": content.get("copy_generation_source", "unknown"),
        "quality_score": content.get("quality_score"),
        "quality_component_scores": content.get("quality_component_scores", {}),
        "rotation_selected": content.get("rotation_selected", {}),
        "candidate_id": content.get("candidate_id", ""),
        "candidate_age_at_publish": content.get("candidate_created_at", ""),
        "batch_gate_results": content.get("batch_gate_results", {}),
        "image_generation_attempts": int(content.get("image_generation_attempts", 0) or 0),
        **_generation_diagnostics(content),
        "quality_warnings": content.get("quality_warnings", []),
        **_conversion_learning_fields(content),
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
    try:
        generate_posts.save_history(history)
        for platform, result in (("facebook", fb_result), ("instagram", ig_result), ("linkedin", li_result)):
            if str(result.get("id") or "").strip() and not dry_run:
                _mark_publish_postprocess_complete(content, platform)
    except Exception as exc:
        for platform, result in (("facebook", fb_result), ("instagram", ig_result), ("linkedin", li_result)):
            if str(result.get("id") or "").strip() and not dry_run:
                _mark_publish_postprocess_error(content, platform, exc)
                raise RuntimeError(f"published_persistence_error:{platform}:{exc}") from exc
        raise

    published_records = [
        record
        for record in platform_records
        if str(record.get("status", "")).strip().lower() in {"published", "dry-run"}
    ]
    if published_records and str(content.get("candidate_id") or ""):
        candidate_pool.consume(str(content["candidate_id"]), published_at=run_started)
    _write_run_outcome(
        "published" if published_records else "blocked_no_publish",
        slot=slot,
        detail="platforms=" + ",".join(str(record.get("platform", "")) for record in published_records),
    )
    if errors:
        raise RuntimeError(" | ".join(errors))
    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
