from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from social_engine.intelligence_os.foundation import bootstrap
from social_engine.intelligence_os.foundation import heartbeat
from social_engine.intelligence_os.intelligence import AutomationService, ResearchIntelligence, classify_source
from social_engine.intelligence_os.knowledge import WorldModel
from social_engine.intelligence_os.models import MasterModelUnavailable, ModelStatus
from social_engine.intelligence_os.operations import JobService
from social_engine.intelligence_os.web import handle


def test_bootstrap_registers_foundation_and_preserves_default_deny(tmp_path):
    service = bootstrap(str(tmp_path))

    capabilities = {item["id"] for item in service.registry.list()}

    assert "system.health" in capabilities
    assert "social.schedule" in capabilities
    assert "content.plan_120_days" in capabilities
    blocked = service.execute_capability(
        "goals.create",
        {"name": "Grow qualified audience", "description": "Increase relevant reach."},
    )
    assert blocked["status"] == "WAITING_APPROVAL"
    assert blocked["approval_id"]


def test_approved_schedule_is_transactional_and_rollbackable(tmp_path):
    service = bootstrap(str(tmp_path))
    arguments = {
        "content_date": "2026-08-25",
        "slot": "morning",
        "scheduled_at": "2026-08-25T13:00:00+00:00",
        "package": {
            "post_id": "approved-post-1",
            "fb_caption": "A useful approved post.",
            "ig_caption": "A useful approved post.",
            "li_text": "A useful approved post.",
            "platform_posts": {},
        },
    }
    pending = service.execute_capability("social.schedule", arguments, operation_id="schedule-request")
    service.policies.create_policy(
        capability="social.schedule",
        rule="Approved social packages may be scheduled.",
        approval_level="EXECUTE_WITH_APPROVAL",
        created_by="owner",
    )
    approval_id = service.policies.request_approval("social.schedule", "owner", arguments)
    service.policies.decide_approval(approval_id, approved=True, decided_by="owner")

    result = service.execute_capability(
        "social.schedule",
        arguments,
        operation_id="schedule-approved",
        approval_id=approval_id,
    )

    assert pending["status"] == "WAITING_APPROVAL"
    assert result["status"] == "COMPLETED"
    assert result["rollback_available"] is True
    rolled_back = service.transactions.rollback(result["transaction_id"])
    assert rolled_back["status"] == "ROLLED_BACK"


def test_schedule_dry_run_does_not_write_social_slot(tmp_path):
    service = bootstrap(str(tmp_path))
    service.policies.create_policy(
        capability="social.schedule",
        rule="Testing only.",
        approval_level="AUTONOMOUS",
        created_by="owner",
    )
    result = service.execute_capability(
        "social.schedule",
        {
            "content_date": "2026-08-26",
            "slot": "midday",
            "scheduled_at": "2026-08-26T17:00:00+00:00",
            "package": {"post_id": "dry-run-post"},
        },
        dry_run=True,
    )

    calendar = service.execute_capability(
        "social.calendar.get", {"start_date": "2026-08-26", "days": 1}
    )
    assert result["status"] == "DRY_RUN_COMPLETE"
    assert calendar["result"]["days"][0]["slots"] == []


def test_idempotent_replay_preserves_transaction_response_contract(tmp_path):
    service = bootstrap(str(tmp_path))
    arguments = {"premise": "A validation scenario"}

    first = service.execute_capability(
        "scenario.create", arguments, dry_run=True, operation_id="same-operation"
    )
    replay = service.execute_capability(
        "scenario.create", arguments, dry_run=True, operation_id="same-operation"
    )

    assert replay["idempotent_replay"] is True
    assert replay["transaction_id"] == first["transaction_id"]
    assert replay["status"] == first["status"]
    assert replay["result"] == first["result"]
    assert replay["rollback_available"] == first["rollback_available"]


def test_world_model_preserves_temporal_assertion_history(tmp_path):
    world = WorldModel(str(tmp_path))
    competitor = world.upsert_entity("CompetitorProduct", "Example 1000")
    first = world.assert_fact(
        competitor["id"], "price_usd", 999,
        classification="OBSERVED_FACT", valid_from="2026-03-01T00:00:00+00:00"
    )
    second = world.assert_fact(
        competitor["id"], "price_usd", 799,
        classification="OBSERVED_FACT", valid_from="2026-08-23T00:00:00+00:00"
    )

    march = world.get_entity(competitor["id"], as_of="2026-03-20T00:00:00+00:00")
    august = world.get_entity(competitor["id"], as_of="2026-08-24T00:00:00+00:00")

    assert march["assertions"][0]["value"] == 999
    assert august["assertions"][0]["value"] == 799
    assert second["supersedes_id"] == first["id"]


