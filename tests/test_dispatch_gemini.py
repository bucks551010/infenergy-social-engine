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


def test_semantic_plate_review_allows_text_free_base_before_overlay():
    class Response:
        text = '{"text_missing_or_illegible":true,"headline_mismatch":true,"cta_missing":true}'

    class Models:
        @staticmethod
        def generate_content(**_kwargs):
            return Response()

    class Client:
        models = Models()

    class Part:
        @staticmethod
        def from_bytes(**_kwargs):
            return object()

    class GenerateContentConfig:
        def __init__(self, **_kwargs):
            pass

    class Types:
        pass

    Types.Part = Part
    Types.GenerateContentConfig = GenerateContentConfig

    accepted, reasons = social_visuals._gemini_semantic_plate_quality(
        Client(), Types, b"image", "instagram", consumer_moment={"person": "host"}
    )

    assert accepted is True
    assert reasons == []


def test_product_reference_approval_binds_source_bytes(tmp_path):
    source = tmp_path / "product.png"
    source.write_bytes(b"verified-product-image")

    approval = social_visuals.approve_product_reference("product-1", str(source))

    assert approval == {
        "product_id": "product-1",
        "source_url": str(source),
        "sha256": "38d5bb317c441f273223710fb2c978073e7cc99c6970694996915da2cc113d94",
    }


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
        "gemini_copy": {
            "provider": "gemini", "strict_provider": True, "fallback_allowed": False,
            "status": "COMPLETE", "model_output_sha256": "prepared-copy", "task": "copy_editing",
        },
        "platform_posts": {
            platform: {"final_caption": "Ready caption", "destination_url": "https://example.test"}
            for platform in ("facebook", "instagram", "linkedin")
        },
        "fb_caption": "Ready caption",
        "ig_caption": "Ready caption",
        "li_text": "Ready caption",
    }


def test_prepare_gemini_copy_authors_captions_and_visual_text(monkeypatch):
    package = _package(carousel=False)
    package["gemini_copy"].update({"status": "PENDING", "model_output_sha256": "", "source_statement": "Preparedness over panic."})
    package["generation_thought"] = {
        "statement": "Preparedness over panic.", "expansion": "A simple plan creates room to think clearly.",
        "action": "Choose one routine.", "pillar": "preparedness_mindset",
    }
    package["generation_contract"] = {"format": "product_story_page", "visible_text": {}}
    monkeypatch.setattr(dispatch_outbox.model_router, "generate_json", lambda *args, **kwargs: {
        "statement": "The smallest battery can run the whole day.",
        "expansion": "Protect the handoff before the routine moves.",
        "action": "Test the full setup where you use it.",
        "visible_text": {
            "headline": "THE SMALLEST BATTERY RUNS THE DAY.",
            "infenergy_line": "POWER THE HANDOFF.",
            "resolution_line": "TEST THE WHOLE ROUTINE.",
        },
        "platform_captions": {
            "facebook": "The smallest battery can run the whole day. Test the handoff.",
            "instagram": "Power the handoff, not only the biggest screen. #Infenergy",
            "linkedin": "Operational continuity often depends on the smallest device. Test the complete workflow.",
        },
    })

    prepared = dispatch_outbox._prepare_gemini_copy(package)

    assert prepared["gemini_copy"]["status"] == "COMPLETE"
    assert prepared["copy_generation_source"] == "gemini"
    assert prepared["fb_caption"].startswith("The smallest battery")
    assert prepared["platform_posts"]["instagram"]["final_caption"].startswith("Power the handoff")
    overlay = prepared["gemini_generation"]["prompts"][0]["v5_direction"]["text_overlay"]
    assert overlay["text"] == "Infenergy | THE SMALLEST BATTERY RUNS THE DAY."
    assert prepared["gemini_copy"]["qa"] == {"schema": "PASS", "forbidden_labels": "PASS", "product_claims": "PASS"}


