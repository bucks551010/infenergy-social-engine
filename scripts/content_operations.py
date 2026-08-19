"""Durable content council, daily-slot, archive, outbox, and transaction state."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Any

from inventory_db import get_db_path, init_inventory_db

SLOTS = ("morning", "midday", "evening")
PLATFORMS = ("facebook", "instagram", "linkedin")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)


def _decode(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _connect(data_dir: str) -> sqlite3.Connection:
    init_inventory_db(data_dir)
    connection = sqlite3.connect(get_db_path(data_dir), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_content_operations(data_dir: str) -> str:
    connection = _connect(data_dir)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS council_sessions (
                decision_id TEXT PRIMARY KEY,
                content_date TEXT NOT NULL,
                slot TEXT NOT NULL,
                status TEXT NOT NULL,
                blackboard_json TEXT NOT NULL,
                rationale_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_council_date_slot
                ON council_sessions(content_date, slot);

            CREATE TABLE IF NOT EXISTS content_candidates (
                candidate_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                status TEXT NOT NULL,
                score REAL,
                loss_reasons_json TEXT NOT NULL,
                content_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(decision_id) REFERENCES council_sessions(decision_id)
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_decision
                ON content_candidates(decision_id, ordinal);

            CREATE TABLE IF NOT EXISTS daily_slots (
                content_date TEXT NOT NULL,
                slot TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                platform_policy_json TEXT NOT NULL,
                content_id TEXT,
                decision_id TEXT,
                outbox_id TEXT,
                status TEXT NOT NULL,
                ready_at TEXT,
                claimed_at TEXT,
                published_at TEXT,
                last_error TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(content_date, slot)
            );

            CREATE TABLE IF NOT EXISTS content_outbox (
                outbox_id TEXT PRIMARY KEY,
                content_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                content_date TEXT NOT NULL,
                slot TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                package_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                ready_at TEXT NOT NULL,
                claimed_at TEXT,
                published_at TEXT,
                last_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_due
                ON content_outbox(status, scheduled_at);

            CREATE TABLE IF NOT EXISTS platform_transactions (
                outbox_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                state TEXT NOT NULL,
                request_key TEXT NOT NULL,
                request_payload_json TEXT NOT NULL,
                external_id TEXT,
                provider_response_json TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(outbox_id, platform),
                UNIQUE(request_key),
                FOREIGN KEY(outbox_id) REFERENCES content_outbox(outbox_id)
            );
            """
        )
        connection.commit()
        return get_db_path(data_dir)
    finally:
        connection.close()


