from __future__ import annotations

import threading
from typing import Any

from .capabilities import register_core_capabilities
from .db import connect, initialize, utc_now
from .governance import PolicyEngine
from .intelligence import AutomationService
from .operations import EventBus
from .registry import CapabilityRegistry
from .service import IntelligenceOS


_LOCK = threading.Lock()
_INSTANCES: dict[str, IntelligenceOS] = {}


def bootstrap(data_dir: str) -> IntelligenceOS:
    with _LOCK:
        if data_dir in _INSTANCES:
            return _INSTANCES[data_dir]
        initialize(data_dir)
        from content_operations import init_content_operations
        init_content_operations(data_dir)
        policies = PolicyEngine(data_dir)
        registry = CapabilityRegistry(data_dir)
        register_core_capabilities(registry, policies)
        _seed_policies(policies)
        service = IntelligenceOS(data_dir, registry, policies)
        EventBus(data_dir).emit(
            "INTELLIGENCE_OS_BOOTSTRAPPED", source="foundation",
            payload={"capabilities": len(registry.list())}, materiality=0.2,
        )
        _INSTANCES[data_dir] = service
        return service


def heartbeat(data_dir: str) -> dict[str, Any]:
    service = bootstrap(data_dir)
    automation_runs = AutomationService(data_dir).run_due(service)
    attention_created = 0
    threshold = 0.7
    for event in service.events.list(100, unprocessed_only=True):
        if float(event.get("materiality", 0)) >= threshold:
            service.attention.create(
                event_id=event["id"],
                title=str(event["type"]).replace("_", " ").title(),
                summary=str(event.get("payload", {}).get("summary") or event.get("payload", {}).get("error") or "Material Infenergy event requires review."),
                urgency=float(event.get("materiality", 0)),
                impact=float(event.get("materiality", 0)),
                confidence=float(event.get("payload", {}).get("confidence", 0.7)),
                time_sensitivity=float(event.get("materiality", 0)),
                reversibility=0.5,
                opportunity_value=float(event.get("payload", {}).get("opportunity_value", 0)),
                risk_value=float(event.get("payload", {}).get("risk_value", event.get("materiality", 0))),
                owner_relevance=1.0,
            )
            attention_created += 1
        with connect(data_dir) as connection:
            connection.execute("UPDATE os_events SET processed_at=? WHERE id=?", (utc_now(), event["id"]))
            connection.commit()
    event_id = service.events.emit(
        "INTELLIGENCE_OS_HEARTBEAT", source="foundation",
        payload={"jobs": len(service.jobs.list(200)), "capabilities": len(service.registry.list())},
        materiality=0.05,
    )
    return {
        "status": "ok", "event_id": event_id,
        "automation_runs": automation_runs,
        "attention_created": attention_created, "time_utc": utc_now(),
    }


def _seed_policies(policies: PolicyEngine) -> None:
    existing = policies.list_policies(active_only=False)
    existing_capabilities = {item["capability"] for item in existing if item["status"] == "ACTIVE"}
    defaults = [
        ("policies.create", "Authenticated owner may define explicit scoped operating policies."),
        ("scenario.create", "Non-mutating scenarios may be created autonomously because they cannot change production state."),
        ("jobs.complete", "The operating agent may persist actual deliverables and close a job that the owner already approved."),
        ("creative.command.produce", "Flagship creative generation and repair may run autonomously; scheduling and publication remain separately governed."),
        ("creative.carousel.generate", "Draft carousel generation and rendering may run autonomously; scheduling and publication remain separately governed."),
    ]
    for capability, rule in defaults:
        if capability in existing_capabilities:
            continue
        policies.create_policy(
            capability=capability, rule=rule, approval_level="AUTONOMOUS",
            created_by="system_bootstrap",
        )