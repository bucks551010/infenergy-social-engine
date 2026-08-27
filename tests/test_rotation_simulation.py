import os
import sys
from datetime import datetime, timedelta, timezone
import json


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from social.candidate_pool import build_rotation_ledger, select_least_recently_used
from social.product_eligibility import filter_evidence_eligible_products
from anti_repeat import check_duplicates


def test_twenty_one_slots_rotate_without_blocking_or_image_waste():
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    history = {"posts": []}
    windows = {"product_feature_days": 7, "topic_days": 21, "hook_days": 60}
    products = [{"product_id": f"product-{index}"} for index in range(35)]
    topics = [{"topic": f"topic-{index}"} for index in range(30)]
    selected_products = []
    selected_topics = []
    exhaustion_events = []

    for index in range(21):
        slot_time = now + timedelta(hours=index * 4)
        ledger = build_rotation_ledger(history, windows, now=slot_time)
        product, product_meta = select_least_recently_used(products, "product_id", ledger, now=slot_time)
        topic, topic_meta = select_least_recently_used(topics, "topic", ledger, now=slot_time)
        assert product is not None
        assert topic is not None
        selected_products.append(product["product_id"])
        selected_topics.append(topic["topic"])
        exhaustion_events.extend([product_meta["rotation_exhausted"], topic_meta["rotation_exhausted"]])
        history["posts"].append(
            {
                "status": "success",
                "product_id": product["product_id"],
                "topic": topic["topic"],
                "run_started_at_utc": slot_time.isoformat(),
            }
        )

    assert len(set(selected_products)) == 21
    assert len(set(selected_topics)) == 21
    assert not any(exhaustion_events)


def test_zero_fact_briefs_are_excluded_before_twenty_one_slot_rotation(tmp_path):
    briefs_dir = tmp_path / "product_briefs"
    briefs_dir.mkdir()
    products = []
    for index in range(49):
        product_id = f"product-{index}"
        products.append({"id": product_id, "name": product_id})
        facts = [f"verified fact {index}"] if index < 36 else []
        (briefs_dir / f"{product_id}.json").write_text(
            json.dumps({"product_id": product_id, "verified_facts": facts}), encoding="utf-8"
        )

    eligible, report = filter_evidence_eligible_products(products, str(tmp_path))
    assert report["eligible_pool_size"] == 36
    assert report["excluded_pool_size"] == 13
    assert {row["reason"] for row in report["exclusions"]} == {"zero_verified_facts"}

    history = {"posts": []}
    windows = {"product_feature_days": 7, "topic_days": 21, "hook_days": 60}
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    selected_ids = []
    for index in range(21):
        slot_time = now + timedelta(hours=index * 4)
        selected, telemetry = select_least_recently_used(
            eligible,
            "product_id",
            build_rotation_ledger(history, windows, now=slot_time),
            value_key="id",
            now=slot_time,
        )
        assert selected is not None
        assert telemetry["rotation_exhausted"] is False
        selected_ids.append(selected["id"])
        history["posts"].append(
            {"status": "success", "product_id": selected["id"], "run_started_at_utc": slot_time.isoformat()}
        )
    assert len(set(selected_ids)) == 21


def test_consecutive_calendar_day_rejects_repeated_premise_but_ignores_skips():
    now = datetime(2026, 8, 27, 0, 5, tzinfo=timezone.utc)
    repeated = {"topic_hash": "outage-family", "scenario": "A family chooses which device stays powered."}
    previous_post = {
        "status": "success",
        "topic_hash": "outage-family",
        "scenario": "A family chooses which device stays powered.",
        "run_started_at_utc": "2026-08-26T23:59:00+00:00",
    }
    result = check_duplicates(repeated, {"posts": [previous_post]}, now_utc=now)
    assert "duplicate_premise_on_consecutive_day" in result["reasons"]

    skipped = {**previous_post, "status": "skipped_duplicate"}
    result = check_duplicates(repeated, {"posts": [skipped]}, now_utc=now)
    assert "duplicate_premise_on_consecutive_day" not in result["reasons"]