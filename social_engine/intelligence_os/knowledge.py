from __future__ import annotations

import uuid
from typing import Any

from .db import connect, decode, encode, initialize, utc_now


FACT_CLASSES = {
    "OBSERVED_FACT", "DERIVED_METRIC", "INFERENCE", "FORECAST",
    "HYPOTHESIS", "RECOMMENDATION", "OWNER_DECISION",
}


class WorldModel:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def upsert_entity(self, entity_type: str, name: str, *, canonical_key: str | None = None, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
        key = canonical_key or f"{entity_type}:{name}".lower().replace(" ", "-")
        now = utc_now()
        with connect(self.data_dir) as connection:
            existing = connection.execute("SELECT id FROM os_entities WHERE canonical_key=?", (key,)).fetchone()
            identifier = existing["id"] if existing else uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO os_entities VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_key) DO UPDATE SET
                    type=excluded.type, name=excluded.name, attributes_json=excluded.attributes_json,
                    updated_at=excluded.updated_at
                """,
                (identifier, entity_type, name, key, encode(attributes or {}), now, now),
            )
            connection.commit()
        return self.get_entity(identifier)

    def get_entity(self, entity_id: str, *, as_of: str | None = None) -> dict[str, Any]:
        as_of = as_of or utc_now()
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_entities WHERE id=?", (entity_id,)).fetchone()
            assertions = connection.execute(
                """
                SELECT * FROM os_assertions WHERE entity_id=? AND valid_from<=?
                  AND (valid_until IS NULL OR valid_until>?)
                ORDER BY predicate, valid_from DESC
                """,
                (entity_id, as_of, as_of),
            ).fetchall()
        if not row:
            raise KeyError(f"entity_not_found:{entity_id}")
        entity = dict(row)
        entity["attributes"] = decode(entity.pop("attributes_json"), {})
        entity["assertions"] = [self._assertion_dict(item) for item in assertions]
        return entity

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        term = f"%{query.strip()}%"
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT id FROM os_entities WHERE name LIKE ? OR canonical_key LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (term, term, max(1, min(limit, 200))),
            ).fetchall()
        return [self.get_entity(row["id"]) for row in rows]

    def assert_fact(
        self,
        entity_id: str,
        predicate: str,
        value: Any,
        *,
        classification: str,
        source_id: str | None = None,
        confidence: float = 1.0,
        evidence_quality: float = 1.0,
        freshness: str = "current",
        assumptions: list[str] | None = None,
        valid_from: str | None = None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        if classification not in FACT_CLASSES:
            raise ValueError(f"invalid_fact_classification:{classification}")
        identifier = uuid.uuid4().hex
        now = utc_now()
        valid_from = valid_from or now
        with connect(self.data_dir) as connection:
            current = connection.execute(
                """
                SELECT id FROM os_assertions
                WHERE entity_id=? AND predicate=? AND valid_until IS NULL
                ORDER BY valid_from DESC LIMIT 1
                """,
                (entity_id, predicate),
            ).fetchone()
            if current:
                connection.execute(
                    "UPDATE os_assertions SET valid_until=? WHERE id=?",
                    (valid_from, current["id"]),
                )
            connection.execute(
                """
                INSERT INTO os_assertions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    identifier, entity_id, predicate, encode(value), classification,
                    max(0.0, min(1.0, confidence)), max(0.0, min(1.0, evidence_quality)),
                    freshness, encode(assumptions or []), source_id, valid_from,
                    observed_at or now, now, current["id"] if current else None,
                ),
            )
            connection.commit()
        return self.get_assertion(identifier)

    def add_source(self, source_type: str, title: str, *, url: str | None = None, publisher: str | None = None, published_at: str | None = None, credibility: float = 0.5, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, source_type, title, url, publisher, published_at, utc_now(), max(0.0, min(1.0, credibility)), encode(metadata or {})),
            )
            connection.commit()
        return {"id": identifier, "type": source_type, "title": title, "url": url, "credibility": credibility}

    def relate(self, source_entity_id: str, relationship: str, target_entity_id: str, *, attributes: dict[str, Any] | None = None, confidence: float = 1.0, provenance: list[str] | None = None, valid_from: str | None = None) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_relationships VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                (identifier, source_entity_id, relationship, target_entity_id, encode(attributes or {}), confidence, encode(provenance or []), valid_from or utc_now(), utc_now()),
            )
            connection.commit()
        return {"id": identifier, "source_entity_id": source_entity_id, "relationship": relationship, "target_entity_id": target_entity_id}

    def get_assertion(self, assertion_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_assertions WHERE id=?", (assertion_id,)).fetchone()
        if not row:
            raise KeyError(f"assertion_not_found:{assertion_id}")
        return self._assertion_dict(row)

    @staticmethod
    def _assertion_dict(row: Any) -> dict[str, Any]:
        data = dict(row)
        data["value"] = decode(data.pop("value_json"), None)
        data["assumptions"] = decode(data.pop("assumptions_json"), [])
        return data


class StrategyService:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def create_goal(self, name: str, description: str, *, priority: int = 50, metrics: list[dict[str, Any]] | None = None, constraints: list[str] | None = None, horizon: str = "ongoing", status: str = "ACTIVE") -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (identifier, name, description, priority, encode(metrics or []), encode(constraints or []), horizon, status, now, now),
            )
            connection.commit()
        return self.get_goal(identifier)

    def get_goal(self, goal_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            raise KeyError(f"goal_not_found:{goal_id}")
        data = dict(row)
        data["metrics"] = decode(data.pop("metrics_json"), [])
        data["constraints"] = decode(data.pop("constraints_json"), [])
        return data

    def list_goals(self, active_only: bool = True) -> list[dict[str, Any]]:
        where = "WHERE status='ACTIVE'" if active_only else ""
        with connect(self.data_dir) as connection:
            ids = [row["id"] for row in connection.execute(f"SELECT id FROM os_goals {where} ORDER BY priority DESC").fetchall()]
        return [self.get_goal(identifier) for identifier in ids]

    def create_strategy(self, name: str, state: dict[str, Any], *, branch: str = "active", parent_id: str | None = None, status: str = "DRAFT") -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT MAX(version) version FROM os_strategies WHERE name=?", (name,)).fetchone()
            version = int(row["version"] or 0) + 1
            connection.execute(
                "INSERT INTO os_strategies VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                (identifier, name, branch, parent_id, version, encode(state), status, now, now, now),
            )
            connection.commit()
        return self.get_strategy(identifier)

    def get_strategy(self, strategy_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_strategies WHERE id=?", (strategy_id,)).fetchone()
        if not row:
            raise KeyError(f"strategy_not_found:{strategy_id}")
        data = dict(row)
        data["state"] = decode(data.pop("state_json"), {})
        return data

    def record_decision(self, *, question: str, decision: str, rationale: str, evidence: list[Any] | None = None, alternatives: list[Any] | None = None, assumptions: list[str] | None = None, confidence: float = 0.5, goals_affected: list[str] | None = None, policies_applied: list[str] | None = None, actions: list[Any] | None = None, owner_approval: str | None = None) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, question, decision, rationale, encode(evidence or []), encode(alternatives or []), encode(assumptions or []), confidence, encode(goals_affected or []), encode(policies_applied or []), encode(actions or []), owner_approval, utc_now()),
            )
            connection.commit()
        return {"id": identifier, "question": question, "decision": decision, "rationale": rationale, "confidence": confidence}

    def create_scenario(self, premise: str, *, assumptions: list[str], baseline: dict[str, Any], changed_variables: list[dict[str, Any]], projected_effects: list[dict[str, Any]], confidence: float, evidence: list[Any], limitations: list[str]) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_scenarios VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, premise, encode(assumptions), encode(baseline), encode(changed_variables), encode(projected_effects), confidence, encode(evidence), encode(limitations), utc_now()),
            )
            connection.commit()
        return {"id": identifier, "premise": premise, "confidence": confidence, "production_mutated": False}


class ResearchService:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def create_mission(self, question: str, *, scope: dict[str, Any], workstreams: list[str], source_requirements: list[str], freshness_requirement: str, depth: str) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_research_missions VALUES (?, ?, ?, ?, ?, ?, ?, 'PLANNING', '', ?, ?)",
                (identifier, question, encode(scope), encode(workstreams), encode(source_requirements), freshness_requirement, depth, now, now),
            )
            connection.commit()
        return {"id": identifier, "question": question, "status": "PLANNING", "workstreams": workstreams}


def add_lineage(data_dir: str, source_type: str, source_id: str, relationship: str, target_type: str, target_id: str, metadata: dict[str, Any] | None = None) -> str:
    identifier = uuid.uuid4().hex
    with connect(data_dir) as connection:
        connection.execute(
            "INSERT INTO os_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (identifier, source_type, source_id, relationship, target_type, target_id, encode(metadata or {}), utc_now()),
        )
        connection.commit()
    return identifier