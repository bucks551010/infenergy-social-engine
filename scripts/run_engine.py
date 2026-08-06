import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import generate_posts
import publish_wordpress
import publish_facebook
import publish_instagram
import publish_linkedin


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_channel_config() -> dict:
    return {
        "wordpress": _env_flag("ENABLE_WORDPRESS", False),
        "facebook": _env_flag("ENABLE_FACEBOOK", True),
        "instagram": _env_flag("ENABLE_INSTAGRAM", True),
        "linkedin": _env_flag("ENABLE_LINKEDIN", True),
    }


def check_secrets() -> None:
    required = ["GEMINI_API_KEY"]
    channels = get_channel_config()
    if channels["wordpress"]:
        required.extend(["WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"])
    if channels["facebook"]:
        required.extend(["META_PAGE_ID", "META_PAGE_ACCESS_TOKEN"])
    if channels["instagram"]:
        required.extend(["META_IG_USER_ID", "META_PAGE_ACCESS_TOKEN"])
    if channels["linkedin"]:
        required.extend(["LINKEDIN_ACCESS_TOKEN"])

    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing required secrets: {', '.join(missing)}")
        sys.exit(1)


def main() -> None:
    check_secrets()
    generate_posts.ensure_runtime_data()
    channels = get_channel_config()

    slot = os.environ.get("POST_SLOT", "morning")
    dry_run = os.environ.get("SOCIAL_DRY_RUN", "true").lower() == "true"

    print(f"\n=== INF Energy Social Engine ===")
    print(f"Slot: {slot} | Dry run: {dry_run} | UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n")
    print(
        "Channels: "
        f"wordpress={channels['wordpress']} "
        f"facebook={channels['facebook']} "
        f"instagram={channels['instagram']} "
        f"linkedin={channels['linkedin']}\n"
    )

    print("[1/5] Generating content with Gemini...")
    content = generate_posts.generate(slot)
    print(f"Topic: {content['topic']}")
    if content.get("product_name"):
        print(f"Product: {content['product_name']} ({content.get('product_sku', 'N/A')})")
    print(f"WP Title: {content['wp_title']}\n")

    errors = []
    wp_result = {"id": "skipped", "link": os.environ.get("WP_URL", "https://www.infenergypower.com")}
    fb_result = {"id": "skipped"}
    ig_result = {"id": "skipped"}
    li_result = {"id": "skipped"}

    print("[2/5] WordPress...")
    if channels["wordpress"]:
        try:
            wp_result = publish_wordpress.publish(content, dry_run=dry_run)
        except Exception as e:
            errors.append(f"WordPress: {e}")
            print(f"[ERROR] WordPress publish failed: {e}")
    else:
        print("[SKIP] WordPress disabled")
    wp_link = wp_result.get("link", os.environ.get("WP_URL", "https://www.infenergypower.com"))

    print("[3/5] Facebook...")
    if channels["facebook"]:
        try:
            fb_result = publish_facebook.publish(content, wp_link, dry_run=dry_run)
        except Exception as e:
            errors.append(f"Facebook: {e}")
            print(f"[ERROR] Facebook publish failed: {e}")
    else:
        print("[SKIP] Facebook disabled")

    print("[4/5] Instagram...")
    if channels["instagram"]:
        try:
            ig_result = publish_instagram.publish(content, dry_run=dry_run)
        except Exception as e:
            errors.append(f"Instagram: {e}")
            print(f"[ERROR] Instagram publish failed: {e}")
    else:
        print("[SKIP] Instagram disabled")

    print("[5/5] LinkedIn...")
    if channels["linkedin"]:
        try:
            li_result = publish_linkedin.publish(content, wp_link, dry_run=dry_run)
        except Exception as e:
            errors.append(f"LinkedIn: {e}")
            print(f"[ERROR] LinkedIn publish failed: {e}")
    else:
        print("[SKIP] LinkedIn disabled")

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

    if errors:
        raise RuntimeError(" | ".join(errors))

    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
