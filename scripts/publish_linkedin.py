import os
import time
import requests
from datetime import datetime, timezone

LI_API = "https://api.linkedin.com/v2"
DEFAULT_LINKEDIN_VERSION = datetime.now(timezone.utc).strftime("%Y%m")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _required_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _headers(include_json: bool = False) -> dict:
    token = _required_env("LINKEDIN_ACCESS_TOKEN")
    linkedin_version = _env("LINKEDIN_VERSION", DEFAULT_LINKEDIN_VERSION)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": linkedin_version,
    }
    if include_json:
        headers["Content-Type"] = "application/json"
    return headers


def _raise_with_body(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        body = ""
        try:
            body = resp.text[:1000]
        except Exception:
            body = "<unavailable>"
        raise requests.HTTPError(f"{e} | response={body}") from e


def _response_body(resp: requests.Response) -> str:
    try:
        return resp.text[:1000]
    except Exception:
        return "<unavailable>"


def _resolve_author_urn() -> str:
    urn = _env("LINKEDIN_AUTHOR_URN")
    if urn:
        return urn

    headers = _headers()
    errors = []

    # First try OpenID userinfo (works when openid/profile scopes are granted).
    resp_userinfo = requests.get(f"{LI_API}/userinfo", headers=headers, timeout=15)
    if resp_userinfo.ok:
        sub = resp_userinfo.json().get("sub", "").strip()
        if sub:
            return f"urn:li:person:{sub}"
    else:
        errors.append(f"userinfo={resp_userinfo.status_code}:{_response_body(resp_userinfo)}")

    # Fallback to legacy /me endpoint (works with r_liteprofile).
    resp_me = requests.get(f"{LI_API}/me", headers=headers, timeout=15)
    if resp_me.ok:
        person_id = resp_me.json().get("id", "").strip()
        if person_id:
            return f"urn:li:person:{person_id}"
    else:
        errors.append(f"me={resp_me.status_code}:{_response_body(resp_me)}")

    details = " | ".join(errors) if errors else "No author identifier returned"
    raise RuntimeError(
        "Unable to resolve LinkedIn author URN automatically. "
        "Set LINKEDIN_AUTHOR_URN in env (e.g., urn:li:person:XXXX or urn:li:organization:XXXX). "
        f"Diagnostics: {details}"
    )


def _post_with_retry(url: str, *, headers: dict, json_payload: dict, timeout: int = 30) -> requests.Response:
    attempts = [0.7, 1.5, 3.0]
    last: requests.Response | None = None
    for idx, wait_s in enumerate(attempts, start=1):
        resp = requests.post(url, headers=headers, json=json_payload, timeout=timeout)
        last = resp
        if resp.ok:
            return resp

        status = resp.status_code
        body = _response_body(resp).lower()
        if status not in (429, 500, 502, 503, 504):
            return resp

        if "throttle" not in body and "rate" not in body and status != 429 and status < 500:
            return resp

        if idx < len(attempts):
            time.sleep(wait_s)

    return last if last is not None else requests.Response()


def _is_duplicate_error(resp: requests.Response) -> bool:
    if resp.status_code not in (400, 409, 422):
        return False
    body = _response_body(resp).lower()
    return "duplicate" in body or "already exists" in body or "same content" in body


def publish(content: dict, wp_link: str, dry_run: bool = False) -> dict:
    text = f"{content['li_text']}\n\n{wp_link}"

    if dry_run:
        print(f"[DRY RUN] LinkedIn: would post:\n{text[:150]}...\n")
        return {"id": "dry-run"}

    author = _resolve_author_urn()

    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    headers = _headers(include_json=True)
    resp = _post_with_retry(
        f"{LI_API}/ugcPosts",
        headers=headers,
        json_payload=payload,
        timeout=30,
    )
    if _is_duplicate_error(resp):
        # Retry once with a minimal variant to avoid duplicate-content rejection.
        variant = content.get("topic", "power update")
        payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"] = (
            f"{text}\n\nUpdate: {variant}"
        )
        resp = _post_with_retry(
            f"{LI_API}/ugcPosts",
            headers=headers,
            json_payload=payload,
            timeout=30,
        )
    _raise_with_body(resp)
    post_id = resp.headers.get("x-restli-id", "posted")
    print(f"[LinkedIn] Posted: {post_id}")
    return {"id": post_id}
