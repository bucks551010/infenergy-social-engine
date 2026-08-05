import os
import base64
import requests

WP_URL = os.environ["WP_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]


def _auth_header() -> dict:
    token = base64.b64encode(f"{WP_USERNAME}:{WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def publish(content: dict, dry_run: bool = False) -> dict:
    if dry_run:
        print(f"[DRY RUN] WordPress: would publish '{content['wp_title']}'")
        return {"id": "dry-run", "link": WP_URL}

    payload = {
        "title": content["wp_title"],
        "content": content["wp_content"],
        "excerpt": content["wp_excerpt"],
        "status": "publish",
    }
    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        headers=_auth_header(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"[WordPress] Published: {data['link']}")
    return {"id": data["id"], "link": data["link"]}
