from __future__ import annotations

import os
import shutil
import sys
import tempfile
import json
import math
import struct
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_instagram
import run_engine
from social import reels


def _components(**overrides):
    base = {
        "topic": "Portable power planning",
        "product_name": "PowerPulse Pro 200",
        "logic_hook": "Know what must stay powered.",
        "on_image_headline": "Start with the device that cannot go dark.",
        "logic_bridge": "Match verified product facts to the job before you pack.",
        "benefit_fragment": "supports a clearer portable-power decision",
        "cta": "Compare your setup.",
        "feature_bullets": ["154Wh"],
    }
    base.update(overrides)
    return base


def test_instagram_can_choose_reel_static_or_carousel_without_hard_coding():
    reel = reels.choose_instagram_media(
        strategy_lock={"reader_job": "decision education", "customer_moment": "planning an outage trip", "topic": "compare portable power"},
        components=_components(),
        visual_plan={"customer_moment": "outage", "visual_message": "decision"},
    )
    carousel = reels.choose_instagram_media(
        strategy_lock={"reader_job": "education", "customer_moment": "planning a trip", "topic": "comparison"},
        components=_components(),
        visual_plan={},
    )
    static = reels.choose_instagram_media(strategy_lock={}, components=_components(logic_bridge=""), visual_plan={})
    assert reel["selected_format"] == "REEL"
    assert carousel["selected_format"] == "CAROUSEL"
    assert static["selected_format"] == "STATIC"


def test_final_state_precedes_motion_and_all_tracks_end_before_freeze():
    decision = {"selected_format": "REEL", "content_job": "decision_support", "motion_value": {"score": 4}}
    plan = reels.build_reel_plan(post_id="reel-1", components=_components(), decision=decision, strategy_lock={"strategy_version": 3})
    assert plan["final_state"]["headline"]
    assert plan["freeze_start_time"] == plan["motion_end_time"]
    assert all(scene["end"] <= plan["freeze_start_time"] for scene in plan["scenes"])
    assert [scene["purpose"] for scene in plan["scenes"]] == ["ATTENTION", "SEQUENCING", "PROOF_AND_HUMAN_USE"]
    assert "PowerPulse" not in plan["scenes"][0]["message"]
    assert "PowerPulse" in plan["scenes"][1]["message"]
    assert "154Wh" in plan["scenes"][2]["message"]
    assert reels.validate_reel_plan(plan)["status"] == "REEL_READY"


def test_pre_render_gate_rejects_motion_that_continues_into_freeze():
    decision = {"selected_format": "REEL", "content_job": "decision_support", "motion_value": {"score": 3}}
    plan = reels.build_reel_plan(post_id="reel-2", components=_components(), decision=decision)
    plan["scenes"][0]["end"] = plan["freeze_start_time"] + 0.1
    gate = reels.validate_reel_plan(plan)
    assert gate["status"] == "REVISE_STORYBOARD"
    assert "animation_track_extends_into_freeze" in gate["reasons"]


def test_technical_qa_fails_closed_for_missing_mp4():
    result = reels.technical_qa({"reel_artifact_path": "missing.mp4"}, {"freeze_start_time": 3.0})
    assert result["status"] == "FAIL"
    assert "missing_or_empty_mp4" in result["reasons"]


def test_scored_story_plan_sets_readable_timing_and_emotional_arc(tmp_path):
    assets = []
    for index in range(3):
        path = tmp_path / f"slide-{index}.png"
        Image.new("RGB", (1080, 1350), (25 + index * 20, 40, 55)).save(path)
        assets.append({"local_path": str(path), "public_url": f"https://media.example/{path.name}"})
    plan = reels.build_scored_story_plan(
        post_id="micro-mission-1", carousel_assets=assets,
        slide_texts=["The lights went out.", "Something moved downstairs behind the breaker panel.", "We found the emergency power kit."],
        emotions=["mystery", "danger", "relief"],
    )
    assert plan["pre_render_gate"] == "SCORED_STORY_READY"
    assert plan["music_score"]["emotional_arc"] == ["mystery", "danger", "relief"]
    assert plan["music_score"]["source"] == "original_cue_based_cinematic_composition"
    assert plan["music_score"]["score_version"] == 2
    assert plan["music_score"]["channels"] == 2
    assert {"low_strings", "felt_piano_motif", "taiko", "brass_swell", "final_resolve"}.issubset(plan["music_score"]["instrumentation"])
    assert plan["scenes"][1]["duration"] > plan["scenes"][0]["duration"]
    assert plan["scenes"][2]["start"] == plan["scenes"][1]["end"]
    assert plan["video_end_time"] == plan["scenes"][-1]["end"]
    if (os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")) and (os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")):
        artifact = reels.render_scored_story_reel(plan, data_dir=str(tmp_path))
        assert reels.technical_qa(artifact, plan)["status"] == "PASS"
        assert artifact["reel_type"] == "SCORED_STORY_REEL"
        assert artifact["story_score"]["commercial_use"] is True


