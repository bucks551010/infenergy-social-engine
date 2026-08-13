from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_posts
from social import platform_presentation


POWERPULSE_ORIGINAL = """A traditional power bank is useful when you need a quick phone top-up.

But a traditional power bank is not the same as dedicated portable backup power. It can miss the job when your devices, ports, capacity, or charging needs grow.

That is why the difference between a power bank and a portable backup solution matters when you are thinking about travel, mobile work, or an outage.

PowerPulse Pro 200 brings 154Wh (41,600mAh), 200W AC output, and 110V into a compact portable-power option.

Key Specs: 154Wh and 41,600mAh translate into stored power for compatible daily devices. Its 200W AC and 110V output give you a more practical way to think about the equipment you carry.

For laptops, phones, cameras, travel, mobile work, and backup situations, start with the real job before you buy.

Review the verified product details.

#PortablePower #BackupPower #TravelPower #Preparedness"""


def _components() -> dict:
    return {
        "product_id": "PPP-200",
        "product_name": "PowerPulse Pro 200",
        "hook": "Match portable power to the job.",
        "logic_hook": "Traditional power bank or portable backup power: match the job first.",
        "benefit_fragment": "keeps compatible daily devices charged away from outlets",
        "use_case_line": "Built for laptops, phones, cameras, travel, mobile work, and backup situations.",
        "feature_bullets": [
            "154Wh and 41,600mAh for stored power",
            "200W AC and 110V output for compatible daily devices",
        ],
        "cta": "Review the verified product details.",
    }


def _word_depth(text: str, phrase: str) -> int:
    words = re.findall(r"\b[\w'-]+\b", text)
    needle = re.findall(r"\b[\w'-]+\b", phrase)
    for index in range(len(words) - len(needle) + 1):
        if [word.lower() for word in words[index:index + len(needle)]] == [word.lower() for word in needle]:
            return index + 1
    return -1


def test_powerpulse_fixture_front_loads_value_without_losing_sales_depth():
    improved, presentation = platform_presentation.refine_caption(
        POWERPULSE_ORIGINAL,
        components=_components(),
        platform="facebook",
    )

    assert _word_depth(improved, "PowerPulse Pro 200") < _word_depth(POWERPULSE_ORIGINAL, "PowerPulse Pro 200")
    assert presentation["above_fold_value_complete"]
    assert presentation["above_fold_use_case"]
    assert presentation["contrast_paragraph_count"] == 0
    assert "154Wh" in improved and "200W" in improved
    assert "laptops, phones, cameras" in improved
    assert len(presentation["selected_hashtags"]) >= 10
    assert presentation["optional_depth_present"]
    assert improved.count("Review the verified product details.") == 1


def test_hashtag_portfolio_is_richer_for_facebook_and_selective_for_linkedin():
    facebook_caption, facebook = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="facebook")
    instagram_caption, instagram = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="instagram")
    linkedin_caption, linkedin = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="linkedin")

    assert 10 <= len(facebook["selected_hashtags"]) <= 15
    assert 10 <= len(instagram["selected_hashtags"]) <= 15
    assert len(linkedin["selected_hashtags"]) <= 5
    assert len({facebook_caption, instagram_caption, linkedin_caption}) == 3
    assert instagram["platform_expression"] == "visual_first_mobile_scannable_caption"
    assert linkedin["platform_expression"] == "professional_decision_support_editorial"
    assert set(facebook["hashtag_categories"]) == {
        "brand", "product", "category", "use_case", "audience_situation", "discovery"
    }


def test_instagram_package_persists_reel_caption_hierarchy_without_rendering():
    posts = generate_posts._build_platform_posts(
        "powerpulse-fixture",
        "fixture",
        "mobile_professional",
        "CONVERSION",
        "https://example.com",
        _components(),
        90.0,
        caption_overrides={"instagram": {"caption": POWERPULSE_ORIGINAL}},
    )
    posts = generate_posts._apply_platform_presentation_priority(posts, _components())
    instagram = posts["instagram"]

    assert instagram["reel_caption"] == instagram["caption"]
    assert instagram["reel_presentation"]["message_hierarchy"] == [
        "hook", "product", "primary_benefit", "selected_proof", "human_use", "action"
    ]
    assert instagram["reel_presentation"]["freeze_frame_priority"][0] == "product"
    assert instagram["presentation"]["above_fold_value_complete"]