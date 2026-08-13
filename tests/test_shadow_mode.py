from __future__ import annotations

import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import run_engine  # noqa: E402


def test_shadow_records_never_report_published():
    records = run_engine._shadow_platform_records(
        {"post_id": "shadow-1", "platform_posts": {}},
        "2026-08-12T00:00:00+00:00",
        {"wordpress": True, "facebook": True, "instagram": True, "linkedin": True},
    )

    assert len(records) == 4
    assert {record["status"] for record in records} == {"shadow_not_published"}
    assert {record["error"] for record in records} == {"shadow_mode_no_external_publication"}


def test_material_integrity_drift_is_a_runtime_publish_error():
    content = {"creative_director": {"strategy_integrity_review": {"verdict": "MATERIAL_DRIFT"}}}

    assert run_engine._strategy_integrity_errors(content) == ["strategy_integrity_material_drift"]


def test_shadow_decision_record_uses_existing_reviews_only():
    content = {
        "topic": "Power priorities",
        "audience_segment": "preparedness-focused households",
        "copy": {"strategy_lock": {"audience": "household", "angle": "prioritize essentials"}},
        "creative_director": {"strategy_integrity_review": {"verdict": "ALIGNED"}},
        "publish_decision": {"decision": "publish"},
    }

    record = run_engine._shadow_decision_record(content)

    assert record["who_it_is_for"] == "household"
    assert record["strategy_integrity_verdict"]["verdict"] == "ALIGNED"