def test_cinematic_story_score_has_cue_dynamics_stereo_motion_and_release(tmp_path):
    plan = {
        "parent_reel_id": "score-test",
        "video_end_time": 6.0,
        "music_score": {"tempo_bpm": 84},
        "scenes": [
            {"emotion": "mystery", "start": 0.0, "end": 1.5, "duration": 1.5},
            {"emotion": "danger", "start": 1.5, "end": 3.0, "duration": 1.5},
            {"emotion": "determination", "start": 3.0, "end": 4.5, "duration": 1.5},
            {"emotion": "relief", "start": 4.5, "end": 6.0, "duration": 1.5},
        ],
    }
    destination = tmp_path / "score.wav"
    reels._render_cinematic_score(plan, destination)
    with wave.open(str(destination), "rb") as audio:
        assert audio.getnchannels() == 2
        assert audio.getframerate() == 48_000
        assert audio.getnframes() == 288_000
        samples = struct.unpack(f"<{audio.getnframes() * 2}h", audio.readframes(audio.getnframes()))

    left = samples[0::2]
    right = samples[1::2]

    def rms(start_seconds, end_seconds):
        start = int(start_seconds * 48_000)
        end = int(end_seconds * 48_000)
        section = left[start:end]
        return math.sqrt(sum(sample * sample for sample in section) / len(section))

    assert rms(3.3, 4.1) > rms(0.45, 1.15) * 1.15
    assert max(abs(sample) for sample in left[int(3.0 * 48_000):int(3.18 * 48_000)]) > rms(3.3, 4.1) * 1.8
    assert sum(abs(left[index] - right[index]) for index in range(0, len(left), 97)) > 100_000
    assert rms(5.8, 5.98) < rms(4.75, 5.35) * 0.55


def test_story_vertical_frame_is_true_reel_canvas_with_story_text(tmp_path):
    source = tmp_path / "slide.png"
    Image.new("RGB", (1080, 1350), (48, 66, 52)).save(source)
    destination = tmp_path / "scene.jpg"
    reels._story_vertical_frame(
        {"asset_path": str(source), "index": 2, "caption": "The warning vanished before the building could respond."},
        destination,
        scene_count=9,
    )
    with Image.open(destination) as frame:
        assert frame.size == (1080, 1920)
        assert frame.getbbox() == (0, 0, 1080, 1920)


def test_font_fallback_honors_requested_size(monkeypatch):
    monkeypatch.setattr(reels.os.path, "exists", lambda _path: False)

    font = reels._font(43)

    assert font.getbbox("Readable story text")[3] >= 35


