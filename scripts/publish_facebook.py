import os
import requests

META_PAGE_ID = os.environ["META_PAGE_ID"]
META_PAGE_ACCESS_TOKEN = os.environ["META_PAGE_ACCESS_TOKEN"]
GRAPH_BASE = "https://graph.facebook.com/v26.0"


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


def _resolve_page_access_token(token: str) -> str:
    """Resolve a page access token from /me/accounts when a user token is provided."""
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/me/accounts",
            params={
                "fields": "id,name,access_token,tasks",
                "access_token": token,
            },
            timeout=20,
        )
        if not resp.ok:
            return token

        data = resp.json().get("data", [])
        if not isinstance(data, list) or not data:
            return token

        # Prefer the configured page id.
        for page in data:
            if str(page.get("id", "")) == str(META_PAGE_ID) and page.get("access_token"):
                return page["access_token"]

        # Fallback to first managed page token if explicit match is not found.
        first = data[0]
        if first.get("access_token"):
            return first["access_token"]
    except Exception:
        return token

    return token


def publish(content: dict, wp_link: str, dry_run: bool = False) -> dict:
    message = f"{content['fb_caption']}\n\n{wp_link}"

    if dry_run:
        print(f"[DRY RUN] Facebook: would post:\n{message[:150]}...\n")
        return {"id": "dry-run"}

    token = _resolve_page_access_token(META_PAGE_ACCESS_TOKEN)

    resp = requests.post(
        f"{GRAPH_BASE}/{META_PAGE_ID}/feed",
        data={
            "message": message,
            "access_token": token,
        },
        timeout=30,
    )
    _raise_with_body(resp)
    data = resp.json()
    print(f"[Facebook] Posted: {data['id']}")
    return {"id": data["id"]}
