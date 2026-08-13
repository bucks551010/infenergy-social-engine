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
    assert "Key specs:" in improved
    assert "mobile work" in improved.lower()
    assert "drones" in improved.lower()
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

    assert instagram["reel_caption"] != instagram["caption"]
    assert "PowerPulse Pro 200" in instagram["reel_caption"]
    assert "154Wh" not in instagram["reel_caption"]
    assert instagram["reel_presentation"]["message_hierarchy"] == [
        "hook", "product", "primary_benefit", "selected_proof", "human_use", "action"
    ]
    assert instagram["reel_presentation"]["freeze_frame_priority"][0] == "product"
    assert instagram["presentation"]["above_fold_value_complete"]


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
    assert facebook["final_caption"].index("https://") < facebook["final_caption"].index("#InfenergyPower")
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


def test_optional_depth_rejects_exact_and_semantic_restarts_of_core_value():
    earlier = [
        "Meet PowerPulse Pro 200: a portable charging backup that supports must-run devices during outages and off-grid use.",
        "Keep it ready in your emergency kit, vehicle, backpack, or travel bag.",
    ]

    assert platform_presentation._depth_classification(
        "Keep it ready in your emergency kit, vehicle, backpack, or travel bag.",
        earlier_layers=earlier,
        product="PowerPulse Pro 200",
    ) == "SEMANTIC_REPEAT"
    assert platform_presentation._depth_classification(
        "It provides support for must-run devices during outages and off-grid use.",
        earlier_layers=earlier,
        product="PowerPulse Pro 200",
    ) == "SEMANTIC_REPEAT"


def test_optional_depth_keeps_new_use_case_and_decision_support_without_system_language():
    earlier = [
        "Meet PowerPulse Pro 200: a portable charging backup that keeps compatible daily devices charged away from outlets.",
        "154Wh (41,600mAh) gives you a compact stored-power reserve for compatible daily devices when an outlet is not nearby.",
    ]

    assert platform_presentation._depth_classification(
        "For photography and remote work, compare the equipment you carry with its published capacity and AC access.",
        earlier_layers=earlier,
        product="PowerPulse Pro 200",
    ) == "ADDITIVE_DEPTH"
    assert platform_presentation._depth_classification(
        "PowerPulse Pro 200 is supporting proof for that decision.",
        earlier_layers=earlier,
        product="PowerPulse Pro 200",
    ) == "LOW_VALUE_FILLER"

    verdict = platform_presentation.final_caption_qa(
        "Meet PowerPulse Pro 200: a portable backup.\n\n"
        "PowerPulse Pro 200 is supporting proof for that decision.\n\n"
        "Review the verified product details.\n\nhttps://example.com",
        platform="facebook",
        components=_components(),
    )
    assert "system_like_customer_language" in verdict["reasons"]


def test_powerpulse_optional_depth_is_additive_and_inventory_keeps_material_sales_ideas():
    improved, presentation = platform_presentation.refine_caption(
        POWERPULSE_ORIGINAL,
        components=_components(),
        platform="facebook",
    )

    classifications = {
        item["text"]: item["classification"]
        for item in presentation["optional_depth_assessment"]
    }
    assert "PowerPulse Pro 200 is supporting proof" not in improved
    assert all(value not in {"SEMANTIC_REPEAT", "LOW_VALUE_FILLER", "REMOVE_DEPTH"}
               for value in classifications.values()
               if value in {"ADDITIVE_DEPTH", "USEFUL_EXPANSION", "SUPPORTING_PROOF"})
    roles = {item["idea"]: item["role"] for item in presentation["content_preservation_map"]}
    assert roles["contrast"] == "CORE"
    assert roles["proof"] == "PROOF"
    assert "drones" in improved.lower()