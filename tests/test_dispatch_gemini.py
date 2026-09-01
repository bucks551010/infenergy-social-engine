from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dispatch_outbox  # noqa: E402
import social_visuals  # noqa: E402
from build_monthly_content import _gemini_generation_plan  # noqa: E402


def _package(carousel: bool = True) -> dict:
    thought = {
        "statement": "Preparedness over panic.",
        "expansion": "A simple plan creates room to think clearly.",
        "prompt": "What will you protect first?",
        "pillar": "preparedness_mindset",
        "visual_motif": "a calm household preparing practical essentials",
        "format": "carousel" if carousel else "single",
    }
    return {
        "post_id": "monthly-test",
        "content_id": "monthly-test",
        "routing": {"platforms": ["facebook", "instagram", "linkedin"]},
        "gemini_generation": _gemini_generation_plan(thought),
        "platform_posts": {
            platform: {"final_caption": "Ready caption", "destination_url": "https://example.test"}
            for platform in ("facebook", "instagram", "linkedin")
        },
        "fb_caption": "Ready caption",
        "ig_caption": "Ready caption",
        "li_text": "Ready caption",
    }


def test_prepare_gemini_assets_generates_every_carousel_slide_once(tmp_path, monkeypatch):
    calls = []

    def generate(content, *, prompt_plan, output_path, platform):
        Path(output_path).write_bytes(b"png")
        calls.append(prompt_plan["slide_index"])
        return {
            "render_engine": "gemini",
            "prompt_sha256": prompt_plan["prompt_sha256"],
            "local_path": output_path,
            "review": {"verdict": "PASS", "issues": []},
            "generation": {"generation_status": "success", "visual_provider": "gemini"},
        }

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setattr(dispatch_outbox, "generate_strict_gemini_image", generate)
    prepared = dispatch_outbox._prepare_gemini_assets(_package(carousel=True), str(tmp_path))

    assert calls == [1, 2, 3, 4, 5, 6]
    assert prepared["gemini_generation"]["status"] == "COMPLETE"
    assert prepared["gemini_generation"]["actual_image_count"] == 6
    assert all(asset["render_engine"] == "gemini" for asset in prepared["carousel_assets"])
    assert all(platform == "gemini" for platform in prepared["generated_visuals"]["render_engines"].values())


def test_dispatch_blocks_every_platform_when_gemini_generation_fails(monkeypatch):
    recovered = []
    published = []
    monkeypatch.setattr(
        dispatch_outbox,
        "claim_due",
        lambda data_dir, now_utc: {"outbox_id": "outbox-1", "package": _package(carousel=False)},
    )
    monkeypatch.setattr(
        dispatch_outbox,
        "_prepare_gemini_assets",
        lambda package, data_dir: (_ for _ in ()).throw(RuntimeError("gemini_generation_failed:quota")),
    )
    monkeypatch.setattr(dispatch_outbox, "release_outbox", lambda data_dir, outbox_id, error: recovered.append(error))
    monkeypatch.setattr(dispatch_outbox, "_publish", lambda package, platform: published.append(platform))

    result = dispatch_outbox.dispatch_due(data_dir="unused", now_utc="2026-08-23T17:00:00+00:00")

    assert result["status"] == "RETRYABLE_FAILURE"
    assert recovered and "gemini_generation_failed" in recovered[0]
    assert published == []


def test_completed_gemini_assets_are_reinspected_before_reuse(tmp_path, monkeypatch):
    package = _package(carousel=False)
    image_path = tmp_path / "cached.png"
    image_path.write_bytes(b"damaged")
    package["gemini_generation"].update({
        "status": "COMPLETE",
        "assets": [{
            "render_engine": "gemini",
            "local_path": str(image_path),
            "public_url": "https://example.test/media/cached.png",
        }],
    })
    monkeypatch.setattr(
        dispatch_outbox,
        "review_rendered_visual",
        lambda path, platform: {"verdict": "REGENERATE_VISUAL", "issues": ["rendered_scanline_corruption"]},
    )

    assert dispatch_outbox._gemini_assets_ready(package, 1) is False


