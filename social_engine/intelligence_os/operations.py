from __future__ import annotations

import uuid
from typing import Any

from .db import connect, decode, encode, initialize, utc_now


class AuditLog:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def record(
        self,
        *,
        actor: str,
        model_or_tool: str,
        action: str,
        status: str,
        result: dict[str, Any] | None = None,
        input_reference: str | None = None,
        transaction_id: str | None = None,
        approval_id: str | None = None,
        cost_usd: float | None = None,
    ) -> str:
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_audit_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier, actor, model_or_tool, action, input_reference,
                    encode(result or {}), status, transaction_id, approval_id,
                    cost_usd, utc_now(),
                ),
            )
            connection.commit()
        return identifier

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT * FROM os_audit_log ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["result"] = decode(data.pop("result_json"), {})
            result.append(data)
        return result


class EventBus:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def emit(
        self,
        event_type: str,
        *,
        source: str,
        payload: dict[str, Any] | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        materiality: float = 0.0,
        occurred_at: str | None = None,
    ) -> str:
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    identifier, event_type, source, subject_type, subject_id,
                    encode(payload or {}), max(0.0, min(1.0, materiality)),
                    occurred_at or utc_now(), utc_now(),
                ),
            )
            connection.commit()
        return identifier

    def list(self, limit: int = 100, *, unprocessed_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE processed_at IS NULL" if unprocessed_only else ""
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                f"SELECT * FROM os_events {where} ORDER BY materiality DESC, occurred_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["payload"] = decode(data.pop("payload_json"), {})
            result.append(data)
        return result


class AttentionService:
    WEIGHTS = {
        "urgency": 0.18,
        "impact": 0.22,
        "confidence": 0.12,
        "time_sensitivity": 0.14,
        "reversibility": 0.06,
        "opportunity_value": 0.10,
        "risk_value": 0.12,
        "owner_relevance": 0.06,
    }

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def create(self, *, title: str, summary: str, event_id: str | None = None, **signals: float) -> dict[str, Any]:
        values = {name: max(0.0, min(1.0, float(signals.get(name, 0.0)))) for name in self.WEIGHTS}
        score = sum(values[name] * weight for name, weight in self.WEIGHTS.items())
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                """
                INSERT INTO os_attention_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, NULL)
                """,
                (
                    identifier, event_id, title, summary,
                    values["urgency"], values["impact"], values["confidence"],
                    values["time_sensitivity"], values["reversibility"],
                    values["opportunity_value"], values["risk_value"],
                    values["owner_relevance"], score, utc_now(),
                ),
            )
            connection.commit()
        return {"id": identifier, "title": title, "summary": summary, "score": round(score, 4), **values}

    def list_open(self, limit: int = 20) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT * FROM os_attention_items WHERE status='OPEN' ORDER BY score DESC, created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_matching(self, summary_prefix: str) -> int:
        with connect(self.data_dir) as connection:
            changed = connection.execute(
                "UPDATE os_attention_items SET status='RESOLVED', resolved_at=? WHERE status='OPEN' AND summary LIKE ?",
                (utc_now(), f"{summary_prefix}%"),
            ).rowcount
            connection.commit()
        return changed


class JobService:
    VALID_STATUSES = {"PLANNING", "RUNNING", "WAITING_APPROVAL", "PAUSED", "FAILED", "COMPLETED", "CANCELED"}

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def create(self, *, job_type: str, objective: str, plan: list[str], operation_id: str | None = None) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_jobs VALUES (?, ?, ?, ?, 0, 'PLANNING', 0, '{}', '[]', 0, '[]', ?, ?, ?)",
                (identifier, job_type, objective, encode(plan), operation_id, now, now),
            )
            for ordinal, name in enumerate(plan):
                connection.execute(
                    "INSERT INTO os_job_steps VALUES (?, ?, ?, ?, 'NOT_STARTED', '{}', '{}', NULL, NULL, NULL)",
                    (uuid.uuid4().hex, identifier, ordinal, name),
                )
            connection.commit()
        return self.get(identifier)

    def get(self, job_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_jobs WHERE id=?", (job_id,)).fetchone()
            steps = connection.execute(
                "SELECT * FROM os_job_steps WHERE job_id=? ORDER BY ordinal", (job_id,)
            ).fetchall()
        if not row:
            raise KeyError(f"job_not_found:{job_id}")
        result = dict(row)
        for key in ("plan_json", "result_json", "errors_json", "steering_json"):
            result[key[:-5]] = decode(result.pop(key), [] if key != "result_json" else {})
        result["steps"] = [dict(step) for step in steps]
        for step in result["steps"]:
            step["checkpoint"] = decode(step.pop("checkpoint_json"), {})
            step["result"] = decode(step.pop("result_json"), {})
        return result

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            ids = [row["id"] for row in connection.execute(
                "SELECT id FROM os_jobs ORDER BY updated_at DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()]
        return [self.get(identifier) for identifier in ids]

    def transition(self, job_id: str, status: str, *, progress: float | None = None, result: dict[str, Any] | None = None) -> dict[str, Any]:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"invalid_job_status:{status}")
        fields = ["status=?", "updated_at=?"]
        values: list[Any] = [status, utc_now()]
        if progress is not None:
            fields.append("progress=?")
            values.append(max(0.0, min(1.0, progress)))
        if result is not None:
            fields.append("result_json=?")
            values.append(encode(result))
        values.append(job_id)
        with connect(self.data_dir) as connection:
            changed = connection.execute(
                f"UPDATE os_jobs SET {', '.join(fields)} WHERE id=?", values
            ).rowcount
            connection.commit()
        if not changed:
            raise KeyError(f"job_not_found:{job_id}")
        return self.get(job_id)

    def checkpoint(self, job_id: str, ordinal: int, *, status: str, checkpoint: dict[str, Any], result: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with connect(self.data_dir) as connection:
            changed = connection.execute(
                """
                UPDATE os_job_steps SET status=?, checkpoint_json=?, result_json=?, error=?,
                    started_at=COALESCE(started_at, ?), finished_at=CASE WHEN ? IN ('COMPLETED','FAILED','SKIPPED') THEN ? ELSE finished_at END
                WHERE job_id=? AND ordinal=?
                """,
                (status, encode(checkpoint), encode(result or {}), error, now, status, now, job_id, ordinal),
            ).rowcount
            total = connection.execute("SELECT COUNT(*) c FROM os_job_steps WHERE job_id=?", (job_id,)).fetchone()["c"]
            completed = connection.execute(
                "SELECT COUNT(*) c FROM os_job_steps WHERE job_id=? AND status IN ('COMPLETED','SKIPPED')", (job_id,)
            ).fetchone()["c"]
            if changed:
                connection.execute(
                    "UPDATE os_jobs SET current_step=?, progress=?, updated_at=? WHERE id=?",
                    (ordinal, completed / max(1, total), now, job_id),
                )
            connection.commit()
        if not changed:
            raise KeyError(f"job_step_not_found:{job_id}:{ordinal}")
        return self.get(job_id)

    def steer(self, job_id: str, instruction: str, actor: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT steering_json FROM os_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(f"job_not_found:{job_id}")
            steering = decode(row["steering_json"], [])
            steering.append({"instruction": instruction, "actor": actor, "created_at": utc_now()})
            connection.execute(
                "UPDATE os_jobs SET steering_json=?, updated_at=? WHERE id=?",
                (encode(steering), utc_now(), job_id),
            )
            connection.commit()
        return self.get(job_id)