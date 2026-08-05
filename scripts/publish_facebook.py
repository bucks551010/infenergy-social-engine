import os
import requests

META_PAGE_ID = os.environ["META_PAGE_ID"]
META_PAGE_ACCESS_TOKEN = os.environ["META_PAGE_ACCESS_TOKEN"]
GRAPH_BASE = "https://graph.facebook.com/v26.0"


def publish(content: dict, wp_link: str, dry_run: bool = False) -> dict:
    message = f"{content['fb_caption']}\n\n{wp_link}"

    if dry_run:
        print(f"[DRY RUN] Facebook: would post:\n{message[:150]}...\n")
        return {"id": "dry-run"}

    resp = requests.post(
        f"{GRAPH_BASE}/{META_PAGE_ID}/feed",
        data={
            "message": message,
            "access_token": META_PAGE_ACCESS_TOKEN,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"[Facebook] Posted: {data['id']}")
    return {"id": data["id"]}
