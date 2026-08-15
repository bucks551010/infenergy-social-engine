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
from social.publish_decision import decide as decide_publication
from social.claim_intelligence import remove_unsupported_numeric_claims
from social import strategy_lock as strategy_lock_intelligence
from social import memory_intelligence
from social import creative_intelligence
from social import platform_presentation, recovery
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


def _remediation_concept(content: dict) -> dict:
    copy = content.get("copy") if isinstance(content.get("copy"), dict) else {}
    insight = copy.get("decision_insight") if isinstance(copy.get("decision_insight"), dict) else {}
    return {"question": str(content.get("selected_hook") or copy.get("hook") or ""), "angle": str((copy.get("strategy_lock") or {}).get("angle") or ""), "decision_thesis": str(insight.get("relationship") or ""), "payoff": str(insight.get("decision_consequence") or copy.get("takeaway") or ""), "human_reality": str((copy.get("strategy_lock") or {}).get("customer_moment") or "")}


def _remediation_context(content: dict, decision: dict, duplicates: dict) -> dict:
    concept = _remediation_concept(content)
    brief = content.get("strategic_brief") if isinstance(content.get("strategic_brief"), dict) else {}
    shortlist = brief.get("opportunity_shortlist") if isinstance(brief.get("opportunity_shortlist"), list) else []
    readiness = ((content.get("copy") or {}).get("evidence_readiness") or content.get("evidence_readiness") or {})
    claims = (readiness.get("claims") or []) if isinstance(readiness, dict) else []
    candidate_attempt_id = str(content.get("candidate_attempt_id") or f"{content.get('post_id')}:candidate-1")
    blocked_fingerprint = recovery.opportunity_fingerprint({
        "product_id": content.get("product_id"),
        "question": concept["question"],
        "angle": concept["angle"],
        "human_reality": concept["human_reality"],
        "decision_thesis": concept["decision_thesis"],
        "reader_job": (content.get("copy") or {}).get("strategy_lock", {}).get("reader_job") or content.get("reader_job"),
        "product_role": (content.get("copy") or {}).get("strategy_lock", {}).get("product_role"),
        "evidence_dependency": "CENTRAL_RESEARCH_REQUIRED" if any(isinstance(claim, dict) and claim.get("centrality") == "CENTRAL" and claim.get("research_status") == "RESEARCH_REQUIRED" for claim in claims) else "",
    })
    strategy = (content.get("copy") or {}).get("strategy_lock") or {}
    blocked_content_mode = "PRODUCT_FIT" if content.get("product_id") else "AUDIENCE_VALUE" if "product-free" in str(strategy.get("positioning") or "").lower() else "DECISION_SUPPORT"
    central_research_block = any(
        isinstance(claim, dict)
        and claim.get("centrality") == "CENTRAL"
        and claim.get("research_status") == "RESEARCH_REQUIRED"
        for claim in claims
    )
    excluded_product_ids = [str(content.get("product_id"))] if not duplicates.get("ok", True) and content.get("product_id") else []
    replacement, alternatives_considered = recovery.select_replacement(
        shortlist,
        excluded_product_ids=set(excluded_product_ids),
        excluded_concepts=set(value for value in concept.values() if value),
        blocked_human_realities={concept["human_reality"]} if concept.get("human_reality") else set(),
        blocked_fingerprint=blocked_fingerprint,
        max_claim_burden_level=1 if central_research_block else None,
        required_content_mode_change=central_research_block,
        blocked_content_mode=blocked_content_mode,
    )
    return {"original_candidate_id": str(content.get("post_id") or ""), "original_candidate_attempt_id": candidate_attempt_id, "original_concept": concept, "blocked_opportunity_fingerprint": blocked_fingerprint, "original_claim_ledger": content.get("claim_ledger") or {}, "original_evidence_readiness": readiness, "original_centrality_summary": {"central_unresolved": [str(claim.get("claim") or "") for claim in claims if isinstance(claim, dict) and claim.get("centrality") == "CENTRAL" and claim.get("research_status") == "RESEARCH_REQUIRED"], "status": str(readiness.get("status") or "")}, "remediation_reason": "central_evidence_block_requires_new_opportunity", "blocked_content_mode": blocked_content_mode, "fallback_type": "CONTENT_MODE_SHIFT" if replacement else "NO_VIABLE_LOW_CLAIM_MODE", "excluded_concepts": [value for value in concept.values() if value], "excluded_product_ids": excluded_product_ids, "exclude_engine_a_decision_thesis": True, "selection_rotation_index": int(content.get("selection_rotation_index") or 0) + 1, "candidate_attempt_id": f"{content.get('post_id')}:candidate-2", "original_governance": decision, "opportunity_shortlist": shortlist, "replacement_candidate": replacement, "alternatives_considered": alternatives_considered}


def _quality_recovery_context(content: dict, decision: dict, duplicates: dict) -> dict:
    """Retire a weak premise after its bounded copy work and continue the retained bench."""
    context = _remediation_context(content, decision, duplicates)
    context["remediation_reason"] = "candidate_quality_below_threshold_requires_new_opportunity"
    context["fallback_type"] = "CANDIDATE_SHIFT" if context.get("replacement_candidate") else "NO_VIABLE_CANDIDATE_SHIFT"
    context["exclude_engine_a_decision_thesis"] = False
    return context


