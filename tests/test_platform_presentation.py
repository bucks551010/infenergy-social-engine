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
        "emotional_outcome": "confidence through better preparation",
        "after_state": "You can keep compatible priority devices available away from wall power instead of organizing the day around the next outlet.",
        "transformation": "Travel, remote work, and outage planning become more controlled when stored power, output, and the devices carried are matched in advance.",
        "why_it_matters": "The value is knowing the backup fits the compatible equipment that must stay available.",
        "situation": "A weak power bank can fail when its capacity and ports do not match the devices carried.",
        "info": "Compare the real job against the published capacity and output before choosing.",
        "use_case_line": "Built for laptops, phones, cameras, travel, mobile work, and backup situations.",
        "product_connection": "PowerPulse Pro 200 supports everyday charging backup using verified product details.",
        "proof": "Checked against the published battery, port, and charging specifications.",
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

    assert improved.startswith(_components()["logic_hook"])
    assert _word_depth(improved, "PowerPulse Pro 200") < _word_depth(improved, "Key specs")
    assert "154Wh" in improved and "41,600mAh" in improved and "200W" in improved and "110V" in improved
    assert _word_depth(improved, "Key specs") < _word_depth(POWERPULSE_ORIGINAL, "Key specs")
    assert _components()["product_connection"] in improved
    assert "⚡ Key specs" in improved
    assert "• 154Wh and 41,600mAh for stored power" in improved
    assert "• 200W AC and 110V output for compatible daily devices" in improved
    assert "remote work" in improved.lower()
    assert "The common assumption:" in improved
    assert "The better question:" in improved
    assert "That is where PowerPulse Pro 200 fits:" in improved
    assert "Invite a practical response" not in improved
    assert "Reader job" not in improved
    assert len(presentation["selected_hashtags"]) == 5
    assert "#TravelPower" in presentation["selected_hashtags"]
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

    assert improved.split("\n\n")[0] == _components()["logic_hook"]
    assert "The common assumption:" in improved
    assert "That is where PowerPulse Pro 200 fits:" in improved
    assert improved.count("154Wh") == 1
    assert improved.count("41,600mAh") == 1
    assert improved.count("200W") == 1
    assert improved.count("110V") == 1
    assert len(improved.split("\n\n")) >= 6
    assert improved.index("PowerPulse Pro 200") < improved.index("⚡ Key specs")
    assert improved.index("⚡ Key specs") < improved.index("How to read those specs")
    hashtag_line = improved.split("\n\n")[-1]
    assert hashtag_line.startswith("#PortablePower #Preparedness")
    assert len(hashtag_line.split()) == 5
    assert len(set(hashtag_line.split())) == 5


def test_benefit_opening_uses_only_approved_component_meaning():
    components = _components()
    improved, presentation = platform_presentation.refine_caption(
        POWERPULSE_ORIGINAL,
        components=components,
        platform="facebook",
    )

    first_four = " ".join(improved.split("\n\n")[:4])
    assert improved.startswith(components["logic_hook"])
    assert components["product_name"] in first_four
    assert components["benefit_fragment"].lower() in first_four.lower()
    assert "powers your laptop all day" not in improved.lower()
    assert "compatible with every" not in improved.lower()
    assert presentation["semantic_layer_evidence"]["primary_benefit"] == components["benefit_fragment"]
    assert components["after_state"].rstrip(".") in presentation["semantic_layer_evidence"]["human_outcome"]


def test_format_caption_keeps_benefit_opening_and_restores_approved_depth():
    components = _components()
    improved, _ = platform_presentation.format_caption(components, platform="facebook")
    assert improved.startswith(components["logic_hook"])
    assert components["situation"] in improved
    assert components["info"] in improved
    assert components["product_name"] in improved
    assert improved.index(components["situation"]) < improved.index(components["product_name"])
    assert improved.index(components["product_name"]) < improved.index("⚡ Key specs")


