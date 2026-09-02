from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from datetime import date, timedelta
from typing import Any

from .db import connect, decode, encode, initialize, utc_now
from .governance import PolicyEngine
from .intelligence import AutomationService, ResearchIntelligence
from .models import CopilotMaster, MasterModelUnavailable, new_session_id
from .operations import AttentionService, AuditLog, EventBus, JobService
from .registry import CapabilityRegistry
from .transactions import TransactionService


MASTER_PROMPT = """You are Infenergy's outcome-driven master intelligence and operating agent.
Work like a capable senior operator, not a question-answer chatbot. Maintain continuity across the supplied durable conversation. Resolve pronouns and short follow-ups such as "go find it", "do that", and "continue" from the prior goal, plan, and results. Never ask the owner to repeat information already present in context.

Own the objective from request to verified outcome: inspect current state, form a concise plan, invoke the registered semantic tools, evaluate their results, adapt, and continue until the objective is complete or a real external blocker remains. Prefer taking safe, reversible action over explaining what the owner could do. Use read-only tools autonomously. Use dry runs to preview mutations. If governance requires approval, create the approval request through the capability, report exactly what is waiting, and explain the single approval needed. Use social.schedule_job_campaign for a completed dated campaign instead of creating an automation or requesting approval for each individual slot. A PLANNING or RUNNING job is not a finished outcome. After an approved job exists, produce the actual requested work product and call jobs.complete with those deliverables before claiming completion. Never claim that a job, plan, publication, or automation exists unless a tool result confirms it.

For natural-language creative requests, use creative.command.produce so character resolution, canon, story, integrated typography, sequence continuity, Studio routing, blocking QA, and automatic repair remain one authoritative contract. Use creative.carousel.generate only for explicitly non-character editorial carousels. Never return a plan when the owner asked to create. Scheduling is separate and requires owner approval; publication.dispatch remains a separate irreversible approval.

Infer reasonable operational details from Infenergy's goals, catalog, strategy, and conversation. Ask a clarifying question only when a missing fact would create material risk or make execution impossible; otherwise state the assumption and proceed. Be concise in chat while doing the detailed work through tools. Use authoritative internal data when available and current external research when needed. For substantial work, establish a durable job or checkpoint before a long tool chain so progress can be resumed safely. Distinguish facts, metrics, inference, forecast, hypothesis, recommendation, and owner decision. Have a point of view. Do not make the owner operate low-level tools. Do not bluff. Respect permissions, approvals, budgets, and policies. Preserve provenance and explain material actions. Never expand your own permissions. The owner is the final authority. Use only registered Infenergy semantic tools; do not use ambient shell, filesystem, credential, or deployment tools.
"""

GENERATION_CONTROL_FIELDS = (
    "content_type", "format", "style", "topic", "platform", "infenergy_usage",
    "product_usage", "campaign", "tone", "objective", "cta", "publishing_date",
    "publishing_time", "creative_instructions",
)


