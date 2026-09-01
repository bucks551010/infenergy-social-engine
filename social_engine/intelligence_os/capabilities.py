from __future__ import annotations

import os
import re
import sys
import threading
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .governance import PolicyEngine
from .intelligence import AutomationService, ResearchIntelligence
from .knowledge import ResearchService, StrategyService, WorldModel
from .models import CopilotMaster
from .operations import AttentionService, JobService
from .registry import Capability, CapabilityRegistry, ExecutionContext


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def object_schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties or {}, "required": required or []}


def register_core_capabilities(registry: CapabilityRegistry, policies: PolicyEngine) -> None:
    data_dir = registry.data_dir
    strategy = StrategyService(data_dir)
    research = ResearchService(data_dir)
    world = WorldModel(data_dir)
    jobs = JobService(data_dir)
    attention = AttentionService(data_dir)
    external_research = ResearchIntelligence(data_dir)
    automations = AutomationService(data_dir)

    def health(_: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        import inventory_db
        from content_operations import daily_status

        db_path = inventory_db.get_db_path(context.data_dir)
        provider_config = {
            "copilot": {"sdk_installed": _module_available("copilot"), "master_model": os.environ.get("INFENERGY_MASTER_MODEL", "gpt-5.6-sol")},
            "gemini": {"configured": bool(os.environ.get("GEMINI_API_KEY", "").strip())},
            "facebook": {"configured": bool(os.environ.get("META_PAGE_ID", "").strip() and os.environ.get("META_PAGE_ACCESS_TOKEN", "").strip())},
            "instagram": {"configured": bool((os.environ.get("META_IG_USER_ID", "") or os.environ.get("META_INSTAGRAM_BUSINESS_ID", "")).strip())},
            "linkedin": {"configured": bool(os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip())},
            "wordpress": {"configured": bool(os.environ.get("WP_URL", "").strip())},
        }
        return {
            "status": "DEGRADED" if not provider_config["copilot"]["sdk_installed"] else "OPERATIONAL",
            "database": {"path": db_path, "exists": os.path.exists(db_path)},
            "providers": provider_config,
            "social_today": daily_status(context.data_dir, date.today()),
            "dry_run": os.environ.get("SOCIAL_DRY_RUN", "true").lower() != "false",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def model_status(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        return CopilotMaster(data_dir).status().__dict__

    def products_list(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        import inventory_db
        products = inventory_db.fetch_products(context.data_dir)
        query = str(payload.get("query", "")).lower().strip()
        if query:
            products = [item for item in products if query in str(item.get("name", "")).lower() or query in str(item.get("sku", "")).lower()]
        limit = max(1, min(int(payload.get("limit", 100)), 500))
        return {"count": len(products[:limit]), "products": products[:limit], "source": "inventory_db"}

    def product_get(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        import inventory_db
        product_id = str(payload["product_id"])
        item = next((row for row in inventory_db.fetch_products(context.data_dir) if str(row.get("id") or row.get("product_id")) == product_id), None)
        if not item:
            raise KeyError(f"product_not_found:{product_id}")
        return {"product": item, "source": "inventory_db"}

    def calendar(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from content_operations import daily_status
        start = date.fromisoformat(str(payload.get("start_date") or date.today().isoformat()))
        days = max(1, min(int(payload.get("days", 7)), 120))
        return {"start_date": start.isoformat(), "days": [daily_status(context.data_dir, start + timedelta(days=index)) for index in range(days)]}

    def schedule_post(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from content_operations import create_council_session, daily_status, ensure_daily_slots, mark_ready, replace_unpublished_slot

        content_date = str(payload["content_date"])
        slot = str(payload.get("slot", "midday")).strip().lower()
        if slot not in {"morning", "midday", "evening"}:
            raise ValueError("slot_must_be_morning_midday_or_evening")
        default_times = {"morning": "13:00:00+00:00", "midday": "17:00:00+00:00", "evening": "23:00:00+00:00"}
        scheduled_at = str(payload.get("scheduled_at") or f"{content_date}T{default_times[slot]}")
        scheduled_datetime = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        if scheduled_datetime.date().isoformat() != content_date:
            raise ValueError("scheduled_at_must_match_content_date")
        package = dict(payload["package"])
        platforms = [str(item).lower() for item in payload.get("platforms", []) if str(item).strip()]
        if platforms:
            package["platforms"] = platforms
            package.setdefault("platform_policy", {})["platforms"] = platforms
        existing_day = daily_status(context.data_dir, content_date)
        existing_slot = next((item for item in existing_day.get("slots", []) if str(item.get("slot", "")).lower() == slot), None)
        if existing_slot and (existing_slot.get("content_id") or existing_slot.get("outbox_id")) and not bool(payload.get("replace_existing", False)):
            raise ValueError(f"slot_already_occupied:{content_date}:{slot}:set_replace_existing_true")
        plan = {
            "actions": ["ensure_daily_slots", "create_decision_record", "write_content_outbox"],
            "affected_resources": [{"type": "social_slot", "id": f"{content_date}:{slot}"}],
            "estimated_cost_usd": 0.0,
            "risks": ["External publication occurs later only if dispatch policy permits"],
            "irreversible_steps": [],
        }
        if context.dry_run:
            return {"plan": plan, "would_schedule": {"content_date": content_date, "slot": slot, "scheduled_at": scheduled_at}}
        day_start = scheduled_datetime
        schedule = {
            "morning": day_start.replace(hour=13, minute=0).isoformat(),
            "midday": day_start.replace(hour=17, minute=0).isoformat(),
            "evening": day_start.replace(hour=23, minute=0).isoformat(),
        }
        schedule[slot] = scheduled_at
        ensure_daily_slots(context.data_dir, content_date, schedule, package.get("platform_policy", {}))
        replace_unpublished_slot(context.data_dir, content_date, slot)
        decision_id = create_council_session(
            context.data_dir, content_date=content_date, slot=slot,
            blackboard={"source": "infenergy_intelligence_os", "transaction_id": context.transaction_id},
            rationale=[str(payload.get("rationale", "Owner-directed schedule"))],
        )
        outbox_id = mark_ready(
            context.data_dir, content_date=content_date, slot=slot,
            scheduled_at=scheduled_at, decision_id=decision_id, package=package,
        )
        return {
            "outbox_id": outbox_id, "decision_id": decision_id, "plan": plan,
            "_rollback": {"content_date": content_date, "slot": slot, "outbox_id": outbox_id},
        }

    def rollback_schedule(data: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from content_operations import replace_unpublished_slot
        cancelled = replace_unpublished_slot(context.data_dir, str(data["content_date"]), str(data["slot"]))
        if not cancelled:
            return {"status": "NOT_REVERSIBLE", "reason": "slot_already_claimed_or_published", "_irreversible": [data]}
        return {"status": "ROLLED_BACK", "content_date": data["content_date"], "slot": data["slot"]}

    def schedule_job_campaign(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        job_id = str(payload["job_id"])
        job = jobs.get(job_id)
        if job["status"] != "COMPLETED":
            raise ValueError(f"job_not_completed:{job_id}")
        start = date.fromisoformat(str(payload["start_date"]))
        end = date.fromisoformat(str(payload["end_date"]))
        if end < start or (end - start).days >= 120:
            raise ValueError("campaign_range_must_be_1_to_120_days")
        result = job.get("result", {})
        deliverables = next(
            (result.get(key) for key in ("posts", "packages", "episodes") if isinstance(result.get(key), list)),
            [],
        )
        dates = [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]
        requested_slots = payload.get("slots")
        if not isinstance(requested_slots, list) or not requested_slots:
            requested_slots = [str(payload.get("slot", "midday"))]
        slots = [str(item).lower() for item in requested_slots]
        by_date_slot: dict[tuple[str, str], dict[str, Any]] = {}
        for item in deliverables:
            if not isinstance(item, dict):
                continue
            content_date = str(item.get("content_date") or item.get("date") or "")
            item_slot = str(item.get("slot") or (slots[0] if len(slots) == 1 else "")).lower()
            if content_date and item_slot:
                by_date_slot[(content_date, item_slot)] = item
        missing = [f"{content_date}:{slot}" for content_date in dates for slot in slots if (content_date, slot) not in by_date_slot]
        if missing:
            raise ValueError(f"job_deliverables_missing_dates:{','.join(missing)}")
        default_times = {"morning": "13:00:00+00:00", "midday": "17:00:00+00:00", "evening": "23:00:00+00:00"}
        schedule_times = payload.get("schedule_times", {})
        if not isinstance(schedule_times, dict):
            schedule_times = {}
        if len(slots) == 1 and payload.get("scheduled_time"):
            schedule_times[slots[0]] = str(payload["scheduled_time"])
        platforms = list(payload.get("platforms", ["facebook", "instagram", "linkedin"]))
        campaign = job.get("result", {}).get("campaign", {})
        campaign_name = campaign.get("name", "Campaign") if isinstance(campaign, dict) else str(campaign)
        if context.dry_run:
            return {
                "job_id": job_id, "campaign": campaign_name, "would_schedule": len(dates) * len(slots),
                "date_range": {"start": dates[0], "end": dates[-1]}, "slots": slots,
                "platforms": platforms, "publication_enabled": False,
            }
        scheduled: list[dict[str, Any]] = []
        try:
            for content_date in dates:
                for slot in slots:
                    deliverable = by_date_slot[(content_date, slot)]
                    scheduled_time = str(schedule_times.get(slot) or default_times.get(slot) or "17:00:00+00:00")
                    scheduled_result = schedule_post({
                        "content_date": content_date,
                        "slot": slot,
                        "scheduled_at": f"{content_date}T{scheduled_time}",
                        "package": {
                            "source_job_id": job_id,
                            "campaign": campaign_name,
                            "deliverable_date": content_date,
                            "slot": slot,
                            "deliverable": deliverable,
                            "platforms": platforms,
                            "publication_enabled": False,
                        },
                        "rationale": f"Load owner-approved {campaign_name} deliverable from completed job {job_id} without publishing.",
                    }, context)
                    scheduled.append({"content_date": content_date, "slot": slot, "outbox_id": scheduled_result["outbox_id"]})
        except Exception:
            for item in reversed(scheduled):
                rollback_schedule(item, context)
            raise
        resolved_alerts = attention.resolve_matching("job_deliverables_missing_dates:")
        return {
            "job_id": job_id, "campaign": campaign_name, "scheduled_count": len(scheduled),
            "platform_adaptation_count": len(scheduled) * len(platforms), "slots": slots,
            "publication_enabled": False, "scheduled": scheduled,
            "resolved_attention_items": resolved_alerts,
            "_rollback": {"slots": scheduled},
        }

    def rollback_job_campaign(data: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        results = [rollback_schedule(item, context) for item in reversed(data.get("slots", []))]
        irreversible = [item for item in results if item.get("status") != "ROLLED_BACK"]
        return {
            "status": "ROLLED_BACK" if not irreversible else "PARTIAL_ROLLBACK",
            "rolled_back": len(results) - len(irreversible),
            "_irreversible": irreversible,
        }

    def goals_get(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        return {"goals": strategy.list_goals(active_only=False)}

    def goal_create(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        if context.dry_run:
            return {"would_create": payload, "production_mutated": False}
        goal = strategy.create_goal(
            str(payload["name"]), str(payload["description"]),
            priority=int(payload.get("priority", 50)), metrics=payload.get("metrics", []),
            constraints=payload.get("constraints", []), horizon=str(payload.get("horizon", "ongoing")),
        )
        return {"goal": goal, "_rollback": {"table": "os_goals", "id": goal["id"]}}

    def policy_list(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        return {"policies": policies.list_policies(active_only=False)}

    def policy_create(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        if context.dry_run:
            return {"would_create": payload, "production_mutated": False}
        policy = policies.create_policy(
            capability=str(payload["capability"]), rule=str(payload["rule"]),
            approval_level=str(payload["approval_level"]), created_by=context.actor,
            scope=payload.get("scope", {}), limits=payload.get("limits", {}),
            valid_until=payload.get("valid_until"),
        )
        return {"policy": policy}

    def research_mission(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        plan = {
            "question": payload["question"],
            "workstreams": payload.get("workstreams", ["primary_sources", "market", "competitors", "consumer_voice", "verification"]),
            "source_requirements": payload.get("source_requirements", ["authoritative", "current", "corroborated_for_high_impact_claims"]),
        }
        if context.dry_run:
            return {"plan": plan, "production_mutated": False}
        mission = research.create_mission(
            str(payload["question"]), scope=payload.get("scope", {}),
            workstreams=plan["workstreams"], source_requirements=plan["source_requirements"],
            freshness_requirement=str(payload.get("freshness_requirement", "current")),
            depth=str(payload.get("depth", "standard")),
        )
        job = jobs.create(
            job_type="RESEARCH_MISSION", objective=str(payload["question"]),
            plan=["plan_sources", *plan["workstreams"], "corroborate", "synthesize", "rank_implications"],
            operation_id=context.operation_id,
        )
        return {"mission": mission, "job": job}

    def jobs_list(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        return {"jobs": jobs.list()}

    def job_steer(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        if context.dry_run:
            return {"would_steer": payload, "production_mutated": False}
        return {"job": jobs.steer(str(payload["job_id"]), str(payload["instruction"]), context.actor)}

    def job_control(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        action = str(payload["action"]).lower()
        statuses = {"pause": "PAUSED", "continue": "RUNNING", "cancel": "CANCELED"}
        if action not in statuses:
            raise ValueError("action_must_be_pause_continue_or_cancel")
        if context.dry_run:
            return {"would_transition": statuses[action], "job_id": payload["job_id"]}
        return {"job": jobs.transition(str(payload["job_id"]), statuses[action])}

    def job_complete(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        job_id = str(payload["job_id"])
        result = dict(payload["result"])
        job = jobs.get(job_id)
        if job["status"] in {"CANCELED", "COMPLETED"}:
            raise ValueError(f"job_not_completable:{job['status']}")
        if context.dry_run:
            return {"would_complete_job": job_id, "deliverable_keys": sorted(result), "production_mutated": False}
        for step in job["steps"]:
            if step["status"] not in {"COMPLETED", "SKIPPED"}:
                jobs.checkpoint(
                    job_id, int(step["ordinal"]), status="COMPLETED",
                    checkpoint={"completed_by": context.actor, "deliverables_persisted": True},
                    result={"deliverable_keys": sorted(result)},
                )
        return {"job": jobs.transition(job_id, "COMPLETED", progress=1.0, result=result), "deliverables": result}

    def scenario_create(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        if context.dry_run:
            return {"scenario": payload, "production_mutated": False}
        return {"scenario": strategy.create_scenario(
            str(payload["premise"]), assumptions=payload.get("assumptions", []),
            baseline=payload.get("baseline", {}), changed_variables=payload.get("changed_variables", []),
            projected_effects=payload.get("projected_effects", []), confidence=float(payload.get("confidence", 0.3)),
            evidence=payload.get("evidence", []), limitations=payload.get("limitations", ["Projection is not an observed fact"]),
        )}

    def world_search(payload: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        return {"entities": world.search(str(payload["query"]), int(payload.get("limit", 50)))}

    def attention_get(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        return {"attention": attention.list_open()}

    def content_120(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from build_monthly_content import build_monthly_calendar, prepare_monthly_gemini_prompts

        horizons = payload.get("horizons") or [
            {"days": "1-14", "state": "production_ready"},
            {"days": "15-30", "state": "approved_concepts"},
            {"days": "31-60", "state": "adaptive_concepts"},
            {"days": "61-90", "state": "themes_story_arcs"},
            {"days": "91-120", "state": "direction_opportunity_reserve"},
        ]
        plan = [
            "load_goals_and_strategy", "analyze_recent_content", "analyze_performance",
            "fingerprint_creative_history", "research_market_and_competitors",
            "analyze_products_and_campaigns", "design_story_arcs_and_franchises",
            "build_rolling_horizon", "diversity_and_saturation_review",
            "owner_strategy_review", "produce_locked_horizon", "qa_and_package", "schedule_approved",
        ]
        if context.dry_run:
            return {"objective": payload.get("objective", "Build adaptive 120-day content system"), "plan": plan, "horizons": horizons, "estimated_cost": "requires provider pricing and production scope", "production_mutated": False}
        job = jobs.create(
            job_type="ADAPTIVE_120_DAY_CONTENT",
            objective=str(payload.get("objective", "Build adaptive 120-day content system")),
            plan=plan, operation_id=context.operation_id,
        )
        jobs.transition(job["id"], "RUNNING", progress=0.05)
        jobs.checkpoint(
            job["id"], 0, status="COMPLETED",
            checkpoint={"builder": "build_monthly_calendar", "days": 120},
        )

        def build_in_background() -> None:
            try:
                calendar = build_monthly_calendar(
                    data_dir=context.data_dir,
                    start_date=payload.get("start_date"),
                    days=120,
                    enqueue=True,
                    replace_unpublished=bool(payload.get("replace_unpublished", True)),
                    content_plan=str(payload.get("content_plan") or "weekly_brand_mix"),
                )
                prepared = prepare_monthly_gemini_prompts(context.data_dir)
                result = {
                    "calendar_path": calendar.get("calendar_path"),
                    "queued": int(calendar.get("queued") or 0),
                    "cancelled_outbox": int(calendar.get("cancelled_outbox") or 0),
                    "single_image_posts": int(calendar.get("single_image_posts") or 0),
                    "carousel_posts": int(calendar.get("carousel_posts") or 0),
                    "product_posts": int(calendar.get("product_posts") or 0),
                    "current_event_posts": int(calendar.get("current_event_posts") or 0),
                    "superhero_posts": int(calendar.get("superhero_posts") or 0),
                    "micro_mission_posts": int(calendar.get("micro_mission_posts") or 0),
                    "historical_mission_posts": int(calendar.get("historical_mission_posts") or 0),
                    "prepared_entries": int(prepared.get("prepared_entries") or 0),
                    "prepared_prompts": int(prepared.get("prepared_prompts") or 0),
                    "content_plan": str(payload.get("content_plan") or "weekly_brand_mix"),
                    "replace_unpublished": bool(payload.get("replace_unpublished", True)),
                }
                for step in jobs.get(job["id"])["steps"]:
                    if step["status"] not in {"COMPLETED", "SKIPPED"}:
                        jobs.checkpoint(
                            job["id"], int(step["ordinal"]), status="COMPLETED",
                            checkpoint={"builder": "build_monthly_calendar", "calendar_path": result["calendar_path"]},
                            result={"queued": result["queued"]},
                        )
                jobs.transition(job["id"], "COMPLETED", progress=1.0, result=result)
            except Exception as exc:
                jobs.transition(
                    job["id"], "FAILED",
                    result={"error": f"{type(exc).__name__}: {exc}", "builder": "build_monthly_calendar"},
                )

        threading.Thread(
            target=build_in_background,
            name=f"content-120-{job['id'][:8]}",
            daemon=True,
        ).start()
        return {
            "job": jobs.get(job["id"]), "horizons": horizons,
            "locked_days": int(payload.get("locked_days", 7)), "dispatched": True,
        }

    def research_news(payload: dict[str, Any], _: ExecutionContext) -> dict[str, Any]:
        return external_research.search_news(
            str(payload.get("query", "energy technology business world news")),
            limit=int(payload.get("limit", 10)), freshness_days=int(payload.get("freshness_days", 2)),
        )

    def findings_get(payload: dict[str, Any], _: ExecutionContext) -> dict[str, Any]:
        return {"findings": external_research.list_findings(int(payload.get("limit", 100)))}

    def automations_get(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        return {"automations": automations.list(), "runs": automations.list_runs(), "watches": automations.list_watches()}

    def automation_create(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        for step in payload.get("steps", []):
            registry.get(str(step.get("capability", "")))
        if context.dry_run:
            return {"would_create": payload, "required_capabilities": [step["capability"] for step in payload.get("steps", [])], "production_mutated": False}
        automation = automations.create(
            name=str(payload["name"]), trigger=payload["trigger"], steps=payload["steps"],
            created_by=context.actor, conditions=payload.get("conditions", []),
            permissions=payload.get("permissions", {}), approval_rules=payload.get("approval_rules", {}),
            schedule=payload.get("schedule", {}), failure_policy=payload.get("failure_policy", {}),
        )
        return {"automation": automation}

    def automation_control(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        status = {"pause": "PAUSED", "resume": "ACTIVE", "disable": "DISABLED"}.get(str(payload["action"]).lower())
        if not status:
            raise ValueError("action_must_be_pause_resume_or_disable")
        if context.dry_run:
            return {"would_set_status": status, "automation_id": payload["automation_id"]}
        return {"automation": automations.set_status(str(payload["automation_id"]), status)}

    def watch_create(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        if context.dry_run:
            return {"would_create": payload, "production_mutated": False}
        return {"watch": automations.create_watch(
            subject=str(payload["subject"]), scope=payload.get("scope", {}),
            frequency=str(payload.get("frequency", "daily")), source_policy=payload.get("source_policy", {}),
            materiality_threshold=float(payload.get("materiality_threshold", 0.7)),
            condition=payload.get("condition", {}), actions=payload.get("actions", []),
            expires_at=payload.get("expires_at"),
        )}

    def decisions_get(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from social_engine.intelligence_os.db import connect, decode
        with connect(context.data_dir) as connection:
            rows = connection.execute("SELECT * FROM os_decisions ORDER BY created_at DESC LIMIT ?", (max(1, min(int(payload.get("limit", 100)), 500)),)).fetchall()
        decisions = []
        for row in rows:
            item = dict(row)
            for key in ("evidence_json", "alternatives_json", "assumptions_json", "goals_affected_json", "policies_applied_json", "actions_json"):
                item[key[:-5]] = decode(item.pop(key), [])
            decisions.append(item)
        return {"decisions": decisions}

    def opportunities_get(_: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from social_engine.intelligence_os.db import connect, decode
        with connect(context.data_dir) as connection:
            rows = connection.execute("SELECT * FROM os_opportunities WHERE status!='DISMISSED' ORDER BY potential_value DESC, confidence DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row); item["evidence"] = decode(item.pop("evidence_json"), []); result.append(item)
        return {"opportunities": result}

    def risks_get(_: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from social_engine.intelligence_os.db import connect, decode
        with connect(context.data_dir) as connection:
            rows = connection.execute("SELECT * FROM os_risks WHERE status!='CLOSED' ORDER BY impact DESC, likelihood DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row); item["evidence"] = decode(item.pop("evidence_json"), []); result.append(item)
        return {"risks": result}

    def creative_score(payload: dict[str, Any], _: ExecutionContext) -> dict[str, Any]:
        from score_content import score_content
        content = payload.get("content")
        if not isinstance(content, dict):
            raise ValueError("content_object_required")
        return {
            "evaluation": score_content(content, payload.get("platforms")),
            "thresholds": {"approve": 82, "regenerate_once": 75, "reject": 0},
            "production_mutated": False,
        }

    def agents_list(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        from agents.dispatcher import agent_contracts, available_agents
        return {"agents": available_agents(), "contracts": agent_contracts()}

    def agent_run(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from agents.dispatcher import run_agent
        name = str(payload["name"])
        params = dict(payload.get("params", {}))
        if context.dry_run:
            return {"would_run": name, "params": params, "production_mutated": False}
        if name == "carousel_slide_writer" and str(params.get("objective", "")).strip():
            result = creative_carousel_generate(params, context)
            return {
                "agent": name,
                "delegated_capability": "creative.carousel.generate",
                "output": result,
                "_rollback": result.pop("_rollback", {}),
            }
        result = run_agent(name, context.data_dir, params)
        if result.get("error"):
            detail = str(result.get("detail") or "").strip()
            raise ValueError(": ".join(part for part in (str(result["error"]), detail) if part))
        return {"agent": name, "output": result}

    def creative_carousel_generate(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from agents.carousel_slide_writer import PLATFORM_LIMITS, run as write_slides
        from build_monthly_content import _render_assets

        platform = str(payload.get("platform", "instagram_feed")).strip().lower()
        slide_count = int(payload.get("slide_count", 6))
        platform_limit = PLATFORM_LIMITS.get(platform, 10)
        objective = str(payload["objective"]).strip()
        title = str(payload.get("title") or objective).strip()
        if context.dry_run:
            return {
                "would_generate": {"objective": objective, "platform": platform, "slide_count": slide_count},
                "platform_limit": platform_limit, "production_mutated": False,
            }
        product = dict(payload.get("product", {}))
        product_id = str(payload.get("product_id", "")).strip()
        if product_id and not product:
            import inventory_db
            product = next(
                (item for item in inventory_db.fetch_products(context.data_dir) if str(item.get("id") or item.get("product_id")) == product_id),
                {},
            )
            if not product:
                raise KeyError(f"product_not_found:{product_id}")
        authored = write_slides(
            context.data_dir,
            principle_key=str(payload.get("principle_key", "contrapositive")),
            archetype_key=str(payload.get("archetype_key", "preparedness_buyer")),
            product=product,
            creative_brief=objective,
            platform=platform,
            slide_count=slide_count,
        )
        thought = {
            "id": f"CREATIVE-{uuid.uuid4().hex[:12]}",
            "format": "carousel",
            "statement": objective,
            "expansion": str(payload.get("supporting_message", objective)),
            "prompt": str(payload.get("cta", "What will you prepare first?")),
            "pillar": str(payload.get("pillar", "preparedness_mindset")),
            "visual_motif": str(payload.get("visual_motif", "premium editorial energy story")),
            "slides": [
                {
                    "role": (
                        "COVER" if index == 0
                        else "FINALE" if index == len(authored["slides"]) - 1
                        else slide["slide_role"]
                    ),
                    "headline": slide["on_image_headline"],
                    "supporting": slide["on_image_subline"],
                }
                for index, slide in enumerate(authored["slides"])
            ],
            "cta": str(payload.get("cta", "What will you prepare first?")),
        }
        rendered = _render_assets(context.data_dir, thought, 0)
        assets = rendered["slides"]
        from PIL import Image
        asset_validation = []
        for index, asset in enumerate(assets, start=1):
            path = Path(str(asset.get("local_path", "")))
            validation = {
                "slide": index,
                "local_path": str(path),
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else 0,
                "decodable": False,
                "width": 0,
                "height": 0,
            }
            if validation["exists"] and validation["size_bytes"] > 0:
                try:
                    with Image.open(path) as image:
                        validation["width"], validation["height"] = image.size
                        image.verify()
                    validation["decodable"] = True
                except Exception:
                    pass
            validation["valid"] = bool(
                validation["exists"]
                and validation["size_bytes"] > 0
                and validation["decodable"]
                and validation["width"] > 0
                and validation["height"] > 0
            )
            asset_validation.append(validation)
        invalid_assets = [item["slide"] for item in asset_validation if not item["valid"]]
        if invalid_assets:
            raise RuntimeError(f"carousel_asset_validation_failed:{','.join(str(item) for item in invalid_assets)}")
        supporting = str(payload.get("supporting_message") or "").strip()
        cta = str(payload.get("cta") or "What would you protect first?").strip()
        facebook_caption = str(payload.get("caption") or "\n\n".join(part for part in (title, objective, supporting, cta) if part)).strip()
        instagram_caption = "\n\n".join(part for part in (objective, supporting, cta, "#Infenergy #Preparedness #PracticalPower") if part)
        linkedin_caption = "\n\n".join(part for part in (title, objective, supporting, f"Practical next step: {cta}") if part)
        platforms = [str(item).lower() for item in payload.get("platforms", []) if str(item).strip()]
        if not platforms:
            platforms = ["facebook", "instagram"]
        package = {
            "post_id": thought["id"].lower(),
            "objective": objective,
            "visual_format": "CAROUSEL",
            "carousel_slides": authored["slides"],
            "carousel_assets": assets,
            "generated_visuals": {name: rendered["primary"]["local_path"] for name in platforms},
            "title": title,
            "fb_caption": facebook_caption,
            "ig_caption": instagram_caption,
            "li_text": linkedin_caption,
            "platforms": platforms,
            "platform_policy": {"platforms": platforms},
            "platform_posts": {},
        }
        platform_copies = {
            "facebook": facebook_caption,
            "instagram": instagram_caption,
            "linkedin": linkedin_caption,
        }
        package["platform_posts"] = {
            name: {"platform": name, "final_caption": platform_copies.get(name, facebook_caption), "content_format": "carousel"}
            for name in platforms
        }
        return {
            "status": "GENERATED",
            "slide_count": len(authored["slides"]),
            "platform": platform,
            "platform_limit": platform_limit,
            "package": package,
            "assets": assets,
            "asset_validation": asset_validation,
            "all_assets_valid": True,
            "next_action": "Call social.schedule with this package; one owner approval will schedule it.",
            "_rollback": {"asset_paths": [item["local_path"] for item in assets]},
        }

    def creative_scored_story_reel(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from social.reels import build_scored_story_plan, render_scored_story_reel, technical_qa

        package = dict(payload["package"])
        carousel_assets = package.get("carousel_assets")
        if not isinstance(carousel_assets, list) or len(carousel_assets) < 2:
            raise ValueError("package_requires_at_least_two_carousel_assets")
        slide_texts = payload.get("slide_texts")
        if not isinstance(slide_texts, list):
            slide_texts = [
                " ".join(part for part in (str(slide.get("on_image_headline") or ""), str(slide.get("on_image_subline") or "")) if part).strip()
                for slide in package.get("carousel_slides", [])
                if isinstance(slide, dict)
            ]
        visual_readings = payload.get("visual_readings")
        if not isinstance(visual_readings, list):
            visual_readings = package.get("visual_readings")
        if not isinstance(visual_readings, list) or len(visual_readings) != len(carousel_assets):
            story_roles = ("setup", "pressure", "evidence", "reveal", "adaptation", "response", "resolution", "reflection")
            camera_moves = ("push", "pan_right", "pull", "pan_left", "hold")
            visual_readings = []
            for index, asset in enumerate(carousel_assets):
                text = str(slide_texts[index] if index < len(slide_texts) else "").strip()
                visual_readings.append({
                    "story_role": story_roles[min(index, len(story_roles) - 1)],
                    "camera_move": camera_moves[index % len(camera_moves)],
                    "focal_x": 0.5,
                    "focal_y": 0.5,
                    "visual_summary": text or f"Carousel frame {index + 1}",
                    "narrative_change": f"Advance the ordered story to frame {index + 1} of {len(carousel_assets)}.",
                    "reading_order": [text] if text else [str(asset.get("local_path") or f"frame {index + 1}")],
                })
        plan = build_scored_story_plan(
            post_id=str(package.get("post_id") or uuid.uuid4().hex),
            carousel_assets=carousel_assets,
            slide_texts=[str(item) for item in slide_texts],
            emotions=[str(item) for item in payload.get("emotions", [])],
            narration_path=str(payload.get("narration_path") or "") or None,
            motion_intensity=float(payload.get("motion_intensity", 0.55)),
            visual_readings=visual_readings,
        )
        plan["auto_narration"] = bool(payload.get("auto_narration", True))
        if context.dry_run:
            return {"would_render": plan, "production_mutated": False}
        artifact = render_scored_story_reel(plan, data_dir=context.data_dir)
        qa = technical_qa(artifact, plan)
        if qa["status"] != "PASS":
            raise RuntimeError(f"scored_story_technical_qa_failed:{','.join(qa['reasons'])}")
        package["instagram_reel"] = artifact
        package["visual_format"] = "SCORED_STORY_REEL"
        package.setdefault("platform_posts", {})["instagram"] = {
            **package.get("platform_posts", {}).get("instagram", {}),
            "platform": "instagram", "media_type": "REEL", "content_format": "reel",
            "final_caption": package.get("ig_caption", ""),
        }
        return {
            "status": "RENDERED", "package": package, "instagram_reel": artifact,
            "plan": plan, "technical_qa": qa,
            "platform_support": {
                "instagram": "READY_FOR_REEL_SCHEDULING",
                "facebook": "CAROUSEL_ASSETS_RETAINED_VIDEO_UPLOAD_NOT_ENABLED",
                "linkedin": "CAROUSEL_ASSETS_RETAINED_VIDEO_UPLOAD_NOT_ENABLED",
            },
            "next_action": "Call social.schedule with this package and include instagram to schedule the Reel.",
            "_rollback": {"asset_paths": [artifact[key] for key in ("reel_artifact_path", "cover_path", "final_freeze_frame_path", "static_derivative_path")]},
        }

    def rollback_creative(data: dict[str, Any], _: ExecutionContext) -> dict[str, Any]:
        removed = []
        for path in data.get("asset_paths", []):
            candidate = Path(str(path))
            if candidate.is_file():
                candidate.unlink()
                removed.append(str(candidate))
        return {"status": "ROLLED_BACK", "removed_assets": removed}

    def publication_operations(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from content_operations import daily_index, operations_readiness
        content_date = payload.get("content_date")
        index = daily_index(context.data_dir, content_date)
        readiness = operations_readiness(context.data_dir, lead_hours=int(payload.get("lead_hours", 2)))
        failures = []
        for detail in index.get("details", []):
            for outbox in detail.get("outbox", []):
                for transaction in outbox.get("transactions", []):
                    if transaction.get("state") in {"FAILED", "AMBIGUOUS"} or transaction.get("last_error"):
                        failures.append(transaction)
        return {"index": index, "readiness": readiness, "publication_failures": failures}

    def publication_detail(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from content_operations import content_detail
        result = content_detail(context.data_dir, str(payload["decision_id"]))
        if not result:
            raise KeyError(f"content_decision_not_found:{payload['decision_id']}")
        return result

    def publication_dispatch(_: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        from dispatch_outbox import dispatch_due
        if context.dry_run:
            from content_operations import operations_readiness
            return {"would_dispatch_due": True, "readiness": operations_readiness(context.data_dir), "production_mutated": False}
        return dispatch_due(data_dir=context.data_dir)

    def brand_positioning(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        from business_intelligence.brand import build_identity, build_positioning, build_voice, build_why, build_worldview
        values = {
            "identity": build_identity(), "why": build_why(), "worldview": build_worldview(),
            "positioning": build_positioning(), "voice": build_voice(),
        }
        return {key: asdict(value) if is_dataclass(value) else value for key, value in values.items()}

    def product_match(payload: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        import inventory_db
        topic = str(payload.get("topic", ""))
        archetype = str(payload.get("archetype", "preparedness_buyer"))
        archetype_words = {
            "preparedness_buyer": "backup outage emergency battery generator home",
            "mobile_professional": "portable charger usb commuter travel work",
            "outdoor_adventurer": "solar camping outdoors off-grid travel",
        }.get(archetype, archetype.replace("_", " "))
        terms = {term for term in re.findall(r"[a-z0-9]+", f"{topic} {archetype_words}".lower()) if len(term) > 2}
        candidates = []
        for product in inventory_db.fetch_products(context.data_dir):
            text = " ".join((str(product.get("name", "")), str(product.get("categories", "")), str(product.get("description", "")), str(product.get("verified_facts", "")))).lower()
            matched = sorted(term for term in terms if term in text)
            candidates.append({
                "product_id": product.get("id") or product.get("product_id"),
                "name": product.get("name"), "score": len(matched), "matched_terms": matched,
                "evidence_eligible": bool(product.get("verified_facts")),
            })
        candidates.sort(key=lambda item: (item["evidence_eligible"], item["score"]), reverse=True)
        limit = max(1, min(int(payload.get("limit", 5)), 25))
        return {"topic": topic, "archetype": archetype, "candidates": candidates[:limit], "method": "catalog_evidence_keyword_fit"}

    def platforms_status(_: dict[str, Any], __: ExecutionContext) -> dict[str, Any]:
        from platform_publishing import list_platforms
        platforms = list_platforms()
        return {
            "platforms": platforms,
            "connected": [item["platform"] for item in platforms if item["status"] == "CONNECTED"],
            "action_required": [item["platform"] for item in platforms if item["status"] in {"REAUTH_REQUIRED", "ERROR"}],
        }

    definitions = [
        Capability("system.health", "System health", "Inspect actual Infenergy provider, database, and social status.", "SYSTEM_HEALTH", health),
        Capability("models.status", "Master model status", "Enumerate authenticated Copilot models and verify the configured master model.", "SYSTEM_HEALTH", model_status),
        Capability("products.list", "List products", "Retrieve canonical Infenergy product records.", "PRODUCTS", products_list, object_schema({"query": {"type": "string"}, "limit": {"type": "integer"}})),
        Capability("products.get", "Get product", "Retrieve one canonical product by identifier.", "PRODUCTS", product_get, object_schema({"product_id": {"type": "string"}}, ["product_id"])),
        Capability("social.calendar.get", "Get social calendar", "Retrieve durable Social Engine slots over a date range.", "SOCIAL", calendar, object_schema({"start_date": {"type": "string"}, "days": {"type": "integer"}})),
        Capability("social.schedule", "Approve and schedule post", "Schedule one finished creative package with one owner approval. A time is selected automatically from the slot when scheduled_at is omitted.", "SOCIAL", schedule_post, object_schema({"content_date": {"type": "string"}, "slot": {"type": "string"}, "scheduled_at": {"type": "string"}, "package": {"type": "object"}, "platforms": {"type": "array"}, "replace_existing": {"type": "boolean"}, "rationale": {"type": "string"}}, ["content_date", "package"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL", supports_rollback=True, rollback_handler=rollback_schedule),
        Capability("social.schedule_job_campaign", "Load completed campaign into calendar", "Load a completed job's dated campaign deliverables from episodes, packages, or posts into one or more durable Social Engine slots with one owner approval and no publication.", "SOCIAL", schedule_job_campaign, object_schema({"job_id": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "slot": {"type": "string"}, "slots": {"type": "array"}, "scheduled_time": {"type": "string"}, "schedule_times": {"type": "object"}, "platforms": {"type": "array"}}, ["job_id", "start_date", "end_date"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL", supports_rollback=True, rollback_handler=rollback_job_campaign),
        Capability("goals.get", "Get goals", "Return active and historical Infenergy goals.", "GOALS", goals_get),
        Capability("goals.create", "Create goal", "Create a versioned persistent Infenergy goal.", "GOALS", goal_create, object_schema({"name": {"type": "string"}, "description": {"type": "string"}, "priority": {"type": "integer"}, "metrics": {"type": "array"}, "constraints": {"type": "array"}, "horizon": {"type": "string"}}, ["name", "description"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL", supports_rollback=False),
        Capability("policies.get", "Get operating policies", "Return exact current autonomy and approval policies.", "OPERATIONS", policy_list),
        Capability("policies.create", "Create operating policy", "Create a scoped, time-aware operating policy for an Infenergy capability.", "OPERATIONS", policy_create, object_schema({"capability": {"type": "string"}, "rule": {"type": "string"}, "approval_level": {"type": "string"}, "scope": {"type": "object"}, "limits": {"type": "object"}, "valid_until": {"type": "string"}}, ["capability", "rule", "approval_level"]), risk_level="GOVERNANCE", permission_requirement="AUTONOMOUS"),
        Capability("research.mission.create", "Create research mission", "Create a durable multi-workstream research mission with source requirements.", "RESEARCH", research_mission, object_schema({"question": {"type": "string"}, "scope": {"type": "object"}, "workstreams": {"type": "array"}, "source_requirements": {"type": "array"}, "freshness_requirement": {"type": "string"}, "depth": {"type": "string"}}, ["question"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL", synchronous=False),
        Capability("jobs.get", "Get jobs", "Inspect durable jobs, steps, progress, checkpoints, errors, and steering.", "OPERATIONS", jobs_list),
        Capability("jobs.steer", "Steer job", "Add an owner instruction to a running durable job.", "OPERATIONS", job_steer, object_schema({"job_id": {"type": "string"}, "instruction": {"type": "string"}}, ["job_id", "instruction"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL"),
        Capability("jobs.control", "Control job", "Pause, continue, or cancel a durable job.", "OPERATIONS", job_control, object_schema({"job_id": {"type": "string"}, "action": {"type": "string"}}, ["job_id", "action"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL"),
        Capability("jobs.complete", "Complete job with deliverables", "Persist the actual completed deliverables for an approved durable job and close every tracked step. Never call with a promise or outline; result must contain the work product.", "OPERATIONS", job_complete, object_schema({"job_id": {"type": "string"}, "result": {"type": "object"}}, ["job_id", "result"]), risk_level="INTERNAL_MUTATION", permission_requirement="AUTONOMOUS"),
        Capability("scenario.create", "Create scenario", "Create an immutable non-production business scenario with explicit uncertainty.", "STRATEGY", scenario_create, object_schema({"premise": {"type": "string"}, "assumptions": {"type": "array"}, "baseline": {"type": "object"}, "changed_variables": {"type": "array"}, "projected_effects": {"type": "array"}, "confidence": {"type": "number"}, "evidence": {"type": "array"}, "limitations": {"type": "array"}}, ["premise"]), risk_level="INTERNAL_MUTATION", permission_requirement="AUTONOMOUS"),
        Capability("world.search", "Search world model", "Search temporal Infenergy entities and current assertions.", "KNOWLEDGE", world_search, object_schema({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"])),
        Capability("attention.get", "Get attention", "Return the highest-materiality unresolved executive attention items.", "OPERATIONS", attention_get),
        Capability("content.plan_120_days", "Build and schedule 120 days", "Build and queue a complete research-informed 120-day weekly brand content calendar with one owner approval.", "SOCIAL", content_120, object_schema({"objective": {"type": "string"}, "start_date": {"type": "string"}, "replace_unpublished": {"type": "boolean"}, "content_plan": {"type": "string"}, "locked_days": {"type": "integer"}, "horizons": {"type": "array"}}), risk_level="INTERNAL_MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL", synchronous=False),
        Capability("research.news", "Research current news", "Retrieve current news through an external provider and store provenance-bearing time-limited findings.", "NEWS", research_news, object_schema({"query": {"type": "string"}, "limit": {"type": "integer"}, "freshness_days": {"type": "integer"}}), cost_class="LOW"),
        Capability("research.findings.get", "Get research findings", "Retrieve the durable Intelligence Library with provenance, credibility, and freshness.", "RESEARCH", findings_get, object_schema({"limit": {"type": "integer"}})),
        Capability("automations.get", "Get automations", "Inspect exact durable automations, schedules, watches, permissions, and status.", "AUTOMATIONS", automations_get),
        Capability("automations.create", "Create automation", "Create a durable capability-based automation with explicit trigger, conditions, approval rules, and failure policy.", "AUTOMATIONS", automation_create, object_schema({"name": {"type": "string"}, "trigger": {"type": "object"}, "conditions": {"type": "array"}, "steps": {"type": "array"}, "permissions": {"type": "object"}, "approval_rules": {"type": "object"}, "schedule": {"type": "object"}, "failure_policy": {"type": "object"}}, ["name", "trigger", "steps"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL", supports_rollback=False),
        Capability("automations.control", "Control automation", "Pause, resume, or disable a durable automation.", "AUTOMATIONS", automation_control, object_schema({"automation_id": {"type": "string"}, "action": {"type": "string"}}, ["automation_id", "action"]), risk_level="MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL"),
        Capability("watches.create", "Create intelligence watch", "Create a condition-based monitor with source and materiality policies.", "AUTOMATIONS", watch_create, object_schema({"subject": {"type": "string"}, "scope": {"type": "object"}, "frequency": {"type": "string"}, "source_policy": {"type": "object"}, "materiality_threshold": {"type": "number"}, "condition": {"type": "object"}, "actions": {"type": "array"}, "expires_at": {"type": "string"}}, ["subject"]), risk_level="INTERNAL_MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL"),
        Capability("decisions.get", "Get decisions", "Retrieve actual durable decision rationale, evidence, assumptions, goals, policies, and actions.", "DECISIONS", decisions_get, object_schema({"limit": {"type": "integer"}})),
        Capability("opportunities.get", "Get opportunities", "Return ranked, evidence-bearing Infenergy opportunities.", "BUSINESS_INTELLIGENCE", opportunities_get),
        Capability("risks.get", "Get risks", "Return ranked, evidence-bearing Infenergy risks and mitigations.", "BUSINESS_INTELLIGENCE", risks_get),
        Capability("creative.score", "Score creative", "Evaluate supplied content with the preserved platform-native quality rubric without generating or publishing anything.", "CREATIVE_STUDIO", creative_score, object_schema({"content": {"type": "object"}, "platforms": {"type": "array"}}, ["content"])),
        Capability("creative.carousel.generate", "Generate carousel package", "Author and render a complete platform-safe carousel package with a caller-selected 2-to-10 slide count. This creates draft assets but does not schedule or publish them.", "CREATIVE_STUDIO", creative_carousel_generate, object_schema({"objective": {"type": "string"}, "title": {"type": "string"}, "platform": {"type": "string"}, "platforms": {"type": "array"}, "slide_count": {"type": "integer"}, "product_id": {"type": "string"}, "product": {"type": "object"}, "principle_key": {"type": "string"}, "archetype_key": {"type": "string"}, "supporting_message": {"type": "string"}, "caption": {"type": "string"}, "cta": {"type": "string"}, "pillar": {"type": "string"}, "visual_motif": {"type": "string"}}, ["objective"]), risk_level="INTERNAL_MUTATION", cost_class="MEDIUM", permission_requirement="AUTONOMOUS", supports_rollback=True, rollback_handler=rollback_creative),
        Capability("creative.scored_story_reel.generate", "Render scored story Reel", "Animate an existing ordered carousel into a vertical H.264 story Reel with readable timing, emotional scoring, free local narration, and Instagram-ready media. Facebook and LinkedIn retain carousel assets until their video upload paths are enabled.", "CREATIVE_STUDIO", creative_scored_story_reel, object_schema({"package": {"type": "object"}, "slide_texts": {"type": "array"}, "emotions": {"type": "array"}, "visual_readings": {"type": "array"}, "narration_path": {"type": "string"}, "auto_narration": {"type": "boolean"}, "motion_intensity": {"type": "number"}}, ["package"]), risk_level="INTERNAL_MUTATION", cost_class="LOW", permission_requirement="EXECUTE_WITH_APPROVAL", supports_rollback=True, rollback_handler=rollback_creative),
        Capability("agents.list", "List operational agents", "List every preserved specialist agent and its accepted parameters and aliases.", "OPERATIONS", agents_list),
        Capability("agents.run", "Run operational agent", "Run a registered specialist with parameters from agents.list. For a complete rendered carousel package, carousel_slide_writer with objective delegates to creative.carousel.generate and validates every asset without scheduling or publishing. Mutation-capable agent execution remains owner-approved.", "OPERATIONS", agent_run, object_schema({"name": {"type": "string"}, "params": {"type": "object"}}, ["name"]), risk_level="INTERNAL_MUTATION", permission_requirement="EXECUTE_WITH_APPROVAL", supports_rollback=True, rollback_handler=rollback_creative),
        Capability("publication.operations.get", "Get publication operations", "Inspect exact daily slots, candidate decisions, outbox state, platform transactions, failures, and readiness actions.", "SOCIAL", publication_operations, object_schema({"content_date": {"type": "string"}, "lead_hours": {"type": "integer"}})),
        Capability("publication.detail.get", "Get publication decision detail", "Retrieve one content council decision with candidates, rationale, outbox packages, and provider transaction evidence.", "SOCIAL", publication_detail, object_schema({"decision_id": {"type": "string"}}, ["decision_id"])),
        Capability("publication.dispatch", "Dispatch due publications", "Dispatch due approved outbox packages through preserved idempotent platform publishers; preview safely with dry run.", "SOCIAL", publication_dispatch, object_schema({}), risk_level="EXTERNAL_IRREVERSIBLE", cost_class="MEDIUM", permission_requirement="EXECUTE_WITH_APPROVAL", supports_rollback=False),
        Capability("brand.positioning.get", "Get brand positioning", "Return owner-first identity, purpose, worldview, competitive position, and voice constraints with preserved source hierarchy.", "BRAND", brand_positioning),
        Capability("products.match", "Match products to intent", "Rank evidence-eligible catalog products against an audience archetype and topic without changing inventory.", "PRODUCTS", product_match, object_schema({"topic": {"type": "string"}, "archetype": {"type": "string"}, "limit": {"type": "integer"}})),
        Capability("platforms.status", "Get platform connections", "Return machine-readable publishing capabilities, feature flags, and credential health for Facebook, Instagram, LinkedIn, TikTok, and YouTube without exposing secrets.", "SYSTEM_HEALTH", platforms_status),
    ]
    for capability in definitions:
        registry.register(capability)


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False