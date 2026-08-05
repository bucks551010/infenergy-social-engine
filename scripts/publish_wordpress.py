import os
import base64
import requests

WP_URL = os.environ["WP_URL"].rstrip("/")
if WP_URL.endswith("/wp-admin"):
    WP_URL = WP_URL[:-9]
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]


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
    _raise_with_body(resp)
    data = resp.json()
    print(f"[WordPress] Published: {data['link']}")
    return {"id": data["id"], "link": data["link"]}
