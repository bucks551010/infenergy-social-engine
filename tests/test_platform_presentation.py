from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_posts
from social import platform_presentation


POWERPULSE_ORIGINAL = """Can your phone act as a mobile power reserve, or should you be carrying a dedicated power station instead? A phone cannot effectively charge the professional gear you need, while PowerPulse Pro 200 helps maintain your workflow away from outlets.

Standard power banks can fall short when capacity and port options do not match the job. The 154Wh capacity and 200W output of PowerPulse Pro 200 are designed for the specific power demands of compatible laptops and other everyday electronics.

While a phone battery is built for internal use, PowerPulse Pro 200 provides 41,600mAh and a 110V AC outlet to keep compatible equipment available through long travel days. Equip your mobile office with PowerPulse Pro 200 when standard portable banks fall short.

PowerPulse Pro 200 is a backup power station that supports must-run devices during outages and off-grid use.

Why buyers choose it: 154Wh, 41,600mAh, 200W, 110V, and 5V.

Key specs: 154Wh, 41,600mAh, 200W. PowerPulse Pro 200 is an essential companion for adventure and emergencies, keeping compatible laptops, cameras, drones, and other electronics charged and ready to go.

Your compact portable power station for travel, photography, remote work, and backup planning.

Invite a practical response. Reader job: encourage purchase intent.

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

    assert _word_depth(improved, "PowerPulse Pro 200") <= _word_depth(POWERPULSE_ORIGINAL, "PowerPulse Pro 200")
    assert "154Wh" in improved and "41,600mAh" in improved and "200W" in improved and "110V" in improved
    assert _word_depth(improved, "Key specs") < _word_depth(POWERPULSE_ORIGINAL, "Key specs")
    assert "laptops, cameras, drones" in improved
    assert "⚡ Key specs" in improved
    assert "• 154Wh and 41,600mAh for stored power" in improved
    assert "• 200W AC and 110V output for compatible daily devices" in improved
    assert "remote work" in improved.lower()
    assert "drones" in improved.lower()
    assert "outages and off-grid use" in improved
    assert "Invite a practical response" not in improved
    assert "Reader job" not in improved
    assert len(presentation["selected_hashtags"]) == 20
    assert "#TravelPower" in presentation["selected_hashtags"]
    assert "#MobileOffice" in presentation["selected_hashtags"]
    assert "#RemoteWork" in presentation["selected_hashtags"]
    assert presentation["optional_depth_present"]
    assert improved.count("Review the verified product details.") == 1
    assert "👉 Review the verified product details." in improved


def test_dense_single_paragraph_becomes_readable_without_losing_approved_sentences():
    dense = (
        "Can your current power bank bridge the gap between a drained laptop and a productive workday? "
        "PowerPulse Pro 200 offers 154Wh and 41,600mAh for compatible professional devices. "
        "Its 200W AC output and 110V outlet support compatible equipment away from wall outlets. "
        "Mobile professionals often struggle when standard power banks do not match their laptops. "
        "The deeper decision is whether the supported job matches the equipment being carried. "
        "Review the verified product details.\n\n"
        "#PortablePower #Preparedness"
    )

    improved, _ = platform_presentation.refine_caption(
        dense,
        components=_components(),
        platform="facebook",
    )

    for sentence in platform_presentation._sentences(dense.split("\n\n")[0]):
        assert sentence in improved
    assert len(improved.split("\n\n")) >= 6
    assert improved.index("PowerPulse Pro 200") < improved.index("Mobile professionals")
    assert improved.index("⚡ Key specs") < improved.index("The deeper decision")
    hashtag_line = improved.split("\n\n")[-1]
    assert hashtag_line.startswith("#PortablePower #Preparedness")
    assert len(hashtag_line.split()) == 20
    assert len(set(hashtag_line.split())) == 20


def test_presentation_preserves_existing_hashtags_and_semantics_across_platforms():
    facebook_caption, facebook = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="facebook")
    instagram_caption, instagram = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="instagram")
    linkedin_caption, linkedin = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="linkedin")

    original_tags = {"#PortablePower", "#BackupPower", "#TravelPower", "#Preparedness"}
    assert original_tags.issubset(facebook["selected_hashtags"])
    assert original_tags.issubset(instagram["selected_hashtags"])
    assert original_tags.issubset(linkedin["selected_hashtags"])
    assert len(facebook["selected_hashtags"]) == 20
    assert len(instagram["selected_hashtags"]) == 20
    assert len(linkedin["selected_hashtags"]) == 20
    assert len(set(facebook["selected_hashtags"])) == 20
    assert "#MobileOffice" in facebook_caption
    assert "#TravelPower" in instagram_caption
    assert "#RemoteWork" in linkedin_caption
    assert "standard portable banks fall short" in facebook_caption.lower()
    assert facebook["platform_expression"] == "source_preserving_priority_editorial"


def test_final_render_preserves_content_metadata_and_places_existing_destination_before_tags():
    posts = generate_posts._build_platform_posts(
        "powerpulse-preservation",
        "fixture",
        "mobile_professional",
        "CONVERSION",
        "https://example.com/products/powerpulse",
        _components(),
        90.0,
        caption_overrides={"facebook": {"caption": POWERPULSE_ORIGINAL}},
    )
    before = {
        key: posts["facebook"].get(key)
        for key in ("product_id", "product_name", "product_role", "destination_url", "utm_url", "campaign_id", "platform")
    }
    facebook = generate_posts._apply_platform_presentation_priority(posts, _components())["facebook"]

    assert {key: facebook.get(key) for key in before} == before
    assert facebook["final_caption"].index("Review the verified product details.") < facebook["final_caption"].index("https://example.com/products/powerpulse")
    assert facebook["final_caption"].index("https://example.com/products/powerpulse") < facebook["final_caption"].index("#PortablePower")


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

    assert instagram["reel_caption"] != instagram["caption"]
    assert "PowerPulse Pro 200" in instagram["reel_caption"]
    assert "154Wh" not in instagram["reel_caption"]
    assert instagram["reel_presentation"]["message_hierarchy"] == [
        "hook", "product", "primary_benefit", "selected_proof", "human_use", "action"
    ]
    assert instagram["reel_presentation"]["freeze_frame_priority"][0] == "product"
    assert "PowerPulse Pro 200" in "\n\n".join(instagram["caption"].split("\n\n")[:2])


def test_final_facebook_caption_is_the_qad_string_with_proof_link_and_paragraphs():
    posts = generate_posts._build_platform_posts(
        "powerpulse-final-caption",
        "fixture",
        "mobile_professional",
        "CONVERSION",
        "https://example.com/products/powerpulse",
        _components(),
        90.0,
        platform_interpretations={"facebook": {"cta_expression": "invite a practical response"}},
    )
    facebook = generate_posts._apply_platform_presentation_priority(posts, _components())["facebook"]

    assert facebook["caption"] == facebook["final_caption"]
    assert facebook["final_caption_qa"]["metrics"]["final_caption"] == facebook["final_caption"]
    assert facebook["presentation"]["paragraph_count"] == len(
        [part for part in facebook["final_caption"].split("\n\n") if part.strip()]
    )
    assert "invite a practical response" not in facebook["final_caption"].lower()
    assert "154Wh" in facebook["final_caption"]
    assert "200W" in facebook["final_caption"]
    assert "https://example.com/products/powerpulse" in facebook["final_caption"]
    assert facebook["final_caption"].index("https://") < facebook["final_caption"].index("#PortablePower")
    assert facebook["final_caption_qa"]["status"] == "PRESENTATION_READY"


def test_final_caption_qa_rejects_unresolved_planning_language():
    caption = "Meet PowerPulse Pro 200.\n\ninvite a practical response"
    verdict = platform_presentation.final_caption_qa(
        caption,
        platform="facebook",
        components=_components(),
        planning_instructions=["invite a practical response"],
    )

    assert verdict["status"] == "REVISE_PRESENTATION"
    assert "internal_instruction_leak" in verdict["reasons"]