def _field_replenishment_context(content: dict, quality_context: dict, critic_feedback: list[str]) -> dict:
    """Keep the failed premise out of one bounded fresh opportunity field."""
    concept = _remediation_concept(content)
    strategy = (content.get("copy") or {}).get("strategy_lock") or {}
    readiness = ((content.get("copy") or {}).get("evidence_readiness") or content.get("evidence_readiness") or {})
    claims = readiness.get("claims") if isinstance(readiness, dict) and isinstance(readiness.get("claims"), list) else []
    search_exclusion = " | ".join(
        str(concept[key]) for key in ("question", "angle", "human_reality") if concept.get(key)
    )
    context = {
        **quality_context,
        "recovery_mode": "FIELD_REPLENISHMENT",
        "remediation_reason": "retained_field_exhausted_after_quality_rejections",
        "retained_field_exclusions": list(quality_context.get("excluded_concepts", [])),
        "excluded_concepts": [search_exclusion] if search_exclusion else [],
        "blocked_human_realities": [concept["human_reality"]] if concept.get("human_reality") else [],
        "blocked_content_modes": [str(quality_context.get("blocked_content_mode") or "")] if quality_context.get("blocked_content_mode") else [],
        "blocked_reader_jobs": [str(strategy.get("reader_job") or content.get("reader_job") or "")] if strategy.get("reader_job") or content.get("reader_job") else [],
        "failed_claim_dependencies": [str(claim.get("claim") or "") for claim in claims if isinstance(claim, dict) and claim.get("centrality") == "CENTRAL"],
        "quality_failure_reasons": list(dict.fromkeys(critic_feedback)),
        "selection_rotation_index": int(content.get("selection_rotation_index") or 0) + 1,
        "candidate_attempt_id": f"{content.get('post_id')}:replenished-field",
    }
    context.pop("replacement_candidate", None)
    context.pop("opportunity_shortlist", None)
    return context


def _logical_candidate_key(content: dict) -> str:
    """Identify a strategic opportunity across regenerated copy artifacts."""
    brief = content.get("strategic_brief") if isinstance(content.get("strategic_brief"), dict) else {}
    strategy = (content.get("copy") or {}).get("strategy_lock") or {}
    identity = {
        "engine": brief.get("engine"),
        "pillar": brief.get("pillar_id"),
        "genre": brief.get("genre_id"),
        "question": brief.get("question") or content.get("selected_hook") or (content.get("copy") or {}).get("hook"),
        "angle": brief.get("angle") or strategy.get("angle"),
        "reader_job": brief.get("reader_job") or strategy.get("reader_job") or content.get("reader_job"),
        "product_id": content.get("product_id"),
    }
    return _stable_hash(json.dumps(identity, sort_keys=True, ensure_ascii=True)) or str(content.get("candidate_attempt_id") or content.get("post_id") or "")


def _research_recovery(content: dict) -> dict:
    """Resolve one central evidence gap through the existing bounded research stack."""
    from social import living_intelligence, public_research, research_router

    copy = content.get("copy") if isinstance(content.get("copy"), dict) else {}
    readiness = copy.get("evidence_readiness") if isinstance(copy.get("evidence_readiness"), dict) else {}
    need = next((item for item in readiness.get("research_needs", []) if isinstance(item, dict)), None)
    if not need:
        return {"status": "NOT_WORTH_RESEARCHING", "reason": "no_central_gap"}

    claim = str(need.get("claim_to_verify") or need.get("claim") or "").strip()
    claim_type = str(need.get("claim_type") or "general_informational")
    verified_product_fact = str(need.get("evidence_available") or "").upper() == "VERIFIED_PRODUCT_FACT"
    strategy = copy.get("strategy_lock") if isinstance(copy.get("strategy_lock"), dict) else {}
    entity = str(content.get("product_name") or content.get("topic") or strategy.get("topic") or "Infenergy Power").strip()
    question = str(need.get("research_question") or f"What authoritative evidence supports: {claim}").strip()
    task = research_router.route(
        question=question,
        why_needed=str(need.get("why_needed") or "The claim is central to the public message."),
        entity=entity,
        decision_affected="social_claim_verification",
        freshness_requirement="current",
    )
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
    state = living_intelligence.load(data_dir)
    cached = state.get("research_evidence") if isinstance(state.get("research_evidence"), list) else []
    reusable = next(
        (
            item for item in cached
            if isinstance(item, dict)
            and str(item.get("claim") or "") == claim
            and research_router.is_fresh(item, task)
            and public_research.validate_claim_authority(
                claim=claim,
                claim_type=claim_type,
                evidence=item,
                verified_product_fact=verified_product_fact,
            ).get("accepted")
            and float(public_research.validate_claim_authority(
                claim=claim,
                claim_type=claim_type,
                evidence=item,
                verified_product_fact=verified_product_fact,
            ).get("support_confidence") or 0) >= 0.75
        ),
        None,
    )
    if reusable:
        return {"status": "RESOLVED", "source": "evidence_memory", "task": task.as_dict(), "evidence": [reusable], "verified_facts": [claim]}

    results = public_research.research(task=task)
    accepted: list[dict] = []
    claim_tokens = {token for token in claim.lower().split() if len(token.strip(".,;:?!")) > 3}
    for result in results:
        if not isinstance(result, dict) or result.get("failure"):
            continue
        extract = " ".join(str(value) for value in result.get("extract", []))
        extract_tokens = {token.strip(".,;:?!").lower() for token in extract.split() if len(token.strip(".,;:?!")) > 3}
        authority = public_research.validate_claim_authority(
            claim=claim,
            claim_type=claim_type,
            evidence=result,
            verified_product_fact=verified_product_fact,
        )
        if authority["accepted"] and float(authority["support_confidence"] or 0) >= 0.75 and len(claim_tokens & extract_tokens) >= 2:
            accepted.append({
                **result,
                **authority,
                "claim": claim,
                "candidate_id": str(content.get("candidate_attempt_id") or content.get("post_id") or ""),
                "status": "RESOLVED",
                "verification_requirement": "central_claim_authoritative_match",
            })
    if not accepted:
        failure = next((str(item.get("failure")) for item in results if isinstance(item, dict) and item.get("failure")), "CLAIM_NOT_SUPPORTED")
        return {"status": "INSUFFICIENT_EVIDENCE", "failure": failure, "task": task.as_dict(), "sources": results}

    state["research_evidence"] = [*cached, *accepted][-100:]
    living_intelligence.save(data_dir, state)
    return {"status": "RESOLVED", "source": "public_research", "task": task.as_dict(), "evidence": accepted, "verified_facts": [claim]}


def _semantic_difference(original: dict, replacement: dict) -> tuple[bool, str]:
    changed = [key for key in original if original.get(key) != replacement.get(key)]
    if not changed:
        return False, "replacement_repeats_original_concept"
    aliases = {"access": "connection", "compatible": "fit", "compatibility": "fit", "device": "fit", "outlet": "airport", "outlets": "airport", "travel": "trip", "battery": "reserve", "capacity": "reserve", "stored": "reserve", "support": "fit"}
    tokens = lambda values: {aliases.get(word.strip(".,;:?!"), word.strip(".,;:?!")) for value in values.values() for word in str(value).lower().split() if len(word.strip(".,;:?!")) > 3}
    before, after = tokens(original), tokens(replacement)
    if len(before & after) / max(1, min(len(before), len(after))) >= 0.35:
        return False, "replacement_semantically_overlaps_blocked_concept"
    return True, "replacement_changes_" + "_and_".join(changed)


