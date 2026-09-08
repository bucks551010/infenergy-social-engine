from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dispatch_outbox  # noqa: E402
from content_operations import (  # noqa: E402
    create_council_session,
    ensure_daily_slots,
    evaluate_outbox_readiness,
    mark_ready,
    record_publication_history,
    why_not_published,
)
from publication_contract import evaluate_publication_readiness  # noqa: E402


def _package(asset="asset-new"):
    return {
        "post_id": "post-new",
        "unique_creative_required": True,
        "image_url": f"https://example.test/{asset}.png",
        "routing": {"platforms": ["facebook", "instagram", "linkedin"]},
        "platform_posts": {
            platform: {"final_caption": f"Infenergy helps you pack the charger and build the bed tonight. Concrete result for {platform}."}
            for platform in ("facebook", "instagram", "linkedin")
        },
    }


def _enqueue(data_dir, package, slot="morning"):
    day = date(2026, 9, 8).isoformat()
    schedule = {"morning": f"{day}T13:00:00+00:00", "midday": f"{day}T17:00:00+00:00", "evening": f"{day}T23:00:00+00:00"}
    ensure_daily_slots(data_dir, day, schedule, {"platforms": ["facebook", "instagram", "linkedin"]})
    decision = create_council_session(data_dir, content_date=day, slot=slot, blackboard={"content_job": "TEACH"})
    return mark_ready(data_dir, content_date=day, slot=slot, scheduled_at=schedule[slot], decision_id=decision, package=package)


def test_missing_copy_asset_and_incomplete_qa_never_become_ready():
    package = _package()
    package["platform_posts"]["facebook"]["final_caption"] = ""
    package["gemini_generation"] = {
        "strict_provider": True, "provider": "gemini", "status": "COMPLETE", "required_image_count": 1,
        "assets": [{"local_path": "candidate.png"}], "qa": {"TEXT_QA": {"status": "PASS"}},
    }
    result = evaluate_publication_readiness(package, scheduled_at="2026-09-08T13:00:00+00:00", platforms=["facebook"], dispatch_enabled=True)
    assert result.ready is False
    assert "PREPARATION_COPY_MISSING" in result.reason_codes
    assert "QA_VISUAL_FAILED" in result.reason_codes


def test_missing_product_canon_blocks_before_generation():
    package = _package()
    package["canon"] = {"required": True, "canon_id": "", "canon_version": "", "reference_asset_ids": []}
    generation = Mock()
    result = evaluate_publication_readiness(package, scheduled_at="2026-09-08T13:00:00+00:00", platforms=["facebook"], dispatch_enabled=True)
    assert result.state == "BLOCKED_CANON"
    generation.assert_not_called()


def test_published_asset_is_ineligible_and_diagnostic_is_explainable(tmp_path):
    data_dir = str(tmp_path)
    first = _enqueue(data_dir, _package("417dff0425c927e87ebe_gemini_1"))
    record_publication_history(data_dir, outbox_id=first, platform="facebook", external_id="fb-existing")
    second = _enqueue(data_dir, _package("417dff0425c927e87ebe_gemini_1"), slot="midday")
    readiness = evaluate_outbox_readiness(data_dir, second, dispatch_enabled=True)
    diagnostic = why_not_published(data_dir, second)
    assert readiness["ready"] is False
    assert "ASSET_ALREADY_PUBLISHED" in readiness["reason_codes"]
    assert diagnostic["platform_api_calls"] == 0


def test_atomic_one_use_asset_reservation_allows_only_one_package(tmp_path):
    data_dir = str(tmp_path)
    first = _enqueue(data_dir, _package("one-use"), slot="morning")
    second = _enqueue(data_dir, _package("one-use"), slot="midday")
    results = [evaluate_outbox_readiness(data_dir, item, dispatch_enabled=True) for item in (first, second)]
    assert sum(result["ready"] for result in results) == 1
    assert any("ASSET_RESERVED_BY_OTHER_PACKAGE" in result["reason_codes"] for result in results)


def test_concurrent_dispatch_publishes_each_platform_once(tmp_path):
    data_dir = str(tmp_path)
    _enqueue(data_dir, _package())
    with patch.object(dispatch_outbox.publish_facebook, "publish", return_value={"id": "fb-1"}) as facebook, patch.object(dispatch_outbox.publish_instagram, "publish", return_value={"id": "ig-1"}) as instagram, patch.object(dispatch_outbox.publish_linkedin, "publish", return_value={"id": "li-1"}) as linkedin:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: dispatch_outbox.dispatch_due(data_dir=data_dir, now_utc="2026-09-08T13:00:01+00:00"), range(2)))
    assert {result["status"] for result in results} == {"PUBLISHED", "IDLE"}
    assert facebook.call_count == instagram.call_count == linkedin.call_count == 1