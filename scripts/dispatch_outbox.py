"""Publish already-final content from the durable outbox without regenerating it."""

from __future__ import annotations

import json
import os
from typing import Any

import publish_facebook
import publish_instagram
import publish_linkedin
from content_operations import (
    PLATFORMS,
    begin_platform_transaction,
    claim_due,
    complete_platform_transaction,
    finalize_outbox,
    platform_transaction,
    release_outbox,
)

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def _enabled_platforms(package: dict[str, Any]) -> list[str]:
    routing = package.get("routing") if isinstance(package.get("routing"), dict) else {}
    configured = routing.get("platforms") if isinstance(routing.get("platforms"), list) else []
    return [platform for platform in PLATFORMS if platform in configured]


def _payload(package: dict[str, Any], platform: str) -> dict[str, Any]:
    platform_posts = package.get("platform_posts") if isinstance(package.get("platform_posts"), dict) else {}
    post = platform_posts.get(platform) if isinstance(platform_posts.get(platform), dict) else {}
    return {
        "final_caption": str(post.get("final_caption") or post.get("caption") or ""),
        "destination_url": str(post.get("destination_url") or package.get("destination_url") or ""),
        "utm_url": str(post.get("utm_url") or post.get("destination_url") or package.get("destination_url") or ""),
        "media": str((package.get("generated_visuals") or {}).get(platform) or ""),
    }


def _publish(package: dict[str, Any], platform: str) -> dict[str, Any]:
    post = ((package.get("platform_posts") or {}).get(platform) or {})
    destination = str(post.get("utm_url") or post.get("destination_url") or package.get("destination_url") or "")
    if platform == "facebook":
        return publish_facebook.publish(package, destination, dry_run=False)
    if platform == "instagram":
        return publish_instagram.publish(package, dry_run=False)
    if platform == "linkedin":
        return publish_linkedin.publish(package, destination, dry_run=False)
    raise ValueError(f"unsupported platform: {platform}")


def dispatch_due(*, data_dir: str = DATA_DIR, now_utc: str | None = None) -> dict[str, Any]:
    claimed = claim_due(data_dir, now_utc)
    if not claimed:
        return {"status": "IDLE", "detail": "no_due_ready_content"}

    outbox_id = str(claimed["outbox_id"])
    package = claimed["package"]
    platforms = _enabled_platforms(package)
    if not platforms:
        finalize_outbox(data_dir, outbox_id, status="EXTERNAL_ACTION_REQUIRED", error="no_routed_platforms")
        return {"status": "EXTERNAL_ACTION_REQUIRED", "outbox_id": outbox_id, "error": "no_routed_platforms"}

    results: dict[str, Any] = {}
    retry_errors: list[str] = []
    ambiguous: list[str] = []
    for platform in platforms:
        existing = platform_transaction(data_dir, outbox_id, platform)
        if existing.get("state") == "CONFIRMED_SUCCESS":
            results[platform] = {"state": "CONFIRMED_SUCCESS", "external_id": existing.get("external_id"), "reused": True}
            continue
        if existing.get("state") in {"AMBIGUOUS", "AUTH_ACTION_REQUIRED"}:
            ambiguous.append(f"{platform}:{existing.get('state')}")
            results[platform] = existing
            continue

        payload = _payload(package, platform)
        begin_platform_transaction(data_dir, outbox_id=outbox_id, platform=platform, payload=payload)
        try:
            response = _publish(package, platform)
            external_id = str(response.get("id") or "").strip()
            if not external_id or external_id in {"skipped", "dry-run"}:
                reason = str(response.get("reason") or "publisher_did_not_confirm_success")
                complete_platform_transaction(
                    data_dir,
                    outbox_id=outbox_id,
                    platform=platform,
                    state="CONFIRMED_FAILURE",
                    provider_response=response,
                    error=reason,
                )
                retry_errors.append(f"{platform}:{reason}")
                results[platform] = {"state": "CONFIRMED_FAILURE", "error": reason}
                continue
            complete_platform_transaction(
                data_dir,
                outbox_id=outbox_id,
                platform=platform,
                state="CONFIRMED_SUCCESS",
                external_id=external_id,
                provider_response=response,
            )
            results[platform] = {"state": "CONFIRMED_SUCCESS", "external_id": external_id}
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
            state = "AUTH_ACTION_REQUIRED" if any(token in error.lower() for token in ("token", "oauth", "unauthorized", "forbidden")) else "CONFIRMED_FAILURE"
            complete_platform_transaction(
                data_dir,
                outbox_id=outbox_id,
                platform=platform,
                state=state,
                error=error,
            )
            if state == "AUTH_ACTION_REQUIRED":
                ambiguous.append(f"{platform}:{error}")
            else:
                retry_errors.append(f"{platform}:{error}")
            results[platform] = {"state": state, "error": error}

    if ambiguous:
        error = " | ".join(ambiguous)
        finalize_outbox(data_dir, outbox_id, status="EXTERNAL_ACTION_REQUIRED", error=error)
        return {"status": "EXTERNAL_ACTION_REQUIRED", "outbox_id": outbox_id, "platforms": results, "error": error}
    if retry_errors:
        error = " | ".join(retry_errors)
        release_outbox(data_dir, outbox_id, error)
        return {"status": "PARTIAL_RETRY", "outbox_id": outbox_id, "platforms": results, "error": error}

    finalize_outbox(data_dir, outbox_id, status="PUBLISHED")
    return {"status": "PUBLISHED", "outbox_id": outbox_id, "platforms": results}


def main() -> None:
    print(json.dumps(dispatch_due(), ensure_ascii=True))


if __name__ == "__main__":
    main()
