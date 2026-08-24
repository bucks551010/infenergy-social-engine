from __future__ import annotations

import email.utils
import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests

from .db import connect, decode, encode, initialize, utc_now
from .knowledge import WorldModel


SOURCE_CREDIBILITY = {
    "government": 0.95,
    "academic": 0.92,
    "standards_body": 0.92,
    "official_company": 0.86,
    "major_publication": 0.80,
    "trade_publication": 0.72,
    "industry_report": 0.68,
    "community_discussion": 0.45,
    "review": 0.42,
    "affiliate": 0.25,
    "unknown": 0.30,
}


def classify_source(url: str, publisher: str = "") -> tuple[str, float]:
    host = (urlparse(url).hostname or "").lower()
    name = publisher.lower()
    if host.endswith(".gov") or ".gov." in host:
        source_type = "government"
    elif host.endswith(".edu") or any(term in name for term in ("university", "journal", "institute of technology")):
        source_type = "academic"
    elif any(term in host for term in ("ieee.org", "iso.org", "ul.com", "iec.ch")):
        source_type = "standards_body"
    elif any(term in host for term in ("reuters.com", "apnews.com", "bloomberg.com", "bbc.", "ft.com")):
        source_type = "major_publication"
    elif any(term in host for term in ("ecoflow.com", "jackery.com", "bluettipower.com", "infenergypower.com")):
        source_type = "official_company"
    elif any(term in host for term in ("reddit.com", "facebook.com", "youtube.com", "forum")):
        source_type = "community_discussion"
    elif any(term in host for term in ("amazon.com", "trustpilot.com")):
        source_type = "review"
    else:
        source_type = "unknown"
    return source_type, SOURCE_CREDIBILITY[source_type]


class ResearchIntelligence:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.world = WorldModel(data_dir)
        initialize(data_dir)

    def search_news(self, query: str, *, limit: int = 10, freshness_days: int = 2) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("research_query_required")
        endpoint = f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss"
        retrieved_at = utc_now()
        response = requests.get(
            endpoint,
            headers={"User-Agent": "InfenergyIntelligenceOS/1.0 (+https://www.infenergypower.com)"},
            timeout=20,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, freshness_days))
        findings: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            description = _strip_html(item.findtext("description") or "")
            publisher = (item.findtext("source") or "").strip()
            published_raw = (item.findtext("pubDate") or "").strip()
            published_at = _parse_date(published_raw)
            if published_at and published_at < cutoff:
                continue
            source_type, credibility = classify_source(url, publisher)
            source = self.world.add_source(
                source_type, title or query, url=url, publisher=publisher,
                published_at=published_at.isoformat() if published_at else None,
                credibility=credibility,
                metadata={"retrieval_provider": "bing_news_rss", "query": query},
            )
            finding = self._store_finding(
                title=title, summary=description, source_id=source["id"],
                source_type=source_type, credibility=credibility, topic=query,
                relevance="Requires master intelligence evaluation against Infenergy goals and current strategy.",
                confidence=credibility, freshness=f"retrieved:{retrieved_at}",
                expires_at=(datetime.now(timezone.utc) + timedelta(days=max(1, freshness_days))).isoformat(),
            )
            findings.append(finding)
            if len(findings) >= max(1, min(limit, 50)):
                break
        return {
            "query": query,
            "retrieved_at": retrieved_at,
            "provider": "bing_news_rss",
            "count": len(findings),
            "findings": findings,
            "limitations": [
                "Search-provider inclusion is not independent corroboration.",
                "Relevance and strategic implications require evaluation against internal Infenergy evidence.",
            ],
        }

    def list_findings(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT * FROM os_research_findings ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for key in ("corroboration_json", "entities_json"):
                item[key[:-5]] = decode(item.pop(key), [])
            result.append(item)
        return result

    def _store_finding(self, *, title: str, summary: str, source_id: str, source_type: str, credibility: float, topic: str, relevance: str, confidence: float, freshness: str, expires_at: str | None) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                """
                INSERT INTO os_research_findings VALUES (?, NULL, ?, ?, ?, ?, ?, '[]', '[]', ?, ?, '', '', ?, ?, ?, ?)
                """,
                (identifier, title, summary, source_id, source_type, credibility, topic, relevance, confidence, freshness, expires_at, now),
            )
            connection.commit()
        return {
            "id": identifier, "title": title, "summary": summary,
            "source_id": source_id, "source_type": source_type,
            "credibility": credibility, "topic": topic, "relevance_to_infenergy": relevance,
            "confidence": confidence, "freshness": freshness, "expires_at": expires_at,
        }


