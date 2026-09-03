from __future__ import annotations

from datetime import datetime, timezone

from anti_repeat import check_duplicates


def test_same_consumer_moment_on_consecutive_day_is_blocked() -> None:
    now = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)
    history = {
        "posts": [
            {
                "date": "2026-09-03",
                "status": "published",
                "consumer_world_id": "work_trade",
                "consumer_moment_id": "last_signature_jobsite",
            }
        ]
    }
    result = check_duplicates(
        {
            "consumer_world_id": "work_trade",
            "consumer_moment_id": "last_signature_jobsite",
        },
        history,
        now_utc=now,
    )

    assert result["ok"] is False
    assert "duplicate_consumer_moment_on_consecutive_day" in result["reasons"]


def test_repeated_world_is_observed_without_blocking_a_fresh_moment() -> None:
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    history = {
        "posts": [
            {"date": "2026-09-03", "status": "published", "consumer_world_id": "family_home", "consumer_moment_id": "one"},
            {"date": "2026-09-05", "status": "published", "consumer_world_id": "family_home", "consumer_moment_id": "two"},
        ]
    }
    result = check_duplicates(
        {"consumer_world_id": "family_home", "consumer_moment_id": "three"},
        history,
        now_utc=now,
    )

    assert result["ok"] is True
    assert "consumer_world_saturated_within_week" in result["observed_reasons"]


def test_discovery_visual_and_product_pair_saturation_are_observed() -> None:
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    moment = {
        "useful_discovery": "Protect the final handoff first",
        "immediate_action": "Put the handoff beside the tool",
        "visual_evidence": ["labeled handoff card"],
    }
    history = {"posts": [{
        "date": "2026-09-05", "status": "published", "product_id": "P1",
        "consumer_moment_id": "handoff", "consumer_root": {"moment": moment},
    }]}
    result = check_duplicates({
        "product_id": "P1", "consumer_moment_id": "handoff", "consumer_root": {"moment": moment},
    }, history, now_utc=now)

    assert "consumer_useful_discovery_saturated_within_window" in result["observed_reasons"]
    assert "consumer_visual_evidence_saturated_within_window" in result["observed_reasons"]
    assert "consumer_product_moment_pair_saturated_within_window" in result["observed_reasons"]