"""Path resolution for the Business Intelligence Foundation.

All BI state lives under ``data/business_intelligence/``. Overridable via
``DATA_DIR`` (already used elsewhere) and ``BI_DATA_DIR`` (BI-specific).
"""

from __future__ import annotations

import glob
import os


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def data_dir() -> str:
    override = os.environ.get("BI_DATA_DIR") or os.environ.get("DATA_DIR")
    if override and os.path.isdir(override):
        return override
    return os.path.join(_repo_root(), "data")


def _repo_data_dir() -> str:
    return os.path.join(_repo_root(), "data")


def _resolve_source_dir(name: str, pattern: str = "*") -> str:
    """Resolve a discovered-source directory under ``name``.

    Prefers the ``DATA_DIR`` override (a generic, shared persistent volume
    in deployment), but falls back to the repo-bundled ``data/<name>`` copy
    when the override path doesn't actually contain the expected files.
    This matters because a deployment volume may exist (and be used for
    other runtime state) without ever being seeded with the git-tracked
    catalog/library data that ships with every checkout.

    ``BI_DATA_DIR`` is treated as an explicit, authoritative BI-only data
    root (used for test isolation and deliberately scoped setups) and is
    NEVER subject to this fallback — an empty catalog there means the
    business genuinely has no offerings, not that data is missing.
    """
    candidate = os.path.join(data_dir(), name)
    if glob.glob(os.path.join(candidate, pattern)):
        return candidate
    if os.environ.get("BI_DATA_DIR"):
        return candidate
    fallback = os.path.join(_repo_data_dir(), name)
    if glob.glob(os.path.join(fallback, pattern)):
        return fallback
    return candidate


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


def consumer_profiles_path() -> str:
    candidate = os.path.join(data_dir(), "marketing", "product_consumer_profiles.json")
    if os.path.isfile(candidate) or os.environ.get("BI_DATA_DIR"):
        return candidate
    return os.path.join(_repo_data_dir(), "marketing", "product_consumer_profiles.json")


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
    return _resolve_source_dir("products", "*.csv")


def product_briefs_dir() -> str:
    return _resolve_source_dir("product_briefs", "*.json")


def marketing_dir() -> str:
    return _resolve_source_dir("marketing", "*")


def founder_manifesto_path() -> str:
    return os.path.join(marketing_dir(), "founder_brand_manifesto.json")


def inventory_db_path() -> str:
    return os.path.join(data_dir(), "inventory.db")


def post_history_path() -> str:
    return os.path.join(data_dir(), "post_history.json")
