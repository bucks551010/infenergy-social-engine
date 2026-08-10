import os
import time
import re
import requests
from urllib.parse import urljoin

import publish_wordpress
from url_safety import is_safe_http_url

GRAPH_BASE = "https://graph.facebook.com/v26.0"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _required_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _post_with_retry(url: str, data: dict, timeout: int = 30) -> requests.Response:
    attempts = [0.7, 1.5, 3.0]
    last: requests.Response | None = None
    for idx, wait_s in enumerate(attempts, start=1):
        resp = requests.post(url, data=data, timeout=timeout)
        last = resp
        if resp.ok:
            return resp

        if resp.status_code not in (429, 500, 502, 503, 504):
            return resp

        if idx < len(attempts):
            time.sleep(wait_s)

    return last if last is not None else requests.Response()


def _graph_error_text(resp: requests.Response) -> str:
    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        payload = {}
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        message = str(err.get("message", "")).strip()
        code = str(err.get("code", "")).strip()
        subcode = str(err.get("error_subcode", "")).strip()
        parts = [p for p in [message, f"code={code}" if code else "", f"subcode={subcode}" if subcode else ""] if p]
        if parts:
            return " | ".join(parts)
    return (resp.text or "").strip()[:1000]


def _wait_for_media_container(ig_user_id: str, creation_id: str, access_token: str, timeout_sec: int = 45) -> tuple[bool, str]:
    deadline = time.time() + timeout_sec
    last_status = ""
    while time.time() < deadline:
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/{creation_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": access_token,
                },
                timeout=20,
            )
            if not resp.ok:
                return False, f"container_status_http_{resp.status_code}: {_graph_error_text(resp)}"
            data = resp.json() if resp.content else {}
            status_code = str(data.get("status_code", "")).strip().upper()
            status = str(data.get("status", "")).strip().upper()
            last_status = status_code or status
            if status_code == "FINISHED" or status == "FINISHED":
                return True, "finished"
            if status_code in {"ERROR", "EXPIRED"} or status in {"ERROR", "EXPIRED"}:
                return False, last_status or "container_not_ready"
        except Exception as e:
            return False, f"container_status_exception:{e}"
        time.sleep(2)
    return False, f"container_not_ready_timeout:last_status={last_status or 'unknown'}"


def _is_valid_public_image(url: str) -> bool:
    if not url:
        return False
    u = str(url).strip().lower()
    if not u.startswith("http"):
        return False
    if any(x in u for x in ("placeholder", "no-image", "default")):
        return False
    return True


def _is_reachable_image_url(url: str, timeout: int = 10) -> bool:
    if not is_safe_http_url(url):
        return False
    try:
        head = requests.head(url, allow_redirects=True, timeout=timeout)
        if head.status_code < 400:
            ctype = (head.headers.get("Content-Type") or "").lower()
            if not ctype or "image" in ctype or "octet-stream" in ctype:
                return True
        get_resp = requests.get(url, allow_redirects=True, timeout=timeout, stream=True)
        try:
            if get_resp.status_code >= 400:
                return False
            ctype = (get_resp.headers.get("Content-Type") or "").lower()
            return "image" in ctype or "octet-stream" in ctype
        finally:
            get_resp.close()
    except Exception:
        return False


def _dedupe_keep_order(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _extract_page_image_candidate(page_url: str, timeout: int = 15) -> str:
    if not page_url or not str(page_url).strip().lower().startswith("http"):
        return ""
    if not is_safe_http_url(page_url):
        return ""
    try:
        resp = requests.get(page_url, timeout=timeout)
        if resp.status_code >= 400:
            return ""
        html = resp.text or ""
        # Prefer OpenGraph image; fall back to Twitter image.
        patterns = [
            r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
            r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
            r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
            r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']twitter:image["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html, flags=re.IGNORECASE)
            if not m:
                continue
            candidate = str(m.group(1) or "").strip()
            if not candidate:
                continue
            candidate = urljoin(page_url, candidate)
            if _is_valid_public_image(candidate):
                return candidate
        return ""
    except Exception:
        return ""


def publish(content: dict, dry_run: bool = False) -> dict:
    ig_default_image = _env("IG_DEFAULT_IMAGE_URL")
    validate_urls = _env("IG_VALIDATE_IMAGE_URLS", "true").lower() in ("1", "true", "yes", "on")
    generated_image_path = str((content.get("generated_visuals") or {}).get("instagram", "")).strip()
    primary_publish_image_url = str(content.get("primary_publish_image_url", "")).strip()

    candidates = []
    if generated_image_path and os.path.exists(generated_image_path):
        try:
            if hasattr(publish_wordpress, "upload_media"):
                media_result = publish_wordpress.upload_media(generated_image_path, dry_run=dry_run)
                hosted_generated = str(media_result.get("source_url", "")).strip()
                if _is_valid_public_image(hosted_generated):
                    candidates.append(hosted_generated)
            else:
                print("[Instagram] Warning: publish_wordpress.upload_media unavailable; skipping generated visual upload")
        except Exception as e:
            print(f"[Instagram] Warning: generated visual upload failed, falling back to catalog imagery: {e}")
    if _is_valid_public_image(primary_publish_image_url):
        candidates.append(primary_publish_image_url)
    product_image = content.get("product_image_url", "")
    if _is_valid_public_image(product_image):
        candidates.append(product_image)
    for c in content.get("product_image_candidates", []) or []:
        if _is_valid_public_image(c):
            candidates.append(c)
    for c in content.get("category_image_candidates", []) or []:
        if _is_valid_public_image(c):
            candidates.append(c)
    if _is_valid_public_image(ig_default_image):
        candidates.append(ig_default_image)
    destination_url = str(content.get("destination_url") or "").strip()
    page_image_candidate = _extract_page_image_candidate(destination_url)
    if _is_valid_public_image(page_image_candidate):
        candidates.append(page_image_candidate)
    candidates = _dedupe_keep_order(candidates)

    image_url = ""
    if validate_urls:
        for candidate in candidates:
            if _is_reachable_image_url(candidate):
                image_url = candidate
                break
        if not image_url and candidates:
            image_url = candidates[0]
            print("[Instagram] Warning: no candidate passed preflight, using first candidate anyway")
    else:
        image_url = candidates[0] if candidates else ""

    if not image_url:
        print("[Instagram] Skipped: no valid image URL candidates")
        return {
            "id": "skipped",
            "reason": "no_valid_image_url_candidates",
            "candidate_count": len(candidates),
        }

    caption = content["ig_caption"]

    if dry_run:
        print(f"[DRY RUN] Instagram: would post:\n{caption[:150]}...\n")
        return {"id": "dry-run"}

    # Step 1: create media container
    ig_user_id = _required_env("META_IG_USER_ID")
    access_token = _required_env("META_PAGE_ACCESS_TOKEN")
    resp = _post_with_retry(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"instagram_media_create_failed_http_{resp.status_code}: {_graph_error_text(resp)}")
    creation_id = resp.json()["id"]

    ready, ready_reason = _wait_for_media_container(ig_user_id, creation_id, access_token)
    if not ready:
        raise RuntimeError(f"instagram_media_not_ready:{ready_reason}")

    # Step 2: publish the container
    resp2 = _post_with_retry(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        {
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=30,
    )
    if not resp2.ok:
        raise RuntimeError(f"instagram_media_publish_failed_http_{resp2.status_code}: {_graph_error_text(resp2)}")
    data = resp2.json()
    print(f"[Instagram] Posted: {data['id']}")
    return {"id": data["id"]}