class IntelligenceOS:
    def __init__(self, data_dir: str, registry: CapabilityRegistry, policies: PolicyEngine):
        self.data_dir = data_dir
        self.registry = registry
        self.policies = policies
        self.transactions = TransactionService(data_dir, registry, policies)
        self.audit = AuditLog(data_dir)
        self.events = EventBus(data_dir)
        self.jobs = JobService(data_dir)
        self.attention = AttentionService(data_dir)
        self.master = CopilotMaster(data_dir)
        initialize(data_dir)

    def create_conversation(self, *, owner_id: str = "owner", title: str = "Infenergy Command") -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        session_id = new_session_id()
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_conversations VALUES (?, ?, ?, ?, 'ACTIVE', '{}', ?, ?)",
                (identifier, owner_id, title, session_id, now, now),
            )
            connection.commit()
        return self.get_conversation(identifier)

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_conversations WHERE id=?", (conversation_id,)).fetchone()
            messages = connection.execute(
                "SELECT * FROM os_messages WHERE conversation_id=? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        if not row:
            raise KeyError(f"conversation_not_found:{conversation_id}")
        result = dict(row)
        result["active_context"] = decode(result.pop("active_context_json"), {})
        result["messages"] = []
        for item in messages:
            message = dict(item)
            message["metadata"] = decode(message.pop("metadata_json"), {})
            result["messages"].append(message)
        return result

    def latest_conversation(self, owner_id: str = "owner") -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute(
                "SELECT id FROM os_conversations WHERE owner_id=? AND status='ACTIVE' ORDER BY updated_at DESC LIMIT 1",
                (owner_id,),
            ).fetchone()
        return self.get_conversation(row["id"]) if row else self.create_conversation(owner_id=owner_id)

    def list_conversations(self, limit: int = 30) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT id, owner_id, title, status, created_at, updated_at FROM os_conversations ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def archive_conversation(self, conversation_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            cursor = connection.execute(
                "UPDATE os_conversations SET status='ARCHIVED', updated_at=? WHERE id=?",
                (utc_now(), conversation_id),
            )
            connection.commit()
        if not cursor.rowcount:
            raise KeyError(conversation_id)
        return self.get_conversation(conversation_id)

    def _persist_copilot_session(self, conversation_id: str, response: dict[str, Any]) -> None:
        session_id = str(response.get("session_id") or "").strip()
        if not session_id:
            return
        with connect(self.data_dir) as connection:
            connection.execute(
                "UPDATE os_conversations SET copilot_session_id=?, updated_at=? WHERE id=?",
                (session_id, utc_now(), conversation_id),
            )
            connection.commit()

    def create_creative(
        self,
        *,
        owner_id: str = "owner",
        title: str = "Untitled creative",
        idea: str = "",
        platform: str = "instagram_feed",
        platforms: list[str] | None = None,
        slide_count: int = 6,
    ) -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        now = utc_now()
        selected_platforms = platforms or ["facebook", "instagram"]
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_creatives VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT', '{}', '{}', '{}', ?, ?)",
                (
                    identifier, owner_id, title.strip() or "Untitled creative", idea.strip(),
                    platform, encode(selected_platforms), max(2, min(int(slide_count), 10)), now, now,
                ),
            )
            connection.commit()
        return self.get_creative(identifier)

    def get_creative(self, creative_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_creatives WHERE id=?", (creative_id,)).fetchone()
        if not row:
            raise KeyError(f"creative_not_found:{creative_id}")
        result = dict(row)
        for key in ("platforms_json", "package_json", "preflight_json", "schedule_json"):
            result[key[:-5]] = decode(result.pop(key), [] if key == "platforms_json" else {})
        return result

    def list_creatives(self, *, owner_id: str = "owner", limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT id FROM os_creatives WHERE owner_id=? ORDER BY updated_at DESC LIMIT ?",
                (owner_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [self.get_creative(str(row["id"])) for row in rows]

    @staticmethod
    def _generation_controls(values: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
        supplied = values if isinstance(values, dict) else {}
        controls: dict[str, dict[str, str]] = {}
        for field in GENERATION_CONTROL_FIELDS:
            candidate = supplied.get(field)
            if isinstance(candidate, dict):
                mode = str(candidate.get("mode") or "AUTO").upper()
                value = str(candidate.get("value") or "").strip()
            else:
                value = str(candidate or "").strip()
                mode = "CUSTOM" if value else "AUTO"
            controls[field] = {"mode": "CUSTOM" if mode == "CUSTOM" else "AUTO", "value": value if mode == "CUSTOM" else ""}
        return controls

    def create_generation_request(
        self,
        *,
        owner_id: str = "owner",
        start_date: str | None = None,
        days: int = 30,
        control_mode: str = "AI_DECIDE",
        guidance: str = "",
        controls: dict[str, Any] | None = None,
        day_overrides: dict[str, Any] | None = None,
        production_window_days: int = 30,
        rolling_production: bool = False,
    ) -> dict[str, Any]:
        horizon_days = int(days)
        if horizon_days < 1 or horizon_days > 365:
            raise ValueError("generation_horizon_must_be_between_1_and_365_days")
        mode = str(control_mode or "AI_DECIDE").upper()
        if mode not in {"AI_DECIDE", "GUIDE_AI", "CUSTOMIZE"}:
            raise ValueError("unsupported_generation_control_mode")
        first = date.fromisoformat(start_date) if start_date else date.today()
        last = first + timedelta(days=horizon_days - 1)
        request_controls = self._generation_controls(controls)
        overrides = day_overrides if isinstance(day_overrides, dict) else {}
        from content_plan_120 import build_120_day_plan

        planned_entries: dict[str, dict[str, Any]] = {}
        chunk_start = first
        remaining = horizon_days
        while remaining:
            chunk_days = min(120, remaining)
            chunk = build_120_day_plan(data_dir=self.data_dir, start_date=chunk_start.isoformat(), days=chunk_days)
            planned_entries.update({str(entry["date"]): entry for entry in chunk.get("entries", []) if isinstance(entry, dict)})
            chunk_start += timedelta(days=chunk_days)
            remaining -= chunk_days
        day_cards = []
        for offset in range(horizon_days):
            current = first + timedelta(days=offset)
            supplied_day = overrides.get(current.isoformat()) if isinstance(overrides.get(current.isoformat()), dict) else {}
            day_controls = self._generation_controls(supplied_day.get("controls"))
            frequency = supplied_day.get("frequency") if isinstance(supplied_day.get("frequency"), dict) else {"mode": "AUTO", "value": ""}
            frequency_mode = "CUSTOM" if str(frequency.get("mode") or "AUTO").upper() == "CUSTOM" else "AUTO"
            frequency_value = str(frequency.get("value") or "") if frequency_mode == "CUSTOM" else ""
            entry = planned_entries.get(current.isoformat(), {})
            requested_count = int(frequency_value) if frequency_value.isdigit() else None
            auto_count = 0 if current.weekday() in {0, 3} else 2 if current.day == 1 else 1
            post_count = max(0, min(requested_count if requested_count is not None else auto_count, 3))
            posts = []
            for post_index in range(post_count):
                title = str(entry.get("title") or entry.get("hook") or f"Infenergy opportunity for {current.strftime('%A')}")
                posts.append({
                    "id": f"{current.isoformat()}-{post_index + 1}",
                    "concept": title if post_index == 0 else f"Platform follow-up: {title}",
                    "content_type": day_controls["content_type"]["value"] if day_controls["content_type"]["mode"] == "CUSTOM" else str(entry.get("post_type_label") or "AI selected"),
                    "format": day_controls["format"]["value"] if day_controls["format"]["mode"] == "CUSTOM" else str(entry.get("format_label") or "AI selected"),
                    "platforms": day_controls["platform"]["value"] if day_controls["platform"]["mode"] == "CUSTOM" else str(entry.get("primary_platform") or "AI selected per channel"),
                    "campaign": day_controls["campaign"]["value"] if day_controls["campaign"]["mode"] == "CUSTOM" else str(entry.get("weekly_arc") or "AI selected"),
                    "status": "PLANNED",
                    "generation_contract": entry,
                })
            day_cards.append({
                "date": current.isoformat(),
                "status": "PLANNED",
                "frequency": {
                    "mode": frequency_mode,
                    "value": frequency_value,
                },
                "controls": day_controls,
                "posts": posts,
            })
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_generation_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PLANNED', ?, ?)",
                (
                    identifier, owner_id, first.isoformat(), last.isoformat(), horizon_days, mode,
                    guidance.strip(), encode(request_controls), encode(day_cards),
                    max(1, min(int(production_window_days), horizon_days)), int(bool(rolling_production)), now, now,
                ),
            )
            connection.commit()
        return self.get_generation_request(identifier)

    def get_generation_request(self, request_id: str) -> dict[str, Any]:
        with connect(self.data_dir) as connection:
            row = connection.execute("SELECT * FROM os_generation_requests WHERE id=?", (request_id,)).fetchone()
        if not row:
            raise KeyError(f"generation_request_not_found:{request_id}")
        result = dict(row)
        result["controls"] = decode(result.pop("controls_json"), {})
        result["day_cards"] = decode(result.pop("day_cards_json"), [])
        result["rolling_production"] = bool(result["rolling_production"])
        return result

    def list_generation_requests(self, *, owner_id: str = "owner", limit: int = 20) -> list[dict[str, Any]]:
        with connect(self.data_dir) as connection:
            rows = connection.execute(
                "SELECT id FROM os_generation_requests WHERE owner_id=? ORDER BY updated_at DESC LIMIT ?",
                (owner_id, max(1, min(int(limit), 100))),
            ).fetchall()
        return [self.get_generation_request(str(row["id"])) for row in rows]

    def update_generation_day(self, request_id: str, day_date: str, updates: dict[str, Any]) -> dict[str, Any]:
        request = self.get_generation_request(request_id)
        cards = request["day_cards"]
        matching = next((card for card in cards if card.get("date") == day_date), None)
        if not matching:
            raise KeyError(f"generation_day_not_found:{day_date}")
        controls = self._generation_controls(updates.get("controls", matching.get("controls")))
        supplied_frequency = updates.get("frequency", matching.get("frequency", {}))
        if not isinstance(supplied_frequency, dict):
            supplied_frequency = {}
        frequency_mode = "CUSTOM" if str(supplied_frequency.get("mode") or "AUTO").upper() == "CUSTOM" else "AUTO"
        frequency_value = str(supplied_frequency.get("value") or "") if frequency_mode == "CUSTOM" else ""
        if frequency_value and (not frequency_value.isdigit() or int(frequency_value) > 3):
            raise ValueError("generation_day_frequency_must_be_between_0_and_3")
        requested_count = int(frequency_value) if frequency_value else None
        auto_count = len(matching.get("posts", []))
        post_count = requested_count if requested_count is not None else auto_count
        existing_posts = matching.get("posts", [])
        base = existing_posts[0] if existing_posts else {
            "concept": f"Infenergy opportunity for {date.fromisoformat(day_date).strftime('%A')}",
            "content_type": "AI selected", "format": "AI selected", "platforms": "AI selected per channel",
            "campaign": "AI selected", "status": "PLANNED", "generation_contract": {},
        }
        posts = []
        for index in range(post_count):
            source = existing_posts[index] if index < len(existing_posts) else base
            posts.append({
                **source,
                "id": f"{day_date}-{index + 1}",
                "concept": source.get("concept") if index == 0 else f"Platform follow-up: {base.get('concept')}",
                "content_type": controls["content_type"]["value"] if controls["content_type"]["mode"] == "CUSTOM" else source.get("content_type", "AI selected"),
                "format": controls["format"]["value"] if controls["format"]["mode"] == "CUSTOM" else source.get("format", "AI selected"),
                "platforms": controls["platform"]["value"] if controls["platform"]["mode"] == "CUSTOM" else source.get("platforms", "AI selected per channel"),
                "campaign": controls["campaign"]["value"] if controls["campaign"]["mode"] == "CUSTOM" else source.get("campaign", "AI selected"),
            })
        matching.update({"frequency": {"mode": frequency_mode, "value": frequency_value}, "controls": controls, "posts": posts})
        with connect(self.data_dir) as connection:
            connection.execute(
                "UPDATE os_generation_requests SET day_cards_json=?, updated_at=? WHERE id=?",
                (encode(cards), utc_now(), request_id),
            )
            connection.commit()
        return self.get_generation_request(request_id)

    def update_creative(self, creative_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_creative(creative_id)
        title = str(updates.get("title", current["title"])).strip() or "Untitled creative"
        idea = str(updates.get("idea", current["idea"])).strip()
        platform = str(updates.get("platform", current["platform"])).strip() or "instagram_feed"
        platforms = updates.get("platforms", current["platforms"])
        if not isinstance(platforms, list) or not platforms:
            raise ValueError("at_least_one_platform_required")
        slide_count = int(updates.get("slide_count", current["slide_count"]))
        if slide_count < 2 or slide_count > 10:
            raise ValueError("slide_count_must_be_between_2_and_10")
        with connect(self.data_dir) as connection:
            connection.execute(
                """
                UPDATE os_creatives
                SET title=?, idea=?, platform=?, platforms_json=?, slide_count=?, updated_at=?
                WHERE id=?
                """,
                (title, idea, platform, encode(platforms), slide_count, utc_now(), creative_id),
            )
            connection.commit()
        return self.get_creative(creative_id)

    def prepare_and_schedule_creative(
        self,
        creative_id: str,
        *,
        content_date: str,
        scheduled_at: str,
        slot: str = "midday",
        actor: str = "owner",
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        creative = self.get_creative(creative_id)
        if not creative["idea"].strip():
            raise ValueError("creative_idea_required")
        generated = self.execute_capability(
            "creative.carousel.generate",
            {
                "objective": creative["idea"],
                "title": creative["title"],
                "platform": creative["platform"],
                "platforms": creative["platforms"],
                "slide_count": creative["slide_count"],
            },
            actor=actor,
            operation_id=f"creative-generate:{creative_id}:{uuid.uuid4().hex}",
        )
        package = generated["result"]["package"]
        assets = package.get("carousel_assets", [])
        missing_assets = [item for item in assets if not str(item.get("local_path", "")).strip()]
        captions = [str(package.get(key, "")).strip() for key in ("fb_caption", "ig_caption", "li_text")]
        from score_content import score_content
        evaluation = score_content(package, creative["platforms"])
        preflight = {
            "passed": len(assets) == creative["slide_count"] and not missing_assets and any(captions),
            "checks": {
                "requested_slide_count": len(assets) == creative["slide_count"],
                "assets_rendered": not missing_assets,
                "platform_copy_present": any(captions),
            },
            "quality": evaluation,
        }
        if not preflight["passed"]:
            with connect(self.data_dir) as connection:
                connection.execute(
                    "UPDATE os_creatives SET status='PREFLIGHT_FAILED', package_json=?, preflight_json=?, updated_at=? WHERE id=?",
                    (encode(package), encode(preflight), utc_now(), creative_id),
                )
                connection.commit()
            raise ValueError("creative_preflight_failed")
        schedule_request = {
            "content_date": content_date,
            "scheduled_at": scheduled_at,
            "slot": slot,
            "package": package,
            "platforms": creative["platforms"],
            "replace_existing": replace_existing,
            "rationale": f"Owner approved creative: {creative['title']}",
        }
        scheduling = self.execute_capability("social.schedule", schedule_request, actor=actor)
        if scheduling.get("status") == "WAITING_APPROVAL":
            approved = self.approve_and_execute(
                str(scheduling["approval_id"]), actor=actor,
                note="Owner clicked Run checks, approve & schedule in Creative Studio",
            )
            scheduling = approved["execution"]
        if scheduling.get("status") != "COMPLETED":
            raise ValueError(f"creative_schedule_failed:{scheduling.get('status', 'unknown')}")
        schedule = {
            "content_date": content_date,
            "scheduled_at": scheduled_at,
            "slot": slot,
            "platforms": creative["platforms"],
            "outbox_id": scheduling["result"].get("outbox_id"),
            "decision_id": scheduling["result"].get("decision_id"),
        }
        with connect(self.data_dir) as connection:
            connection.execute(
                """
                UPDATE os_creatives
                SET status='SCHEDULED', package_json=?, preflight_json=?, schedule_json=?, updated_at=?
                WHERE id=?
                """,
                (encode(package), encode(preflight), encode(schedule), utc_now(), creative_id),
            )
            connection.commit()
        return {"creative": self.get_creative(creative_id), "preflight": preflight, "scheduling": scheduling}

    def execute_capability(
        self,
        capability: str,
        arguments: dict[str, Any],
        *,
        actor: str = "owner",
        dry_run: bool = False,
        operation_id: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        return self.transactions.execute(
            capability, arguments, actor=actor, dry_run=dry_run,
            operation_id=operation_id, approval_id=approval_id,
        )

    def approve_and_execute(self, approval_id: str, *, actor: str = "owner", note: str = "Owner approved and executed") -> dict[str, Any]:
        approval = self.policies.get_approval(approval_id)
        if approval["actor"] != actor:
            raise ValueError("approval_actor_mismatch")
        if approval["status"] == "PENDING":
            self.policies.decide_approval(approval_id, approved=True, decided_by=actor, note=note)
        elif approval["status"] not in {"APPROVED", "CONSUMED"}:
            raise ValueError(f"approval_not_executable:{approval['status']}")
        result = self.execute_capability(
            approval["capability"], approval["request"], actor=actor,
            approval_id=approval_id, operation_id=f"approval:{approval_id}",
        )
        if approval["status"] == "CONSUMED" and not result.get("idempotent_replay"):
            raise ValueError("consumed_approval_transaction_missing")
        if result.get("status") in {"COMPLETED", "DRY_RUN_COMPLETE"}:
            if approval["status"] != "CONSUMED":
                self.policies.consume_approval(approval_id)
            self.policies.supersede_pending(
                capability=approval["capability"], actor=actor, except_id=approval_id,
            )
        return {"approval": self.policies.get_approval(approval_id), "execution": result}

    def command(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        actor: str = "owner",
    ) -> dict[str, Any]:
        conversation = self.get_conversation(conversation_id) if conversation_id else self.latest_conversation(actor)
        from social.command_center import is_flagship_creative_command
        if is_flagship_creative_command(message):
            self._message(conversation["id"], "user", message)
            execution = self.execute_capability(
                "creative.command.produce",
                {"command": message},
                actor=actor,
                operation_id=f"creative-command:{uuid.uuid4().hex}",
            )
            if execution.get("status") == "WAITING_APPROVAL":
                content = "Creative production is waiting for the required owner approval. No generation or delivery is being claimed."
                self._message(conversation["id"], "assistant", content, execution)
                return {
                    "status": "WAITING_APPROVAL",
                    "conversation_id": conversation["id"],
                    "message": content,
                    "approval_id": execution.get("approval_id"),
                    "execution": execution,
                }
            result = execution.get("result", {})
            production_status = str(result.get("production_status") or execution.get("status") or "")
            asset_count = int(result.get("asset_count") or len(result.get("assets", [])))
            if production_status == "DELIVERED":
                content = f"Produced and validated {asset_count} finished asset{'s' if asset_count != 1 else ''}. The deliverable is ready for review; scheduling and publishing were not performed."
            else:
                content = f"Creative production status: {production_status}. {result.get('failure') or result.get('next_action') or 'No finished deliverable is being claimed.'}"
            self._message(conversation["id"], "assistant", content, execution)
            return {
                "status": production_status,
                "conversation_id": conversation["id"],
                "message": content,
                "execution": execution,
                "creative": result,
            }
        pending = self.policies.list_approvals(actor=actor, status="PENDING", limit=1)
        if pending and self._is_approval_intent(message):
            self._message(conversation["id"], "user", message)
            approved = self.approve_and_execute(pending[0]["id"], actor=actor, note="Natural-language owner approval")
            job = approved["execution"].get("result", {}).get("job")
            if isinstance(job, dict) and job.get("status") != "COMPLETED":
                return self.continue_approved_job(conversation["id"], approved, actor)
            content = self._approval_result_message(approved)
            self._message(conversation["id"], "assistant", content, approved)
            return {
                "status": approved["execution"].get("status", "COMPLETED"),
                "conversation_id": conversation["id"], "message": content,
                "approval": approved["approval"], "execution": approved["execution"],
            }
        prompt = self._command_prompt(message, conversation, actor)
        self._message(conversation["id"], "user", message)
        try:
            response = asyncio.run(
                self.master.converse(
                    prompt,
                    session_id=conversation["copilot_session_id"],
                    system_message=MASTER_PROMPT + "\nAvailable capabilities:\n" + self.registry.semantic_catalog(),
                    tools=self._copilot_tools(actor),
                )
            )
            content = response["content"]
            self._persist_copilot_session(conversation["id"], response)
            self._message(conversation["id"], "assistant", content, response)
            self.audit.record(
                actor=actor, model_or_tool=response["model"], action="MASTER_RESPONSE",
                status="COMPLETED", result={"conversation_id": conversation["id"]},
            )
            return {"status": "COMPLETED", "conversation_id": conversation["id"], "message": content, "model": response["model"]}
        except TimeoutError:
            content = (
                "The operation exceeded its execution window before a verified result was available. "
                "No completion is being claimed. Your objective and conversation context are preserved; "
                "send “continue” to resume from the recorded state."
            )
            self._message(conversation["id"], "assistant", content, {"timed_out": True})
            self.audit.record(
                actor=actor, model_or_tool="github-copilot-sdk", action="MASTER_RESPONSE_TIMEOUT",
                status="TIMED_OUT", result={"conversation_id": conversation["id"]},
            )
            return {"status": "TIMED_OUT", "conversation_id": conversation["id"], "message": content}
        except MasterModelUnavailable as exc:
            status = exc.status.__dict__
            content = (
                f"Master intelligence is unavailable: {status['reason']}. "
                f"Configured model: {status['configured_model']}. "
                f"Actual available models: {[item.get('id') for item in status['available_models']]}. "
                "No strategic-model downgrade was performed."
            )
            self._message(conversation["id"], "assistant", content, {"blocked": True, "model_status": status})
            self.audit.record(
                actor=actor, model_or_tool="github-copilot-sdk", action="MASTER_RESPONSE_BLOCKED",
                status="BLOCKED", result=status,
            )
            return {"status": "BLOCKED", "conversation_id": conversation["id"], "message": content, "model_status": status}

    @staticmethod
    def _is_approval_intent(message: str) -> bool:
        normalized = re.sub(r"[^a-z0-9 ]", " ", message.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return bool(re.search(r"\b(approve|approved|i approve|yes proceed|go ahead|start building|proceed)\b", normalized))

    @staticmethod
    def _approval_result_message(approved: dict[str, Any]) -> str:
        approval = approved["approval"]
        execution = approved["execution"]
        transaction_id = execution.get("transaction_id", "not recorded")
        result = execution.get("result", {})
        job = result.get("job") if isinstance(result, dict) else None
        if isinstance(job, dict):
            return (
                f"Approved and executed **{approval['capability']}** exactly once. "
                f"Durable job `{job.get('id')}` now exists with status **{job.get('status')}** "
                f"and {len(job.get('steps', []))} tracked steps. Transaction: `{transaction_id}`. "
                "This confirms the job was created; it does not claim unfinished deliverables are complete."
            )
        return (
            f"Approved and executed **{approval['capability']}** exactly once. "
            f"Status: **{execution.get('status')}**. Transaction: `{transaction_id}`."
        )

    def continue_approved_job(self, conversation_id: str, approved: dict[str, Any], actor: str = "owner") -> dict[str, Any]:
        execution = approved["execution"]
        job = execution["result"]["job"]
        request = (
            f"Owner approval {approved['approval']['id']} was consumed and created durable job {job['id']} "
            f"for capability {approved['approval']['capability']}. Continue autonomously now. Produce the actual requested "
            "deliverables—not another plan or promise—then persist them with jobs.complete. If available tools genuinely "
            "cannot produce a required artifact, complete everything they can and name only the exact external blocker."
        )
        conversation = self.get_conversation(conversation_id)
        prompt = self._command_prompt(request, conversation, actor)
        try:
            response = asyncio.run(self.master.converse(
                prompt, session_id=conversation["copilot_session_id"],
                system_message=MASTER_PROMPT + "\nAvailable capabilities:\n" + self.registry.semantic_catalog(),
                tools=self._copilot_tools(actor),
            ))
            content = response["content"]
            self._persist_copilot_session(conversation_id, response)
            self._message(conversation_id, "assistant", content, {**response, "continued_after_approval": True})
            return {
                "status": "COMPLETED", "conversation_id": conversation_id,
                "message": content, "model": response["model"],
                "approval": approved["approval"], "execution": execution,
            }
        except TimeoutError:
            content = self._approval_result_message(approved) + " Continuation is still recorded in the durable job."
            self._message(conversation_id, "assistant", content, {"timed_out": True, "continued_after_approval": True})
            return {"status": "TIMED_OUT", "conversation_id": conversation_id, "message": content, "approval": approved["approval"], "execution": execution}
        except Exception as exc:
            content = (
                self._approval_result_message(approved)
                + " Automatic continuation could not start, but the approval succeeded and the durable job was not lost. "
                "Send `continue` to resume this same job."
            )
            self._message(
                conversation_id, "assistant", content,
                {"continuation_error": f"{type(exc).__name__}: {exc}", "continued_after_approval": True},
            )
            return {
                "status": "CONTINUATION_FAILED", "conversation_id": conversation_id,
                "message": content, "approval": approved["approval"], "execution": execution,
                "continuation_error": f"{type(exc).__name__}: {exc}",
            }

    def dispatch_approved_job_continuation(
        self, conversation_id: str, approved: dict[str, Any], actor: str = "owner",
    ) -> None:
        threading.Thread(
            target=self.continue_approved_job,
            args=(conversation_id, approved, actor),
            name=f"approved-job-{approved['approval']['id'][:8]}",
            daemon=True,
        ).start()

    def _command_prompt(self, message: str, conversation: dict[str, Any], actor: str) -> str:
        messages = conversation.get("messages", [])[-20:]
        transcript_parts = []
        total_chars = 0
        for item in reversed(messages):
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            content = content[-4000:]
            entry = f"{str(item.get('role', 'unknown')).upper()}: {content}"
            if total_chars + len(entry) > 24000:
                break
            transcript_parts.append(entry)
            total_chars += len(entry)
        transcript = "\n\n".join(reversed(transcript_parts)) or "No prior messages in this session."
        operating_context = self._operating_context(actor)
        return (
            "CONTINUING DURABLE INFENERGY SESSION\n"
            "Treat the transcript as authoritative conversational context. Continue the owner's existing objective; "
            "do not restart discovery or ask for details already supplied.\n\n"
            f"RECENT CONVERSATION\n{transcript}\n\n"
            f"CURRENT OPERATING STATE\n{json.dumps(operating_context, ensure_ascii=False, default=str)}\n\n"
            f"CURRENT OWNER REQUEST\n{message}\n\n"
            "Now take the next useful actions with tools and return the verified outcome, a pending approval, or one genuine blocker."
        )

    def _operating_context(self, actor: str) -> dict[str, Any]:
        jobs = self.jobs.list(10)
        with connect(self.data_dir) as connection:
            approval_rows = connection.execute(
                """
                SELECT id, capability, status, created_at, decided_at
                FROM os_approvals WHERE actor=?
                ORDER BY created_at DESC LIMIT 10
                """,
                (actor,),
            ).fetchall()
        return {
            "active_jobs": [
                {
                    "id": item.get("id"),
                    "type": item.get("job_type"),
                    "objective": item.get("objective"),
                    "status": item.get("status"),
                    "progress": item.get("progress"),
                    "current_step": item.get("current_step"),
                    "updated_at": item.get("updated_at"),
                }
                for item in jobs
                if item.get("status") not in {"COMPLETED", "CANCELED"}
            ],
            "recent_approvals": [dict(row) for row in approval_rows],
            "open_attention_count": len(self.attention.list_open(10)),
            "instruction": "Continue existing work when it matches the owner's request; do not invent a paused job.",
        }

    def executive_state(self) -> dict[str, Any]:
        health = self.execute_capability("system.health", {}, operation_id=f"state-health-{uuid.uuid4().hex}")
        automations = AutomationService(self.data_dir)
        return {
            "time_utc": utc_now(),
            "health": health.get("result", {}),
            "attention": self.attention.list_open(10),
            "approvals": self.policies.list_approvals(actor="owner", limit=20),
            "jobs": self.jobs.list(20),
            "policies": self.policies.list_policies(),
            "recent_events": self.events.list(20),
            "recent_activity": self.audit.list(20),
            "research_findings": ResearchIntelligence(self.data_dir).list_findings(20),
            "automations": automations.list(),
            "automation_runs": automations.list_runs(20),
            "watches": automations.list_watches(),
            "conversation": self.latest_conversation(),
        }

    def _copilot_tools(self, actor: str) -> list[Any]:
        from copilot import Tool
        from copilot.tools import ToolResult

        tools = []
        for descriptor in self.registry.list():
            capability_id = descriptor["id"]

            async def handler(invocation: Any, capability_id: str = capability_id) -> ToolResult:
                try:
                    payload = dict(invocation.arguments or {})
                    dry_run = bool(payload.pop("dry_run", False))
                    approval_id = payload.pop("approval_id", None)
                    result = self.execute_capability(
                        capability_id, payload, actor=actor, dry_run=dry_run,
                        approval_id=approval_id,
                    )
                    return ToolResult(
                        text_result_for_llm=json.dumps(result, ensure_ascii=False, default=str),
                        result_type="success",
                    )
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    return ToolResult(text_result_for_llm=error, result_type="failure", error=error)

            schema = dict(descriptor["input_schema"])
            properties = dict(schema.get("properties", {}))
            properties.update({
                "dry_run": {"type": "boolean", "description": "Preview without mutation."},
                "approval_id": {"type": "string", "description": "Owner-approved request identifier."},
            })
            schema["properties"] = properties
            tools.append(Tool(
                name=capability_id.replace(".", "_"),
                description=descriptor["description"], parameters=schema,
                handler=handler, skip_permission=True,
                metadata={"capability_id": capability_id, "risk_level": descriptor["risk_level"]},
            ))
        return tools

    def _message(self, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> str:
        identifier = uuid.uuid4().hex
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                "INSERT INTO os_messages VALUES (?, ?, ?, ?, ?, ?)",
                (identifier, conversation_id, role, content, encode(metadata or {}), now),
            )
            connection.execute("UPDATE os_conversations SET updated_at=? WHERE id=?", (now, conversation_id))
            connection.commit()
        return identifier