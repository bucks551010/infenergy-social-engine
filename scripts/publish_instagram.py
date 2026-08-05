import os
import requests

META_IG_USER_ID = os.environ["META_IG_USER_ID"]
META_PAGE_ACCESS_TOKEN = os.environ["META_PAGE_ACCESS_TOKEN"]
# Instagram feed posts require an image. Add a public branded image URL as secret IG_DEFAULT_IMAGE_URL.
IG_DEFAULT_IMAGE_URL = os.environ.get("IG_DEFAULT_IMAGE_URL", "")
GRAPH_BASE = "https://graph.facebook.com/v26.0"


def publish(content: dict, dry_run: bool = False) -> dict:
    image_url = content.get("product_image_url") or IG_DEFAULT_IMAGE_URL
    if not image_url:
        print("[Instagram] Skipped: no product image and no IG_DEFAULT_IMAGE_URL configured")
        return {"id": "skipped"}

    caption = content["ig_caption"]

    if dry_run:
        print(f"[DRY RUN] Instagram: would post:\n{caption[:150]}...\n")
        return {"id": "dry-run"}

    # Step 1: create media container
    resp = requests.post(
        f"{GRAPH_BASE}/{META_IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": META_PAGE_ACCESS_TOKEN,
        },
        timeout=30,
    )
    resp.raise_for_status()
    creation_id = resp.json()["id"]

    # Step 2: publish the container
    resp2 = requests.post(
        f"{GRAPH_BASE}/{META_IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": META_PAGE_ACCESS_TOKEN,
        },
        timeout=30,
    )
    resp2.raise_for_status()
    data = resp2.json()
    print(f"[Instagram] Posted: {data['id']}")
    return {"id": data["id"]}