def test_dispatch_preflights_all_strict_artifacts_before_any_publisher_call(monkeypatch):
    package = _package(carousel=False)
    package["gemini_generation"].update({"status": "COMPLETE", "assets": []})
    package["generated_visuals"] = {platform: "cached.png" for platform in ("facebook", "instagram", "linkedin")}
    recovered = []
    published = []
    monkeypatch.setattr(
        dispatch_outbox,
        "claim_due",
        lambda data_dir, now_utc: {"outbox_id": "outbox-1", "package": package},
    )
    monkeypatch.setattr(dispatch_outbox, "_prepare_gemini_assets", lambda package, data_dir: package)
    monkeypatch.setattr(dispatch_outbox, "update_claimed_package", lambda *args: None)
    monkeypatch.setattr(dispatch_outbox, "platform_transaction", lambda data_dir, outbox_id, platform: {})
    monkeypatch.setattr(
        dispatch_outbox,
        "review_rendered_visual",
        lambda path, platform: {"verdict": "REGENERATE_VISUAL", "issues": ["rendered_scanline_corruption"]},
    )
    monkeypatch.setattr(dispatch_outbox, "release_outbox", lambda data_dir, outbox_id, error: recovered.append(error))
    monkeypatch.setattr(dispatch_outbox, "_publish", lambda package, platform: published.append(platform))

    result = dispatch_outbox.dispatch_due(data_dir="unused", now_utc="2026-08-23T17:00:00+00:00")

    assert result["status"] == "RETRYABLE_FAILURE"
    assert "facebook_strict_artifact_invalid:rendered_scanline_corruption" in recovered[0]
    assert published == []


def test_shared_square_gemini_artifact_is_valid_for_linkedin_dispatch(monkeypatch):
    package = _package(carousel=False)
    package["generated_visuals"] = {"linkedin": "gemini-square.png"}
    reviewed_platforms = []
    monkeypatch.setattr(
        dispatch_outbox,
        "review_rendered_visual",
        lambda path, platform: reviewed_platforms.append(platform) or {"verdict": "PASS", "issues": []},
    )

    assert dispatch_outbox._strict_publish_artifact_error(package, "linkedin") == ""
    assert reviewed_platforms == ["instagram"]


def test_linkedin_preflight_failure_blocks_facebook_and_instagram(monkeypatch):
    package = _package(carousel=False)
    package["gemini_generation"].update({"status": "COMPLETE", "assets": []})
    package["generated_visuals"] = {platform: f"{platform}.png" for platform in ("facebook", "instagram", "linkedin")}
    published = []
    released = []
    monkeypatch.setattr(
        dispatch_outbox,
        "claim_due",
        lambda data_dir, now_utc: {"outbox_id": "outbox-1", "package": package},
    )
    monkeypatch.setattr(dispatch_outbox, "_prepare_gemini_assets", lambda package, data_dir: package)
    monkeypatch.setattr(dispatch_outbox, "update_claimed_package", lambda *args: None)
    monkeypatch.setattr(
        dispatch_outbox,
        "_strict_publish_artifact_error",
        lambda package, platform: "linkedin_strict_artifact_invalid:damaged" if platform == "linkedin" else "",
    )
    monkeypatch.setattr(dispatch_outbox, "release_outbox", lambda data_dir, outbox_id, error: released.append(error))
    monkeypatch.setattr(dispatch_outbox, "_publish", lambda package, platform: published.append(platform))

    result = dispatch_outbox.dispatch_due(data_dir="unused", now_utc="2026-08-23T17:00:00+00:00")

    assert result["status"] == "RETRYABLE_FAILURE"
    assert released == ["linkedin_strict_artifact_invalid:damaged"]
    assert published == []


