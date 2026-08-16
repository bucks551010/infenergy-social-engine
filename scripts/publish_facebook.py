import os
import time
import requests

GRAPH_BASE = "https://graph.facebook.com/v26.0"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _required_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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


def _resolve_page_access_token(token: str, page_id: str) -> str:
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
            if str(page.get("id", "")) == str(page_id) and page.get("access_token"):
                return page["access_token"]

        # Fallback to first managed page token if explicit match is not found.
        first = data[0]
        if first.get("access_token"):
            return first["access_token"]
    except Exception:
        return token

    return token


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


def publish(content: dict, wp_link: str, dry_run: bool = False) -> dict:
    facebook_package = (content.get("platform_posts") or {}).get("facebook") or {}
    message = str(facebook_package.get("final_caption") or content["fb_caption"])
    if not facebook_package.get("final_caption") and wp_link and wp_link not in message:
        message = f"{message}\n\n{wp_link}"
    image_path = str((content.get("generated_visuals") or {}).get("facebook", "")).strip()
    image_url = str(content.get("primary_publish_image_url", "")).strip()
    if not image_url.startswith("http"):
        image_url = str(content.get("product_image_url", "")).strip()
    require_image = _env_flag("FB_REQUIRE_IMAGE", True)

    if dry_run:
        print(f"[DRY RUN] Facebook: would post:\n{message[:150]}...\n")
        return {"id": "dry-run"}

    page_id = _required_env("META_PAGE_ID")
    token = _resolve_page_access_token(_required_env("META_PAGE_ACCESS_TOKEN"), page_id)

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{GRAPH_BASE}/{page_id}/photos",
                data={
                    "caption": message,
                    "published": "true",
                    "access_token": token,
                },
                files={"source": (os.path.basename(image_path), f, "image/png")},
                timeout=60,
            )
    elif image_url.startswith("http"):
        resp = requests.post(
            f"{GRAPH_BASE}/{page_id}/photos",
            data={
                "caption": message,
                "published": "true",
                "url": image_url,
                "access_token": token,
            },
            timeout=60,
        )
    else:
        if require_image:
            raise RuntimeError(
                "Facebook image is required but no generated visual or product image URL was available"
            )
        resp = _post_with_retry(
            f"{GRAPH_BASE}/{page_id}/feed",
            {
                "message": message,
                "access_token": token,
            },
            timeout=30,
        )
    _raise_with_body(resp)
    data = resp.json()
    print(f"[Facebook] Posted: {data['id']}")
    return {"id": data["id"]}


def delete(post_id: str) -> dict:
    """Delete a previously published Facebook page post/photo by its object id."""
    page_id = _required_env("META_PAGE_ID")
    token = _resolve_page_access_token(_required_env("META_PAGE_ACCESS_TOKEN"), page_id)
    resp = requests.delete(
        f"{GRAPH_BASE}/{post_id}",
        params={"access_token": token},
        timeout=30,
    )
    _raise_with_body(resp)
    data = resp.json() if resp.content else {}
    print(f"[Facebook] Deleted: {post_id}")
    return {"id": post_id, "success": bool(data.get("success", True))}
