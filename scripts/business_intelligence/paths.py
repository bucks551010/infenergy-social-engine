"""Path resolution for the Business Intelligence Foundation.

All BI state lives under ``data/business_intelligence/``. Overridable via
``DATA_DIR`` (already used elsewhere) and ``BI_DATA_DIR`` (BI-specific).
"""

from __future__ import annotations

import os


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def data_dir() -> str:
    override = os.environ.get("BI_DATA_DIR") or os.environ.get("DATA_DIR")
    if override and os.path.isdir(override):
        return override
    return os.path.join(_repo_root(), "data")


def bi_dir() -> str:
    d = os.path.join(data_dir(), "business_intelligence")
    os.makedirs(d, exist_ok=True)
    return d


def profile_dir() -> str:
    d = os.path.join(bi_dir(), "profile")
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, "versions"), exist_ok=True)
    return d


def sources_dir() -> str:
    d = os.path.join(bi_dir(), "sources")
    os.makedirs(d, exist_ok=True)
    return d


def evidence_dir() -> str:
    d = os.path.join(bi_dir(), "evidence")
    os.makedirs(d, exist_ok=True)
    return d


def offerings_dir() -> str:
    d = os.path.join(bi_dir(), "offerings")
    os.makedirs(d, exist_ok=True)
    return d


def audiences_dir() -> str:
    d = os.path.join(bi_dir(), "audiences")
    os.makedirs(d, exist_ok=True)
    return d


def brand_dir() -> str:
    d = os.path.join(bi_dir(), "brand")
    os.makedirs(d, exist_ok=True)
    return d


def social_dir() -> str:
    d = os.path.join(bi_dir(), "social")
    os.makedirs(d, exist_ok=True)
    return d


def research_dir() -> str:
    d = os.path.join(bi_dir(), "research")
    os.makedirs(d, exist_ok=True)
    return d


def learning_dir() -> str:
    d = os.path.join(bi_dir(), "learning")
    os.makedirs(d, exist_ok=True)
    return d


def compiled_dir() -> str:
    d = os.path.join(bi_dir(), "compiled")
    os.makedirs(d, exist_ok=True)
    return d


def overrides_dir() -> str:
    d = os.path.join(bi_dir(), "owner_overrides")
    os.makedirs(d, exist_ok=True)
    return d


# --- Discovered source locations (Infenergy-current) -----------------------


def products_csv_dir() -> str:
    return os.path.join(data_dir(), "products")


def product_briefs_dir() -> str:
    return os.path.join(data_dir(), "product_briefs")


def marketing_dir() -> str:
    return os.path.join(data_dir(), "marketing")


def founder_manifesto_path() -> str:
    return os.path.join(marketing_dir(), "founder_brand_manifesto.json")


def inventory_db_path() -> str:
    return os.path.join(data_dir(), "inventory.db")


def post_history_path() -> str:
    return os.path.join(data_dir(), "post_history.json")