def _finalize_evidence_remediation(content: dict, remediation_context: dict) -> None:
    remediation = content.get("evidence_remediation") if isinstance(content.get("evidence_remediation"), dict) else {}
    if remediation.get("status") == "ABSTAINED_NO_VIABLE_REPLACEMENT":
        return
    replacement = _remediation_concept(content)
    materially_different, reason = _semantic_difference(remediation_context["original_concept"], replacement)
    readiness = ((content.get("copy") or {}).get("evidence_readiness") or content.get("evidence_readiness") or {})
    content["evidence_remediation"] = {**remediation_context, "status": "REMEDIATION_CANDIDATE", "attempt_limit": 1, "replacement_candidate_id": str(content.get("post_id") or ""), "replacement_candidate_attempt_id": str(content.get("candidate_attempt_id") or ""), "replacement_concept": replacement, "semantic_difference_reason": reason, "replacement_evidence_readiness": readiness, "visual_reuse_allowed": False}
    if not materially_different:
        content["validation_status"] = "failed"
        content["validation_errors"] = list(content.get("validation_errors", [])) + ["remediation_reused_blocked_concept"]


def _final_memory_record(content: dict, final_outcome: str) -> dict:
    copy = content.get("copy") if isinstance(content.get("copy"), dict) else {}
    remediation = content.get("evidence_remediation") if isinstance(content.get("evidence_remediation"), dict) else {}
    return {"human_reality": (copy.get("strategy_lock") or {}).get("customer_moment", ""), "value_idea": (copy.get("strategy_lock") or {}).get("angle", ""), "question": copy.get("hook") or content.get("selected_hook", ""), "takeaway": copy.get("takeaway", ""), "memory_anchor": copy.get("memory_anchor", ""), "response_contract": copy.get("response_contract", {}), "evidence_outcome": (copy.get("evidence_readiness") or {}).get("status", ""), "remediation_used": bool(remediation), "original_blocked_concept": remediation.get("original_concept", {}), "final_concept": _remediation_concept(content), "final_outcome": final_outcome}


def _generation_diagnostics(content: dict) -> dict:
    """Persist the evidence required to explain a rejected or published run."""
    return {
        "copy": content.get("copy", {}),
        "candidate_attempt_id": content.get("candidate_attempt_id", ""),
        "selection_rotation_index": content.get("selection_rotation_index"),
        "fb_caption": content.get("fb_caption", ""),
        "orchestrator_quality": content.get("orchestrator_quality", {}),
        "claim_ledger": content.get("claim_ledger", {}),
        "creative_director": content.get("creative_director", {}),
        "copy_generation_method": content.get("copy_generation_method", ""),
        "copy_fallback_reason": content.get("copy_fallback_reason"),
        "visual_generation": (content.get("generated_visuals") or {}).get("visual_generation", {}),
        "platform_posts": content.get("platform_posts", {}),
        "creative_decision_packet": content.get("creative_decision_packet", {}),
        "publish_decision": content.get("publish_decision", {}),
        "evidence_remediation": content.get("evidence_remediation", {}),
        "final_memory": content.get("final_memory", {}),
    }


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
    return str(receipt.get("external_post_id") or receipt.get("facebook_post_id") or receipt.get("instagram_media_id") or "").strip()


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

def _strategy_integrity_errors(content: dict) -> list[str]:
    review = (content.get("creative_director") or {}).get("strategy_integrity_review", {})
    if str(review.get("verdict", "")).upper() == "MATERIAL_DRIFT":
        return ["strategy_integrity_material_drift"]
    human_review = (content.get("creative_director") or {}).get("independent_human_connection_review", {})
    if str(human_review.get("verdict", "")).upper() == "DO_NOT_PUBLISH":
        return ["human_connection_review_do_not_publish"]
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
_TERMINAL_FINDINGS = {
    "product_url_missing",
    "product_unavailable_or_out_of_stock",
    "image_candidate_mismatch",
    "orchestration_control_plane_blocked",
    "strategy_integrity_material_drift",
    "human_connection_review_do_not_publish",
}


def _retryability_classification(decision: dict, findings: list[str]) -> str:
    """Fail closed: only known content corrections may consume another attempt."""
    reasons = {str(item) for item in decision.get("reasons", []) if str(item)} | {str(item) for item in findings if str(item)}
    if any(reason in _TERMINAL_FINDINGS for reason in reasons):
        return "TERMINAL"
    if any(reason in _RETRYABLE_CONTENT_FINDINGS or reason.startswith(_RETRYABLE_CONTENT_PREFIXES) for reason in reasons):
        return "RETRYABLE_CONTENT"
    return "TERMINAL"


def _evidence_safe_remediation_feedback(content: dict) -> list[str]:
    """Request one new, verified-facts-first candidate after research governance blocks a claim."""
    product = str(content.get("product_name") or content.get("product_id") or "the product")
    return [
        "The prior candidate is blocked by central unsupported reasoning. Do not restate, soften, or remove metadata from that claim.",
        f"Choose a materially new, single-situation angle for {product} using only verified product facts already supplied to the generator.",
        "Express feature to function to practical use to human value without asserting compatibility, runtime, safety, outage performance, or other unverified consequences.",
        "Keep one natural human situation, a useful verified-fact takeaway, and an earned CTA. Abstain if no such angle is available.",
    ]


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
        if corrections:
            mapping[key] = sanitized
            removed.extend(corrections)

    for field in ("wp_content", "selected_hook"):
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
                if isinstance(post.get("final_caption"), str):
                    sanitize(post, "final_caption")
        fields = {"facebook": "fb_caption", "instagram": "ig_caption", "linkedin": "li_text"}
        for platform, flat in fields.items():
            post = posts.get(platform) if isinstance(posts.get(platform), dict) else {}
            if not isinstance(post.get("final_caption") or post.get("caption"), str):
                sanitize(content, flat)
        for platform, flat in fields.items():
            post = posts.get(platform) if isinstance(posts.get(platform), dict) else {}
            caption = str(post.get("final_caption") or post.get("caption") or content.get(flat) or "").strip()
            if caption:
                post["caption"] = caption
                post["final_caption"] = caption
                content[flat] = caption
    else:
        for flat in ("fb_caption", "ig_caption", "li_text"):
            sanitize(content, flat)
    return list(dict.fromkeys(removed))