def test_product_free_caption_is_idempotent_and_never_invents_a_product():
    components = {
        "product_id": None,
        "funnel_stage": "ATTENTION",
        "product_name": "",
        "logic_hook": "Why is overnight charging not always the problem people assume?",
        "logic_bridge": "Understanding basic electrical terminology helps explain what is happening.",
        "benefit_fragment": "supports a more reliable preparedness setup",
        "emotional_outcome": "confidence through better preparation",
        "feature_bullets": [],
        "cta": "Save this checklist and compare your current setup.",
    }
    once, _ = platform_presentation.format_caption(components, platform="facebook")
    twice, _ = platform_presentation.refine_caption(
        once,
        components=components,
        platform="facebook",
        product_led=False,
    )

    assert "✨" not in twice
    assert "For you, that means" not in twice
    assert twice.startswith("Why is overnight charging not always the problem people assume?")
    assert twice.count("👉 Save this guidance for your next planning session.") == 1
    assert twice.count("⚡ Key specs") <= 1
    assert "this product" not in twice.lower()
    assert "supporting proof for that decision" not in twice.lower()
    assert "remember:" not in twice.lower()
    assert _["engagement_structure"][:3] == [
        "human_pattern_interrupt",
        "relatable_tension",
        "fresh_reframe",
    ]
    assert _["content_ideology"] == "earn_participation_through_relevance_not_bait"


def test_product_free_education_has_its_own_actionable_structure():
    components = {
        "product_id": None,
        "funnel_stage": "EDUCATION",
        "product_name": "",
        "logic_hook": "What should a household identify before an outage?",
        "situation": "An unranked list of devices makes the first decision harder.",
        "logic_bridge": "Start with communication, health, and essential daily continuity.",
        "why_it_matters": "Clear priorities reduce guesswork when normal routines are interrupted.",
        "transformation": "A short priority order turns concern into an actionable plan.",
        "feature_bullets": [],
        "cta": "Save this framework for your next planning check.",
    }

    caption, presentation = platform_presentation.format_caption(components, platform="facebook")

    assert "A practical way to use this:" in caption
    assert all(f"{index}." in caption for index in (1, 2, 3))
    assert "Key specs" not in caption
    assert "this product" not in caption.lower()
    assert presentation["engagement_structure"][2] == "three_step_actionable_framework"
    assert presentation["content_ideology"] == "teach_for_capability_without_forcing_a_sale"
    assert presentation["platform_expression"] == "facebook_education_engagement_editorial"


def test_sales_pyramid_applies_to_products_other_than_powerpulse():
    components = _components()
    components.update({
        "product_id": "CAMP-FAN-12K",
        "product_name": "3-in-1 Portable Camping Fan",
        "benefit_fragment": "keeps air moving while adding light and backup phone power at camp",
        "situation": "Hot, dark campsites can force three separate tools into limited packing space.",
        "after_state": "One matched setup can cover airflow, area light, and compatible phone charging.",
        "feature_bullets": ["12,000mAh", "5V"],
    })

    caption, presentation = platform_presentation.format_caption(components, platform="instagram")

    assert caption.startswith(components["logic_hook"])
    assert "The common assumption:" in caption
    assert "That is where 3-in-1 Portable Camping Fan fits:" in caption
    assert caption.count("12,000mAh") == 1
    assert caption.count("5V") == 1
    assert presentation["sales_structure"][0] == "human_moment"
    assert presentation["platform_expression"] == "instagram_benefit_led_product_sales_editorial"


def test_final_presentation_keeps_only_the_current_approved_cta():
    components = _components()
    caption = (
        "Match portable power to the job.\n\n"
        "👉 Keep it ready in your travel bag.\n\n"
        "👉 Review the verified product details.\n\n"
        "#PortablePower"
    )

    improved, _ = platform_presentation.refine_caption(
        caption,
        components=components,
        platform="facebook",
    )

    assert "Keep it ready in your travel bag" not in improved
    assert improved.count("👉 Review the verified product details.") == 1
    assert "\n\n👉 Review the verified product details." in improved