def test_gemini_http_options_bound_timeout_and_attempts(monkeypatch):
    from google.genai import types

    monkeypatch.setenv("GEMINI_REQUEST_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("GEMINI_REQUEST_ATTEMPTS", "1")
    options = social_visuals._gemini_http_options(types)

    assert options.timeout == 45_000
    assert options.retry_options.attempts == 1


def test_truth_overlay_uses_compact_partial_width_panel():
    image = Image.new("RGB", (1200, 1200), "#d8e0e4")
    rendered, error = social_visuals._apply_v5_text_overlay(
        image,
        {
            "text_overlay": {
                "enabled": True,
                "text": "Infenergy | Recovery is communal.",
                "placement": "upper third",
                "safe_margin_ratio": 0.055,
            }
        },
    )

    assert error == ""
    assert rendered.getpixel((70, 70)) != (216, 224, 228)
    assert rendered.getpixel((1100, 100)) == (216, 224, 228)
    assert rendered.getpixel((600, 500)) == (216, 224, 228)


def test_truth_overlay_fails_closed_without_scalable_font(monkeypatch):
    image = Image.new("RGB", (1200, 1200), "white")
    monkeypatch.setattr(social_visuals, "_overlay_font", lambda *args, **kwargs: None)

    _, error = social_visuals._apply_v5_text_overlay(
        image,
        {"text_overlay": {"enabled": True, "text": "Infenergy | A useful truth."}},
    )

    assert error == "scalable_font_unavailable_for_overlay"


def test_pregenerate_updates_ready_package_without_claim_or_publish(monkeypatch):
    package = _package(carousel=False)
    prepared = _package(carousel=False)
    prepared["gemini_generation"]["status"] = "COMPLETE"
    updates = []
    published = []
    monkeypatch.setattr(
        dispatch_outbox,
        "upcoming_ready_packages",
        lambda *args, **kwargs: [{"outbox_id": "outbox-1", "package": package}],
    )
    monkeypatch.setattr(dispatch_outbox, "_gemini_assets_ready", lambda *args: False)
    monkeypatch.setattr(dispatch_outbox, "_prepare_gemini_assets", lambda *args: prepared)
    monkeypatch.setattr(dispatch_outbox, "update_ready_package", lambda *args: updates.append(args) or True)
    monkeypatch.setattr(dispatch_outbox, "_publish", lambda *args: published.append(args))

    result = dispatch_outbox.pregenerate_upcoming(data_dir="unused")

    assert result == {"status": "PREGENERATED", "outbox_id": "outbox-1"}
    assert updates and updates[0][1:] == ("outbox-1", prepared)
    assert published == []


def test_pregenerate_failure_leaves_package_retryable(monkeypatch):
    package = _package(carousel=False)
    updates = []
    monkeypatch.setattr(
        dispatch_outbox,
        "upcoming_ready_packages",
        lambda *args, **kwargs: [{"outbox_id": "outbox-1", "package": package}],
    )
    monkeypatch.setattr(dispatch_outbox, "_gemini_assets_ready", lambda *args: False)
    monkeypatch.setattr(
        dispatch_outbox,
        "_prepare_gemini_assets",
        lambda *args: (_ for _ in ()).throw(TimeoutError("provider timeout")),
    )
    monkeypatch.setattr(dispatch_outbox, "update_ready_package", lambda *args: updates.append(args) or True)

    result = dispatch_outbox.pregenerate_upcoming(data_dir="unused")

    assert result["status"] == "RETRYABLE_FAILURE"
    assert "provider timeout" in result["error"]
    assert updates == []


def test_pregenerate_skips_completed_package_and_prepares_next(monkeypatch):
    completed = _package(carousel=False)
    pending = _package(carousel=False)
    pending["content_id"] = "monthly-next"
    prepared = dict(pending)
    updates = []
    monkeypatch.setattr(
        dispatch_outbox,
        "upcoming_ready_packages",
        lambda *args, **kwargs: [
            {"outbox_id": "outbox-complete", "package": completed},
            {"outbox_id": "outbox-next", "package": pending},
        ],
    )
    monkeypatch.setattr(
        dispatch_outbox,
        "_gemini_assets_ready",
        lambda package, required_count: package is completed,
    )
    monkeypatch.setattr(dispatch_outbox, "_prepare_gemini_assets", lambda *args: prepared)
    monkeypatch.setattr(dispatch_outbox, "update_ready_package", lambda *args: updates.append(args) or True)

    result = dispatch_outbox.pregenerate_upcoming(data_dir="unused")

    assert result == {"status": "PREGENERATED", "outbox_id": "outbox-next"}
    assert updates[0][1] == "outbox-next"