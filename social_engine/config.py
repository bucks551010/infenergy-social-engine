from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
PRODUCTS_DIR = ROOT / "data" / "products"


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "production")
    timezone: str = os.getenv("TIMEZONE", "America/Chicago")
    brand_url: str = os.getenv("BRAND_URL", "https://www.infenergypower.com")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "")

    enable_wordpress: bool = os.getenv("ENABLE_WORDPRESS", "false").lower() == "true"
    enable_facebook: bool = os.getenv("ENABLE_FACEBOOK", "true").lower() == "true"
    enable_instagram: bool = os.getenv("ENABLE_INSTAGRAM", "true").lower() == "true"
    enable_linkedin: bool = os.getenv("ENABLE_LINKEDIN", "true").lower() == "true"

    wp_url: str = os.getenv("WP_URL", "")
    wp_username: str = os.getenv("WP_USERNAME", "")
    wp_app_password: str = os.getenv("WP_APP_PASSWORD", "")

    meta_page_id: str = os.getenv("META_PAGE_ID", "")
    meta_page_access_token: str = os.getenv("META_PAGE_ACCESS_TOKEN", "")
    meta_instagram_business_id: str = os.getenv(
        "META_INSTAGRAM_BUSINESS_ID", os.getenv("META_IG_USER_ID", "")
    )

    linkedin_access_token: str = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    linkedin_author_urn: str = os.getenv("LINKEDIN_AUTHOR_URN", "")

    social_dry_run: bool = os.getenv("SOCIAL_DRY_RUN", "true").lower() == "true"
    manual_run_token: str = os.getenv("MANUAL_RUN_TOKEN", "")

    morning_utc: str = os.getenv("POST_SCHEDULE_MORNING", "13:00")
    midday_utc: str = os.getenv("POST_SCHEDULE_MIDDAY", "17:00")
    evening_utc: str = os.getenv("POST_SCHEDULE_EVENING", "23:00")


SETTINGS = Settings()
