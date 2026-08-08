import json
import hashlib
import os
import re
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

            CREATE TABLE IF NOT EXISTS selling_ideology (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                framework_mode TEXT,
                primary_conversion TEXT,
                tone_blend TEXT,
                value_lens TEXT,
                message_filter TEXT,
                cta_mode TEXT,
                campaign_behavior TEXT,
                proof_rule TEXT,
                disqualify_alternative TEXT,
                core_promise TEXT,
                audience_priority_json TEXT,
                psychographics_json TEXT,
                lifestyle_positioning_json TEXT,
                pillar_messages_json TEXT,
                objection_handling_json TEXT,
                cta_ladder_json TEXT,
                banned_phrases_json TEXT,
                schema_version TEXT,
                updated_at_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gemini_style_reference_repo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                style_key TEXT UNIQUE,
                style_name TEXT NOT NULL,
                reference_url TEXT,
                visual_product_image_override_url TEXT,
                style_notes TEXT,
                tags_json TEXT,
                priority INTEGER DEFAULT 100,
                active INTEGER DEFAULT 1,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS visual_generation_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                active_style_keys_json TEXT,
                visual_product_image_override_url TEXT,
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


def has_selling_ideology(data_dir: str) -> bool:
    conn = _connect(data_dir)
    try:
        row = conn.execute("SELECT 1 AS ok FROM selling_ideology WHERE id = 1").fetchone()
        return bool(row)
    finally:
        conn.close()


def upsert_selling_ideology(data_dir: str, ideology: dict) -> bool:
    if not isinstance(ideology, dict):
        return False

    conn = _connect(data_dir)
    try:
        conn.execute(
            """
            INSERT INTO selling_ideology (
                id, framework_mode, primary_conversion, tone_blend, value_lens,
                message_filter, cta_mode, campaign_behavior, proof_rule,
                disqualify_alternative, core_promise, audience_priority_json,
                psychographics_json, lifestyle_positioning_json,
                pillar_messages_json, objection_handling_json, cta_ladder_json,
                banned_phrases_json, schema_version, updated_at_utc
            ) VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                framework_mode = excluded.framework_mode,
                primary_conversion = excluded.primary_conversion,
                tone_blend = excluded.tone_blend,
                value_lens = excluded.value_lens,
                message_filter = excluded.message_filter,
                cta_mode = excluded.cta_mode,
                campaign_behavior = excluded.campaign_behavior,
                proof_rule = excluded.proof_rule,
                disqualify_alternative = excluded.disqualify_alternative,
                core_promise = excluded.core_promise,
                audience_priority_json = excluded.audience_priority_json,
                psychographics_json = excluded.psychographics_json,
                lifestyle_positioning_json = excluded.lifestyle_positioning_json,
                pillar_messages_json = excluded.pillar_messages_json,
                objection_handling_json = excluded.objection_handling_json,
                cta_ladder_json = excluded.cta_ladder_json,
                banned_phrases_json = excluded.banned_phrases_json,
                schema_version = excluded.schema_version,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                str(ideology.get("framework_mode", "")).strip(),
                str(ideology.get("primary_conversion", "")).strip(),
                str(ideology.get("tone_blend", "")).strip(),
                str(ideology.get("value_lens", "")).strip(),
                str(ideology.get("message_filter", "")).strip(),
                str(ideology.get("cta_mode", "")).strip(),
                str(ideology.get("campaign_behavior", "")).strip(),
                str(ideology.get("proof_rule", "")).strip(),
                str(ideology.get("disqualify_alternative", "")).strip(),
                str(ideology.get("core_promise", "")).strip(),
                _to_json(ideology.get("audience_priority", [])),
                _to_json(ideology.get("psychographics", [])),
                _to_json(ideology.get("lifestyle_positioning", [])),
                _to_json(ideology.get("pillar_messages", [])),
                _to_json(ideology.get("objection_handling", [])),
                _to_json(ideology.get("cta_ladder", [])),
                _to_json(ideology.get("banned_phrases", [])),
                str(ideology.get("schema_version", "v1")).strip() or "v1",
                _utc_now(),
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def fetch_selling_ideology(data_dir: str) -> dict:
    conn = _connect(data_dir)
    try:
        row = conn.execute("SELECT * FROM selling_ideology WHERE id = 1").fetchone()
        if not row:
            return {}
        return {
            "framework_mode": str(row["framework_mode"] or "").strip(),
            "primary_conversion": str(row["primary_conversion"] or "").strip(),
            "tone_blend": str(row["tone_blend"] or "").strip(),
            "value_lens": str(row["value_lens"] or "").strip(),
            "message_filter": str(row["message_filter"] or "").strip(),
            "cta_mode": str(row["cta_mode"] or "").strip(),
            "campaign_behavior": str(row["campaign_behavior"] or "").strip(),
            "proof_rule": str(row["proof_rule"] or "").strip(),
            "disqualify_alternative": str(row["disqualify_alternative"] or "").strip(),
            "core_promise": str(row["core_promise"] or "").strip(),
            "audience_priority": _from_json(row["audience_priority_json"], []),
            "psychographics": _from_json(row["psychographics_json"], []),
            "lifestyle_positioning": _from_json(row["lifestyle_positioning_json"], []),
            "pillar_messages": _from_json(row["pillar_messages_json"], []),
            "objection_handling": _from_json(row["objection_handling_json"], []),
            "cta_ladder": _from_json(row["cta_ladder_json"], []),
            "banned_phrases": _from_json(row["banned_phrases_json"], []),
            "schema_version": str(row["schema_version"] or "v1").strip(),
            "updated_at_utc": str(row["updated_at_utc"] or "").strip(),
        }
    finally:
        conn.close()


def fetch_gemini_style_references(data_dir: str, active_only: bool = True, limit: int = 50) -> list[dict]:
    init_inventory_db(data_dir)
    conn = _connect(data_dir)
    try:
        query = (
            "SELECT id, style_key, style_name, reference_url, visual_product_image_override_url, "
            "style_notes, tags_json, priority, active, created_at_utc, updated_at_utc "
            "FROM gemini_style_reference_repo "
        )
        args: list = []
        if active_only:
            query += "WHERE active = 1 "
        query += "ORDER BY priority ASC, id ASC LIMIT ?"
        args.append(max(1, min(int(limit or 50), 500)))
        rows = conn.execute(query, tuple(args)).fetchall()
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "id": int(row["id"]),
                    "style_key": str(row["style_key"] or "").strip(),
                    "style_name": str(row["style_name"] or "").strip(),
                    "reference_url": str(row["reference_url"] or "").strip(),
                    "visual_product_image_override_url": str(row["visual_product_image_override_url"] or "").strip(),
                    "style_notes": str(row["style_notes"] or "").strip(),
                    "tags": _from_json(row["tags_json"], []),
                    "priority": int(row["priority"] or 100),
                    "active": bool(int(row["active"] or 0)),
                    "created_at_utc": str(row["created_at_utc"] or "").strip(),
                    "updated_at_utc": str(row["updated_at_utc"] or "").strip(),
                }
            )
        return out
    finally:
        conn.close()


def fetch_visual_generation_settings(data_dir: str) -> dict:
    init_inventory_db(data_dir)
    conn = _connect(data_dir)
    try:
        row = conn.execute("SELECT * FROM visual_generation_settings WHERE id = 1").fetchone()
        if not row:
            return {
                "active_style_keys": [],
                "visual_product_image_override_url": "",
                "updated_at_utc": "",
            }
        return {
            "active_style_keys": _from_json(row["active_style_keys_json"], []),
            "visual_product_image_override_url": str(row["visual_product_image_override_url"] or "").strip(),
            "updated_at_utc": str(row["updated_at_utc"] or "").strip(),
        }
    finally:
        conn.close()


def upsert_visual_generation_settings(data_dir: str, settings: dict) -> bool:
    if not isinstance(settings, dict):
        return False
    init_inventory_db(data_dir)
    conn = _connect(data_dir)
    try:
        conn.execute(
            """
            INSERT INTO visual_generation_settings (
                id, active_style_keys_json, visual_product_image_override_url, updated_at_utc
            ) VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                active_style_keys_json = excluded.active_style_keys_json,
                visual_product_image_override_url = excluded.visual_product_image_override_url,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                _to_json(settings.get("active_style_keys", [])),
                str(settings.get("visual_product_image_override_url", "")).strip(),
                _utc_now(),
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def upsert_gemini_style_references(data_dir: str, references: list[dict]) -> int:
    if not isinstance(references, list):
        return 0
    init_inventory_db(data_dir)
    conn = _connect(data_dir)
    try:
        now = _utc_now()
        rows = []
        for ref in references:
            if not isinstance(ref, dict):
                continue
            style_key = str(ref.get("style_key", "")).strip().lower()
            style_name = str(ref.get("style_name", "")).strip()
            if not style_key:
                style_key = re.sub(r"[^a-z0-9]+", "_", style_name.lower()).strip("_")
            if not style_key or not style_name:
                continue
            rows.append(
                (
                    style_key,
                    style_name,
                    str(ref.get("reference_url", "")).strip(),
                    str(ref.get("visual_product_image_override_url", "")).strip(),
                    str(ref.get("style_notes", "")).strip(),
                    _to_json(ref.get("tags", [])),
                    int(ref.get("priority", 100) or 100),
                    1 if bool(ref.get("active", True)) else 0,
                    now,
                    now,
                )
            )
        if not rows:
            return 0

        conn.executemany(
            """
            INSERT INTO gemini_style_reference_repo (
                style_key, style_name, reference_url, visual_product_image_override_url,
                style_notes, tags_json, priority, active, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(style_key) DO UPDATE SET
                style_name = excluded.style_name,
                reference_url = excluded.reference_url,
                visual_product_image_override_url = excluded.visual_product_image_override_url,
                style_notes = excluded.style_notes,
                tags_json = excluded.tags_json,
                priority = excluded.priority,
                active = excluded.active,
                updated_at_utc = excluded.updated_at_utc
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def seed_gemini_style_idea_repo(data_dir: str) -> dict:
    refs = [
        {
            "style_key": "review_board_high_contrast",
            "style_name": "Review Board High Contrast",
            "style_notes": "Dark steel background, yellow review lockup, dense trust badges, product hero right.",
            "tags": ["high_contrast", "review", "badge_grid", "retail_board"],
            "priority": 10,
            "active": True,
        },
        {
            "style_key": "warm_lifestyle_orange",
            "style_name": "Warm Lifestyle Orange",
            "style_notes": "Warm orange light, aspirational human context, simplified icon row and strong CTA rail.",
            "tags": ["lifestyle", "warm_palette", "cta_focus"],
            "priority": 20,
            "active": True,
        },
        {
            "style_key": "spec_comparison_overlay",
            "style_name": "Spec Comparison Overlay",
            "style_notes": "Side-by-side performance framing, technical overlays, clear stat hierarchy.",
            "tags": ["comparison", "specs", "proof"],
            "priority": 30,
            "active": True,
        },
        {
            "style_key": "urgent_power_cta",
            "style_name": "Urgent Power CTA",
            "style_notes": "Emergency-use positioning, hazard accent color, scarcity CTA treatment.",
            "tags": ["urgency", "cta", "emergency"],
            "priority": 40,
            "active": True,
        },
        {
            "style_key": "infographic_grid_proof",
            "style_name": "Infographic Grid Proof",
            "style_notes": "Compact icon tiles for proof points, legible metrics, premium editorial spacing.",
            "tags": ["infographic", "proof", "icons"],
            "priority": 50,
            "active": True,
        },
    ]
    added = upsert_gemini_style_references(data_dir, refs)
    settings = fetch_visual_generation_settings(data_dir)
    active_keys = settings.get("active_style_keys", []) if isinstance(settings, dict) else []
    if not active_keys:
        upsert_visual_generation_settings(
            data_dir,
            {
                "active_style_keys": [r["style_key"] for r in refs],
                "visual_product_image_override_url": str(settings.get("visual_product_image_override_url", "")) if isinstance(settings, dict) else "",
            },
        )
    return {
        "seeded": added,
        "active_styles": [r["style_key"] for r in refs],
    }


def bootstrap_visual_repo_from_env(data_dir: str) -> dict:
    init_inventory_db(data_dir)
    summary = {
        "auto_seeded": 0,
        "imported_refs": 0,
        "deduped_refs": 0,
        "override_updated": False,
        "active_keys_updated": False,
    }

    all_refs = fetch_gemini_style_references(data_dir, active_only=False, limit=500)
    allow_seed = str(os.environ.get("VISUAL_REPO_AUTO_SEED", "true")).strip().lower() not in ("0", "false", "no")
    if allow_seed and not all_refs:
        seeded = seed_gemini_style_idea_repo(data_dir)
        summary["auto_seeded"] = int(seeded.get("seeded", 0) or 0)
        all_refs = fetch_gemini_style_references(data_dir, active_only=False, limit=500)

    refs_env = str(os.environ.get("GEMINI_STYLE_REFERENCES", "")).strip()
    if refs_env:
        raw_items = [p.strip() for p in re.split(r"[;\n,]", refs_env) if p.strip()]
        imported: list[dict] = []
        stable_keys: set[str] = set()
        env_urls: list[str] = []
        rank = 1000
        for item in raw_items:
            if not item.startswith("http"):
                continue
            normalized_url = item.strip()
            style_key = f"env_ref_{hashlib.sha1(normalized_url.encode('utf-8')).hexdigest()[:12]}"
            stable_keys.add(style_key)
            env_urls.append(normalized_url)
            imported.append(
                {
                    "style_key": style_key,
                    "style_name": f"Env Reference {rank - 999}",
                    "reference_url": normalized_url,
                    "visual_product_image_override_url": "",
                    "style_notes": "Imported from GEMINI_STYLE_REFERENCES",
                    "tags": ["env_import", "reference"],
                    "priority": rank,
                    "active": True,
                }
            )
            rank += 1
        if imported:
            summary["imported_refs"] = upsert_gemini_style_references(data_dir, imported)
            conn = _connect(data_dir)
            try:
                url_placeholders = ", ".join(["?"] * len(env_urls))
                key_placeholders = ", ".join(["?"] * len(stable_keys))
                cleanup_sql = (
                    "DELETE FROM gemini_style_reference_repo "
                    "WHERE style_notes = ? "
                    f"AND reference_url IN ({url_placeholders}) "
                    f"AND style_key NOT IN ({key_placeholders})"
                )
                params = [
                    "Imported from GEMINI_STYLE_REFERENCES",
                    *env_urls,
                    *sorted(stable_keys),
                ]
                cur = conn.execute(cleanup_sql, tuple(params))
                summary["deduped_refs"] = int(cur.rowcount or 0)
                conn.commit()
            finally:
                conn.close()

    settings = fetch_visual_generation_settings(data_dir)
    override_env = str(os.environ.get("VISUAL_PRODUCT_IMAGE_OVERRIDE", "")).strip()
    active_keys_env = str(os.environ.get("GEMINI_STYLE_ACTIVE_KEYS", "")).strip()

    next_override = str(settings.get("visual_product_image_override_url", "")).strip()
    if override_env and override_env.startswith("http") and override_env != next_override:
        next_override = override_env
        summary["override_updated"] = True

    next_active_keys = settings.get("active_style_keys", []) if isinstance(settings.get("active_style_keys", []), list) else []
    if active_keys_env:
        parsed_keys = [k.strip().lower() for k in active_keys_env.split(",") if k.strip()]
        if parsed_keys and parsed_keys != next_active_keys:
            next_active_keys = parsed_keys
            summary["active_keys_updated"] = True
    elif not next_active_keys:
        refs = fetch_gemini_style_references(data_dir, active_only=True, limit=500)
        fallback_keys = [str(r.get("style_key", "")).strip() for r in refs if str(r.get("style_key", "")).strip()]
        if fallback_keys:
            next_active_keys = fallback_keys
            summary["active_keys_updated"] = True

    upsert_visual_generation_settings(
        data_dir,
        {
            "active_style_keys": next_active_keys,
            "visual_product_image_override_url": next_override,
        },
    )
    summary["repo_count"] = len(fetch_gemini_style_references(data_dir, active_only=False, limit=500))
    summary["active_count"] = len(fetch_gemini_style_references(data_dir, active_only=True, limit=500))
    return summary


def get_inventory_snapshot(data_dir: str) -> dict:
    init_inventory_db(data_dir)
    products = fetch_products(data_dir)
    brand = fetch_brand_profile(data_dir)
    ideology = fetch_selling_ideology(data_dir)
    visual_settings = fetch_visual_generation_settings(data_dir)
    style_refs = fetch_gemini_style_references(data_dir, active_only=False, limit=500)
    return {
        "db_path": get_db_path(data_dir),
        "products_count": len(products),
        "sample_product_ids": [str(p.get("id", "")) for p in products[:10]],
        "brand_profile_present": bool(brand),
        "selling_ideology_present": bool(ideology),
        "gemini_style_repo_count": len(style_refs),
        "gemini_style_repo_active_count": len([r for r in style_refs if r.get("active")]),
        "visual_override_url_present": bool(str(visual_settings.get("visual_product_image_override_url", "")).strip()),
        "brand_name": str(brand.get("brand_name", "")),
        "personality_name": str(brand.get("personality_name", "")),
        "brand_updated_at_utc": str(brand.get("updated_at_utc", "")),
        "selling_ideology_updated_at_utc": str(ideology.get("updated_at_utc", "")),
        "visual_settings_updated_at_utc": str(visual_settings.get("updated_at_utc", "")),
    }
