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


def publish(content: dict, dry_run: bool = False) -> dict:
    ig_default_image = _env("IG_DEFAULT_IMAGE_URL")
    image_url = content.get("product_image_url") or ig_default_image
    if not image_url:
        print("[Instagram] Skipped: no product image and no IG_DEFAULT_IMAGE_URL configured")
        return {"id": "skipped"}

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
    resp.raise_for_status()
    creation_id = resp.json()["id"]

    # Step 2: publish the container
    resp2 = _post_with_retry(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        {
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=30,
    )
    resp2.raise_for_status()
    data = resp2.json()
    print(f"[Instagram] Posted: {data['id']}")
    return {"id": data["id"]}
