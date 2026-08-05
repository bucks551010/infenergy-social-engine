import os
import requests

LINKEDIN_ACCESS_TOKEN = os.environ["LINKEDIN_ACCESS_TOKEN"]
# Set LINKEDIN_AUTHOR_URN to urn:li:person:ID (personal) or urn:li:organization:ID (company page)
LINKEDIN_AUTHOR_URN = os.environ.get("LINKEDIN_AUTHOR_URN", "")

LI_API = "https://api.linkedin.com/v2"


def _resolve_author_urn() -> str:
    if LINKEDIN_AUTHOR_URN:
        return LINKEDIN_AUTHOR_URN
    # Auto-resolve from token when URN is not provided
    resp = requests.get(
        f"{LI_API}/userinfo",
        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
        timeout=15,
    )
    resp.raise_for_status()
    sub = resp.json()["sub"]
    return f"urn:li:person:{sub}"


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
    resp.raise_for_status()
    post_id = resp.headers.get("x-restli-id", "posted")
    print(f"[LinkedIn] Posted: {post_id}")
    return {"id": post_id}
