from __future__ import annotations

import os
import sys
from unittest.mock import patch

from PIL import Image

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import social_visuals  # noqa: E402


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