def test_prepare_gemini_copy_fails_closed_without_model_output(monkeypatch):
    package = _package(carousel=False)
    package["gemini_copy"].update({"status": "PENDING", "model_output_sha256": ""})
    monkeypatch.setattr(dispatch_outbox.model_router, "generate_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(dispatch_outbox.model_router, "last_error", lambda: "quota unavailable")

    with __import__("pytest").raises(RuntimeError, match="gemini_copy_generation_failed:quota unavailable"):
        dispatch_outbox._prepare_gemini_copy(package)


def test_current_news_refresh_invalidates_completed_gemini_copy(monkeypatch):
    package = _package(carousel=False)
    package.update({
        "weekly_role": "current_news",
        "content_date": "2026-09-04",
        "generation_thought": {
            "statement": "Old headline", "overlay_text": "Old headline", "instagram_hook": "Old headline",
            "expansion": "Explain the consequence.", "action": "Make one plan.", "prompt": "What changes?",
            "pillar": "outage_readiness", "visual_motif": "A current event scene", "format": "single",
        },
    })
    monkeypatch.setattr(dispatch_outbox, "_load_current_news", lambda _limit: [
        {"title": "Fresh verified headline", "url": "https://news.example/fresh", "published": "today"},
    ])

    refreshed = dispatch_outbox._refresh_current_news_package(package)

    assert refreshed["gemini_copy"]["status"] == "PENDING"
    assert refreshed["gemini_copy"]["model_output_sha256"] == ""
    assert refreshed["gemini_copy"]["source_statement"] == "Fresh verified headline"


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


def test_prepare_gemini_assets_preserves_portrait_generation_contract(tmp_path, monkeypatch):
    platforms = []
    package = _package(carousel=False)
    package["gemini_generation"]["aspect_ratio"] = "9:16"

    def generate(content, *, prompt_plan, output_path, platform):
        Path(output_path).write_bytes(b"png")
        platforms.append(platform)
        return {
            "render_engine": "gemini",
            "prompt_sha256": prompt_plan["prompt_sha256"],
            "local_path": output_path,
            "review": {"verdict": "PASS", "issues": []},
            "generation": {"generation_status": "success", "visual_provider": "gemini"},
        }

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setattr(dispatch_outbox, "generate_strict_gemini_image", generate)
    dispatch_outbox._prepare_gemini_assets(package, str(tmp_path))

    assert platforms == ["iis_reel_cover"]


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


def test_truth_overlay_uses_text_first_scene_preserving_editorial_treatment():
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
    assert rendered.getpixel((1100, 100)) != (216, 224, 228)
    assert rendered.getpixel((600, 500)) == (216, 224, 228)


def test_truth_overlay_decor_tracks_the_message_theme():
    assert social_visuals._truth_overlay_motif("Protect the communication layer.") == "connection"
    assert social_visuals._truth_overlay_motif("Leave ready. Travel connected.") == "connection"
    assert social_visuals._truth_overlay_motif("Build the backup plan.") == "shield"
    assert social_visuals._truth_overlay_motif("Power the day.") == "power"


def test_comic_overlay_renders_each_exact_line_in_its_panel():
    image = Image.new("RGB", (1080, 1920), "white")
    texts = [
        "THE LAPTOP HAD 62%. THE HOTSPOT HAD 4%.",
        "POWER THE WORKFLOW, NOT JUST THE BIGGEST SCREEN.",
        "PROTECT THE SMALLEST DEPENDENCY.",
    ]

    rendered, error = social_visuals._apply_v5_text_overlay(image, {
        "text_overlay": {"enabled": True, "text": "Infenergy | Comic", "comic_panel_text": texts},
    })

    assert error == ""
    assert rendered.getpixel((40, 40)) != (255, 255, 255)
    assert rendered.getpixel((40, 680)) != (255, 255, 255)
    assert rendered.getpixel((40, 1320)) != (255, 255, 255)


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