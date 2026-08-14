from __future__ import annotations

import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import run_engine  # noqa: E402
from score_content import score_content  # noqa: E402
import worker  # noqa: E402


def test_shadow_records_never_report_published():
    records = run_engine._shadow_platform_records(
        {"post_id": "shadow-1", "platform_posts": {}},
        "2026-08-12T00:00:00+00:00",
        {"wordpress": True, "facebook": True, "instagram": True, "linkedin": True},
    )

    assert {record["platform"] for record in records} == {"facebook", "instagram", "linkedin", "wordpress"}
    assert {record["status"] for record in records} == {"shadow_not_published"}
    assert {record["error"] for record in records} == {"shadow_mode_no_external_publication"}
    wordpress = next(record for record in records if record["platform"] == "wordpress")
    assert wordpress["platform_post_id"] == "skipped"


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


def test_shadow_decision_record_persists_creative_cognition():
    content = {
        "creative_decision_packet": {
            "SELECTED_ANSWER": {"creative_concept": "decision-support"},
            "selected_copy_concept": {"approach": "educational_insight"},
            "hook_selection": {"family": "educational_insight"},
            "feed_intelligence": {"what_feed_needs_next": ["a different layout"]},
            "platform_interpretations": {"instagram": {"format": "carousel_or_reel"}},
            "originality_review": {"passed": True},
        },
    }

    record = run_engine._shadow_decision_record(content)

    assert record["creative_concept"] == "decision-support"
    assert record["copy_approach"] == "educational_insight"
    assert record["originality_verdict"]["passed"] is True


def test_history_audit_redacts_secret_bearing_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "post_history.json").write_text(
        '{"posts":[{"post_id":"audit-1","publish_decision":{"decision":"do_not_publish"},"api_token":"hidden","nested":{"password":"hidden","caption":"safe"}}]}',
        encoding="utf-8",
    )

    audit = worker._history_audit("audit-1")

    assert audit["post_id"] == "audit-1"
    assert audit["publish_decision"]["decision"] == "do_not_publish"
    assert "api_token" not in audit
    assert "password" not in audit["nested"]
    assert audit["nested"]["caption"] == "safe"


def test_generation_diagnostics_persists_final_memory_and_remediation():
    content = {
        "final_memory": {"final_outcome": "abstain", "memory_anchor": "Keep it factual."},
        "evidence_remediation": {"status": "ABSTAINED_NO_VIABLE_REPLACEMENT"},
    }

    diagnostics = run_engine._generation_diagnostics(content)

    assert diagnostics["final_memory"]["final_outcome"] == "abstain"
    assert diagnostics["evidence_remediation"]["status"] == "ABSTAINED_NO_VIABLE_REPLACEMENT"


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
