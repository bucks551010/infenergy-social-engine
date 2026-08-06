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


def check_secrets(dry_run: bool, channels: dict) -> None:
    required: list[str] = []
    # AI key is optional because generator has deterministic fallback content.
    if not os.environ.get("GEMINI_API_KEY"):
        print("[WARN] GEMINI_API_KEY is not set. Using deterministic fallback content.")

    if dry_run:
        return

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


def _latest_marketing_bundle_info() -> tuple[str, str]:
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
    marketing_dir = os.path.join(data_dir, "marketing")
    if not os.path.isdir(marketing_dir):
        return "none", "not found"

    files = [
        os.path.join(marketing_dir, f)
        for f in os.listdir(marketing_dir)
        if f.startswith("marketing_bundle_") and f.endswith(".json")
    ]
    if not files:
        return "none", "not found"

    latest = max(files, key=os.path.getmtime)
    ts = datetime.fromtimestamp(os.path.getmtime(latest), tz=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    freshness = "fresh" if age_hours <= 48 else "stale"
    return os.path.basename(latest), freshness


def main() -> None:
    slot = os.environ.get("POST_SLOT", "morning")
    dry_run = os.environ.get("SOCIAL_DRY_RUN", "true").lower() == "true"
    channels = get_channel_config()
    check_secrets(dry_run=dry_run, channels=channels)
    generate_posts.ensure_runtime_data()
    bundle_name, bundle_freshness = _latest_marketing_bundle_info()

    print(f"\n=== INF Energy Social Engine ===")
    print(f"Slot: {slot} | Dry run: {dry_run} | UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n")
    print(
        "Channels: "
        f"wordpress={channels['wordpress']} "
        f"facebook={channels['facebook']} "
        f"instagram={channels['instagram']} "
        f"linkedin={channels['linkedin']}\n"
    )
    print(f"Marketing bundle: {bundle_name} ({bundle_freshness})\n")

    print("[1/5] Generating content with Gemini...")
    content = generate_posts.generate(slot)
    print(f"Topic: {content['topic']}")
    print(f"Marketing strategy bundle: {'loaded' if content.get('marketing_bundle_used') else 'not loaded'}")
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
