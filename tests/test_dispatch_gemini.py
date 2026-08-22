from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dispatch_outbox  # noqa: E402
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

    assert calls == [1, 2, 3, 4]
    assert prepared["gemini_generation"]["status"] == "COMPLETE"
    assert prepared["gemini_generation"]["actual_image_count"] == 4
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
    monkeypatch.setattr(dispatch_outbox, "recover_outbox", lambda data_dir, outbox_id, error: recovered.append(error))
    monkeypatch.setattr(dispatch_outbox, "_publish", lambda package, platform: published.append(platform))

    result = dispatch_outbox.dispatch_due(data_dir="unused", now_utc="2026-08-23T17:00:00+00:00")

    assert result["status"] == "CONTENT_RECOVERING"
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


def test_dispatch_rechecks_strict_artifact_at_publisher_boundary(monkeypatch):
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
    monkeypatch.setattr(dispatch_outbox, "recover_outbox", lambda data_dir, outbox_id, error: recovered.append(error))
    monkeypatch.setattr(dispatch_outbox, "_publish", lambda package, platform: published.append(platform))

    result = dispatch_outbox.dispatch_due(data_dir="unused", now_utc="2026-08-23T17:00:00+00:00")

    assert result["status"] == "CONTENT_RECOVERING"
    assert "facebook_strict_artifact_invalid:rendered_scanline_corruption" in recovered[0]
    assert published == []