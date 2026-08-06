import os
import requests

LINKEDIN_ACCESS_TOKEN = os.environ["LINKEDIN_ACCESS_TOKEN"]
# Set LINKEDIN_AUTHOR_URN to urn:li:person:ID (personal) or urn:li:organization:ID (company page)
LINKEDIN_AUTHOR_URN = os.environ.get("LINKEDIN_AUTHOR_URN", "")

LI_API = "https://api.linkedin.com/v2"


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
    urn = LINKEDIN_AUTHOR_URN.strip()
    if urn:
        return urn

    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
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


def publish(content: dict, wp_link: str, dry_run: bool = False) -> dict:
    author = _resolve_author_urn()
    text = f"{content['li_text']}\n\n{wp_link}"

    if dry_run:
        print(f"[DRY RUN] LinkedIn: would post as {author}:\n{text[:150]}...\n")
        return {"id": "dry-run"}

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

    resp = requests.post(
        f"{LI_API}/ugcPosts",
        headers={
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json=payload,
        timeout=30,
    )
    _raise_with_body(resp)
    post_id = resp.headers.get("x-restli-id", "posted")
    print(f"[LinkedIn] Posted: {post_id}")
    return {"id": post_id}
