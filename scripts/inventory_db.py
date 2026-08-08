import json
import os
import sqlite3
from datetime import datetime, timezone


DEFAULT_DB_FILE = "inventory.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path(data_dir: str) -> str:
    db_file = str(os.environ.get("INVENTORY_DB_FILE", DEFAULT_DB_FILE)).strip() or DEFAULT_DB_FILE
    return os.path.join(data_dir, db_file)


def _connect(data_dir: str) -> sqlite3.Connection:
    os.makedirs(data_dir, exist_ok=True)
    conn = sqlite3.connect(get_db_path(data_dir))
    conn.row_factory = sqlite3.Row
    return conn


def _to_json(value) -> str:
    if value is None:
        return "[]"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps([str(value)], ensure_ascii=False)


def _from_json(value: str, fallback):
    raw = str(value or "").strip()
    if not raw:
        return fallback
    try:
        parsed = json.loads(raw)
        return parsed
    except Exception:
        return fallback


def init_inventory_db(data_dir: str) -> str:
    conn = _connect(data_dir)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                sku TEXT,
                regular_price TEXT,
                sale_price TEXT,
                in_stock TEXT,
                stock_qty TEXT,
                product_url TEXT,
                categories_json TEXT,
                metrics_json TEXT,
                fact_snippet TEXT,
                image_url TEXT,
                image_candidates_json TEXT,
                category_image_candidates_json TEXT,
                source TEXT,
                updated_at_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS brand_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                brand_name TEXT,
                tagline TEXT,
                mission TEXT,
                positioning TEXT,
                audience_summary TEXT,
                personality_name TEXT,
                personality_traits_json TEXT,
                tone_rules_json TEXT,
                voice_rules_json TEXT,
                approved_phrases_json TEXT,
                cta_style_json TEXT,
                trust_close TEXT,
                words_to_use_json TEXT,
                words_to_avoid_json TEXT,
                forbidden_phrases_json TEXT,
                core_values_json TEXT,
                additional_notes TEXT,
                updated_at_utc TEXT NOT NULL
            );
            """
        )
        conn.commit()
        return get_db_path(data_dir)
    finally:
        conn.close()


def products_count(data_dir: str) -> int:
    conn = _connect(data_dir)
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()
        return int(row["c"]) if row else 0
    finally:
        conn.close()


def has_brand_profile(data_dir: str) -> bool:
    conn = _connect(data_dir)
    try:
        row = conn.execute("SELECT 1 AS ok FROM brand_profile WHERE id = 1").fetchone()
        return bool(row)
    finally:
        conn.close()


def upsert_products(data_dir: str, products: list[dict], source: str = "seed") -> int:
    if not products:
        return 0
    conn = _connect(data_dir)
    try:
        now = _utc_now()
        rows = []
        for p in products:
            product_id = str(p.get("id", "")).strip()
            name = str(p.get("name", "")).strip()
            if not (product_id and name):
                continue
            rows.append(
                (
                    product_id,
                    name,
                    str(p.get("sku", "")).strip(),
                    str(p.get("price", "")).strip(),
                    str(p.get("sale_price", "")).strip(),
                    str(p.get("in_stock", "")).strip(),
                    str(p.get("stock", "")).strip(),
                    str(p.get("product_url", "")).strip(),
                    _to_json(p.get("categories", [])),
                    _to_json(p.get("metrics", [])),
                    str(p.get("fact_snippet", "")).strip(),
                    str(p.get("image_url", "")).strip(),
                    _to_json(p.get("image_candidates", [])),
                    _to_json(p.get("category_image_candidates", [])),
                    source,
                    now,
                )
            )
        if not rows:
            return 0

        conn.executemany(
            """
            INSERT INTO products (
                product_id, name, sku, regular_price, sale_price, in_stock, stock_qty, product_url,
                categories_json, metrics_json, fact_snippet, image_url, image_candidates_json,
                category_image_candidates_json, source, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                name = excluded.name,
                sku = excluded.sku,
                regular_price = excluded.regular_price,
                sale_price = excluded.sale_price,
                in_stock = excluded.in_stock,
                stock_qty = excluded.stock_qty,
                product_url = excluded.product_url,
                categories_json = excluded.categories_json,
                metrics_json = excluded.metrics_json,
                fact_snippet = excluded.fact_snippet,
                image_url = excluded.image_url,
                image_candidates_json = excluded.image_candidates_json,
                category_image_candidates_json = excluded.category_image_candidates_json,
                source = excluded.source,
                updated_at_utc = excluded.updated_at_utc
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def fetch_products(data_dir: str) -> list[dict]:
    conn = _connect(data_dir)
    try:
        rows = conn.execute(
            """
            SELECT
                product_id, name, sku, regular_price, sale_price, in_stock, stock_qty, product_url,
                categories_json, metrics_json, fact_snippet, image_url, image_candidates_json,
                category_image_candidates_json
            FROM products
            ORDER BY name COLLATE NOCASE ASC
            """
        ).fetchall()
        products: list[dict] = []
        for row in rows:
            products.append(
                {
                    "id": str(row["product_id"] or "").strip(),
                    "name": str(row["name"] or "").strip(),
                    "sku": str(row["sku"] or "").strip(),
                    "price": str(row["regular_price"] or "").strip(),
                    "sale_price": str(row["sale_price"] or "").strip(),
                    "in_stock": str(row["in_stock"] or "").strip(),
                    "stock": str(row["stock_qty"] or "").strip(),
                    "product_url": str(row["product_url"] or "").strip(),
                    "categories": _from_json(row["categories_json"], []),
                    "metrics": _from_json(row["metrics_json"], []),
                    "fact_snippet": str(row["fact_snippet"] or "").strip(),
                    "image_url": str(row["image_url"] or "").strip(),
                    "image_candidates": _from_json(row["image_candidates_json"], []),
                    "category_image_candidates": _from_json(row["category_image_candidates_json"], []),
                }
            )
        return products
    finally:
        conn.close()


def upsert_brand_profile(data_dir: str, profile: dict) -> bool:
    if not isinstance(profile, dict):
        return False

    conn = _connect(data_dir)
    try:
        conn.execute(
            """
            INSERT INTO brand_profile (
                id, brand_name, tagline, mission, positioning, audience_summary,
                personality_name, personality_traits_json, tone_rules_json, voice_rules_json,
                approved_phrases_json, cta_style_json, trust_close, words_to_use_json,
                words_to_avoid_json, forbidden_phrases_json, core_values_json,
                additional_notes, updated_at_utc
            ) VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                brand_name = excluded.brand_name,
                tagline = excluded.tagline,
                mission = excluded.mission,
                positioning = excluded.positioning,
                audience_summary = excluded.audience_summary,
                personality_name = excluded.personality_name,
                personality_traits_json = excluded.personality_traits_json,
                tone_rules_json = excluded.tone_rules_json,
                voice_rules_json = excluded.voice_rules_json,
                approved_phrases_json = excluded.approved_phrases_json,
                cta_style_json = excluded.cta_style_json,
                trust_close = excluded.trust_close,
                words_to_use_json = excluded.words_to_use_json,
                words_to_avoid_json = excluded.words_to_avoid_json,
                forbidden_phrases_json = excluded.forbidden_phrases_json,
                core_values_json = excluded.core_values_json,
                additional_notes = excluded.additional_notes,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                str(profile.get("brand_name", "")).strip(),
                str(profile.get("tagline", "")).strip(),
                str(profile.get("mission", "")).strip(),
                str(profile.get("positioning", "")).strip(),
                str(profile.get("audience_summary", "")).strip(),
                str(profile.get("personality_name", "")).strip(),
                _to_json(profile.get("personality_traits", [])),
                _to_json(profile.get("tone_rules", [])),
                _to_json(profile.get("voice_rules", [])),
                _to_json(profile.get("approved_phrases", [])),
                _to_json(profile.get("cta_style", [])),
                str(profile.get("trust_close", "")).strip(),
                _to_json(profile.get("words_to_use", [])),
                _to_json(profile.get("words_to_avoid", [])),
                _to_json(profile.get("forbidden_phrases", [])),
                _to_json(profile.get("core_values", [])),
                str(profile.get("additional_notes", "")).strip(),
                _utc_now(),
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def fetch_brand_profile(data_dir: str) -> dict:
    conn = _connect(data_dir)
    try:
        row = conn.execute("SELECT * FROM brand_profile WHERE id = 1").fetchone()
        if not row:
            return {}
        return {
            "brand_name": str(row["brand_name"] or "").strip(),
            "tagline": str(row["tagline"] or "").strip(),
            "mission": str(row["mission"] or "").strip(),
            "positioning": str(row["positioning"] or "").strip(),
            "audience_summary": str(row["audience_summary"] or "").strip(),
            "personality_name": str(row["personality_name"] or "").strip(),
            "personality_traits": _from_json(row["personality_traits_json"], []),
            "tone_rules": _from_json(row["tone_rules_json"], []),
            "voice_rules": _from_json(row["voice_rules_json"], []),
            "approved_phrases": _from_json(row["approved_phrases_json"], []),
            "cta_style": _from_json(row["cta_style_json"], []),
            "trust_close": str(row["trust_close"] or "").strip(),
            "words_to_use": _from_json(row["words_to_use_json"], []),
            "words_to_avoid": _from_json(row["words_to_avoid_json"], []),
            "forbidden_phrases": _from_json(row["forbidden_phrases_json"], []),
            "core_values": _from_json(row["core_values_json"], []),
            "additional_notes": str(row["additional_notes"] or "").strip(),
            "updated_at_utc": str(row["updated_at_utc"] or "").strip(),
        }
    finally:
        conn.close()


def get_inventory_snapshot(data_dir: str) -> dict:
    init_inventory_db(data_dir)
    products = fetch_products(data_dir)
    brand = fetch_brand_profile(data_dir)
    return {
        "db_path": get_db_path(data_dir),
        "products_count": len(products),
        "sample_product_ids": [str(p.get("id", "")) for p in products[:10]],
        "brand_profile_present": bool(brand),
        "brand_name": str(brand.get("brand_name", "")),
        "personality_name": str(brand.get("personality_name", "")),
        "brand_updated_at_utc": str(brand.get("updated_at_utc", "")),
    }