def test_presentation_preserves_existing_hashtags_and_semantics_across_platforms():
    facebook_caption, facebook = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="facebook")
    instagram_caption, instagram = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="instagram")
    linkedin_caption, linkedin = platform_presentation.refine_caption(POWERPULSE_ORIGINAL, components=_components(), platform="linkedin")

    original_tags = {"#PortablePower", "#BackupPower", "#TravelPower", "#Preparedness"}
    assert original_tags.issubset(facebook["selected_hashtags"])
    assert original_tags.issubset(instagram["selected_hashtags"])
    assert original_tags.issubset(linkedin["selected_hashtags"])
    assert len(facebook["selected_hashtags"]) == 5
    assert len(instagram["selected_hashtags"]) == 8
    assert len(linkedin["selected_hashtags"]) == 5
    assert len(set(facebook["selected_hashtags"])) == 5
    assert "#TravelPower" in instagram_caption
    assert _components()["situation"].lower() in facebook_caption.lower()
    assert facebook["platform_expression"] == "facebook_benefit_led_product_sales_editorial"


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


def test_powerpulse_specs_appear_once_and_unsupported_broad_claims_are_repaired():
    source = POWERPULSE_ORIGINAL.replace(
        "Standard power banks can fall short",
        "Most compact batteries fail",
    ) + "\n\nThis ensures real-world compatibility and keeps your laptop running mid-flight."
    improved, _ = platform_presentation.refine_caption(source, components=_components(), platform="instagram")

    assert improved.count("154Wh") == 1
    assert improved.count("41,600mAh") == 1
    assert improved.count("200W") == 1
    assert improved.count("110V") == 1
    assert "ensures real-world compatibility" not in improved.lower()
    assert "most compact batteries fail" not in improved.lower()
    assert "keeps your laptop running mid-flight" not in improved.lower()
    assert "compare the real job against the published capacity and output" in improved.lower()


def test_long_useful_copy_passes_when_paragraphs_remain_readable():
    paragraph = "Compare the published capability with the devices and responsibilities that must remain available before choosing a backup plan."
    long_caption = "\n\n".join([paragraph for _ in range(20)])
    metrics = platform_presentation.evaluate(long_caption, platform="instagram")

    assert metrics["word_count"] > 200
    assert metrics["reading_burden"] == "APPROPRIATE"
    assert metrics["longest_paragraph_words"] < 80


def test_product_caption_repairs_checklist_cta_when_no_checklist_exists():
    components = _components()
    components["cta"] = "Save this checklist and compare your current setup."
    improved, _ = platform_presentation.refine_caption(
        "Match the published capability with the equipment you carry.\n\n#PortablePower",
        components=components,
        platform="linkedin",
    )

    assert "Save this checklist" not in improved
    assert "Review the verified product details." in improved
    qa = platform_presentation.final_caption_qa(
        platform_presentation.render_platform_caption(
            improved,
            destination_url="https://www.infenergypower.com/product/powerpulse-pro-200/",
            platform="linkedin",
        ),
        platform="linkedin",
        components={**components, "cta": "Review the verified product details."},
    )
    assert "promised_plan_missing_actionable_steps" not in qa["reasons"]


def test_general_planning_language_does_not_promise_a_numbered_plan():
    components = _components()
    components["cta"] = "Review the verified product details."
    caption = (
        "Power planning becomes clearer when you compare published capability with the equipment you carry.\n\n"
        "Travel and outage planning benefit from that comparison.\n\n"
        "Review the verified product details.\n\n"
        "https://www.infenergypower.com/product/powerpulse-pro-200/"
    )
    qa = platform_presentation.final_caption_qa(
        caption,
        platform="linkedin",
        components=components,
    )

    assert "promised_plan_missing_actionable_steps" not in qa["reasons"]


def test_instagram_mobile_first_screen_has_entry_point_and_breathing_room():
    improved, _ = platform_presentation.refine_caption(
        POWERPULSE_ORIGINAL,
        components=_components(),
        platform="instagram",
    )
    preview = platform_presentation.mobile_first_screen(improved)

    assert preview["entry_point_visible"] is True
    assert preview["breathing_room"] is True
    assert preview["dense_first_screen"] is False
    assert _components()["logic_hook"] in preview["visible_text"].replace("\n", " ")


def test_mobile_first_screen_detects_dense_wall():
    dense = " ".join(["unbroken"] * 120)
    preview = platform_presentation.mobile_first_screen(dense)

    assert preview["breathing_room"] is False
    assert preview["dense_first_screen"] is True