def test_job_checkpoints_and_steering_survive_reload(tmp_path):
    jobs = JobService(str(tmp_path))
    job = jobs.create(job_type="RESEARCH", objective="Research portable power", plan=["plan", "research", "synthesize"])
    jobs.transition(job["id"], "RUNNING")
    jobs.checkpoint(job["id"], 0, status="COMPLETED", checkpoint={"sources": 3})
    jobs.steer(job["id"], "Prioritize primary sources", "owner")

    restored = JobService(str(tmp_path)).get(job["id"])

    assert restored["status"] == "RUNNING"
    assert restored["steps"][0]["checkpoint"] == {"sources": 3}
    assert restored["steering"][0]["instruction"] == "Prioritize primary sources"


def test_master_conversation_fails_closed_without_configured_model(tmp_path, monkeypatch):
    service = bootstrap(str(tmp_path))
    unavailable = ModelStatus(
        provider="github-copilot-sdk",
        configured_model="gpt-5.6-sol",
        authenticated=True,
        available=False,
        available_models=[{"id": "gpt-5.4", "name": "GPT-5.4"}],
        reason="configured_master_model_not_in_authenticated_model_list",
        checked_at=datetime.now(timezone.utc).isoformat(),
    )

    async def blocked(*args, **kwargs):
        raise MasterModelUnavailable(unavailable)

    monkeypatch.setattr(service.master, "converse", blocked)
    result = service.command("What matters today?")

    assert result["status"] == "BLOCKED"
    assert result["model_status"]["available_models"] == [{"id": "gpt-5.4", "name": "GPT-5.4"}]
    assert "No strategic-model downgrade" in result["message"]


def test_master_continues_durable_conversation_context(tmp_path, monkeypatch):
    service = bootstrap(str(tmp_path))
    prompts = []

    async def converse(prompt, **kwargs):
        prompts.append({"prompt": prompt, "system_message": kwargs["system_message"]})
        return {
            "content": "Completed the next useful step.",
            "model": "gpt-5.6-sol",
            "provider": "github-copilot-sdk",
            "session_id": kwargs["session_id"],
        }

    monkeypatch.setattr(service.master, "converse", converse)
    first = service.command("My audience is campers and off-grid travelers.")
    second = service.command(
        "Build a week of content for them.", conversation_id=first["conversation_id"]
    )

    assert second["status"] == "COMPLETED"
    assert "My audience is campers and off-grid travelers." in prompts[1]["prompt"]
    assert "Build a week of content for them." in prompts[1]["prompt"]
    assert "CURRENT OPERATING STATE" in prompts[1]["prompt"]
    assert "outcome-driven master intelligence" in prompts[1]["system_message"]
    assert "do not restart discovery" in prompts[1]["prompt"]


def test_command_center_and_api_are_served(tmp_path):
    status, content_type, page = handle("GET", "/os", None, str(tmp_path))
    api_status, api_type, payload = handle("GET", "/api/os/capabilities", None, str(tmp_path))
    create_status, create_type, created_payload = handle(
        "POST", "/api/os/conversations", {"title": "Fresh objective"}, str(tmp_path)
    )
    js_status, js_type, javascript = handle("GET", "/os/assets/app.js", None, str(tmp_path))
    css_status, css_type, stylesheet = handle("GET", "/os/assets/styles.css", None, str(tmp_path))

    assert status == 200
    assert content_type.startswith("text/html")
    assert b"Infenergy Intelligence OS" in page
    assert b'id="mobile-nav"' in page
    assert b'app.js?v=4' in page
    assert api_status == 200
    assert api_type.startswith("application/json")
    assert b"system.health" in payload
    assert create_status == 201
    assert create_type.startswith("application/json")
    assert json.loads(created_payload)["conversation"]["title"] == "Fresh objective"
    assert js_status == 200
    assert js_type.startswith("text/javascript")
    assert b"function renderResearch" in javascript
    assert b"function renderSocial" in javascript
    assert b"function renderHealth" in javascript
    assert b"function activateView" in javascript
    assert b"function richText" in javascript
    assert b"/api/os/conversations" in javascript
    assert b"JSON.stringify(item" not in javascript
    assert css_status == 200
    assert css_type.startswith("text/css")
    assert b".provider-grid" in stylesheet
    assert b".slot-grid" in stylesheet
    assert b".mobile-view-picker" in stylesheet
    assert b"overflow-x: hidden" in stylesheet
    assert b"grid-template-columns: minmax(0, 1fr)" in stylesheet


def test_120_day_plan_is_a_durable_approval_gated_job(tmp_path):
    service = bootstrap(str(tmp_path))
    arguments = {
        "objective": "Entertainment first; product when it fits; keep the future adaptive.",
        "locked_days": 7,
    }
    dry_run = service.execute_capability("content.plan_120_days", arguments, dry_run=True)
    pending = service.execute_capability("content.plan_120_days", arguments)

    assert dry_run["status"] == "DRY_RUN_COMPLETE"
    assert dry_run["required_approval"]["required"] is True
    assert pending["status"] == "WAITING_APPROVAL"


