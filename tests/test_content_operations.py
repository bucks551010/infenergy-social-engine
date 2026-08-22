from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from content_operations import (  # noqa: E402
    archive_candidate,
    begin_platform_transaction,
    claim_due,
    complete_platform_transaction,
    content_detail,
    create_council_session,
    daily_status,
    daily_markdown,
    ensure_daily_slots,
    init_content_operations,
    mark_ready,
    mark_slot_external_action,
    operations_readiness,
    reconcile_ready_inventory,
    reconcile_stale_claims,
    upcoming_ready_packages,
    update_ready_package,
)


def _schedule(day: str) -> dict[str, str]:
    return {
        "morning": f"{day}T13:00:00+00:00",
        "midday": f"{day}T17:00:00+00:00",
        "evening": f"{day}T23:00:00+00:00",
    }


def test_daily_slots_outbox_and_archive_survive_restart(tmp_path):
    day = "2026-08-19"
    data_dir = str(tmp_path)
    init_content_operations(data_dir)
    slots = ensure_daily_slots(data_dir, day, _schedule(day), {"mode": "owner_schedule"})
    assert [slot["slot"] for slot in slots] == ["morning", "midday", "evening"]

    decision_id = create_council_session(
        data_dir,
        content_date=day,
        slot="morning",
        blackboard={
            "human_reality": "A household decides what must keep working first.",
            "brain": {"before": "buy more", "movement": "prioritize", "after": "match needs"},
            "heart": {"response": "clarity", "after": "calm capability"},
            "content_job": "HELP_PLAN",
        },
        rationale=["Preparedness starts with priorities, not purchases."],
    )
    for ordinal in range(1, 8):
        archive_candidate(
            data_dir,
            decision_id=decision_id,
            ordinal=ordinal,
            content={"post_id": f"candidate-{ordinal}", "master_copy": f"Draft {ordinal}"},
            status="SELECTED" if ordinal == 4 else "NOT_SELECTED",
            score=90 + ordinal,
            loss_reasons=[] if ordinal == 4 else ["lower_ranked_compliant_candidate"],
        )

    package = {
        "content_id": "candidate-4",
        "master_copy": "Final copy",
        "platform_presentations": {
            "facebook": {"final_caption": "Facebook final\n\nSecond paragraph"},
            "instagram": {"final_caption": "Instagram final\n\nSecond paragraph"},
            "linkedin": {"final_caption": "LinkedIn final\n\nSecond paragraph"},
        },
        "media_asset": {"status": "READY", "role": "FINAL_SOCIAL_CREATIVE"},
    }
    outbox_id = mark_ready(
        data_dir,
        content_date=day,
        slot="morning",
        scheduled_at=_schedule(day)["morning"],
        decision_id=decision_id,
        package=package,
    )

    # Reinitialize against the same SQLite file to simulate a process restart.
    init_content_operations(data_dir)
    status = daily_status(data_dir, day)
    assert status["required"] == 3
    assert status["ready"] == 1
    assert status["missing"] == 2
    detail = content_detail(data_dir, decision_id)
    assert len(detail["candidates"]) == 7
    assert detail["candidates"][3]["status"] == "SELECTED"

    claimed = claim_due(data_dir, "2026-08-19T13:00:01+00:00")
    assert claimed and claimed["outbox_id"] == outbox_id
    assert claimed["package"]["platform_presentations"]["instagram"]["final_caption"].count("\n\n") == 1
    assert claim_due(data_dir, "2026-08-19T13:00:02+00:00") is None


def test_pregeneration_updates_only_unclaimed_ready_package(tmp_path):
    day = "2026-08-19"
    data_dir = str(tmp_path)
    ensure_daily_slots(data_dir, day, _schedule(day), {"mode": "owner_schedule"})
    decision_id = create_council_session(
        data_dir,
        content_date=day,
        slot="morning",
        blackboard={"content_job": "TEACH"},
    )
    outbox_id = mark_ready(
        data_dir,
        content_date=day,
        slot="morning",
        scheduled_at=_schedule(day)["morning"],
        decision_id=decision_id,
        package={"content_id": "content-1", "generation": "pending"},
    )

    rows = upcoming_ready_packages(data_dir, before_utc="2026-08-20T00:00:00+00:00")
    assert [row["outbox_id"] for row in rows] == [outbox_id]
    assert update_ready_package(data_dir, outbox_id, {"content_id": "content-1", "generation": "complete"}) is True

    claimed = claim_due(data_dir, "2026-08-19T13:00:01+00:00")
    assert claimed["package"]["generation"] == "complete"
    assert update_ready_package(data_dir, outbox_id, {"content_id": "overwritten"}) is False


def test_platform_transaction_states_are_idempotent_and_persistent(tmp_path):
    day = date(2026, 8, 19)
    data_dir = str(tmp_path)
    ensure_daily_slots(data_dir, day, _schedule(day.isoformat()), {"platforms": ["facebook"]})
    decision_id = create_council_session(
        data_dir,
        content_date=day.isoformat(),
        slot="morning",
        blackboard={"content_job": "TEACH"},
    )
    outbox_id = mark_ready(
        data_dir,
        content_date=day.isoformat(),
        slot="morning",
        scheduled_at=_schedule(day.isoformat())["morning"],
        decision_id=decision_id,
        package={"content_id": "content-1"},
    )
    request_key = begin_platform_transaction(
        data_dir,
        outbox_id=outbox_id,
        platform="facebook",
        payload={"message": "Line one\n\nLine two"},
    )
    assert request_key == f"{outbox_id}:facebook"
    complete_platform_transaction(
        data_dir,
        outbox_id=outbox_id,
        platform="facebook",
        state="CONFIRMED_SUCCESS",
        external_id="fb-123",
        provider_response={"id": "fb-123"},
    )
    init_content_operations(data_dir)
    # A second begin reuses the same request key instead of creating another transaction.
    assert begin_platform_transaction(
        data_dir,
        outbox_id=outbox_id,
        platform="facebook",
        payload={"message": "Line one\n\nLine two"},
    ) == request_key