def test_powerpulse_product_sales_copy_follows_human_first_sequence():
    caption, presentation = platform_presentation.refine_caption(
        POWERPULSE_ORIGINAL,
        components=_components(),
        platform="instagram",
    )
    paragraphs = caption.split("\n\n")

    assert paragraphs[0] == _components()["logic_hook"]
    assert paragraphs[1].startswith("The common assumption:")
    assert "The better question:" in paragraphs[1]
    assert paragraphs[2].startswith("That is where PowerPulse Pro 200 fits:")
    assert paragraphs[3].startswith("⚡ Key specs\n• 154Wh")
    assert caption.count("154Wh") == 1
    assert caption.count("41,600mAh") == 1
    assert caption.count("200W") == 1
    assert caption.count("110V") == 1
    assert presentation["sales_structure"][:6] == [
        "human_moment",
        "current_belief",
        "desired_belief",
        "dominant_proposition",
        "product_fit",
        "mechanism",
    ]
    mobile = platform_presentation.mobile_first_screen(caption)
    assert mobile["entry_point_visible"] is True
    assert mobile["breathing_room"] is True


def test_product_sales_education_does_not_repeat_numeric_specs():
    components = _components()
    components["info"] = "154Wh is a practical anchor for comparing real fit before purchase."
    caption, _ = platform_presentation.refine_caption(
        POWERPULSE_ORIGINAL,
        components=components,
        platform="facebook",
    )

    assert caption.count("154Wh") == 1
    assert caption.count("41,600mAh") == 1
    assert caption.count("200W") == 1
    assert caption.count("110V") == 1
    assert "How to read those specs: Compare the published capacity and output" in caption


def test_product_sales_repairs_fragmentary_framework_copy():
    components = _components()
    components["editorial_framework"] = {
        "human_moment": "before a trip",
        "desired_belief": "how does this fit the real job.",
        "mechanism": "154Wh",
        "functional_transformation": "more control control",
    }

    caption, _ = platform_presentation.format_caption(components, platform="facebook")

    assert "\n\nbefore a trip\n\n" not in caption
    assert "The better question: How does this fit the real job?" in caption
    assert caption.count("154Wh") == 1
    assert "control control" not in caption


def test_product_sales_long_imported_detail_is_readable():
    components = _components()
    components["info"] = " ".join(["Source-backed product context"] * 30)

    caption, _ = platform_presentation.format_caption(components, platform="facebook")

    assert platform_presentation.evaluate(caption, platform="facebook")["reading_burden"] == "APPROPRIATE"
    assert len(caption.split("How to read those specs:", 1)[1].split("\n\n", 1)[0].split()) <= 50


def test_engagement_rejects_product_language_and_overpromising_cta():
    components = {
        "product_id": None,
        "funnel_stage": "ATTENTION",
        "product_name": "",
        "logic_hook": "If staying powered matters, waiting until power is gone is not a plan.",
        "situation": "The product gets picked before compatibility is mapped.",
        "logic_bridge": "The selected Infenergy product would have mattered.",
        "why_it_matters": "That gives you another product you hope will be useful.",
        "transformation": "A clear priority makes discussion easier.",
        "feature_bullets": [],
        "cta": "Tap the link to calculate your risk score in 60 seconds.",
    }

    caption, presentation = platform_presentation.format_caption(components, platform="facebook")

    assert "product" not in caption.lower()
    assert "infenergy" not in caption.lower()
    assert "risk score" not in caption.lower()
    assert "tap the link" not in caption.lower()
    assert "Share the first priority you would protect and why." in caption
    assert presentation["content_ideology"] == "earn_participation_through_relevance_not_bait"


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
    assert "PowerPulse Pro 200" in "\n\n".join(instagram["caption"].split("\n\n")[:3])


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


def test_final_caption_qa_rejects_internal_sales_process_language():
    caption = (
        "Meet PowerPulse Pro 200.\n\n"
        "Treat 154Wh as one verified input.\n\n"
        "For this topic, compare product-fit guidance.\n\n"
        "For you, that means confidence through better preparation.\n\n"
        "How does this help practical product-fit guidance?\n\n"
        "The practical context: a practical power decision."
    )
    verdict = platform_presentation.final_caption_qa(
        caption,
        platform="facebook",
        components=_components(),
    )

    assert verdict["status"] == "REVISE_PRESENTATION"
    assert "internal_instruction_leak" in verdict["reasons"]