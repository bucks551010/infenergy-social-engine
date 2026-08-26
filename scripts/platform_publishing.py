from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlatformCapability:
    id: str
    formats: tuple[str, ...]
    requires_video: bool
    supports_scheduling: bool
    supports_status: bool
    feature_flag: str | None
    required_credentials: tuple[str, ...]


CAPABILITIES = {
    "facebook": PlatformCapability("facebook", ("static_image", "carousel"), False, True, False, None, ("META_PAGE_ID", "META_PAGE_ACCESS_TOKEN")),
    "instagram": PlatformCapability("instagram", ("static_image", "carousel", "short_video"), False, True, True, None, ("META_IG_USER_ID", "META_PAGE_ACCESS_TOKEN")),
    "linkedin": PlatformCapability("linkedin", ("static_image", "carousel"), False, True, False, None, ("LINKEDIN_ACCESS_TOKEN",)),
    "youtube": PlatformCapability("youtube", ("short_video", "long_video"), True, True, True, "YOUTUBE_PUBLISHING_ENABLED", ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")),
    "tiktok": PlatformCapability("tiktok", ("short_video",), True, True, True, "TIKTOK_PUBLISHING_ENABLED", ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")),
}


class PublicationError(RuntimeError):
    def __init__(self, provider: str, category: str, safe_message: str, *, retryable: bool = False):
        super().__init__(safe_message)
        self.provider = provider
        self.category = category
        self.safe_message = safe_message
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "category": self.category, "safe_message": self.safe_message, "retryable": self.retryable}


def _configured(name: str) -> bool:
    value = os.environ.get(name, "").strip()
    return bool(value and value.upper() not in {"REPLACE_ME", "SET_ME"})


def connection_health(platform: str) -> dict[str, Any]:
    capability = CAPABILITIES[platform]
    flag_enabled = capability.feature_flag is None or os.environ.get(capability.feature_flag, "false").strip().lower() == "true"
    missing = [name for name in capability.required_credentials if not _configured(name)]
    if not flag_enabled:
        status = "DISABLED"
    elif missing:
        status = "REAUTH_REQUIRED"
    else:
        status = "CONNECTED"
    return {
        "platform": platform,
        "status": status,
        "publishing_enabled": flag_enabled and not missing,
        "missing_configuration": missing,
        "capabilities": {
            "formats": list(capability.formats),
            "scheduling": capability.supports_scheduling,
            "status_monitoring": capability.supports_status,
        },
    }


def list_platforms() -> list[dict[str, Any]]:
    return [connection_health(platform) for platform in CAPABILITIES]


def validate_content(platform: str, content: dict[str, Any]) -> None:
    if platform not in CAPABILITIES:
        raise PublicationError(platform, "CONTENT_VALIDATION_FAILURE", "Unsupported publishing platform")
    capability = CAPABILITIES[platform]
    if capability.requires_video:
        reel = content.get("instagram_reel") if isinstance(content.get("instagram_reel"), dict) else {}
        urls = reel.get("public_urls") if isinstance(reel.get("public_urls"), dict) else {}
        video_url = str(urls.get("video") or "").strip()
        if not video_url.startswith("https://") or not video_url.lower().split("?", 1)[0].endswith(".mp4"):
            raise PublicationError(platform, "MEDIA_FAILURE", f"{platform} requires a public HTTPS MP4 Reel")
    health = connection_health(platform)
    if platform in {"youtube", "tiktok"} and health["status"] == "DISABLED":
        raise PublicationError(platform, "PLATFORM_POLICY_FAILURE", f"{platform} publishing is disabled")
    if platform in {"youtube", "tiktok"} and health["status"] != "CONNECTED":
        raise PublicationError(platform, "AUTH_FAILURE", f"{platform} account requires configuration")


def publish(platform: str, content: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    if not dry_run:
        validate_content(platform, content)
    module = importlib.import_module(f"publish_{platform}")
    try:
        if platform in {"facebook", "linkedin"}:
            result = module.publish(content, "", dry_run=dry_run)
        else:
            result = module.publish(content, dry_run=dry_run)
    except PublicationError:
        raise
    except Exception as exc:
        text = str(exc).lower()
        if any(token in text for token in ("401", "403", "oauth", "token", "credential")):
            category, retryable = "AUTH_FAILURE", False
        elif any(token in text for token in ("429", "quota", "rate limit")):
            category, retryable = "RATE_LIMIT", True
        elif any(token in text for token in ("timeout", "502", "503", "504", "connection")):
            category, retryable = "NETWORK_FAILURE", True
        elif any(token in text for token in ("video", "codec", "media", "resolution")):
            category, retryable = "MEDIA_FAILURE", False
        else:
            category, retryable = "UNKNOWN_FAILURE", False
        raise PublicationError(platform, category, str(exc), retryable=retryable) from exc
    if not isinstance(result, dict) or not str(result.get("id") or "").strip():
        raise PublicationError(platform, "PLATFORM_PROCESSING_FAILURE", "Publisher returned no platform identifier")
    return result


def get_status(platform: str, platform_post_id: str) -> dict[str, Any]:
    if platform not in {"youtube", "tiktok"}:
        return {"platform": platform, "id": platform_post_id, "status": "STATUS_NOT_SUPPORTED"}
    module = importlib.import_module(f"publish_{platform}")
    return module.get_status(platform_post_id)