def test_restart_reopens_ready_package_without_routed_platform(tmp_path):
    day = "2026-08-20"
    data_dir = str(tmp_path)
    ensure_daily_slots(data_dir, day, _schedule(day), {"mode": "owner_schedule"})
    decision_id = create_council_session(
        data_dir,
        content_date=day,
        slot="morning",
        blackboard={"content_job": "TEACH"},
    )
    outbox_id = mark_ready(
        data_dir,
        content_date=day,
        slot="morning",
        scheduled_at=_schedule(day)["morning"],
        decision_id=decision_id,
        package={"content_id": "content-1", "routing": {"platforms": []}},
    )

    recovered = reconcile_ready_inventory(data_dir)
    status = daily_status(data_dir, day)

    assert recovered == [{"outbox_id": outbox_id, "reason": "ready_package_has_no_routed_platforms"}]
    assert status["slots"][0]["status"] == "RECOVERING"


def test_provider_outage_is_external_action_not_content_failure(tmp_path):
    day = "2026-08-20"
    data_dir = str(tmp_path)
    ensure_daily_slots(data_dir, day, _schedule(day), {"mode": "owner_schedule"})
    decision_id = create_council_session(
        data_dir,
        content_date=day,
        slot="evening",
        blackboard={"content_job": "TEACH", "final_copy": {"instagram": "Archived copy"}},
    )

    mark_slot_external_action(
        data_dir,
        content_date=day,
        slot="evening",
        decision_id=decision_id,
        error="gemini_monthly_spend_cap",
    )
    status = daily_status(data_dir, day)
    detail = content_detail(data_dir, decision_id)

    evening = next(slot for slot in status["slots"] if slot["slot"] == "evening")
    assert evening["status"] == "EXTERNAL_ACTION_REQUIRED"
    assert evening["last_error"] == "gemini_monthly_spend_cap"
    assert detail["status"] == "EXTERNAL_ACTION_REQUIRED"


def test_operations_readiness_detects_missing_package_before_clock(tmp_path):
    day = "2026-08-20"
    data_dir = str(tmp_path)
    ensure_daily_slots(data_dir, day, _schedule(day), {"mode": "owner_schedule"})

    readiness = operations_readiness(
        data_dir,
        now_utc=datetime(2026, 8, 20, 12, 30, tzinfo=timezone.utc),
        lead_hours=2,
        publisher_ready={"facebook": True, "instagram": True, "linkedin": True},
        dispatcher_active=True,
    )

    morning = next(slot for slot in readiness["slots"] if slot["slot"] == "morning")
    assert morning["late_for_readiness"] is True
    assert readiness["service_health"] == "HEALTHY"
    assert readiness["content_supply_health"] == "ACTION_REQUIRED"
    assert any(action["action"] == "RECOVER_OR_PULL_READY_RESERVE" for action in readiness["actions"])


def test_restart_recovers_stale_claim_without_external_transaction(tmp_path):
    day = "2026-08-20"
    data_dir = str(tmp_path)
    ensure_daily_slots(data_dir, day, _schedule(day), {"mode": "owner_schedule"})
    decision_id = create_council_session(data_dir, content_date=day, slot="morning", blackboard={"content_job": "TEACH"})
    outbox_id = mark_ready(
        data_dir,
        content_date=day,
        slot="morning",
        scheduled_at=_schedule(day)["morning"],
        decision_id=decision_id,
        package={"content_id": "content-1", "routing": {"platforms": ["facebook"]}},
    )
    claim_due(data_dir, "2026-08-20T13:00:01+00:00")

    recovered = reconcile_stale_claims(
        data_dir,
        now_utc=datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc),
        stale_minutes=15,
    )
    status = daily_status(data_dir, day)

    assert recovered == [{"outbox_id": outbox_id, "reason": "stale_claim_recovered_after_restart"}]
    assert status["slots"][0]["status"] == "READY"


def test_human_readable_daily_ledger_is_derived_from_canonical_records(tmp_path):
    day = "2026-08-20"
    data_dir = str(tmp_path)
    ensure_daily_slots(data_dir, day, _schedule(day), {"mode": "owner_schedule"})
    decision_id = create_council_session(
        data_dir,
        content_date=day,
        slot="morning",
        blackboard={"human_reality": "A household plans before pressure.", "brain": {"movement": "PRIORITIZE"}, "heart": {"after": "CLARITY"}, "content_job": "HELP_PLAN"},
    )
    archive_candidate(
        data_dir,
        decision_id=decision_id,
        ordinal=1,
        content={"post_id": "draft-1"},
        status="NOT_SELECTED",
        score=70,
        loss_reasons=["weaker premise"],
    )
    mark_ready(
        data_dir,
        content_date=day,
        slot="morning",
        scheduled_at=_schedule(day)["morning"],
        decision_id=decision_id,
        package={"content_id": "final-1", "topic": "Outage priorities", "routing": {"platforms": ["facebook"]}},
    )

    ledger = daily_markdown(data_dir, day)

    assert "INFENERGY CONTENT - 2026-08-20" in ledger
    assert "SLOT 1 - MORNING" in ledger
    assert "Human Reality: A household plans before pressure." in ledger
    assert "Candidate 1: NOT_SELECTED; why not selected: weaker premise" in ledger