class AutomationService:
    VALID_STATES = {"ACTIVE", "PAUSED", "DISABLED"}

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        initialize(data_dir)

    def create(
        self,
        *,
        name: str,
        trigger: dict[str, Any],
        steps: list[dict[str, Any]],
        created_by: str,
        conditions: list[dict[str, Any]] | None = None,
        permissions: dict[str, Any] | None = None,
        approval_rules: dict[str, Any] | None = None,
        schedule: dict[str, Any] | None = None,
        failure_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not steps or any(not str(step.get("capability", "")).strip() for step in steps):
            raise ValueError("automation_steps_require_capability_ids")
        identifier = uuid.uuid4().hex
        now = utc_now()
        next_run = _next_run(schedule or trigger)
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_automations VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', NULL, ?, ?, ?, ?, ?)",
                (
                    identifier, name, encode(trigger), encode(conditions or []), encode(steps),
                    encode(permissions or {}), encode(approval_rules or {}), encode(schedule or {}),
                    next_run, encode(failure_policy or {"max_retries": 2, "on_exhausted": "notify_owner"}),
                    created_by, now, now,
                ),
            )
            connection.commit()
        return self.get(identifier)

    def get(self, automation_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_automations WHERE id=?", (automation_id,)).fetchone()
        if not row:
            raise KeyError(f"automation_not_found:{automation_id}")
        item = dict(row)
        for key in ("trigger_json", "conditions_json", "steps_json", "permissions_json", "approval_rules_json", "schedule_json", "failure_policy_json"):
            item[key[:-5]] = decode(item.pop(key), {} if key not in ("conditions_json", "steps_json") else [])
        return item

    def list(self) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            ids = [row["id"] for row in connection.execute("SELECT id FROM os_automations ORDER BY updated_at DESC").fetchall()]
        return [self.get(identifier) for identifier in ids]

    def set_status(self, automation_id: str, status: str) -> dict[str, Any]:
        if status not in self.VALID_STATES:
            raise ValueError(f"invalid_automation_status:{status}")
        with connect(self.data_dir) as connection:
            changed = connection.execute(
                "UPDATE os_automations SET status=?, updated_at=? WHERE id=?",
                (status, utc_now(), automation_id),
            ).rowcount
            connection.commit()
        if not changed:
            raise KeyError(f"automation_not_found:{automation_id}")
        return self.get(automation_id)

    def create_watch(self, *, subject: str, scope: dict[str, Any], frequency: str, source_policy: dict[str, Any], materiality_threshold: float, condition: dict[str, Any], actions: list[dict[str, Any]], expires_at: str | None = None) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_watches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)",
                (identifier, subject, encode(scope), frequency, encode(source_policy), materiality_threshold, encode(condition), encode(actions), expires_at, now, now),
            )
            connection.commit()
        return {"id": identifier, "subject": subject, "frequency": frequency, "materiality_threshold": materiality_threshold, "status": "ACTIVE"}

    def list_watches(self) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute("SELECT * FROM os_watches ORDER BY updated_at DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for key in ("scope_json", "source_policy_json", "condition_json", "actions_json"):
                item[key[:-5]] = decode(item.pop(key), {})
            result.append(item)
        return result

    def due(self, now: str | None = None) -> list[dict[str, Any]]:
        now = now or utc_now()
        with connect(self.data_dir) as connection:
            ids = [
                row["id"] for row in connection.execute(
                    "SELECT id FROM os_automations WHERE status='ACTIVE' AND next_run IS NOT NULL AND next_run<=? ORDER BY next_run",
                    (now,),
                ).fetchall()
            ]
        return [self.get(identifier) for identifier in ids]

    def run_due(self, service: Any, *, max_runs: int = 10) -> list[dict[str, Any]]:
        completed: list[dict[str, Any]] = []
        for automation in self.due()[:max_runs]:
            run_id = uuid.uuid4().hex
            started_at = utc_now()
            status = "SUCCEEDED"
            outputs: list[dict[str, Any]] = []
            error = None
            with connect(self.data_dir) as connection:
                connection.execute(
                    "INSERT INTO os_automation_runs VALUES (?, ?, 'RUNNING', ?, NULL, ?, '[]', NULL)",
                    (run_id, automation["id"], started_at, encode(automation["trigger"])),
                )
                connection.commit()
            try:
                for index, step in enumerate(automation["steps"]):
                    capability_id = str(step["capability"])
                    result = service.execute_capability(
                        capability_id,
                        dict(step.get("arguments", {})),
                        actor=f"automation:{automation['id']}",
                        operation_id=f"automation:{automation['id']}:{run_id}:{index}",
                    )
                    outputs.append({"step": index, "capability": capability_id, "result": result})
                    if result.get("status") in {"WAITING_APPROVAL", "FAILED"}:
                        status = result["status"]
                        break
            except Exception as exc:
                status = "FAILED"
                error = f"{type(exc).__name__}: {exc}"
            finished_at = utc_now()
            next_run = _next_run(automation.get("schedule") or automation.get("trigger") or {})
            with connect(self.data_dir) as connection:
                connection.execute(
                    "UPDATE os_automation_runs SET status=?, finished_at=?, output_json=?, error=? WHERE id=?",
                    (status, finished_at, encode(outputs), error, run_id),
                )
                connection.execute(
                    "UPDATE os_automations SET last_run=?, next_run=?, updated_at=? WHERE id=?",
                    (finished_at, next_run, finished_at, automation["id"]),
                )
                connection.commit()
            completed.append({"run_id": run_id, "automation_id": automation["id"], "status": status, "outputs": outputs, "error": error})
        return completed

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT * FROM os_automation_runs ORDER BY started_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["trigger_payload"] = decode(item.pop("trigger_payload_json"), {})
            item["output"] = decode(item.pop("output_json"), [])
            result.append(item)
        return result


def _parse_date(value: str) -> datetime | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _next_run(schedule: dict[str, Any]) -> str | None:
    every_minutes = schedule.get("every_minutes")
    if every_minutes:
        return (datetime.now(timezone.utc) + timedelta(minutes=max(1, int(every_minutes)))).isoformat()
    return schedule.get("next_run")