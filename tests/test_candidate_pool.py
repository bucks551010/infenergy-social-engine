import os
import sys
from datetime import datetime, timedelta, timezone


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from social.candidate_pool import CandidatePool, build_rotation_ledger, select_least_recently_used
import run_engine


def test_rotation_prefers_eligible_least_recently_used():
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    history = {
        "posts": [
            {"status": "success", "product_id": "recent", "run_started_at_utc": (now - timedelta(days=1)).isoformat()},
            {"status": "success", "product_id": "older", "run_started_at_utc": (now - timedelta(days=10)).isoformat()},
        ]
    }
    ledger = build_rotation_ledger(history, {"product_feature_days": 7, "topic_days": 21, "hook_days": 60}, now=now)

    selected, telemetry = select_least_recently_used(
        [{"product_id": "recent"}, {"product_id": "older"}, {"product_id": "unused"}],
        "product_id",
        ledger,
        now=now,
    )

    assert selected == {"product_id": "unused"}
    assert telemetry["selection_reason"] == "eligible_lru"
    assert telemetry["excluded_count"] == 1


def test_rotation_falls_back_when_entire_pool_is_in_cooldown():
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    history = {
        "posts": [
            {"status": "success", "topic": "newer", "run_started_at_utc": (now - timedelta(days=1)).isoformat()},
            {"status": "success", "topic": "older", "run_started_at_utc": (now - timedelta(days=2)).isoformat()},
        ]
    }
    ledger = build_rotation_ledger(history, {"product_feature_days": 7, "topic_days": 21, "hook_days": 60}, now=now)

    selected, telemetry = select_least_recently_used(
        [{"topic": "newer"}, {"topic": "older"}], "topic", ledger, now=now
    )

    assert selected == {"topic": "older"}
    assert telemetry["rotation_exhausted"] is True


def test_candidate_pool_expires_and_consumes(tmp_path):
    pool = CandidatePool(str(tmp_path), ttl_days=7)
    candidate = pool.add({"post_id": "post-1"}, rotation={"topic": "Topic"}, batch_gate_results={"passed": True})

    assert pool.depth() == 1
    assert pool.consume(candidate["candidate_id"]) is True
    assert pool.depth() == 0


def test_failed_pooled_candidate_is_quarantined_before_fresh_retry(tmp_path):
    pool = CandidatePool(str(tmp_path))
    candidate = pool.add({"post_id": "pooled-1"}, rotation={}, batch_gate_results={})

    quarantined = run_engine._quarantine_failed_pooled_candidate(
        pool,
        {"candidate_id": candidate["candidate_id"]},
        reason="duplicate_exact_caption_within_window",
    )

    assert quarantined is True
    assert pool.available() == []