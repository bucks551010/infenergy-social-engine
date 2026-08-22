"""Publish already-final content from the durable outbox without regenerating it."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import publish_facebook
import publish_instagram
import publish_linkedin
from social_visuals import generate_strict_gemini_image, review_rendered_visual
from content_operations import (
    PLATFORMS,
    begin_platform_transaction,
    claim_due,
    complete_platform_transaction,
    finalize_outbox,
    platform_transaction,
    recover_outbox,
    release_outbox,
    update_claimed_package,
)

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def _delivery_enforced() -> bool:
    return str(os.environ.get("ENFORCE_SOCIAL_DELIVERY", "false")).strip().lower() in {"1", "true", "yes", "on"}


def _enabled_platforms(package: dict[str, Any]) -> list[str]:
    if _delivery_enforced():
        return list(PLATFORMS)
    routing = package.get("routing") if isinstance(package.get("routing"), dict) else {}
    configured = routing.get("platforms") if isinstance(routing.get("platforms"), list) else []
    return [platform for platform in PLATFORMS if platform in configured]


def _payload(package: dict[str, Any], platform: str) -> dict[str, Any]:
    platform_posts = package.get("platform_posts") if isinstance(package.get("platform_posts"), dict) else {}
    post = platform_posts.get(platform) if isinstance(platform_posts.get(platform), dict) else {}
    carousel_media = [
        str(asset.get("local_path") if platform == "facebook" else asset.get("public_url") or "").strip()
        for asset in package.get("carousel_assets", []) or []
        if isinstance(asset, dict)
    ]
    return {
        "final_caption": str(post.get("final_caption") or post.get("caption") or ""),
        "destination_url": str(post.get("destination_url") or package.get("destination_url") or ""),
        "utm_url": str(post.get("utm_url") or post.get("destination_url") or package.get("destination_url") or ""),
        "media": str((package.get("generated_visuals") or {}).get(platform) or ""),
        "carousel_media": [media for media in carousel_media if media] if platform in {"facebook", "instagram"} else [],
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


def _public_media_url(file_name: str) -> str:
    base = str(os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "").strip().rstrip("/")
    if base and not base.startswith("http"):
        base = f"https://{base}"
    if not base:
        raise RuntimeError("public_media_base_url_missing")
    return f"{base}/media/{file_name}"


def _gemini_assets_ready(package: dict[str, Any], required_count: int) -> bool:
    generation = package.get("gemini_generation") if isinstance(package.get("gemini_generation"), dict) else {}
    assets = generation.get("assets") if isinstance(generation.get("assets"), list) else []
    return (
        generation.get("status") == "COMPLETE"
        and len(assets) == required_count
        and all(
            isinstance(asset, dict)
            and asset.get("render_engine") == "gemini"
            and os.path.isfile(str(asset.get("local_path") or ""))
            and str(asset.get("public_url") or "").startswith("http")
            and review_rendered_visual(str(asset.get("local_path") or ""), "instagram").get("verdict") == "PASS"
            for asset in assets
        )
    )


def _strict_publish_artifact_error(package: dict[str, Any], platform: str) -> str:
    generation = package.get("gemini_generation") if isinstance(package.get("gemini_generation"), dict) else {}
    if generation.get("strict_provider") is not True:
        return ""
    visuals = package.get("generated_visuals") if isinstance(package.get("generated_visuals"), dict) else {}
    artifact_path = str(visuals.get(platform) or "").strip()
    review = review_rendered_visual(artifact_path, platform)
    if review.get("verdict") == "PASS":
        return ""
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    return f"{platform}_strict_artifact_invalid:{','.join(str(issue) for issue in issues) or 'artifact_review_failed'}"


def _prepare_gemini_assets(package: dict[str, Any], data_dir: str) -> dict[str, Any]:
    generation = package.get("gemini_generation") if isinstance(package.get("gemini_generation"), dict) else {}
    prompts = generation.get("prompts") if isinstance(generation.get("prompts"), list) else []
    required_count = int(generation.get("required_image_count") or 0)
    if generation.get("provider") != "gemini" or generation.get("fallback_allowed") is not False:
        raise RuntimeError("strict_gemini_generation_contract_missing")
    if required_count < 1 or len(prompts) != required_count:
        raise RuntimeError("gemini_prompt_count_mismatch")
    if _gemini_assets_ready(package, required_count):
        return package

    public_dir = os.path.join(data_dir, "public_media")
    os.makedirs(public_dir, exist_ok=True)
    post_id = str(package.get("post_id") or package.get("content_id") or "monthly")
    assets: list[dict[str, Any]] = []
    for prompt_plan in prompts:
        if not isinstance(prompt_plan, dict):
            raise RuntimeError("gemini_prompt_invalid")
        slide_index = int(prompt_plan.get("slide_index") or len(assets) + 1)
        file_name = f"{post_id}_gemini_{slide_index}.png"
        output_path = os.path.abspath(os.path.join(public_dir, file_name))
        result = generate_strict_gemini_image(
            package,
            prompt_plan=prompt_plan,
            output_path=output_path,
            platform="instagram",
        )
        result.update({
            "slide_index": slide_index,
            "role": str(prompt_plan.get("role") or "image"),
            "public_url": _public_media_url(file_name),
        })
        assets.append(result)

    if len(assets) != required_count or any(asset.get("render_engine") != "gemini" for asset in assets):
        raise RuntimeError("strict_gemini_generation_incomplete")
    generation.update({
        "status": "COMPLETE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "actual_image_count": len(assets),
        "assets": assets,
    })
    package["gemini_generation"] = generation
    package["carousel_assets"] = assets if len(assets) > 1 else []
    first = assets[0]
    package["primary_publish_image_url"] = first["public_url"]
    package["generated_visuals"] = {
        "facebook": first["local_path"],
        "instagram": first["local_path"],
        "linkedin": first["local_path"],
        "render_engine": "gemini",
        "render_engines": {platform: "gemini" for platform in PLATFORMS},
        "artifact_reviews": {platform: first["review"] for platform in PLATFORMS},
        "gemini_generated_at_utc": generation["generated_at_utc"],
    }
    return package


def _creative_package_error(package: dict[str, Any], platforms: list[str]) -> str:
    visuals = package.get("generated_visuals") if isinstance(package.get("generated_visuals"), dict) else {}
    engines = visuals.get("render_engines") if isinstance(visuals.get("render_engines"), dict) else {}
    reviews = visuals.get("artifact_reviews") if isinstance(visuals.get("artifact_reviews"), dict) else {}
    visual_plan = package.get("visual_plan") if isinstance(package.get("visual_plan"), dict) else {}
    route = str(visual_plan.get("creative_route") or visual_plan.get("visual_format") or "").strip().upper()
    explicit_packshot = route in {"PACKSHOT", "PACKSHOT_ONLY", "PREMIUM_PRODUCT_HERO"}
    for platform in platforms:
        review = reviews.get(platform) if isinstance(reviews.get(platform), dict) else {}
        if review.get("verdict") == "REGENERATE_VISUAL":
            return f"{platform}_visual_requires_recovery"
        if str(engines.get(platform) or "") == "approved_product_photo" and not explicit_packshot:
            return f"{platform}_packshot_only_without_explicit_route"
    return ""


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
    creative_error = "" if _delivery_enforced() else _creative_package_error(package, platforms)
    if creative_error:
        recover_outbox(data_dir, outbox_id, creative_error)
        return {"status": "CONTENT_RECOVERING", "outbox_id": outbox_id, "error": creative_error}
    generation = package.get("gemini_generation") if isinstance(package.get("gemini_generation"), dict) else {}
    if generation.get("strict_provider") is True:
        try:
            package = _prepare_gemini_assets(package, data_dir)
            update_claimed_package(data_dir, outbox_id, package)
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
            recover_outbox(data_dir, outbox_id, error)
            return {"status": "CONTENT_RECOVERING", "outbox_id": outbox_id, "error": error}

    results: dict[str, Any] = {}
    retry_errors: list[str] = []
    ambiguous: list[str] = []
    for platform in platforms:
        existing = platform_transaction(data_dir, outbox_id, platform)
        if existing.get("state") == "CONFIRMED_SUCCESS":
            results[platform] = {"state": "CONFIRMED_SUCCESS", "external_id": existing.get("external_id"), "reused": True}
            continue
        if existing.get("state") in {"AMBIGUOUS", "AUTH_ACTION_REQUIRED"} and not _delivery_enforced():
            ambiguous.append(f"{platform}:{existing.get('state')}")
            results[platform] = existing
            continue

        artifact_error = _strict_publish_artifact_error(package, platform)
        if artifact_error:
            recover_outbox(data_dir, outbox_id, artifact_error)
            return {"status": "CONTENT_RECOVERING", "outbox_id": outbox_id, "platforms": results, "error": artifact_error}

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
