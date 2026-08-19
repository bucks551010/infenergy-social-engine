from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch
import sys
import types
import google

from PIL import Image

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import social_visuals  # noqa: E402
import run_engine  # noqa: E402


def test_approved_gemini_creative_recovers_failed_platform_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(social_visuals, "VISUAL_DIR", str(tmp_path))

    def fake_generate(content, platform, plan, file_path):
        if platform == "facebook":
            Image.new("RGB", (1200, 1200), "#50646f").save(file_path)
            return True, "", {"generation_status": "success", "artifact_path": file_path}
        return False, "semantic_quality_rejected:gibberish_or_garbled_text", {"generation_status": "failed"}

    monkeypatch.setattr(social_visuals, "_generate_gemini_full_creative", fake_generate)
    monkeypatch.setattr(social_visuals, "_load_visual_repo_context", lambda: {"references": [], "settings": {}})
    monkeypatch.setattr(social_visuals, "_resolve_product_source", lambda *args, **kwargs: "https://example.com/reference.jpg")

    visuals = social_visuals.generate_visuals({"post_id": "winner", "product_id": "CAMP-FAN-12K"}, {})

    assert visuals["render_engine"] == "gemini"
    assert all(Path(visuals[platform]).is_file() for platform in ("facebook", "instagram", "linkedin"))
    assert Image.open(visuals["instagram"]).size == social_visuals._platform_visual_spec("instagram")["target"]
    assert Image.open(visuals["linkedin"]).size == social_visuals._platform_visual_spec("linkedin")["target"]
    assert visuals["visual_generation"]["instagram"]["final_creative_status"] == "approved_gemini_creative_syndicated"
    assert visuals["visual_generation"]["linkedin"]["syndicated_from_platform"] == "facebook"
    assert visuals["visual_generation"]["instagram"]["fallback_used"] is False


def _image(path, size=(1080, 1080)):
    image = Image.new("RGB", size, "#d9dde2")
    for x in range(size[0] // 3, (size[0] * 2) // 3):
        for y in range(size[1] // 3, (size[1] * 2) // 3):
            image.putpixel((x, y), (50, 66, 74))
    image.save(path)


def test_powerpulse_raw_fallback_is_packshot_only_without_explicit_route(tmp_path):
    artifact = tmp_path / "powerpulse.png"
    _image(artifact, social_visuals._platform_visual_spec("instagram")["target"])
    review = social_visuals._fallback_creative_review(
        {"product_id": "PPP-200", "product_name": "PowerPulse Pro 200"},
        {"creative_route": "PRODUCT_IN_CONTEXT"},
        str(artifact),
        "instagram",
    )

    assert review["creative_classification"] == "PACKSHOT_ONLY"
    assert review["verdict"] == "REGENERATE_VISUAL"
    assert review["recovery_action"] == "CHANGE_CREATIVE_ROUTE"


def test_packshot_can_only_pass_when_creative_director_explicitly_selects_it(tmp_path):
    artifact = tmp_path / "hero.png"
    _image(artifact, social_visuals._platform_visual_spec("facebook")["target"])
    review = social_visuals._fallback_creative_review(
        {"product_id": "PPP-200"},
        {"creative_route": "PREMIUM_PRODUCT_HERO"},
        str(artifact),
        "facebook",
    )

    assert review["creative_classification"] == "EXPLICIT_PRODUCT_HERO"
    assert review["verdict"] == "PASS"


def test_product_free_editorial_source_is_not_misclassified_as_packshot(tmp_path):
    artifact = tmp_path / "editorial.png"
    _image(artifact, social_visuals._platform_visual_spec("linkedin")["target"])
    review = social_visuals._fallback_creative_review(
        {"product_id": None},
        {"creative_route": "EDITORIAL_HUMAN_SCENE"},
        str(artifact),
        "linkedin",
    )

    assert review["creative_classification"] == "EDITORIAL_SOURCE_IMAGE"
    assert review["verdict"] == "PASS"


def test_gemini_image_quota_failure_short_circuits_following_calls(tmp_path, monkeypatch):
    calls = {"count": 0}

    class Models:
        def generate_content(self, **_kwargs):
            calls["count"] += 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED monthly spending cap")

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = lambda **_kwargs: types.SimpleNamespace(models=Models())
    fake_types = types.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = lambda **kwargs: kwargs
    fake_types.ImageConfig = lambda **kwargs: kwargs
    fake_types.Part = types.SimpleNamespace(from_bytes=lambda **kwargs: kwargs)
    fake_genai.types = fake_types
    monkeypatch.setattr(google, "genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(social_visuals, "_GEMINI_IMAGE_UNAVAILABLE_REASON", "")
    content = {"post_id": "quota-test", "selected_cta": "Learn more"}

    first = social_visuals._generate_gemini_full_creative(content, "facebook", {}, str(tmp_path / "first.png"))
    second = social_visuals._generate_gemini_full_creative(content, "instagram", {}, str(tmp_path / "second.png"))

    assert first[0] is False and second[0] is False
    assert calls["count"] == 1
    assert "resource_exhausted" in second[1].lower()


def test_final_file_qa_preserves_packshot_only_rejection(tmp_path):
    artifact = tmp_path / "powerpulse.png"
    _image(artifact, social_visuals._platform_visual_spec("facebook")["target"])
    content = {
        "generated_visuals": {
            "facebook": str(artifact),
            "artifact_reviews": {
                "facebook": {
                    "verdict": "REGENERATE_VISUAL",
                    "issues": ["packshot_only_without_explicit_route"],
                    "creative_classification": "PACKSHOT_ONLY",
                    "recovery_action": "CHANGE_CREATIVE_ROUTE",
                }
            },
        }
    }

    reviews = run_engine._ensure_final_artifact_qa(
        content,
        {"facebook": True, "instagram": False, "linkedin": False},
    )

    assert reviews["facebook"]["verdict"] == "REGENERATE_VISUAL"
    assert reviews["facebook"]["creative_classification"] == "PACKSHOT_ONLY"
    assert "packshot_only_without_explicit_route" in reviews["facebook"]["issues"]