def _lock_final_captions(content: dict, active_channels: dict[str, bool] | None = None) -> list[str]:
    """Freeze the one public string after the last text mutation."""
    from social import platform_presentation

    components = content.get("post_components") if isinstance(content.get("post_components"), dict) else {}
    posts = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
    flat_fields = {"facebook": "fb_caption", "instagram": "ig_caption", "linkedin": "li_text"}
    active_channels = active_channels or {platform: True for platform in flat_fields}
    errors: list[str] = []
    locks: dict[str, str] = {}
    for platform, flat_field in flat_fields.items():
        package = posts.get(platform) if isinstance(posts.get(platform), dict) else {}
        caption = str(package.get("final_caption") or package.get("caption") or content.get(flat_field) or "").strip()
        if not caption:
            if active_channels.get(platform):
                errors.append(f"{platform}_final_caption_missing")
            continue
        if not components and not isinstance(package.get("final_caption_qa"), dict):
            package["caption"] = caption
            package["final_caption"] = caption
            package["final_caption_lock"] = caption
            content[flat_field] = caption
            locks[platform] = caption
            continue
        qa = platform_presentation.final_caption_qa(
            caption,
            platform=platform,
            components=components,
            planning_instructions=list(package.get("planning_instructions") or []),
        )
        package["caption"] = caption
        package["final_caption"] = caption
        package["final_caption_qa"] = qa
        package["final_caption_lock"] = caption
        content[flat_field] = caption
        locks[platform] = caption
        if active_channels.get(platform) and qa.get("status") != "PRESENTATION_READY":
            errors.append(f"{platform}_final_presentation_not_ready")
    content["final_caption_locks"] = locks
    return errors


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


def _record_no_viable_opportunity_abstention(
    *,
    slot: str,
    dry_run: bool,
    shadow_mode: bool,
    runtime_metrics: dict,
    total_started: float,
) -> None:
    """Record a normal terminal decision when freshness leaves no eligible opportunity."""
    run_started = str(runtime_metrics.get("started_at_utc") or datetime.now(timezone.utc).isoformat())
    _apply_phase8_budget(
        runtime_metrics,
        "total",
        time.perf_counter() - total_started,
        float(os.environ.get("PHASE8_BUDGET_TOTAL_SEC", "420")),
    )
    history = generate_posts.load_history()
    history.setdefault("posts", []).append({
        "post_id": f"abstain-{_stable_hash(run_started + slot)[:12]}",
        "platform_post_id": None,
        "platform": "multi",
        "published_at": run_started,
        "run_started_at_utc": run_started,
        "slot": slot,
        "error": "no_viable_opportunities",
        "status": "abstained_no_viable_opportunity",
        "dry_run": dry_run,
        "shadow_mode": shadow_mode,
        "platform_records": [],
        "generation_attempts": [],
        "final_memory": {
            "final_outcome": "abstain",
            "reason": "no_viable_opportunities",
        },
        "phase8_runtime": runtime_metrics,
    })
    history["posts"] = history["posts"][-200:]
    generate_posts.save_history(history)
    print("[ABSTAIN] No viable opportunities remain after freshness filtering.")


def _mark_no_viable_replacement_abstention(content: dict) -> None:
    """Keep the original candidate auditable when its one replacement cannot be selected."""
    content["validation_status"] = "failed"
    content["validation_errors"] = list(content.get("validation_errors", [])) + ["no_viable_replacement_opportunity"]
    remediation = content.get("evidence_remediation")
    if isinstance(remediation, dict):
        remediation["status"] = "ABSTAINED_NO_VIABLE_REPLACEMENT"
        remediation["replacement_candidate_id"] = ""
        remediation["semantic_difference_reason"] = "no_viable_replacement_opportunity"


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

    from social import visual_contract

    visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
    render_engines = visuals.get("render_engines") if isinstance(visuals.get("render_engines"), dict) else {}
    overlays = visuals.get("product_overlay_applied") if isinstance(visuals.get("product_overlay_applied"), dict) else {}
    contract = visual_contract.requirements(content)
    require_ai_visual = contract["ai_visual_required"] and os.environ.get("LIVE_REQUIRE_AI_VISUAL", "true").strip().lower() in {"1", "true", "yes", "on"}
    require_product = contract["product_reference_required"] and os.environ.get("LIVE_REQUIRE_PRODUCT_VISUAL", "true").strip().lower() in {"1", "true", "yes", "on"}

    errors: list[str] = []
    if require_product and str(visuals.get("product_specific_source_present", "false")).lower() != "true":
        errors.append("product_specific_image_source_missing")
    for platform in requested:
        if not str(visuals.get(platform, "")).strip():
            errors.append(f"{platform}_visual_missing")
        if require_ai_visual and str(render_engines.get(platform, "")) not in {"gemini", "cloudflare"}:
            errors.append(f"{platform}_visual_not_ai_generated")
        if contract["product_overlay_required"] and overlays.get(platform) is not True:
            errors.append(f"{platform}_product_overlay_missing")
    instagram_post = ((content.get("platform_posts") or {}).get("instagram") or {})
    if effective_channels.get("instagram") and str(instagram_post.get("media_type") or "").upper() == "REEL":
        reel = content.get("instagram_reel") if isinstance(content.get("instagram_reel"), dict) else {}
        for qa_name in ("technical_qa", "motion_qa", "freeze_qa", "final_frame_qa", "cover_qa"):
            if str((reel.get(qa_name) or {}).get("status") or "").upper() != "PASS":
                errors.append(f"instagram_reel_{qa_name}_failed")
        presentation = instagram_post.get("presentation") if isinstance(instagram_post.get("presentation"), dict) else {}
        if str(presentation.get("presentation_critic") or "").upper() != "PASS":
            errors.append("instagram_reel_platform_presentation_failed")
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


