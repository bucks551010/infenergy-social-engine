from __future__ import annotations

import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import run_engine  # noqa: E402
from score_content import score_content  # noqa: E402


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


def test_single_platform_scores_ignore_missing_other_social_channels():
    content = {
        "selected_hook": "How do you match backup power to the device that matters?",
        "selected_cta": "Compare options",
        "product_name": "Power Station",
        "fb_caption": "What device would you keep running first at home? Compare the device load before you choose. #PortablePower",
        "ig_caption": "MATCH POWER TO THE DEVICE\n\nCompare device load before you choose. #PortablePower #BackupPower #Preparedness",
        "li_text": "Continuity planning starts by matching device load to available backup power. Compare options. #Resilience",
    }

    for platform in ("facebook", "instagram", "linkedin"):
        single = score_content(content, requested_platforms=[platform])
        assert set(single["platform_results"]) == {platform}
        assert single["total"] == single["platform_results"][platform]["total"]


def test_multiplatform_score_contains_three_independent_native_verdicts():
    content = {
        "selected_hook": "How do you match backup power to the device that matters?",
        "selected_cta": "Compare options",
        "product_name": "Power Station",
        "fb_caption": "What device would you keep running first at home? Compare the device load before you choose. #PortablePower",
        "ig_caption": "MATCH POWER TO THE DEVICE\n\nCompare device load before you choose. #PortablePower #BackupPower #Preparedness",
        "li_text": "Continuity planning starts by matching device load to available backup power. Compare options. #Resilience",
    }

    scored = score_content(content, requested_platforms=["facebook", "instagram", "linkedin"])

    assert set(scored["platform_results"]) == {"facebook", "instagram", "linkedin"}
    assert scored["platform_results"]["facebook"]["native_checks"] == ["conversational_context"]
    assert scored["platform_results"]["instagram"]["native_checks"] == ["visual_hook_and_saveability"]
    assert scored["platform_results"]["linkedin"]["native_checks"] == ["professional_decision_support"]