def test_real_renderer_freezes_actual_video_when_ffmpeg_is_available():
    if not (os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")):
        pytest.skip("FFmpeg is not installed for local acceptance")
    if not (os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")):
        pytest.skip("FFprobe is not installed for local acceptance")
    decision = {"selected_format": "REEL", "content_job": "decision_support", "motion_value": {"score": 4}}
    plan = reels.build_reel_plan(post_id="rendered-reel", components=_components(), decision=decision)
    with tempfile.TemporaryDirectory() as data_dir:
        artifact = reels.render_reel(plan, source_image=None, data_dir=data_dir)
        technical = reels.technical_qa(artifact, plan)
        freeze = reels.freeze_qa(artifact, plan)
        final_frame = reels.final_frame_qa(artifact)
        cover = reels.cover_qa(artifact)
    assert technical["status"] == "PASS"
    assert freeze["status"] == "PASS", json.dumps(freeze)
    assert freeze["freeze_verified"]
    assert final_frame["status"] == "PASS"
    assert cover["status"] == "PASS"


@pytest.mark.parametrize(
    ("post_id", "reader_job", "customer_moment", "topic"),
    [
        ("product-reveal", "product reveal", "packing for a trip", "portable power"),
        ("spec-story", "decision education", "comparing verified specifications", "portable power comparison"),
        ("human-use-case", "decision support", "keeping family devices ready during an outage", "outage planning"),
        ("slideshow", "education", "planning a travel kit", "travel readiness"),
        ("information-reel", "technical explanation", "choosing the right power reserve", "decision framework"),
    ],
)
def test_local_reel_acceptance_families_render_without_publishing(post_id, reader_job, customer_moment, topic):
    if not (os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")):
        pytest.skip("FFmpeg is not installed for local acceptance")
    if not (os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")):
        pytest.skip("FFprobe is not installed for local acceptance")
    components = _components(topic=topic)
    decision = {"selected_format": "REEL", "content_job": reader_job, "motion_value": {"score": 4}}
    plan = reels.build_reel_plan(post_id=post_id, components=components, decision=decision, strategy_lock={"customer_moment": customer_moment})
    with tempfile.TemporaryDirectory() as data_dir:
        artifact = reels.render_reel(plan, source_image=None, data_dir=data_dir)
        assert reels.technical_qa(artifact, plan)["status"] == "PASS"
        assert reels.motion_qa(plan)["status"] == "PASS"
        assert reels.freeze_qa(artifact, plan)["status"] == "PASS"
        assert reels.final_frame_qa(artifact)["status"] == "PASS"
        assert reels.cover_qa(artifact)["status"] == "PASS"
        assert Path(artifact["static_derivative_path"]).exists()


def test_reel_publisher_uses_public_video_cover_and_never_wordpress_upload():
    response = Mock(ok=True)
    response.json.side_effect = [{"id": "container-1"}, {"id": "ig-media-1"}]
    content = {
        "ig_caption": "Caption",
        "platform_posts": {"instagram": {"media_type": "REEL"}},
        "instagram_reel": {"public_urls": {"video": "https://media.example/reel.mp4", "cover": "https://media.example/cover.jpg"}},
    }
    with patch.dict(os.environ, {"META_IG_USER_ID": "ig-user", "META_PAGE_ACCESS_TOKEN": "token"}, clear=False), \
         patch.object(publish_instagram, "_is_reachable_public_url", return_value=True), \
         patch.object(publish_instagram, "_wait_for_media_container", return_value=(True, "finished")), \
         patch.object(publish_instagram, "_post_with_retry", return_value=response) as post, \
         patch.object(publish_instagram.publish_wordpress, "upload_media") as wordpress_upload:
        result = publish_instagram.publish(content)
    first_payload = post.call_args_list[0].args[1]
    assert result == {"id": "ig-media-1", "container_id": "container-1", "media_type": "REEL"}
    assert first_payload["media_type"] == "REELS"
    assert first_payload["video_url"].endswith(".mp4")
    assert first_payload["cover_url"].endswith(".jpg")
    wordpress_upload.assert_not_called()


def test_reel_preflight_accepts_own_persisted_public_media(tmp_path):
    media_dir = tmp_path / "public_media"
    media_dir.mkdir()
    (media_dir / "story.mp4").write_bytes(b"video")
    with patch.dict(os.environ, {"DATA_DIR": str(tmp_path), "RAILWAY_PUBLIC_DOMAIN": "social.example"}, clear=False), \
         patch.object(publish_instagram.requests, "head") as head:
        assert publish_instagram._is_reachable_public_url(
            "https://social.example/media/story.mp4", media_kind="video"
        )
    head.assert_not_called()


def test_reel_preflight_rejects_wrong_local_media_type(tmp_path):
    media_dir = tmp_path / "public_media"
    media_dir.mkdir()
    (media_dir / "story.jpg").write_bytes(b"image")
    with patch.dict(os.environ, {"DATA_DIR": str(tmp_path), "RAILWAY_PUBLIC_DOMAIN": "social.example"}, clear=False):
        assert not publish_instagram._is_reachable_public_url(
            "https://social.example/media/story.jpg", media_kind="video"
        )


def test_reel_preflight_does_not_trust_lookalike_domain(tmp_path):
    media_dir = tmp_path / "public_media"
    media_dir.mkdir()
    (media_dir / "story.mp4").write_bytes(b"video")
    response = Mock(status_code=404, headers={})
    with patch.dict(os.environ, {"DATA_DIR": str(tmp_path), "RAILWAY_PUBLIC_DOMAIN": "social.example"}, clear=False), \
         patch.object(publish_instagram.requests, "head", return_value=response) as head:
        assert not publish_instagram._is_reachable_public_url(
            "https://social.example.attacker.test/media/story.mp4", media_kind="video"
        )
    head.assert_called_once()


def test_reel_receipt_is_durable_and_blocks_duplicate_meta_publish():
    content = {
        "post_id": "reel-candidate",
        "platform_posts": {"instagram": {"media_type": "REEL"}},
        "instagram_reel": {"reel_artifact_path": "/data/public_media/reel.mp4", "cover_path": "/data/public_media/cover.jpg", "final_freeze_frame_path": "/data/public_media/final.png"},
    }
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False):
        receipt = run_engine._persist_publish_receipt(content, platform="instagram", external_post_id="ig-1", container_id="container-1", run_id="run-1")
        loaded = run_engine._successful_publish_receipt(content, "instagram")
        run_engine._mark_publish_postprocess_error(content, "instagram", RuntimeError("history failed"))
        failed = run_engine._successful_publish_receipt(content, "instagram")
    assert receipt["instagram_media_id"] == "ig-1"
    assert loaded["container_id"] == "container-1"
    assert failed["postprocess_status"] == "published_persistence_error"
    assert run_engine._receipt_external_id(failed) == "ig-1"


def test_reel_plan_keeps_caption_complementary_and_static_derivative_unpublished():
    decision = {"selected_format": "REEL", "content_job": "decision_support", "motion_value": {"score": 4}}
    plan = reels.build_reel_plan(post_id="reel-3", components=_components(), decision=decision)
    assert "without restating" in plan["caption_strategy"]
    assert plan["cover_strategy"] == "final_freeze_frame"
    assert "static_derivative" not in plan.get("publish_targets", [])