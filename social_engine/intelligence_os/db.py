from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def database_path(data_dir: str) -> str:
    name = os.environ.get("INTELLIGENCE_OS_DB_FILE", "intelligence_os.db").strip()
    return os.path.join(data_dir, name or "intelligence_os.db")


@contextmanager
def connect(data_dir: str) -> Iterator[sqlite3.Connection]:
    os.makedirs(data_dir, exist_ok=True)
    connection = sqlite3.connect(database_path(data_dir), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
    finally:
        connection.close()


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def decode(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def initialize(data_dir: str) -> str:
    now = utc_now()
    with connect(data_dir) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS os_schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_capabilities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                domain TEXT NOT NULL,
                input_schema_json TEXT NOT NULL,
                output_schema_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                cost_class TEXT NOT NULL,
                permission_requirement TEXT NOT NULL,
                synchronous INTEGER NOT NULL,
                supports_dry_run INTEGER NOT NULL,
                supports_rollback INTEGER NOT NULL,
                version TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                health TEXT NOT NULL DEFAULT 'UNKNOWN',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_policies (
                id TEXT PRIMARY KEY,
                capability TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                rule TEXT NOT NULL,
                approval_level TEXT NOT NULL,
                limits_json TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_until TEXT,
                created_by TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_os_policies_capability
                ON os_policies(capability, status);

            CREATE TABLE IF NOT EXISTS os_approvals (
                id TEXT PRIMARY KEY,
                capability TEXT NOT NULL,
                actor TEXT NOT NULL,
                request_json TEXT NOT NULL,
                status TEXT NOT NULL,
                decided_by TEXT,
                decision_note TEXT,
                created_at TEXT NOT NULL,
                decided_at TEXT
            );

            CREATE TABLE IF NOT EXISTS os_audit_log (
                id TEXT PRIMARY KEY,
                actor TEXT NOT NULL,
                model_or_tool TEXT NOT NULL,
                action TEXT NOT NULL,
                input_reference TEXT,
                result_json TEXT NOT NULL,
                status TEXT NOT NULL,
                transaction_id TEXT,
                approval_id TEXT,
                cost_usd REAL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_os_audit_created
                ON os_audit_log(created_at DESC);

            CREATE TABLE IF NOT EXISTS os_transactions (
                id TEXT PRIMARY KEY,
                operation_id TEXT NOT NULL UNIQUE,
                objective TEXT NOT NULL,
                actor TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                status TEXT NOT NULL,
                before_state_json TEXT NOT NULL,
                after_state_json TEXT NOT NULL,
                rollback_data_json TEXT NOT NULL,
                irreversible_json TEXT NOT NULL,
                owner_approval TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_transaction_operations (
                id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                capability TEXT NOT NULL,
                input_json TEXT NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                rollback_json TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(transaction_id) REFERENCES os_transactions(id)
            );

            CREATE TABLE IF NOT EXISTS os_events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                subject_type TEXT,
                subject_id TEXT,
                payload_json TEXT NOT NULL,
                materiality REAL NOT NULL DEFAULT 0,
                occurred_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                processed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_os_events_unprocessed
                ON os_events(processed_at, materiality DESC, occurred_at DESC);

            CREATE TABLE IF NOT EXISTS os_attention_items (
                id TEXT PRIMARY KEY,
                event_id TEXT,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                urgency REAL NOT NULL,
                impact REAL NOT NULL,
                confidence REAL NOT NULL,
                time_sensitivity REAL NOT NULL,
                reversibility REAL NOT NULL,
                opportunity_value REAL NOT NULL,
                risk_value REAL NOT NULL,
                owner_relevance REAL NOT NULL,
                score REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(event_id) REFERENCES os_events(id)
            );

            CREATE TABLE IF NOT EXISTS os_jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                objective TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                current_step INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL,
                errors_json TEXT NOT NULL,
                cost_usd REAL NOT NULL DEFAULT 0,
                steering_json TEXT NOT NULL,
                operation_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_job_steps (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                checkpoint_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                error TEXT,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(job_id, ordinal),
                FOREIGN KEY(job_id) REFERENCES os_jobs(id)
            );

            CREATE TABLE IF NOT EXISTS os_workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                trigger_json TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                failure_policy_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_automations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                trigger_json TEXT NOT NULL,
                conditions_json TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                permissions_json TEXT NOT NULL,
                approval_rules_json TEXT NOT NULL,
                schedule_json TEXT NOT NULL,
                status TEXT NOT NULL,
                last_run TEXT,
                next_run TEXT,
                failure_policy_json TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_automation_runs (
                id TEXT PRIMARY KEY,
                automation_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                trigger_payload_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY(automation_id) REFERENCES os_automations(id)
            );

            CREATE INDEX IF NOT EXISTS idx_os_automation_runs_automation
                ON os_automation_runs(automation_id, started_at DESC);

            CREATE TABLE IF NOT EXISTS os_watches (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                frequency TEXT NOT NULL,
                source_policy_json TEXT NOT NULL,
                materiality_threshold REAL NOT NULL,
                condition_json TEXT NOT NULL,
                actions_json TEXT NOT NULL,
                expires_at TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_conversations (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                title TEXT NOT NULL,
                copilot_session_id TEXT,
                status TEXT NOT NULL,
                active_context_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES os_conversations(id)
            );

            CREATE TABLE IF NOT EXISTS os_creatives (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                title TEXT NOT NULL,
                idea TEXT NOT NULL,
                platform TEXT NOT NULL,
                platforms_json TEXT NOT NULL,
                slide_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                package_json TEXT NOT NULL,
                preflight_json TEXT NOT NULL,
                schedule_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_os_creatives_updated
                ON os_creatives(owner_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS os_generation_requests (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                horizon_days INTEGER NOT NULL,
                control_mode TEXT NOT NULL,
                guidance TEXT NOT NULL,
                controls_json TEXT NOT NULL,
                day_cards_json TEXT NOT NULL,
                production_window_days INTEGER NOT NULL,
                rolling_production INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_os_generation_requests_updated
                ON os_generation_requests(owner_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS os_sources (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                publisher TEXT,
                published_at TEXT,
                retrieved_at TEXT NOT NULL,
                credibility REAL NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                canonical_key TEXT NOT NULL UNIQUE,
                attributes_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_assertions (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                value_json TEXT NOT NULL,
                classification TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_quality REAL NOT NULL,
                freshness TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                source_id TEXT,
                valid_from TEXT NOT NULL,
                valid_until TEXT,
                observed_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                supersedes_id TEXT,
                FOREIGN KEY(entity_id) REFERENCES os_entities(id),
                FOREIGN KEY(source_id) REFERENCES os_sources(id)
            );
            CREATE INDEX IF NOT EXISTS idx_os_assertions_temporal
                ON os_assertions(entity_id, predicate, valid_from DESC);

            CREATE TABLE IF NOT EXISTS os_relationships (
                id TEXT PRIMARY KEY,
                source_entity_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                attributes_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                provenance_json TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_until TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_entity_id) REFERENCES os_entities(id),
                FOREIGN KEY(target_entity_id) REFERENCES os_entities(id)
            );

            CREATE TABLE IF NOT EXISTS os_goals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                priority INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                constraints_json TEXT NOT NULL,
                horizon TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                branch TEXT NOT NULL,
                parent_id TEXT,
                version INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                status TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_until TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_decisions (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                decision TEXT NOT NULL,
                rationale TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                alternatives_json TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                goals_affected_json TEXT NOT NULL,
                policies_applied_json TEXT NOT NULL,
                actions_json TEXT NOT NULL,
                owner_approval TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_research_missions (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                workstreams_json TEXT NOT NULL,
                source_requirements_json TEXT NOT NULL,
                freshness_requirement TEXT NOT NULL,
                depth TEXT NOT NULL,
                status TEXT NOT NULL,
                synthesis TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_research_findings (
                id TEXT PRIMARY KEY,
                mission_id TEXT,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                source_id TEXT,
                source_type TEXT NOT NULL,
                credibility REAL NOT NULL,
                corroboration_json TEXT NOT NULL,
                entities_json TEXT NOT NULL,
                topic TEXT NOT NULL,
                relevance TEXT NOT NULL,
                opportunity TEXT NOT NULL,
                risk TEXT NOT NULL,
                confidence REAL NOT NULL,
                freshness TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(mission_id) REFERENCES os_research_missions(id),
                FOREIGN KEY(source_id) REFERENCES os_sources(id)
            );

            CREATE TABLE IF NOT EXISTS os_opportunities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                why_infenergy TEXT NOT NULL,
                potential_value REAL NOT NULL,
                confidence REAL NOT NULL,
                time_sensitivity REAL NOT NULL,
                effort REAL NOT NULL,
                recommended_action TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_risks (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                likelihood REAL NOT NULL,
                impact REAL NOT NULL,
                confidence REAL NOT NULL,
                timeframe TEXT NOT NULL,
                mitigation TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_scenarios (
                id TEXT PRIMARY KEY,
                premise TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                baseline_json TEXT NOT NULL,
                changed_variables_json TEXT NOT NULL,
                projected_effects_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                limitations_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_experiments (
                id TEXT PRIMARY KEY,
                hypothesis TEXT NOT NULL,
                variants_json TEXT NOT NULL,
                controls_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                starts_at TEXT,
                ends_at TEXT,
                result_json TEXT NOT NULL,
                statistical_notes TEXT NOT NULL,
                conclusion TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_models (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                purpose TEXT NOT NULL,
                quality REAL,
                cost_class TEXT NOT NULL,
                latency_class TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                available INTEGER NOT NULL,
                benchmark_json TEXT NOT NULL,
                checked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_cost_records (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT,
                session_id TEXT,
                capability TEXT,
                job_id TEXT,
                units_json TEXT NOT NULL,
                cost_usd REAL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS os_lineage (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_os_lineage_source
                ON os_lineage(source_type, source_id);
            CREATE INDEX IF NOT EXISTS idx_os_lineage_target
                ON os_lineage(target_type, target_id);
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO os_schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now),
        )
        connection.commit()
    return database_path(data_dir)