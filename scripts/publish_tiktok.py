from __future__ import annotations

import os
from typing import Any

import requests

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
PUBLISH_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or value.upper() in {"REPLACE_ME", "SET_ME"}:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _access_token() -> str:
    configured = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    if configured and configured.upper() not in {"REPLACE_ME", "SET_ME"}:
        return configured
    response = requests.post(
        TOKEN_URL,
        data={
            "client_key": _required("TIKTOK_CLIENT_KEY"),
            "client_secret": _required("TIKTOK_CLIENT_SECRET"),
            "refresh_token": _required("TIKTOK_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    token = str(response.json().get("access_token") or "").strip()
    if not token:
        raise RuntimeError("tiktok_oauth_refresh_returned_no_access_token")
    return token


def _video_url(content: dict[str, Any]) -> str:
    reel = content.get("instagram_reel") if isinstance(content.get("instagram_reel"), dict) else {}
    urls = reel.get("public_urls") if isinstance(reel.get("public_urls"), dict) else {}
    url = str(urls.get("video") or "").strip()
    if not url.startswith("https://"):
        raise RuntimeError("tiktok_requires_public_https_video_url")
    return url


def publish(content: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    video_url = _video_url(content)
    title = str(content.get("tiktok_caption") or content.get("ig_caption") or content.get("fb_caption") or "Infenergy Story").strip()[:2200]
    if dry_run:
        return {"id": "dry-run", "media_type": "VIDEO", "platform": "tiktok"}
    token = _access_token()
    response = requests.post(
        PUBLISH_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json={
            "post_info": {
                "title": title,
                "privacy_level": os.environ.get("TIKTOK_PRIVACY_LEVEL", "PUBLIC_TO_EVERYONE").strip() or "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    if error and str(error.get("code") or "ok") != "ok":
        raise RuntimeError(f"tiktok_publish_error:{error.get('code')}:{error.get('message')}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    publish_id = str(data.get("publish_id") or "").strip()
    if not publish_id:
        raise RuntimeError("tiktok_publish_returned_no_publish_id")
    return {"id": publish_id, "publish_id": publish_id, "media_type": "VIDEO", "status": "PROCESSING"}


def get_status(publish_id: str) -> dict[str, Any]:
    response = requests.post(
        STATUS_URL,
        headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json; charset=UTF-8"},
        json={"publish_id": publish_id},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    if error and str(error.get("code") or "ok") != "ok":
        raise RuntimeError(f"tiktok_status_error:{error.get('code')}:{error.get('message')}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "platform": "tiktok", "id": publish_id,
        "status": str(data.get("status") or "UNKNOWN").upper(),
        "fail_reason": data.get("fail_reason"), "public_post_ids": data.get("publicaly_available_post_id") or [],
    }