def test_source_quality_and_news_findings_retain_provenance(tmp_path, monkeypatch):
    rss = b"""<?xml version='1.0'?><rss><channel><item><title>Battery safety update</title><link>https://www.energy.gov/example</link><description>New official guidance.</description><source>Department of Energy</source><pubDate>Sun, 23 Aug 2026 12:00:00 GMT</pubDate></item></channel></rss>"""

    class Response:
        content = rss

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr("social_engine.intelligence_os.intelligence.requests.get", lambda *args, **kwargs: Response())
    source_type, credibility = classify_source("https://www.energy.gov/example")
    result = ResearchIntelligence(str(tmp_path)).search_news("battery safety", freshness_days=365)

    assert source_type == "government"
    assert credibility == pytest.approx(0.95)
    assert result["count"] == 1
    assert result["findings"][0]["source_id"]
    assert result["findings"][0]["expires_at"]


def test_automation_and_watch_are_durable_and_capability_based(tmp_path):
    automations = AutomationService(str(tmp_path))
    created = automations.create(
        name="Morning intelligence",
        trigger={"type": "schedule"},
        schedule={"every_minutes": 1440},
        steps=[{"capability": "research.news", "arguments": {"query": "portable power"}}],
        created_by="owner",
    )
    watch = automations.create_watch(
        subject="EcoFlow pricing",
        scope={"market": "US"},
        frequency="daily",
        source_policy={"prefer": ["official_company"]},
        materiality_threshold=0.8,
        condition={"price_change_percent": {"gte": 10}},
        actions=[{"capability": "attention.get"}],
    )

    assert AutomationService(str(tmp_path)).get(created["id"])["steps"][0]["capability"] == "research.news"
    assert automations.list_watches()[0]["id"] == watch["id"]
    assert automations.set_status(created["id"], "PAUSED")["status"] == "PAUSED"


def test_material_events_become_attention_items(tmp_path):
    service = bootstrap(str(tmp_path))
    service.events.emit(
        "PROVIDER_DOWN",
        source="test",
        payload={"error": "Publisher authentication failed", "confidence": 1.0},
        materiality=0.95,
    )

    result = heartbeat(str(tmp_path))

    assert result["attention_created"] == 1
    assert service.attention.list_open()[0]["title"] == "Provider Down"


def test_due_automation_runs_registered_capability_and_records_result(tmp_path):
    service = bootstrap(str(tmp_path))
    automations = AutomationService(str(tmp_path))
    created = automations.create(
        name="Immediate health check",
        trigger={"type": "schedule"},
        schedule={"next_run": "2000-01-01T00:00:00+00:00"},
        steps=[{"capability": "system.health", "arguments": {}}],
        created_by="owner",
    )

    runs = automations.run_due(service)

    assert runs[0]["automation_id"] == created["id"]
    assert runs[0]["status"] == "SUCCEEDED"
    assert runs[0]["outputs"][0]["capability"] == "system.health"
    assert automations.list_runs()[0]["status"] == "SUCCEEDED"


def test_creative_scoring_adapter_uses_preserved_quality_engine(tmp_path):
    service = bootstrap(str(tmp_path))
    result = service.execute_capability(
        "creative.score",
        {
            "content": {
                "selected_hook": "How prepared is your home for an outage?",
                "selected_cta": "Compare the right fit",
                "product_name": "Power Station",
                "funnel_stage": "EDUCATION",
                "platform_posts": {"facebook": {"caption": "Home outage planning starts with checking your real device load. Compare the Power Station against what you need to keep powered, then share what matters most in your home?"}},
            },
            "platforms": ["facebook"],
        },
    )

    assert result["status"] == "COMPLETED"
    assert result["result"]["evaluation"]["platform_results"]["facebook"]["total"] > 0
    assert result["result"]["production_mutated"] is False


def test_publication_operations_and_dispatch_preview_are_safe(tmp_path):
    service = bootstrap(str(tmp_path))
    operations = service.execute_capability("publication.operations.get", {})
    preview = service.execute_capability("publication.dispatch", {}, dry_run=True)

    assert operations["status"] == "COMPLETED"
    assert "readiness" in operations["result"]
    assert preview["status"] == "DRY_RUN_COMPLETE"
    assert preview["result"]["production_mutated"] is False


def test_copilot_tool_adapter_uses_sdk_invocation_contract(tmp_path):
    import asyncio
    from copilot.tools import ToolInvocation

    service = bootstrap(str(tmp_path))
    tool = next(item for item in service._copilot_tools("owner") if item.name == "system_health")
    result = asyncio.run(tool.handler(ToolInvocation(tool_name="system_health", arguments={})))

    assert result.result_type == "success"
    payload = json.loads(result.text_result_for_llm)
    assert payload["status"] == "COMPLETED"
    assert payload["result"]["status"] in {"OPERATIONAL", "DEGRADED"}