def _repair_final_presentations(content: dict, effective_channels: dict[str, bool]) -> list[str]:
    """Repair public rendering only; strategy, claims, product role, and visuals stay locked."""
    components = content.get("post_components") if isinstance(content.get("post_components"), dict) else {}
    packages = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
    repaired: list[str] = []
    for platform in ("facebook", "instagram", "linkedin"):
        if not effective_channels.get(platform):
            continue
        package = packages.get(platform) if isinstance(packages.get(platform), dict) else {}
        qa = package.get("final_caption_qa") if isinstance(package.get("final_caption_qa"), dict) else {}
        if qa.get("status") == "PRESENTATION_READY":
            continue
        caption, presentation = platform_presentation.format_caption(components, platform=platform)
        final_caption = platform_presentation.render_platform_caption(
            caption,
            destination_url=str(content.get("destination_url") or ""),
            platform=platform,
        )
        package["caption"] = final_caption
        package["final_caption"] = final_caption
        package["presentation"] = presentation
        packages[platform] = package
        repaired.append(platform)
    if repaired:
        content["platform_posts"] = packages
        _lock_final_captions(content, effective_channels)
    return repaired


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


def _ensure_final_artifact_qa(content: dict, effective_channels: dict[str, bool]) -> dict[str, dict]:
    """Inspect the actual generated artifact before either governance or shadow stop."""
    if not any(effective_channels.get(platform) for platform in ("facebook", "instagram", "linkedin")):
        return {}
    pre_visual_gate = content.get("pre_visual_gate") if isinstance(content.get("pre_visual_gate"), dict) else {}
    candidate_id = str(content.get("candidate_attempt_id") or content.get("post_id") or "")
    visuals = content.get("generated_visuals") if isinstance(content.get("generated_visuals"), dict) else {}
    active_platforms = [platform for platform in ("facebook", "instagram", "linkedin") if effective_channels.get(platform)]
    existing_reviews = visuals.get("artifact_reviews") if isinstance(visuals.get("artifact_reviews"), dict) else {}
    has_required_artifacts = bool(visuals) and all(
        str(
            visuals.get(platform)
            or (existing_reviews.get(platform) if isinstance(existing_reviews.get(platform), dict) else {}).get("artifact_path")
            or ""
        ).strip()
        for platform in active_platforms
    )
    if not has_required_artifacts:
        if not (
            pre_visual_gate.get("status") == "PASS"
            and pre_visual_gate.get("flux_authorized") is True
            and str(pre_visual_gate.get("selected_candidate") or "") == candidate_id
        ):
            return {}
        visuals = generate_posts.generate_visuals(content, visual_plan=content.get("visual_plan"), platforms=active_platforms)
        content["generated_visuals"] = visuals
    if pre_visual_gate:
        generation = visuals.get("visual_generation") if isinstance(visuals.get("visual_generation"), dict) else {}
        pre_visual_gate["estimated_flux_neurons"] = {
            platform: metadata.get("estimated_neurons")
            for platform, metadata in generation.items()
            if isinstance(metadata, dict) and metadata.get("estimated_neurons") is not None
        }
        pre_visual_gate["image_calls"] = sum(
            1 for metadata in generation.values()
            if isinstance(metadata, dict) and metadata.get("visual_generation_attempted")
        )
        content["pre_visual_gate"] = pre_visual_gate
    if content.get("reel_render_deferred") and visuals.get("instagram"):
        from social import reels

        reel_plan = content.get("reel_plan") if isinstance(content.get("reel_plan"), dict) else {}
        reel_gate = reels.validate_reel_plan(reel_plan)
        content["reel_pre_render_gate"] = reel_gate
        if reel_gate.get("status") == "REEL_READY":
            reel_artifacts = reels.render_reel(reel_plan, source_image=str(visuals["instagram"]))
            reel_artifacts["technical_qa"] = reels.technical_qa(reel_artifacts, reel_plan)
            reel_artifacts["freeze_qa"] = reels.freeze_qa(reel_artifacts, reel_plan)
            reel_artifacts["final_frame_qa"] = reels.final_frame_qa(reel_artifacts)
            reel_artifacts["cover_qa"] = reels.cover_qa(reel_artifacts)
            reel_artifacts["motion_qa"] = reels.motion_qa(reel_plan)
            content["instagram_reel"] = reel_artifacts
            platform_posts = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
            if isinstance(platform_posts.get("instagram"), dict):
                platform_posts["instagram"]["reel"] = reel_artifacts
            content["reel_render_deferred"] = False
    reviews = visuals.get("artifact_reviews") if isinstance(visuals.get("artifact_reviews"), dict) else {}
    for platform in ("facebook", "instagram", "linkedin"):
        if effective_channels.get(platform):
            existing_review = reviews.get(platform) if isinstance(reviews.get(platform), dict) else {}
            artifact_path = str(visuals.get(platform) or existing_review.get("artifact_path") or "")
            allow_native_size = str(((visuals.get("render_engines") or {}).get(platform) or "")) == "cloudflare"
            reviews[platform] = (
                review_rendered_visual(artifact_path, platform, allow_native_size=True)
                if allow_native_size
                else review_rendered_visual(artifact_path, platform)
            )
    visuals["artifact_reviews"] = reviews
    content["artifact_visual_qa"] = reviews
    return reviews


