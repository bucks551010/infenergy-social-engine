import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import generate_posts
import publish_wordpress
import publish_facebook
import publish_instagram
import publish_linkedin

REQUIRED_SECRETS = [
    "GEMINI_API_KEY", "WP_URL", "WP_USERNAME", "WP_APP_PASSWORD",
    "META_PAGE_ID", "META_PAGE_ACCESS_TOKEN", "META_IG_USER_ID",
    "LINKEDIN_ACCESS_TOKEN",
]


def check_secrets() -> None:
    missing = [k for k in REQUIRED_SECRETS if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing required secrets: {', '.join(missing)}")
        sys.exit(1)


def main() -> None:
    check_secrets()

    slot = os.environ.get("POST_SLOT", "morning")
    dry_run = os.environ.get("SOCIAL_DRY_RUN", "true").lower() == "true"

    print(f"\n=== INF Energy Social Engine ===")
    print(f"Slot: {slot} | Dry run: {dry_run} | UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n")

    print("[1/5] Generating content with Gemini...")
    content = generate_posts.generate(slot)
    print(f"Topic: {content['topic']}")
    if content.get("product_name"):
        print(f"Product: {content['product_name']} ({content.get('product_sku', 'N/A')})")
    print(f"WP Title: {content['wp_title']}\n")

    print("[2/5] WordPress...")
    wp_result = publish_wordpress.publish(content, dry_run=dry_run)
    wp_link = wp_result.get("link", os.environ.get("WP_URL", "https://www.infenergypower.com"))

    print("[3/5] Facebook...")
    fb_result = publish_facebook.publish(content, wp_link, dry_run=dry_run)

    print("[4/5] Instagram...")
    ig_result = publish_instagram.publish(content, dry_run=dry_run)

    print("[5/5] LinkedIn...")
    li_result = publish_linkedin.publish(content, wp_link, dry_run=dry_run)

    # Persist history so the next run picks a fresh topic
    history = generate_posts.load_history()
    history["posts"].append({
        "date": content["date"],
        "slot": slot,
        "topic": content["topic"],
        "pillar": content["pillar"],
        "topic_hash": content["topic_hash"],
        "product_name": content.get("product_name", ""),
        "product_sku": content.get("product_sku", ""),
        "dry_run": dry_run,
        "wp_id": wp_result.get("id"),
        "fb_id": fb_result.get("id"),
        "ig_id": ig_result.get("id"),
        "li_id": li_result.get("id"),
    })
    history["posts"] = history["posts"][-200:]
    generate_posts.save_history(history)

    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
