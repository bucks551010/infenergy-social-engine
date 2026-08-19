"""Compile existing owned intelligence into reusable, persistent production packages."""

from __future__ import annotations

import json
import csv
import glob
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import inventory_db
import requests
from social.blocker_transformation_registry import registry as blocker_registry

PACKAGED_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

PACKAGE_TYPES = (
    "BUSINESS_CONSTITUTION",
    "AUDIENCE_WORLD",
    "PRODUCT_INTELLIGENCE",
    "PRODUCT_VISUAL_TRUTH",
    "TRUTH_CABINET",
    "CONTENT_READINESS",
    "BRAND_CREATIVE_GRAMMAR",
    "PLATFORM_PRESENTATION",
    "CAMPAIGN_CONTINUITY",
    "DAILY_SLOT",
    "BLOCKER_TRANSFORMATION_REGISTRY",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: str, fallback: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return fallback


def _static_path(data_dir: str, *parts: str) -> str:
    runtime_path = os.path.join(data_dir, *parts)
    return runtime_path if os.path.exists(runtime_path) else os.path.join(PACKAGED_DATA_DIR, *parts)


def _connect(data_dir: str) -> sqlite3.Connection:
    inventory_db.init_inventory_db(data_dir)
    connection = sqlite3.connect(inventory_db.get_db_path(data_dir), timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def init_package_store(data_dir: str) -> None:
    connection = _connect(data_dir)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_packages (
                package_type TEXT NOT NULL,
                package_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                missing_fields_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                last_verified TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(package_type, package_id)
            );
            CREATE TABLE IF NOT EXISTS ready_reserve (
                seed_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                seed_json TEXT NOT NULL,
                freshness_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def _status(payload: dict[str, Any], required: tuple[str, ...], owner_only: tuple[str, ...] = ()) -> tuple[str, list[str]]:
    missing = [field for field in required if payload.get(field) in (None, "", [], {})]
    if not missing:
        return "COMPLETE", []
    if missing and set(missing).issubset(owner_only):
        return "UNKNOWN_OWNER_ONLY", missing
    return "PARTIAL", missing


def _upsert(
    connection: sqlite3.Connection,
    *,
    package_type: str,
    package_id: str,
    payload: dict[str, Any],
    required: tuple[str, ...],
    provenance: list[str],
    owner_only: tuple[str, ...] = (),
) -> dict[str, Any]:
    status, missing = _status(payload, required, owner_only)
    now = _now()
    connection.execute(
        """
        INSERT INTO intelligence_packages
        (package_type, package_id, status, payload_json, missing_fields_json, provenance_json, last_verified, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(package_type, package_id) DO UPDATE SET
            status=excluded.status,
            payload_json=excluded.payload_json,
            missing_fields_json=excluded.missing_fields_json,
            provenance_json=excluded.provenance_json,
            last_verified=excluded.last_verified,
            updated_at=excluded.updated_at
        """,
        (
            package_type,
            package_id,
            status,
            json.dumps(payload, ensure_ascii=True, default=str),
            json.dumps(missing),
            json.dumps(provenance),
            now,
            now,
        ),
    )
    return {"package_type": package_type, "package_id": package_id, "status": status, "missing_fields": missing}


def _product_package(product: dict[str, Any]) -> dict[str, Any]:
    facts = list(product.get("metrics") or [])
    snippet = str(product.get("fact_snippet") or "").strip()
    if snippet:
        facts.append(snippet)
    images = list(product.get("image_candidates") or [])
    if product.get("image_url") and product["image_url"] not in images:
        images.insert(0, product["image_url"])
    return {
        "product_id": product.get("id"),
        "name": product.get("name"),
        "canonical_url": product.get("product_url"),
        "category": list(product.get("categories") or []),
        "verified_facts": facts,
        "known_limitations": ["Runtime and compatibility require device-specific verification."],
        "safe_benefit_bridges": ["Compare published capacity and output with the actual device and job."],
        "unsupported_territory": ["Unverified runtime", "Unverified compatibility", "Guaranteed safety or protection"],
        "content_angles": ["product fit", "specification literacy", "matched-to-need guidance"],
        "visual_references": images,
        "in_stock": product.get("in_stock"),
        "last_verified": _now(),
    }


def _owned_product_urls(data_dir: str) -> dict[str, str]:
    from generate_posts import _canonical_product_url_from_row

    urls: dict[str, str] = {}
    paths = glob.glob(os.path.join(data_dir, "products", "*.csv"))
    if not paths:
        paths = glob.glob(os.path.join(PACKAGED_DATA_DIR, "products", "*.csv"))
    for path in paths:
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    url = _canonical_product_url_from_row(row)
                    if not url:
                        continue
                    for key in (str(row.get("ID") or "").strip(), str(row.get("SKU") or "").strip()):
                        if key:
                            urls[key] = url
        except OSError:
            continue
    return urls


def _normalize_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _match_researched_urls(products: list[dict[str, Any]], pages: list[dict[str, str]]) -> dict[str, str]:
    matched: dict[str, str] = {}
    for product in products:
        product_id = str(product.get("id") or "")
        sku = _normalize_identity(str(product.get("sku") or product_id))
        name = _normalize_identity(str(product.get("name") or ""))
        exact_matches: list[dict[str, str]] = []
        parent_matches: list[dict[str, str]] = []
        for page in pages:
            page_sku = _normalize_identity(page.get("sku", ""))
            page_name = _normalize_identity(page.get("name", ""))
            if (sku and page_sku and sku == page_sku) or (name and page_name and name == page_name):
                exact_matches.append(page)
            elif (
                name
                and page_name
                and bool(page.get("has_options"))
                and name.startswith(f"{page_name} ")
            ):
                parent_matches.append(page)
        candidates = exact_matches or parent_matches
        unique_urls = {str(page.get("url") or "").strip() for page in candidates if str(page.get("url") or "").strip()}
        if len(unique_urls) == 1:
            matched[product_id] = unique_urls.pop()
    return matched


def _research_first_party_product_urls(products: list[dict[str, Any]]) -> dict[str, str]:
    site = str(os.environ.get("FIRST_PARTY_SITE_URL") or "https://infenergypower.com").rstrip("/")
    if urlparse(site).hostname not in {"infenergypower.com", "www.infenergypower.com"}:
        return {}
    try:
        store_response = requests.get(f"{site}/wp-json/wc/store/v1/products?per_page=100", timeout=20)
        store_response.raise_for_status()
        store_products = store_response.json()
        store_pages = [
            {
                "url": str(item.get("permalink") or ""),
                "sku": str(item.get("sku") or ""),
                "name": str(item.get("name") or ""),
                "has_options": bool(item.get("has_options")),
            }
            for item in store_products
            if isinstance(item, dict)
            and str(item.get("permalink") or "").startswith(("https://infenergypower.com/product/", "https://www.infenergypower.com/product/"))
        ] if isinstance(store_products, list) else []
        store_matches = _match_researched_urls(products, store_pages)
    except (requests.RequestException, ValueError):
        store_matches = {}
    unmatched = [product for product in products if str(product.get("id") or "") not in store_matches]
    if not unmatched:
        return store_matches
    try:
        response = requests.get(f"{site}/wp-sitemap-posts-product-1.xml", timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        urls = [
            str(node.text or "").strip()
            for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            if str(node.text or "").strip().startswith(("https://infenergypower.com/product/", "https://www.infenergypower.com/product/"))
        ]
    except (requests.RequestException, ET.ParseError):
        return {}
    pages: list[dict[str, str]] = []
    for url in urls:
        try:
            page = requests.get(url, timeout=10)
            page.raise_for_status()
        except requests.RequestException:
            continue
        sku_match = re.search(r'"sku"\s*:\s*"([^"]+)"', page.text, flags=re.IGNORECASE)
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', page.text, flags=re.IGNORECASE)
        pages.append({
            "url": url,
            "sku": sku_match.group(1) if sku_match else "",
            "name": name_match.group(1) if name_match else "",
        })
    return {**_match_researched_urls(unmatched, pages), **store_matches}


def compile_packages(data_dir: str) -> dict[str, Any]:
    init_package_store(data_dir)
    constitution_path = _static_path(data_dir, "marketing", "human_truth", "constitution.json")
    audience_path = _static_path(data_dir, "social", "audience_world.json")
    creative_path = _static_path(data_dir, "social", "brand_design_tokens.json")
    living_path = os.path.join(data_dir, "social", "living_intelligence.json")
    constitution = _load(constitution_path, {})
    audiences = (_load(audience_path, {}) or {}).get("segments", {})
    creative = _load(creative_path, {})
    living = _load(living_path, {})
    products = inventory_db.fetch_products(data_dir)
    owned_urls = _owned_product_urls(data_dir)
    missing_products = [product for product in products if not product.get("product_url") and not owned_urls.get(str(product.get("id") or "")) and not owned_urls.get(str(product.get("sku") or ""))]
    researched_urls = _research_first_party_product_urls(missing_products) if missing_products else {}
    for product in products:
        product["product_url"] = product.get("product_url") or owned_urls.get(str(product.get("id") or "")) or owned_urls.get(str(product.get("sku") or "")) or researched_urls.get(str(product.get("id") or "")) or ""
    if any(product.get("product_url") for product in products):
        inventory_db.upsert_products(data_dir, products, source="intelligence_enrichment")
    brand = inventory_db.fetch_brand_profile(data_dir)
    ideology = inventory_db.fetch_selling_ideology(data_dir)
    rows: list[dict[str, Any]] = []
    connection = _connect(data_dir)
    try:
        business = {
            "business_name": brand.get("brand_name") or "Infenergy Power",
            "purpose": constitution.get("worldview", {}).get("business_role") or brand.get("mission"),
            "founder_worldview": constitution.get("founder_origin"),
            "positioning": brand.get("positioning") or constitution.get("reputation_destination"),
            "voice": constitution.get("voice") or brand.get("voice_rules"),
            "preparedness_philosophy": constitution.get("worldview"),
            "trust_principles": constitution.get("trust_boundaries"),
            "selling_philosophy": ideology,
            "approved_owner_truths": constitution.get("core_mandates"),
            "authority_order": constitution.get("source_authority_order"),
        }
        rows.append(_upsert(
            connection,
            package_type="BUSINESS_CONSTITUTION",
            package_id="infenergy",
            payload=business,
            required=("business_name", "purpose", "founder_worldview", "positioning", "voice", "trust_principles", "approved_owner_truths", "authority_order"),
            provenance=[constitution_path, inventory_db.get_db_path(data_dir)],
        ))
        for audience_id, audience in audiences.items():
            payload = {"audience_id": audience_id, **audience, "source_authority": "OWNED_AUDIENCE_MODEL"}
            rows.append(_upsert(
                connection,
                package_type="AUDIENCE_WORLD",
                package_id=audience_id,
                payload=payload,
                required=("name", "problems", "questions", "goals", "decisions", "objections", "lifestyle_context", "emotional_drivers", "purchase_context"),
                provenance=[audience_path],
            ))
        product_packages: list[dict[str, Any]] = []
        for product in products:
            payload = _product_package(product)
            product_packages.append(payload)
            rows.append(_upsert(
                connection,
                package_type="PRODUCT_INTELLIGENCE",
                package_id=str(product.get("id")),
                payload=payload,
                required=("product_id", "name", "canonical_url", "verified_facts", "safe_benefit_bridges", "unsupported_territory"),
                provenance=[inventory_db.get_db_path(data_dir), "data/product_briefs/*.json"],
            ))
            visual = {
                "product_id": product.get("id"),
                "approved_source_images": payload["visual_references"],
                "canonical_front_view": product.get("image_url"),
                "shape": None,
                "proportions": None,
                "ports": None,
                "buttons": None,
                "display": None,
                "details_must_preserve": ["Use only the approved source image for detailed depiction."],
                "details_must_not_invent": ["ports", "buttons", "screens", "logos", "accessories", "dimensions"],
                "safe_visual_distance": "environmental or incidental when exact detail cannot be preserved",
                "best_creative_roles": ["product-in-context", "supporting", "background"],
            }
            rows.append(_upsert(
                connection,
                package_type="PRODUCT_VISUAL_TRUTH",
                package_id=str(product.get("id")),
                payload=visual,
                required=("product_id", "approved_source_images", "canonical_front_view", "details_must_preserve", "details_must_not_invent", "safe_visual_distance"),
                owner_only=("shape", "proportions", "ports", "buttons", "display"),
                provenance=[inventory_db.get_db_path(data_dir)],
            ))
        truth = {
            "authority_order": constitution.get("source_authority_order"),
            "owner_truth": constitution.get("core_mandates"),
            "business_truth": business,
            "product_facts": {item["product_id"]: item["verified_facts"] for item in product_packages if item["verified_facts"]},
            "known_limitations": {item["product_id"]: item["known_limitations"] for item in product_packages},
            "allowed_public_use": "Use within stated scope and limitations; never elevate hypothesis to fact.",
        }
        rows.append(_upsert(
            connection,
            package_type="TRUTH_CABINET",
            package_id="current",
            payload=truth,
            required=("authority_order", "owner_truth", "business_truth", "product_facts", "known_limitations", "allowed_public_use"),
            provenance=[constitution_path, inventory_db.get_db_path(data_dir)],
        ))
        moment_worlds = constitution.get("moment_worlds") or []
        for moment in moment_worlds:
            readiness = {
                "readiness_id": moment.get("id"),
                "why_this_matters": moment.get("responsibility"),
                "who": moment.get("person"),
                "when": moment.get("decision_state"),
                "human_realities": [moment],
                "brain_movements": ["PRIORITIZE", "UNDERSTAND", "PLAN", "DECIDE"],
                "heart_responses": ["CLARITY", "CAPABILITY", "CONTROL"],
                "verified_facts": [],
                "safe_claims": [moment.get("human_question"), moment.get("capability_goal")],
                "claims_to_avoid": constitution.get("voice", {}).get("anti_language", []),
                "content_jobs": constitution.get("content_jobs", []),
                "story_routes": ["HUMAN_MOMENT", "EDUCATIONAL_STORY", "NO_STORY_REQUIRED"],
                "product_role": moment.get("product_role"),
                "visual_territories": [scene for scene in constitution.get("scene_library", []) if scene.get("product_role") == moment.get("product_role")],
                "natural_responses": ["SAVE", "PLAN", "COMPARE", "LEARN"],
                "freshness": "CHECK_AT_SELECTION",
            }
            rows.append(_upsert(
                connection,
                package_type="CONTENT_READINESS",
                package_id=str(moment.get("id")),
                payload=readiness,
                required=("why_this_matters", "who", "when", "human_realities", "brain_movements", "heart_responses", "safe_claims", "content_jobs", "visual_territories"),
                provenance=[constitution_path],
            ))
            seed_id = str(moment.get("id"))
            connection.execute(
                """
                INSERT INTO ready_reserve(seed_id, status, seed_json, freshness_key, created_at, updated_at)
                VALUES (?, 'AVAILABLE', ?, ?, ?, ?)
                ON CONFLICT(seed_id) DO UPDATE SET seed_json=excluded.seed_json,
                    freshness_key=excluded.freshness_key, updated_at=excluded.updated_at
                """,
                (seed_id, json.dumps(readiness, ensure_ascii=True), f"{seed_id}:CHECK_AT_SELECTION", _now(), _now()),
            )
        creative_package = {
            **creative,
            "visual_world": constitution.get("scene_library"),
            "premium_standard": ["editorial", "human", "believable", "calm capability"],
            "packshot_indicators": ["plain background", "centered product", "no scene", "no depth", "no visual thesis"],
            "prohibited_cliches": creative.get("must_avoid_in_generated_imagery", []),
        }
        rows.append(_upsert(
            connection,
            package_type="BRAND_CREATIVE_GRAMMAR",
            package_id="infenergy",
            payload=creative_package,
            required=("brand_colors", "photography_style", "visual_world", "premium_standard", "packshot_indicators", "prohibited_cliches"),
            provenance=[creative_path, constitution_path],
        ))
        platform_rules = {
            "facebook": {"tone": "substantial, human, conversational", "opening": "central idea early", "paragraphs": "natural thought groups", "hashtags_max": 5, "destination": "canonical then internal tracking", "media": "designed creative"},
            "instagram": {"tone": "visual-first and mobile-scannable", "opening": "central idea in first screen", "paragraphs": "deliberate whitespace", "hashtags_max": 8, "destination": "canonical", "media": "designed creative"},
            "linkedin": {"tone": "editorial, professional, thought-led", "opening": "insight first", "paragraphs": "readable progression", "hashtags_max": 5, "destination": "canonical", "media": "designed creative"},
        }
        for platform, rules in platform_rules.items():
            rows.append(_upsert(
                connection,
                package_type="PLATFORM_PRESENTATION",
                package_id=platform,
                payload=rules,
                required=("tone", "opening", "paragraphs", "hashtags_max", "destination", "media"),
                provenance=["scripts/social/platform_presentation.py"],
            ))
        campaign = living.get("campaign_state") or {"state": "EMPTY_BY_DESIGN", "decision": "ignore"}
        rows.append(_upsert(
            connection,
            package_type="CAMPAIGN_CONTINUITY",
            package_id="current",
            payload=campaign,
            required=("decision",),
            provenance=[living_path],
        ))
        rows.append(_upsert(
            connection,
            package_type="BLOCKER_TRANSFORMATION_REGISTRY",
            package_id="current",
            payload={"transformations": blocker_registry()},
            required=("transformations",),
            provenance=["scripts/social/blocker_transformation_registry.py"],
        ))
        has_slots = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_slots'"
        ).fetchone()
        if has_slots:
            for slot_row in connection.execute("SELECT * FROM daily_slots ORDER BY content_date, scheduled_at").fetchall():
                slot_payload = dict(slot_row)
                slot_payload["platform"] = json.loads(slot_payload.pop("platform_policy_json") or "{}")
                rows.append(_upsert(
                    connection,
                    package_type="DAILY_SLOT",
                    package_id=f"{slot_payload['content_date']}:{slot_payload['slot']}",
                    payload=slot_payload,
                    required=("content_date", "slot", "scheduled_at", "status"),
                    provenance=[inventory_db.get_db_path(data_dir)],
                ))
        connection.commit()
    finally:
        connection.close()
    return package_coverage(data_dir)


def package_coverage(data_dir: str) -> dict[str, Any]:
    init_package_store(data_dir)
    connection = _connect(data_dir)
    try:
        rows = connection.execute(
            "SELECT package_type, package_id, status, missing_fields_json, updated_at FROM intelligence_packages ORDER BY package_type, package_id"
        ).fetchall()
        reserve = connection.execute("SELECT COUNT(*) FROM ready_reserve WHERE status='AVAILABLE'").fetchone()[0]
    finally:
        connection.close()
    packages = [
        {
            "package_type": row["package_type"],
            "package_id": row["package_id"],
            "status": row["status"],
            "missing_fields": json.loads(row["missing_fields_json"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
    counts = {status: sum(1 for item in packages if item["status"] == status) for status in ("COMPLETE", "PARTIAL", "UNKNOWN_OWNER_ONLY")}
    return {"packages": packages, "counts": counts, "ready_reserve_available": int(reserve), "package_types": sorted({item["package_type"] for item in packages})}


def ready_reserve(data_dir: str, limit: int = 20) -> list[dict[str, Any]]:
    init_package_store(data_dir)
    connection = _connect(data_dir)
    try:
        rows = connection.execute(
            "SELECT seed_id, seed_json, freshness_key FROM ready_reserve WHERE status='AVAILABLE' ORDER BY seed_id LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [{"seed_id": row["seed_id"], "freshness_key": row["freshness_key"], **json.loads(row["seed_json"])} for row in rows]
    finally:
        connection.close()
