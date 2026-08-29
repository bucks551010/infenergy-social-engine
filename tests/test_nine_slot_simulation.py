from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import dispatch_outbox  # noqa: E402
from content_operations import (  # noqa: E402
    archive_candidate,
    claim_due,
    create_council_session,
    daily_status,
    ensure_daily_slots,
    init_content_operations,
    mark_ready,
    reconcile_stale_claims,
)


INJECTIONS = (
    "FIRST_PRODUCT_FAILURE",
    "UNSUPPORTED_OPTIONAL_CLAIM",
    "CENTRAL_RESEARCH_FAILURE",
    "LOW_QUALITY_FIRST_PREMISE",
    "DUPLICATE_ANGLE",
    "PACKSHOT_ONLY_FIRST_VISUAL",
    "IMAGE_PROVIDER_TIMEOUT",
    "PROCESS_RESTART_AND_STALE_LOCK",
    "ARCHIVE_WRITE_INTERRUPTION",
)


def _package(content_id: str, platform: str, injection: str) -> dict:
    caption = (
        f"A clear entry point for {injection.lower().replace('_', ' ')}.\n\n"
        "This recovered package keeps useful depth while using known-safe guidance.\n\n"
        "Review the plan before the clock.\n\n"
        "https://www.infenergypower.com\n\n#InfenergyPower #Preparedness"
    )
    return {
        "content_id": content_id,
        "post_id": content_id,
        "destination_url": "https://www.infenergypower.com",
        "fb_caption": caption,
        "ig_caption": caption,
        "li_text": caption,
        "routing": {"platforms": [platform], "policy": "simulation_owner_schedule"},
        "platform_posts": {
            platform: {
                "final_caption": caption,
                "destination_url": "https://www.infenergypower.com",
                "utm_url": f"https://www.infenergypower.com?utm_source={platform}",
                "final_caption_qa": {"status": "PRESENTATION_READY", "reasons": []},
            }
        },
        "generated_visuals": {
            platform: f"/data/generated_visuals/{content_id}_{platform}.png",
            "render_engines": {platform: "gemini"},
            "artifact_reviews": {platform: {"verdict": "PASS", "creative_classification": "GENERATED_CONCEPT"}},
        },
        "visual_plan": {"creative_route": "EDITORIAL_HUMAN_SCENE", "visual_thesis": "Human clarity before equipment."},
        "recovery": {"injected_condition": injection, "result": "CONTENT_RECOVERED"},
    }


def test_three_day_nine_slot_simulation_converges_with_failures_and_restarts(tmp_path):
    data_dir = str(tmp_path)
    start = datetime(2026, 8, 20, tzinfo=timezone.utc)
    outboxes: list[str] = []
    platforms = ("facebook", "instagram", "linkedin")

    for index, injection in enumerate(INJECTIONS):
        day_offset, slot_index = divmod(index, 3)
        day = (start + timedelta(days=day_offset)).date().isoformat()
        schedule = {
            "morning": f"{day}T13:00:00+00:00",
            "midday": f"{day}T17:00:00+00:00",
            "evening": f"{day}T23:00:00+00:00",
        }
        slot = ("morning", "midday", "evening")[slot_index]
        platform = platforms[slot_index]
        ensure_daily_slots(data_dir, day, schedule, {"platforms": [platform]})
        decision_id = create_council_session(
            data_dir,
            content_date=day,
            slot=slot,
            blackboard={
                "round_0_feasibility": {"injected_condition": injection, "decision": "CHANGE_BEFORE_FINAL"},
                "human_reality": f"A real person faces {injection.lower().replace('_', ' ')}.",
                "brain": {"before": "uncertain", "movement": "PLAN", "after": "clear next step"},
                "heart": {"response": "CLARITY", "after": "CAPABILITY"},
                "content_job": "HELP_PLAN",
                "recovery": {"owner": "RECOVERY_MANAGER", "result": "RECOVERED"},
            },
            rationale=[f"Recovered injected condition: {injection}"],
        )
        archive_candidate(
            data_dir,
            decision_id=decision_id,
            ordinal=1,
            content={"post_id": f"rejected-{index}", "injection": injection},
            status="NOT_SELECTED",
            score=60,
            loss_reasons=[injection],
        )
        final = _package(f"content-{index}", platform, injection)
        archive_candidate(
            data_dir,
            decision_id=decision_id,
            ordinal=2,
            content=final,
            status="SELECTED",
            score=95,
            loss_reasons=[],
        )
        outboxes.append(mark_ready(
            data_dir,
            content_date=day,
            slot=slot,
            scheduled_at=schedule[slot],
            decision_id=decision_id,
            package=final,
        ))
        if slot_index == 2:
            init_content_operations(data_dir)  # process restart between simulated days

    # Simulate a stale run lock/claim before dispatch and recover it after restart.
    claimed = claim_due(data_dir, "2026-08-20T13:00:01+00:00")
    assert claimed is not None
    recovered = reconcile_stale_claims(
        data_dir,
        now_utc=datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc),
        stale_minutes=15,
    )
    assert recovered[0]["reason"] == "stale_claim_recovered_after_restart"

    instagram_attempts = {"count": 0}

    def instagram_publish(*_args, **_kwargs):
        instagram_attempts["count"] += 1
        if instagram_attempts["count"] == 1:
            raise RuntimeError("injected provider timeout")
        return {"id": f"ig-{instagram_attempts['count']}"}

    with patch.object(dispatch_outbox.publish_facebook, "publish", side_effect=lambda *_args, **_kwargs: {"id": "fb-confirmed"}), \
        patch.object(dispatch_outbox.publish_instagram, "publish", side_effect=instagram_publish), \
        patch.object(dispatch_outbox.publish_linkedin, "publish", side_effect=lambda *_args, **_kwargs: {"id": "li-confirmed"}):
        for attempt in range(12):
            dispatch_outbox.dispatch_due(
                data_dir=data_dir,
                now_utc=(datetime(2026, 8, 23, tzinfo=timezone.utc) + timedelta(minutes=attempt)).isoformat(),
            )

    for day_offset in range(3):
        day = (start + timedelta(days=day_offset)).date().isoformat()
        status = daily_status(data_dir, day)
        assert status["published"] == 3
        assert status["missing"] == 0
        assert all(slot["status"] == "PUBLISHED" for slot in status["slots"])
    assert len(outboxes) == 9