def _pre_visual_gate(content: dict, effective_channels: dict[str, bool], scoring: dict) -> dict:
    """Use existing non-visual governance as the authorization boundary for costly image inference."""
    social_channels = ("facebook", "instagram", "linkedin")
    validation_ok = content.get("validation_status") == "passed"
    duplicates = content.get("duplicate_check") if isinstance(content.get("duplicate_check"), dict) else {}
    duplicate_ok = bool(duplicates.get("ok", True))
    strategy_errors = _strategy_integrity_errors(content)
    presentation_errors = _final_presentation_errors(content, effective_channels)
    evidence = ((content.get("copy") or {}).get("evidence_readiness") or content.get("evidence_readiness") or {})
    evidence_status = str(evidence.get("status") or "READY") if isinstance(evidence, dict) else "READY"
    claims_ready = evidence_status not in {"RESEARCH_REQUIRED", "HIGH_RISK_UNVERIFIED"}
    evidence_ready = evidence_status == "READY"
    decision = content.get("publish_decision") if isinstance(content.get("publish_decision"), dict) else {}
    if not decision:
        decision = decide_publication(
            legacy_score=scoring,
            validation={"passed": validation_ok and not strategy_errors and not presentation_errors, "errors": list(content.get("validation_errors", [])) + strategy_errors + presentation_errors},
            duplicates=duplicates,
            conversion_quality_score=float((content.get("conversion_quality_score") or {}).get("total", 100) or 100),
            orchestrator_quality=content.get("orchestrator_quality"),
            visual_errors=[],
            evidence_readiness=evidence,
        )
    active_social_channels = any(effective_channels.get(platform) for platform in social_channels)
    passed = bool(active_social_channels and validation_ok and duplicate_ok and claims_ready and evidence_ready and not strategy_errors and not presentation_errors and decision.get("publishable"))
    reasons = list(dict.fromkeys(list(decision.get("reasons", [])) + strategy_errors + presentation_errors))
    return {
        "status": "PASS" if passed else "FAIL",
        "strategy_ready": not strategy_errors,
        "copy_ready": validation_ok,
        "claims_ready": claims_ready,
        "evidence_ready": evidence_ready,
        "freshness_ready": duplicate_ok,
        "duplicate_ready": duplicate_ok,
        "campaign_ready": active_social_channels,
        "platform_text_ready": not presentation_errors,
        "selected_candidate": str(content.get("candidate_attempt_id") or content.get("post_id") or ""),
        "estimated_flux_neurons": {},
        "flux_authorized": passed,
        "image_calls": 0,
        "reasons": reasons,
    }


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
    t_preview = time.perf_counter()
    try:
        preview_content = generate_posts.generate(
            slot,
            funnel_stage_override=funnel_stage_override,
            product_id_override=product_id_override,
            pipeline_override=pipeline_override,
            defer_visuals=True,
        )
    except RuntimeError as exc:
        if str(exc) != "no viable opportunities generated":
            raise
        _record_no_viable_opportunity_abstention(
            slot=slot,
            dry_run=dry_run,
            shadow_mode=shadow_mode,
            runtime_metrics=runtime_metrics,
            total_started=t_total,
        )
        return
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
    # Explore the retained field cheaply through bounded candidate revisions,
    # then permit one fresh field with the failed premise excluded.
    decision_budget = max(2, int(os.environ.get("CONTENT_DECISION_MAX_REALIZATIONS", "8")))
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
    evidence_remediation_used = False
    research_recovery_used = False
    research_verified_facts: list[str] = []
    field_replenished = False
    candidate_realizations: dict[str, int] = {}
    active_candidate_key = ""
    candidate_identity_reset = True
    original_research_block: dict | None = None
    remediation_context: dict | None = None
    recovery_story: dict = {"candidate_a": {}, "classification": "", "alternatives_considered": [], "candidate_b_selected": False, "presentation_repairs": []}
    t_generation = time.perf_counter()
    for idx in range(decision_budget):
        if idx > 0:
            try:
                content = generate_posts.generate(
                    slot,
                    funnel_stage_override=funnel_stage_override,
                    product_id_override=locked_product_id,
                    pipeline_override=pipeline_override,
                    approved_strategy=locked_strategy or None,
                    revision_feedback=pending_feedback,
                    remediation_context=remediation_context,
                    verified_facts_override=research_verified_facts or None,
                    defer_visuals=True,
                )
            except RuntimeError as exc:
                if str(exc) != "no viable opportunities generated":
                    raise
                _mark_no_viable_replacement_abstention(content)
                break
            if evidence_remediation_used and remediation_context:
                content["evidence_remediation"] = {**remediation_context, "status": "REMEDIATION_CANDIDATE", "attempt_limit": 1}
                content["recovery_story"] = recovery_story
            if pending_scope == "copy" and _can_carry_forward_visuals(prior_generated_visuals, content, effective_channels):
                content["generated_visuals"] = prior_generated_visuals
                content["revision_reused_components"] = ["generated_visuals"]

        claim_corrections = _enforce_candidate_claim_boundary(content)
        caption_lock_errors = _lock_final_captions(content, effective_channels)
        validation = validate_generated_content(content)
        if caption_lock_errors:
            validation = {
                "passed": False,
                "errors": list(validation.get("errors", [])) + caption_lock_errors,
                "warnings": list(validation.get("warnings", [])),
            }
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
        if candidate_identity_reset or not active_candidate_key:
            active_candidate_key = _logical_candidate_key(content) or f"realization-{idx + 1}"
            candidate_identity_reset = False
        candidate_key = active_candidate_key
        candidate_realizations[candidate_key] = candidate_realizations.get(candidate_key, 0) + 1
        candidate_realization_count = candidate_realizations[candidate_key]

        # Conversion Logic Engine rule (spec section 23): below 80 CQS, automatically
        # attempt improvement before publishing rather than accepting a "warning"-only gate.
        cqs_total = float((content.get("conversion_quality_score") or {}).get("total", 100) or 100)
        publish_decision = decide_publication(
            legacy_score=scoring,
            validation=validation,
            duplicates=duplicates,
            conversion_quality_score=cqs_total,
            orchestrator_quality=content.get("orchestrator_quality"),
            evidence_readiness=((content.get("copy") or {}).get("evidence_readiness") or content.get("evidence_readiness")),
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
        research_required = str(publish_decision.get("decision") or "") == "do_not_publish" and "RESEARCH_REQUIRED" in {
            str(reason) for reason in publish_decision.get("reasons", [])
        }
        research_outcome: dict = {}
        if research_required and not research_recovery_used:
            research_recovery_used = True
            research_outcome = _research_recovery(content)
            content["research_recovery"] = research_outcome
            if research_outcome.get("status") == "RESOLVED":
                research_verified_facts = list(research_outcome.get("verified_facts") or [])
                pending_feedback = [
                    "Use the newly verified evidence precisely; do not add claims beyond its stated scope.",
                    "Keep the existing human reality, reader value, and strategy intact.",
                ]
                pending_scope = "copy"
                original_research_block = _candidate_audit(content)
                attempts.append({
                    "attempt": f"{idx + 1}:research",
                    "decision": "research_resolved_continue_same_candidate",
                    "research_recovery": research_outcome,
                })
                continue
            original_research_block = _candidate_audit(content)
            retryability = "EVIDENCE_SAFE_REMEDIATION"
        elif research_required and not evidence_remediation_used:
            original_research_block = _candidate_audit(content)
            retryability = "EVIDENCE_SAFE_REMEDIATION"
        failure_reasons = list(validation.get("errors", [])) + list(duplicates.get("reasons", [])) + list(publish_decision.get("reasons", []))
        recovery_classification = recovery.classify_failure(failure_reasons)
        strategic_replacement_needed = any(
            marker in str(reason).lower()
            for reason in failure_reasons
            for marker in ("duplicate", "research_required", "unsupported", "semantic", "stale", "campaign_conflict")
        )
        if idx == 0 and strategic_replacement_needed and not evidence_remediation_used:
            original_research_block = _candidate_audit(content)
            retryability = "EVIDENCE_SAFE_REMEDIATION"
        diagnosis = _cognitive_diagnosis(
            content,
            strategy=current_strategy or locked_strategy,
            removed_claims=claim_corrections,
            findings=critic_feedback,
        )
        diagnosis["metacognition"]["attempt_budget_remaining"] = decision_budget - idx - 1

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
                "evidence_remediation": {
                    "used": evidence_remediation_used,
                    "original_research_block": original_research_block,
                },
                "recovery_classification": recovery_classification,
            }
        )

        metacognitive_review = creative_intelligence.metacognitive_review(attempts)
        diagnosis["metacognition"].update(metacognitive_review)
        attempts[-1]["cognitive_diagnosis"] = diagnosis
        content["creative_concept_escalation"] = metacognitive_review

        if publish_decision["publishable"]:
            break

        quality_candidate_shift_needed = (
            candidate_realization_count >= 2
            and idx + 1 < decision_budget
            and not evidence_remediation_used
            and validation.get("passed")
            and duplicates.get("ok")
            and str(((content.get("copy") or {}).get("evidence_readiness") or {}).get("status") or "READY") == "READY"
            and len([finding for finding in critic_feedback if finding in {
                "hook-payoff mismatch", "novelty_angle_weak", "specificity_weak", "intent_response_value_weak",
            }]) >= 2
        )
        if quality_candidate_shift_needed:
            remediation_context = _quality_recovery_context(content, publish_decision, duplicates)
            replacement_candidate = remediation_context.get("replacement_candidate")
            if isinstance(replacement_candidate, dict):
                recovery_story.update({
                    "candidate_a": _candidate_audit(content),
                    "candidate_a_rank": 1,
                    "candidate_a_blockers": list(dict.fromkeys(critic_feedback)),
                    "classification": "QUALITY_CANDIDATE_SHIFT",
                    "candidate_b_selected": True,
                    "candidate_b_rank": replacement_candidate.get("rank"),
                    "alternatives_considered": remediation_context.get("alternatives_considered", []),
                })
                pending_feedback = [
                    "Select a materially different opportunity that improves novelty, specificity, and reader response value.",
                    "Preserve existing claim, evidence, freshness, and governance requirements.",
                ]
                pending_scope = "strategy"
                prior_generated_visuals = {}
                locked_strategy = {}
                locked_product_id = ""
                candidate_identity_reset = True
                continue
            if not field_replenished:
                remediation_context = _field_replenishment_context(content, remediation_context, critic_feedback)
                recovery_story["field_replenished"] = True
                pending_feedback = [
                    "Explore a materially different human reality, content mode, and reader payoff from the retired premise.",
                    "Preserve existing evidence, freshness, and governance requirements.",
                ]
                pending_scope = "strategy"
                prior_generated_visuals = {}
                locked_strategy = {}
                locked_product_id = ""
                field_replenished = True
                candidate_identity_reset = True
                continue
            recovery_story["candidate_field_exhausted"] = True
            break

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
                defer_visuals=True,
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
                evidence_readiness=((content.get("copy") or {}).get("evidence_readiness") or content.get("evidence_readiness")),
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

        # Each selected candidate receives one bounded critic-directed revision.
        if candidate_realization_count == 1 and not evidence_remediation_used and (
            publish_decision["decision"] in {"revise", "regenerate"}
            or (publish_decision["decision"] == "do_not_publish" and retryability in {"RETRYABLE_CONTENT", "EVIDENCE_SAFE_REMEDIATION"})
        ):
            if retryability == "EVIDENCE_SAFE_REMEDIATION":
                evidence_remediation_used = True
                remediation_context = _remediation_context(content, publish_decision, duplicates)
                replacement_candidate = remediation_context.get("replacement_candidate")
                if not isinstance(replacement_candidate, dict):
                    recovery_story.update({
                        "candidate_a": _candidate_audit(content),
                        "candidate_a_rank": 1,
                        "candidate_a_blockers": list(dict.fromkeys(failure_reasons)),
                        "classification": recovery_classification,
                        "candidate_b_selected": False,
                        "alternatives_considered": remediation_context.get("alternatives_considered", []),
                    })
                    content["evidence_remediation"] = {
                        "status": "ABSTAINED_NO_VIABLE_REPLACEMENT",
                        "attempt_limit": 1,
                        **remediation_context,
                    }
                    break
                remediation_context["recovery_mode"] = "STRATEGIC_REPLACEMENT"
                recovery_story.update({
                    "candidate_a": _candidate_audit(content),
                    "candidate_a_rank": 1,
                    "candidate_a_blockers": list(dict.fromkeys(failure_reasons)),
                    "classification": recovery_classification,
                    "candidate_b_selected": True,
                    "candidate_b_rank": replacement_candidate.get("rank"),
                    "alternatives_considered": remediation_context.get("alternatives_considered", []),
                })
                pending_feedback = _evidence_safe_remediation_feedback(content) if research_required else [
                    "Select a materially different opportunity. Preserve all claim, evidence, freshness, and governance requirements.",
                ]
                pending_scope = "strategy"
                prior_generated_visuals = {}
                content["evidence_remediation"] = {
                    "status": "ORIGINAL_BLOCKED",
                    "attempt_limit": 1,
                    **remediation_context,
                }
                locked_strategy = {}
                locked_product_id = ""
                candidate_identity_reset = True
            else:
                pending_feedback = critic_feedback or ["Improve the candidate so it meets the existing critic threshold."]
                pending_scope = diagnosis["repair_scope"] if diagnosis["repair_scope"] != "angle_and_hook_promise" else "strategy"
                prior_generated_visuals = dict(content.get("generated_visuals") or {})
            if retryability != "EVIDENCE_SAFE_REMEDIATION" and diagnosis["metacognition"]["action"] == "RECONSIDER_ANGLE" and locked_strategy:
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
            previous_decision = str(publish_decision["decision"])
            previous_current_findings = list(critic_feedback)
            continue

        if publish_decision["decision"] == "do_not_publish":
            break

        # The governed decision is authoritative for recovery; legacy scoring
        # identifies weak copy but must not terminate viable search territory.
        if idx + 1 >= decision_budget:
            break
    _apply_phase8_budget(runtime_metrics, "generation", time.perf_counter() - t_generation, generation_budget)

    final_validation_ok = content.get("validation_status") == "passed"
    if evidence_remediation_used and remediation_context:
        _finalize_evidence_remediation(content, remediation_context)
        final_validation_ok = content.get("validation_status") == "passed"
    final_score = float(content.get("quality_score") or 0)
    duplicate_ok = bool(content.get("duplicate_check", {}).get("ok", True))
    initial_presentation_errors = _final_presentation_errors(content, effective_channels)
    if final_validation_ok and duplicate_ok and initial_presentation_errors:
        repaired = _repair_final_presentations(content, effective_channels)
        if repaired:
            revalidated = validate_generated_content(content)
            content["validation_status"] = "passed" if revalidated.get("passed") else "failed"
            content["validation_errors"] = list(revalidated.get("errors", []))
            final_validation_ok = bool(revalidated.get("passed"))
            recovery_story["presentation_repairs"] = repaired
    pre_visual_gate = _pre_visual_gate(content, effective_channels, scoring)
    content["pre_visual_gate"] = pre_visual_gate
    if pre_visual_gate["flux_authorized"]:
        _ensure_final_artifact_qa(content, effective_channels)
        artifact_errors = _artifact_visual_errors_by_platform(content, effective_channels)
    else:
        artifact_errors = {}
    for platform, issues in artifact_errors.items():
        effective_channels[platform] = False
        channel_reasons[platform] = f"artifact_visual_qa:{','.join(issues)}"
    visual_gate_errors = _live_visual_gate_errors(content, effective_channels, dry_run or shadow_mode)
    visual_gate_errors.extend(_strategy_integrity_errors(content))
    visual_gate_errors.extend(_final_presentation_errors(content, effective_channels))
    content["artifact_visual_qa"] = (content.get("generated_visuals") or {}).get("artifact_reviews", {})
    content["artifact_visual_qa_failures"] = artifact_errors
    if visual_gate_errors:
        content["validation_status"] = "failed"
        content["validation_errors"] = list(content.get("validation_errors", [])) + visual_gate_errors
        content.setdefault("quality_warnings", []).append("live_visual_gate_blocked")
        final_validation_ok = False

    final_cqs_total = float((content.get("conversion_quality_score") or {}).get("total", 100) or 100)
    if final_cqs_total < 80:
        content.setdefault("quality_warnings", []).append(f"cqs_below_target_after_retries:{final_cqs_total}")
        print(f"[QUALITY] Published with Conversion Quality Score {final_cqs_total} after exhausting retries (target 80).")

    final_decision = decide_publication(
        legacy_score=scoring,
        validation={"passed": final_validation_ok, "errors": content.get("validation_errors", [])},
        duplicates=content.get("duplicate_check", {}),
        conversion_quality_score=final_cqs_total,
        orchestrator_quality=content.get("orchestrator_quality"),
        visual_errors=visual_gate_errors,
        evidence_readiness=((content.get("copy") or {}).get("evidence_readiness") or content.get("evidence_readiness")),
    )
    content["publish_decision"] = final_decision
    content["recovery_story"] = recovery_story
    if evidence_remediation_used and isinstance(content.get("evidence_remediation"), dict):
        content["evidence_remediation"]["final_outcome"] = final_decision.get("decision")
    content["final_memory"] = _final_memory_record(content, str(final_decision.get("decision") or ""))
    if not final_decision["publishable"] and not shadow_mode:
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
        print("\n=== Done (skipped) ===\n")
        return

    if shadow_mode:
        history = generate_posts.load_history()
        run_started = datetime.now(timezone.utc).isoformat()
        platform_records = _shadow_platform_records(content, run_started, effective_channels)
        _apply_phase8_budget(runtime_metrics, "total", time.perf_counter() - t_total, total_budget)
        shadow_status = "shadow_completed" if final_decision["publishable"] else "shadow_abstained_governance"
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
            "status": shadow_status, "decision_record": _shadow_decision_record(content),
            "channel_reasons": channel_reasons, "phase5_channel_readiness": phase5_readiness,
            "phase6_learning": _build_phase6_learning(content=content, platform_records=platform_records, errors=list(final_decision.get("reasons", [])), status=shadow_status),
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
        "product_image_url": content.get("product_image_url", ""),
        "generated_visuals": content.get("generated_visuals", {}),
        "visual_plan": content.get("visual_plan", {}),
        "primary_publish_image_url": content.get("primary_publish_image_url", ""),
        "copy_generation_source": content.get("copy_generation_source", "unknown"),
        "quality_score": content.get("quality_score"),
        "quality_component_scores": content.get("quality_component_scores", {}),
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
        for platform, result in (("facebook", fb_result), ("instagram", ig_result)):
            if str(result.get("id") or "").strip() and not dry_run:
                _mark_publish_postprocess_complete(content, platform)
    except Exception as exc:
        for platform, result in (("facebook", fb_result), ("instagram", ig_result)):
            if str(result.get("id") or "").strip() and not dry_run:
                _mark_publish_postprocess_error(content, platform, exc)
                raise RuntimeError(f"published_persistence_error:{platform}:{exc}") from exc
        raise

    if errors:
        raise RuntimeError(" | ".join(errors))

    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
