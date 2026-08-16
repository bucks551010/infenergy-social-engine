import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_engine
from social import platform_presentation


def _content():
    return {
        "post_id": "candidate-1",
        "topic": "Power Stations",
        "pillar": "portable_power",
        "generated_visuals": {"facebook": "/data/generated_visuals/candidate-1_facebook.png"},
        "copy": {"strategy_lock": {"strategy_version": 1}},
    }


def test_receipt_survives_later_history_failure_and_prevents_duplicate_publish():
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False):
        receipt = run_engine._persist_publish_receipt(
            _content(), platform="facebook", external_post_id="fb-123", run_id="run-1"
        )
        run_engine._mark_publish_postprocess_error(_content(), "facebook", RuntimeError("history write failed"))
        loaded = run_engine._successful_publish_receipt(_content(), "facebook")

    assert receipt["facebook_post_id"] == "fb-123"
    assert loaded["facebook_post_id"] == "fb-123"
    assert loaded["postprocess_status"] == "published_persistence_error"


def test_reconcile_receipt_creates_honest_recovery_row():
    with tempfile.TemporaryDirectory() as data_dir:
        with patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), patch.object(run_engine.generate_posts, "DATA_DIR", data_dir), patch.object(run_engine.generate_posts, "BASE_DATA_DIR", data_dir):
            receipt = run_engine._persist_publish_receipt(
                _content(), platform="facebook", external_post_id="fb-123", run_id="2026-08-13T20:19:39Z"
            )
            assert run_engine._reconcile_publish_receipt(receipt)
            history = run_engine.generate_posts.load_history()

    row = history["posts"][-1]
    assert row["status"] == "published_persistence_recovered"
    assert row["fb_id"] == "fb-123"
    assert row["recovery"]["aggregate_history_previously_failed"]


def test_reconcile_external_success_does_not_invent_candidate_data():
    with tempfile.TemporaryDirectory() as data_dir:
        with patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), patch.object(run_engine.generate_posts, "DATA_DIR", data_dir), patch.object(run_engine.generate_posts, "BASE_DATA_DIR", data_dir):
            receipt = run_engine._persist_reconciled_publish_receipt(
                platform="facebook",
                external_post_id="1082101284324756",
                published_at="2026-08-13T20:21:49.200910Z",
                run_started="2026-08-13T20:19:39.115419Z",
            )
            assert run_engine._reconcile_publish_receipt(receipt)
            history = run_engine.generate_posts.load_history()

    row = history["posts"][-1]
    assert receipt["reconciled"]
    assert row["fb_id"] == "1082101284324756"
    assert row["post_id"] == ""
    assert "post_id" not in row["recovery"]["recovered_fields"]


def test_normalization_accepts_orchestrator_without_legacy_date():
    normalized = run_engine._normalize_history_content(
        {"created_at": "2026-08-13T20:19:39+00:00", "strategic_brief": {"topic_path": {"topic": "Power Stations"}, "pillar_id": "portable_power"}},
        run_started="2026-08-13T20:20:00+00:00",
    )
    assert normalized["date"] == "2026-08-13"
    assert normalized["topic"] == "Power Stations"
    assert normalized["pillar"] == "portable_power"


def test_facebook_presentation_surfaces_approved_specs_without_hiding_them():
    components = {
        "logic_hook": "Can your phone power the gear you need away from an outlet?",
        "situation": "Before a trip, identify the device you cannot afford to lose.",
        "logic_bridge": "Match the job to verified product facts before you pack.",
        "benefit_fragment": "keeps compatible daily devices charged away from outlets",
        "product_name": "PowerPulse Pro 200",
        "cta": "Compare your setup.",
        "feature_bullets": ["154Wh", "41,600mAh", "200W", "110V"],
    }
    improved, presentation = platform_presentation.format_caption(components, platform="facebook")

    assert "⚡ Key specs" in improved
    assert "154Wh" in improved
    assert "41,600mAh" in improved
    assert "200W" in improved
    assert "110V" in improved
    assert presentation["presentation_critic"] == "PASS"


def test_platform_expressions_are_native_and_reject_generic_engagement_bait():
    components = {
        "logic_hook": "What must stay powered before a trip?",
        "logic_bridge": "Start with the device and compare verified facts.",
        "benefit_fragment": "supports a practical product-fit decision",
        "product_name": "PowerPulse Pro 200",
        "cta": "Learn more.",
        "feature_bullets": ["154Wh", "200W"],
    }
    facebook, _ = platform_presentation.format_caption(components, platform="facebook")
    instagram, _ = platform_presentation.format_caption(components, platform="instagram")
    linkedin, _ = platform_presentation.format_caption(components, platform="linkedin")
    bait = platform_presentation.evaluate("What do you think? Tell us below.", platform="facebook")

    assert len({facebook, instagram, linkedin}) == 3
    assert bait["generic_engagement_bait"]


def test_final_presentation_gate_blocks_non_ready_facebook_copy():
    errors = run_engine._final_presentation_errors(
        {
            "platform_posts": {
                "facebook": {
                    "final_caption_qa": {"status": "REVISE_PRESENTATION"},
                }
            }
        },
        {"facebook": True, "instagram": False, "linkedin": False},
    )

    assert errors == ["facebook_final_presentation_not_ready"]


def test_reel_presentation_failure_falls_back_to_static_when_reel_qa_passes():
    content = {
        "platform_posts": {
            "instagram": {
                "media_type": "REEL",
                "presentation": {"presentation_critic": "REVISE"},
            }
        },
        "instagram_media_decision": {"selected_format": "REEL"},
        "instagram_reel": {
            name: {"status": "PASS"}
            for name in ("technical_qa", "motion_qa", "freeze_qa", "final_frame_qa", "cover_qa")
        },
        "generated_visuals": {
            "instagram": "/data/generated_visuals/instagram.png",
            "render_engines": {"instagram": "gemini"},
            "product_overlay_applied": {"instagram": True},
            "product_specific_source_present": "true",
        },
        "product_id": "PPP-200",
    }

    errors = run_engine._live_visual_gate_errors(
        content,
        {"facebook": False, "instagram": True, "linkedin": False},
        dry_run=False,
    )

    assert errors == []
    assert content["platform_posts"]["instagram"]["media_type"] == "STATIC"
    assert content["instagram_media_decision"]["selected_format"] == "STATIC"