def ensure_daily_slots(
    data_dir: str,
    content_date: str | date,
    schedule: dict[str, str],
    platform_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    init_content_operations(data_dir)
    day = content_date.isoformat() if isinstance(content_date, date) else str(content_date)
    now = _now()
    connection = _connect(data_dir)
    try:
        for slot in SLOTS:
            scheduled_at = str(schedule[slot])
            connection.execute(
                """
                INSERT INTO daily_slots (
                    content_date, slot, scheduled_at, platform_policy_json,
                    status, updated_at
                ) VALUES (?, ?, ?, ?, 'UNPLANNED', ?)
                ON CONFLICT(content_date, slot) DO UPDATE SET
                    scheduled_at=excluded.scheduled_at,
                    platform_policy_json=excluded.platform_policy_json,
                    updated_at=excluded.updated_at
                """,
                (day, slot, scheduled_at, _json(platform_policy), now),
            )
        connection.commit()
        return daily_status(data_dir, day)["slots"]
    finally:
        connection.close()


def create_council_session(
    data_dir: str,
    *,
    content_date: str,
    slot: str,
    blackboard: dict[str, Any],
    rationale: list[str] | None = None,
    decision_id: str | None = None,
) -> str:
    identifier = decision_id or uuid.uuid4().hex
    now = _now()
    connection = _connect(data_dir)
    try:
        connection.execute(
            """
            INSERT INTO council_sessions VALUES (?, ?, ?, 'COUNCIL_ACTIVE', ?, ?, ?, ?)
            """,
            (identifier, content_date, slot, _json(blackboard), _json(rationale or []), now, now),
        )
        connection.execute(
            """
            UPDATE daily_slots SET decision_id=?, status='COUNCIL_ACTIVE', updated_at=?
            WHERE content_date=? AND slot=?
            """,
            (identifier, now, content_date, slot),
        )
        connection.commit()
        return identifier
    finally:
        connection.close()


def archive_candidate(
    data_dir: str,
    *,
    decision_id: str,
    ordinal: int,
    content: dict[str, Any],
    status: str,
    score: float | None = None,
    loss_reasons: list[str] | None = None,
) -> str:
    candidate_id = str(content.get("candidate_id") or content.get("post_id") or uuid.uuid4().hex)
    connection = _connect(data_dir)
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO content_candidates
            (candidate_id, decision_id, ordinal, status, score, loss_reasons_json, content_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (candidate_id, decision_id, ordinal, status, score, _json(loss_reasons or []), _json(content), _now()),
        )
        connection.commit()
        return candidate_id
    finally:
        connection.close()


def mark_ready(
    data_dir: str,
    *,
    content_date: str,
    slot: str,
    scheduled_at: str,
    decision_id: str,
    package: dict[str, Any],
) -> str:
    outbox_id = uuid.uuid4().hex
    content_id = str(package.get("content_id") or package.get("post_id") or uuid.uuid4().hex)
    now = _now()
    connection = _connect(data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE")
        session = connection.execute(
            "SELECT blackboard_json FROM council_sessions WHERE decision_id=?",
            (decision_id,),
        ).fetchone()
        blackboard = _decode(session["blackboard_json"], {}) if session else {}
        platform_posts = package.get("platform_posts") if isinstance(package.get("platform_posts"), dict) else {}
        blackboard.update({
            "research": package.get("research") or package.get("research_summary") or {},
            "content_readiness": package.get("evidence_readiness") or package.get("claim_ledger") or {},
            "master_copy": package.get("master_copy") or package.get("copy") or package.get("wp_content") or "",
            "final_copy": {
                "facebook": ((platform_posts.get("facebook") or {}).get("final_caption") or package.get("fb_caption") or ""),
                "instagram": ((platform_posts.get("instagram") or {}).get("final_caption") or package.get("ig_caption") or ""),
                "linkedin": ((platform_posts.get("linkedin") or {}).get("final_caption") or package.get("li_text") or ""),
            },
            "engagement": package.get("engagement") or {"cta": package.get("selected_cta") or ""},
            "creative_routes": package.get("creative_routes") or package.get("visual_plan", {}).get("creative_routes") or [],
            "art_direction": package.get("visual_plan") or {},
            "visual_assets": package.get("generated_visuals") or {},
            "selected_visual": package.get("primary_publish_image_url") or package.get("generated_visuals") or {},
            "platform_presentations": platform_posts,
            "destination": package.get("destination_url") or "",
            "schedule": {"date": content_date, "slot": slot, "scheduled_at": scheduled_at},
            "archive_state": "ARCHIVED",
            "publication_state": "READY",
        })
        connection.execute(
            """
            INSERT INTO content_outbox
            (outbox_id, content_id, decision_id, content_date, slot, scheduled_at,
             package_json, status, created_at, ready_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'READY', ?, ?)
            """,
            (outbox_id, content_id, decision_id, content_date, slot, scheduled_at, _json(package), now, now),
        )
        connection.execute(
            """
            UPDATE daily_slots SET content_id=?, decision_id=?, outbox_id=?, status='READY',
                ready_at=?, updated_at=?, last_error=NULL
            WHERE content_date=? AND slot=?
            """,
            (content_id, decision_id, outbox_id, now, now, content_date, slot),
        )
        connection.execute(
            "UPDATE council_sessions SET status='READY', blackboard_json=?, updated_at=? WHERE decision_id=?",
            (_json(blackboard), now, decision_id),
        )
        connection.commit()
        return outbox_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def claim_due(data_dir: str, now_utc: str | None = None) -> dict[str, Any] | None:
    now = now_utc or _now()
    connection = _connect(data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT * FROM content_outbox
            WHERE status IN ('READY', 'DUE') AND scheduled_at <= ?
            ORDER BY scheduled_at, created_at LIMIT 1
            """,
            (now,),
        ).fetchone()
        if not row:
            connection.commit()
            return None
        claimed_at = _now()
        changed = connection.execute(
            """
            UPDATE content_outbox SET status='CLAIMED', claimed_at=?, attempt_count=attempt_count+1
            WHERE outbox_id=? AND status IN ('READY', 'DUE')
            """,
            (claimed_at, row["outbox_id"]),
        ).rowcount
        if changed != 1:
            connection.rollback()
            return None
        connection.execute(
            """
            UPDATE daily_slots SET status='CLAIMED', claimed_at=?, updated_at=?
            WHERE outbox_id=?
            """,
            (claimed_at, claimed_at, row["outbox_id"]),
        )
        connection.commit()
        result = dict(row)
        result["status"] = "CLAIMED"
        result["claimed_at"] = claimed_at
        result["package"] = _decode(result.pop("package_json"), {})
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def begin_platform_transaction(
    data_dir: str,
    *,
    outbox_id: str,
    platform: str,
    payload: dict[str, Any],
) -> str:
    if platform not in PLATFORMS:
        raise ValueError(f"unsupported platform: {platform}")
    request_key = f"{outbox_id}:{platform}"
    now = _now()
    connection = _connect(data_dir)
    try:
        connection.execute(
            """
            INSERT INTO platform_transactions
            (outbox_id, platform, state, request_key, request_payload_json,
             attempt_count, created_at, updated_at)
            VALUES (?, ?, 'REQUEST_SENT', ?, ?, 1, ?, ?)
            ON CONFLICT(outbox_id, platform) DO UPDATE SET
                state=CASE
                    WHEN platform_transactions.state='CONFIRMED_SUCCESS' THEN platform_transactions.state
                    WHEN platform_transactions.state='AMBIGUOUS' THEN platform_transactions.state
                    ELSE 'REQUEST_SENT'
                END,
                request_payload_json=excluded.request_payload_json,
                attempt_count=platform_transactions.attempt_count+1,
                updated_at=excluded.updated_at
            """,
            (outbox_id, platform, request_key, _json(payload), now, now),
        )
        connection.commit()
        return request_key
    finally:
        connection.close()


def platform_transaction(data_dir: str, outbox_id: str, platform: str) -> dict[str, Any]:
    connection = _connect(data_dir)
    try:
        row = connection.execute(
            "SELECT * FROM platform_transactions WHERE outbox_id=? AND platform=?",
            (outbox_id, platform),
        ).fetchone()
        if not row:
            return {}
        result = dict(row)
        result["request_payload"] = _decode(result.pop("request_payload_json"), {})
        result["provider_response"] = _decode(result.pop("provider_response_json"), {})
        return result
    finally:
        connection.close()


def complete_platform_transaction(
    data_dir: str,
    *,
    outbox_id: str,
    platform: str,
    state: str,
    external_id: str = "",
    provider_response: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    allowed = {"CONFIRMED_SUCCESS", "CONFIRMED_FAILURE", "AMBIGUOUS", "AUTH_ACTION_REQUIRED"}
    if state not in allowed:
        raise ValueError(f"invalid transaction state: {state}")
    connection = _connect(data_dir)
    try:
        connection.execute(
            """
            UPDATE platform_transactions
            SET state=?, external_id=?, provider_response_json=?, last_error=?, updated_at=?
            WHERE outbox_id=? AND platform=?
            """,
            (state, external_id or None, _json(provider_response or {}), error or None, _now(), outbox_id, platform),
        )
        connection.commit()
    finally:
        connection.close()


def release_outbox(data_dir: str, outbox_id: str, error: str) -> None:
    now = _now()
    connection = _connect(data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE content_outbox SET status='READY', claimed_at=NULL, last_error=? WHERE outbox_id=?",
            (error, outbox_id),
        )
        connection.execute(
            "UPDATE daily_slots SET status='READY', claimed_at=NULL, last_error=?, updated_at=? WHERE outbox_id=?",
            (error, now, outbox_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def recover_outbox(data_dir: str, outbox_id: str, error: str) -> None:
    now = _now()
    connection = _connect(data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE content_outbox SET status='RECOVERING', claimed_at=NULL, last_error=? WHERE outbox_id=?",
            (error, outbox_id),
        )
        connection.execute(
            "UPDATE daily_slots SET status='RECOVERING', claimed_at=NULL, last_error=?, updated_at=? WHERE outbox_id=?",
            (error, now, outbox_id),
        )
        connection.execute(
            """
            UPDATE council_sessions SET status='RECOVERING', updated_at=?
            WHERE decision_id=(SELECT decision_id FROM content_outbox WHERE outbox_id=?)
            """,
            (now, outbox_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def reconcile_ready_inventory(data_dir: str) -> list[dict[str, str]]:
    connection = _connect(data_dir)
    recovered: list[dict[str, str]] = []
    try:
        rows = connection.execute(
            "SELECT outbox_id, package_json FROM content_outbox WHERE status='READY'"
        ).fetchall()
    finally:
        connection.close()
    for row in rows:
        package = _decode(row["package_json"], {})
        routing = package.get("routing") if isinstance(package.get("routing"), dict) else {}
        platforms = routing.get("platforms") if isinstance(routing.get("platforms"), list) else []
        issue = ""
        if not platforms:
            issue = "ready_package_has_no_routed_platforms"
        visuals = package.get("generated_visuals") if isinstance(package.get("generated_visuals"), dict) else {}
        engines = visuals.get("render_engines") if isinstance(visuals.get("render_engines"), dict) else {}
        reviews = visuals.get("artifact_reviews") if isinstance(visuals.get("artifact_reviews"), dict) else {}
        visual_plan = package.get("visual_plan") if isinstance(package.get("visual_plan"), dict) else {}
        route = str(visual_plan.get("creative_route") or visual_plan.get("visual_format") or "").strip().upper()
        explicit_packshot = route in {"PACKSHOT", "PACKSHOT_ONLY", "PREMIUM_PRODUCT_HERO"}
        for platform in platforms:
            review = reviews.get(platform) if isinstance(reviews.get(platform), dict) else {}
            if review.get("verdict") == "REGENERATE_VISUAL":
                issue = f"{platform}_visual_requires_recovery"
                break
            if str(engines.get(platform) or "") == "approved_product_photo" and not explicit_packshot:
                issue = f"{platform}_packshot_only_without_explicit_route"
                break
        if issue:
            recover_outbox(data_dir, str(row["outbox_id"]), issue)
            recovered.append({"outbox_id": str(row["outbox_id"]), "reason": issue})
    return recovered


def finalize_outbox(
    data_dir: str,
    outbox_id: str,
    *,
    status: str,
    error: str = "",
) -> None:
    allowed = {"PUBLISHED", "EXTERNAL_ACTION_REQUIRED"}
    if status not in allowed:
        raise ValueError(f"invalid outbox final status: {status}")
    now = _now()
    published_at = now if status == "PUBLISHED" else None
    connection = _connect(data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE content_outbox SET status=?, published_at=?, last_error=? WHERE outbox_id=?
            """,
            (status, published_at, error or None, outbox_id),
        )
        connection.execute(
            """
            UPDATE daily_slots SET status=?, published_at=?, last_error=?, updated_at=? WHERE outbox_id=?
            """,
            (status, published_at, error or None, now, outbox_id),
        )
        connection.execute(
            """
            UPDATE council_sessions SET status=?, updated_at=?
            WHERE decision_id=(SELECT decision_id FROM content_outbox WHERE outbox_id=?)
            """,
            (status, now, outbox_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def mark_slot_external_action(
    data_dir: str,
    *,
    content_date: str,
    slot: str,
    decision_id: str,
    error: str,
) -> None:
    now = _now()
    connection = _connect(data_dir)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE daily_slots SET status='EXTERNAL_ACTION_REQUIRED', decision_id=?,
                last_error=?, updated_at=? WHERE content_date=? AND slot=?
            """,
            (decision_id, error, now, content_date, slot),
        )
        connection.execute(
            "UPDATE council_sessions SET status='EXTERNAL_ACTION_REQUIRED', updated_at=? WHERE decision_id=?",
            (now, decision_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def daily_status(data_dir: str, content_date: str | date | None = None) -> dict[str, Any]:
    day = content_date.isoformat() if isinstance(content_date, date) else str(content_date or date.today().isoformat())
    connection = _connect(data_dir)
    try:
        rows = connection.execute(
            "SELECT * FROM daily_slots WHERE content_date=? ORDER BY scheduled_at",
            (day,),
        ).fetchall()
        slots = []
        for row in rows:
            item = dict(row)
            item["platform_policy"] = _decode(item.pop("platform_policy_json"), {})
            slots.append(item)
        counts = {status: sum(1 for row in slots if row["status"] == status) for status in {
            "UNPLANNED", "COUNCIL_ACTIVE", "READY", "DUE", "CLAIMED", "PUBLISHING", "PUBLISHED", "EXTERNAL_ACTION_REQUIRED"
        }}
        ready = counts.get("READY", 0) + counts.get("DUE", 0)
        published = counts.get("PUBLISHED", 0)
        return {
            "date": day,
            "required": len(SLOTS),
            "published": published,
            "ready": ready,
            "in_production": counts.get("CLAIMED", 0) + counts.get("PUBLISHING", 0),
            "missing": max(0, len(SLOTS) - published - ready - counts.get("CLAIMED", 0) - counts.get("PUBLISHING", 0)),
            "slots": slots,
        }
    finally:
        connection.close()


def content_detail(data_dir: str, decision_id: str) -> dict[str, Any]:
    connection = _connect(data_dir)
    try:
        session = connection.execute(
            "SELECT * FROM council_sessions WHERE decision_id=?", (decision_id,)
        ).fetchone()
        if not session:
            return {}
        candidates = connection.execute(
            "SELECT * FROM content_candidates WHERE decision_id=? ORDER BY ordinal", (decision_id,)
        ).fetchall()
        result = dict(session)
        result["blackboard"] = _decode(result.pop("blackboard_json"), {})
        result["rationale"] = _decode(result.pop("rationale_json"), [])
        result["candidates"] = []
        for candidate in candidates:
            item = dict(candidate)
            item["loss_reasons"] = _decode(item.pop("loss_reasons_json"), [])
            item["content"] = _decode(item.pop("content_json"), {})
            result["candidates"].append(item)
        outbox = connection.execute(
            "SELECT * FROM content_outbox WHERE decision_id=? ORDER BY created_at", (decision_id,)
        ).fetchall()
        result["outbox"] = []
        for row in outbox:
            item = dict(row)
            item["package"] = _decode(item.pop("package_json"), {})
            transactions = connection.execute(
                "SELECT * FROM platform_transactions WHERE outbox_id=? ORDER BY platform",
                (item["outbox_id"],),
            ).fetchall()
            item["transactions"] = []
            for transaction in transactions:
                record = dict(transaction)
                record["request_payload"] = _decode(record.pop("request_payload_json"), {})
                record["provider_response"] = _decode(record.pop("provider_response_json"), {})
                item["transactions"].append(record)
            result["outbox"].append(item)
        return result
    finally:
        connection.close()


def daily_index(data_dir: str, content_date: str | date | None = None) -> dict[str, Any]:
    summary = daily_status(data_dir, content_date)
    details: list[dict[str, Any]] = []
    for slot in summary["slots"]:
        decision_id = str(slot.get("decision_id") or "")
        details.append(content_detail(data_dir, decision_id) if decision_id else {"slot": slot["slot"]})
    return {**summary, "details": details}
