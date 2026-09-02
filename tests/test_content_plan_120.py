from __future__ import annotations

import json
import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from content_plan_120 import build_120_day_plan  # noqa: E402
from social_engine.intelligence_os.web import handle  # noqa: E402


def _write_profiles(data_dir, count: int = 8) -> None:
    marketing = data_dir / "marketing"
    marketing.mkdir(parents=True)
    profiles = {
        f"PRODUCT-{index:02d}": {
            "product_name": f"Product {index}",
            "product_type": "portable_power",
            "market_role": f"role {index}",
            "primary_promise": f"promise {index}",
            "core_customer_truth": f"truth {index}",
            "primary_call_to_action": f"compare product {index}",
            "personas": [{"name": f"Persona {index}", "use_case": f"use case {index}"}],
        }
        for index in range(count)
    }
    (marketing / "product_consumer_profiles.json").write_text(
        json.dumps({"profiles": profiles}),
        encoding="utf-8",
    )


def test_plan_covers_catalog_and_never_creates_generation_artifacts(tmp_path):
    _write_profiles(tmp_path, count=12)

    plan = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )

    assert plan["status"] == "TEXT_PREVIEW_READY"
    assert plan["mode"] == "TEXT_ONLY"
    assert plan["concept_count"] == 120
    assert plan["catalog_products_used"] == plan["catalog_size"] == 12
    assert plan["catalog_coverage_complete"] is True
    assert plan["image_generation_enabled"] is False
    assert plan["image_count"] == 0
    assert not (tmp_path / "public_media").exists()
    assert not (tmp_path / "inventory.db").exists()
    assert len({entry["date"] for entry in plan["entries"]}) == 120
    assert plan["date_coverage"] == {
        "expected_days": 120,
        "planned_days": 120,
        "continuous": True,
    }
    assert all(entry["production_status"] == "CONCEPT_ONLY" for entry in plan["entries"])
    assert all(entry["image_status"] == "NOT_GENERATED" for entry in plan["entries"])
    assert all(entry["generation_prompts"] == [] for entry in plan["entries"])
    assert all(entry["media_assets"] == [] for entry in plan["entries"])


def test_plan_preserves_intervention_cadence_and_continuous_format_rotation(tmp_path):
    _write_profiles(tmp_path)

    plan = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )
    interventions = [
        entry for entry in plan["entries"]
        if entry["series"] == "Infenergy Intervention"
    ]

    assert len(interventions) == 34
    assert all(
        (entry["weekday"], entry["slot"]) in {
            ("Tuesday", "midday"),
            ("Friday", "morning"),
        }
        for entry in interventions
    )
    assert [entry["installment"] for entry in interventions] == list(range(1, 35))
    friday_interventions = [entry for entry in interventions if entry["weekday"] == "Friday"]
    tuesday_interventions = [entry for entry in interventions if entry["weekday"] == "Tuesday"]
    assert all(entry["format"] == "product_micro_mission_comic" for entry in friday_interventions)
    assert all(entry["format"] != "product_micro_mission_comic" for entry in tuesday_interventions)
    assert {entry["format"] for entry in tuesday_interventions} == {
        "cinematic_brand_poster",
        "educational_story_carousel",
    }
    assert all(entry["canon_required"] for entry in interventions)
    superhero_posts = [
        entry for entry in interventions
        if entry["format"] == "product_micro_mission_comic"
    ]
    assert plan["superhero_with_text_count"] == len(superhero_posts) == 17
    assert all(entry["format_label"] == "Superhero with text" for entry in superhero_posts)
    assert all(entry["visible_text"]["headline"] for entry in superhero_posts)
    assert all(entry["visible_text"]["infenergy_line"] for entry in superhero_posts)
    assert all(entry["visible_text"]["resolution_line"] for entry in superhero_posts)
    assert all(entry["delivery_label"] == "Product Story comic strip" for entry in superhero_posts)
    assert all(entry["platform"] == "instagram_story" for entry in superhero_posts)
    assert all(entry["aspect_ratio"] == "9:16" for entry in superhero_posts)
    assert all(entry["canvas_px"] == {"width": 1080, "height": 1920} for entry in superhero_posts)
    assert all(entry["canvas_count"] == 1 for entry in superhero_posts)
    assert all(entry["panel_count"] == 3 for entry in superhero_posts)
    assert all(entry["layout"] == "single_vertical_comic_strip" for entry in superhero_posts)
    assert all(entry["product_required"] is True for entry in superhero_posts)
    assert all(entry["product_id"] == entry["product"]["product_id"] for entry in superhero_posts)
    assert all(entry["product_name"] == entry["product"]["product_name"] for entry in superhero_posts)
    assert all(entry["product_reference_required"] is True for entry in superhero_posts)
    assert all(entry["product_integration"]["required"] is True for entry in superhero_posts)
    assert all("Removing the product" in entry["product_integration"]["plot_test"] for entry in superhero_posts)
    assert all(entry["product_name"] in entry["story_sequence"][2] for entry in superhero_posts)
    assert len({entry["entertainment_mode"] for entry in superhero_posts}) == 6
    assert all(entry["entertainment_hook"] and entry["visual_reveal"] for entry in superhero_posts)
    assert 0 < sum(entry["humor_enabled"] for entry in superhero_posts) < len(superhero_posts)
    assert all("never the customer" in entry["humor_guardrail"] for entry in superhero_posts)
    assert all(len(entry["story_sequence"]) == 3 for entry in superhero_posts)
    assert all(
        any("not a carousel" in constraint for constraint in entry["delivery_constraints"])
        for entry in superhero_posts
    )
    assert all(
        any("affect the plot" in constraint for constraint in entry["delivery_constraints"])
        for entry in superhero_posts
    )
    assert all(entry["image_status"] == "NOT_GENERATED" for entry in superhero_posts)


def test_weekly_company_quotes_are_verbatim_sourced_and_audience_matched(tmp_path):
    _write_profiles(tmp_path)
    plan = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )
    with open("data/marketing/infenergy_company_knowledge.json", "r", encoding="utf-8") as handle:
        knowledge = json.load(handle)
    statements = {
        message["id"]: message["statement"]
        for message in knowledge["super_message_library"]
    }
    quotes = [
        entry for entry in plan["entries"]
        if entry["format"] == "infenergy_company_quote_visual"
    ]

    assert plan["weekly_company_quote_count"] == len(quotes) == 17
    assert plan["company_super_message_bank_count"] == len(statements) == 52
    assert len(statements.values()) == len(set(statements.values()))
    assert all(len(statement.split()) <= 12 for statement in statements.values())
    assert all(entry["weekday"] == "Sunday" for entry in quotes)
    assert len({entry["company_source"]["message_id"] for entry in quotes}) == len(quotes)
    assert all(entry["verbatim_company_quote"] is True for entry in quotes)
    assert all(entry["company_source"]["knowledge_id"] == knowledge["knowledge_id"] for entry in quotes)
    assert all(
        entry["exact_visible_text"] == [statements[entry["company_source"]["message_id"]]]
        for entry in quotes
    )
    assert all(entry["company_source"]["support_thought_id"].startswith("T") for entry in quotes)
    assert all(len(entry["exact_visible_text"][0].split()) <= 12 for entry in quotes)
    assert all(entry["support_statement"] != entry["exact_visible_text"][0] for entry in quotes)
    expected_audiences = {
        "mobile_professional": "mobile_professional",
        "outdoor_enthusiast": "outdoor",
        "caregiver": "caregiver",
        "small_business_operator": "mobile_professional",
        "preparedness_buyer": "preparedness_builder",
    }
    assert all(
        entry["company_source"]["audience"] == expected_audiences[entry["audience_id"]]
        for entry in quotes
    )
    assert all(entry["aspect_ratio"] == "4:5" for entry in quotes)
    assert all(entry["canvas_px"] == {"width": 1080, "height": 1350} for entry in quotes)
    assert all(entry["canvas_count"] == 1 for entry in quotes)
    assert all(entry["layout"] == "single_frame_integrated_typography" for entry in quotes)
    assert all(entry["integrated_typography"] is True for entry in quotes)
    assert all(entry["canon_required"] is True for entry in quotes)
    assert all(entry["character"] == "Infenergy" for entry in quotes)
    assert all(entry["image_status"] == "NOT_GENERATED" for entry in quotes)


def test_plan_uses_bundled_verified_catalog_when_runtime_volume_is_empty(tmp_path):
    plan = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )

    assert plan["catalog_size"] > 0
    assert all(
        entry["product_id"] and entry["product_name"]
        for entry in plan["entries"]
        if entry["format"] == "product_micro_mission_comic"
    )


def test_plan_uses_bundled_company_messages_when_runtime_copy_is_stale(tmp_path):
    marketing_dir = tmp_path / "marketing"
    marketing_dir.mkdir()
    (marketing_dir / "infenergy_company_knowledge.json").write_text(
        json.dumps({"knowledge_id": "stale-volume-copy", "thought_library": []}),
        encoding="utf-8",
    )

    plan = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )

    quotes = [
        entry for entry in plan["entries"]
        if entry["format"] == "infenergy_company_quote_visual"
    ]
    assert len(quotes) == 17
    assert all(entry["company_source"]["knowledge_id"] == "infenergy-company-truth" for entry in quotes)


def test_plan_exposes_progressively_adaptive_horizons(tmp_path):
    _write_profiles(tmp_path)

    entries = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )["entries"]

    assert entries[13]["state"] == "LOCKED"
    assert entries[14]["state"] == "SHAPED"
    assert entries[29]["state"] == "SHAPED"
    assert entries[30]["state"] == "ADAPTIVE"
    assert entries[59]["state"] == "ADAPTIVE"
    assert entries[60]["state"] == "DIRECTIONAL"
    assert entries[89]["state"] == "DIRECTIONAL"
    assert entries[90]["state"] == "OPPORTUNITY"


def test_plan_is_driven_by_consumer_psychographics_and_funnel_strategy(tmp_path):
    _write_profiles(tmp_path)

    plan = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )
    entries = plan["entries"]

    assert {entry["audience_id"] for entry in entries} == {
        "caregiver",
        "mobile_professional",
        "outdoor_enthusiast",
        "preparedness_buyer",
        "small_business_operator",
    }
    assert {entry["creative_territory"] for entry in entries} == {
        "Care Without Chaos",
        "Freedom, Designed",
        "Never Miss the Moment",
        "Prepared, Not Precious",
        "Range Is a Feeling",
    }
    assert {stage: sum(entry["funnel_stage"] == stage for entry in entries) for stage in {
        "ATTENTION", "EDUCATION", "DESIRE", "TRUST", "CONVERSION",
    }} == {
        "ATTENTION": 24,
        "EDUCATION": 36,
        "DESIRE": 30,
        "TRUST": 18,
        "CONVERSION": 12,
    }
    assert all(entry["demographic_lens"] for entry in entries)
    assert all(entry["psychographic"] for entry in entries)
    assert all(entry["consumer_desire"] for entry in entries)
    assert all(entry["identity_signal"] for entry in entries)
    assert all(entry["transformation"]["from"] != entry["transformation"]["to"] for entry in entries)
    assert all(entry["brain_movement"] and entry["heart_after"] for entry in entries)
    assert all(entry["primary_platform"] and entry["platform_treatment"] for entry in entries)
    assert not {"Readiness Myth Lab", "One Honest Job", "Saturday Field Test"} & {
        entry["series"] for entry in entries
    }


def test_plan_includes_the_complete_editorial_post_type_taxonomy(tmp_path):
    _write_profiles(tmp_path)

    plan = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )

    expected_types = {
        "current_event",
        "product_education",
        "statement",
        "humor",
        "framework",
        "micro_story",
        "explainer",
        "drill",
        "myth",
    }
    assert set(plan["post_type_taxonomy"]) == expected_types
    assert set(plan["post_type_counts"]) == expected_types
    assert all(count > 0 for count in plan["post_type_counts"].values())
    assert {entry["post_type"] for entry in plan["entries"]} == expected_types
    assert all(entry["post_type_label"] for entry in plan["entries"])
    assert all(
        entry["title"].startswith("Myth Check:") and entry["hook"].startswith("Myth:")
        for entry in plan["entries"]
        if entry["post_type"] == "myth"
    )
    assert all(
        "verified, current source" in entry["story"]
        for entry in plan["entries"]
        if entry["post_type"] == "current_event"
    )
    assert all(
        entry["title"].startswith("The 3-Part Framework:")
        for entry in plan["entries"]
        if entry["post_type"] == "framework"
    )
    assert all(
        entry["title"].startswith("60-Second Drill:")
        for entry in plan["entries"]
        if entry["post_type"] == "drill"
    )


def test_plan_matches_specialized_products_to_relevant_arcs(tmp_path):
    marketing = tmp_path / "marketing"
    marketing.mkdir(parents=True)
    product_types = {
        "bike": "electric_bike",
        "fan": "portable_fan",
        "solar": "solar_panel",
        "system": "power_system_bundle",
        "water": "portable_water_filter",
    }
    profiles = {
        product_id: {
            "product_name": product_id.title(),
            "product_type": product_type,
            "market_role": f"verified {product_type} role",
            "personas": [{"name": "Matched customer", "use_case": product_type}],
        }
        for product_id, product_type in product_types.items()
    }
    (marketing / "product_consumer_profiles.json").write_text(
        json.dumps({"profiles": profiles}),
        encoding="utf-8",
    )

    entries = build_120_day_plan(
        data_dir=str(tmp_path),
        start_date="2026-09-02",
    )["entries"]
    arcs_by_product = {product_id: set() for product_id in product_types}
    for entry in entries:
        product = entry.get("product")
        if product:
            arcs_by_product[product["product_id"]].add(entry["weekly_arc"])

    expected_arcs = {
        "bike": "Roadside Plot Twist",
        "fan": "Soft Life, Hard Backup",
        "solar": "Sun Chaser Math",
        "system": "Big Energy, Better Taste",
        "water": "Water Has Main-Character Stakes",
    }
    assert all(arc in arcs_by_product[product_id] for product_id, arc in expected_arcs.items())


def test_os_content_plan_route_is_text_only_and_read_only(tmp_path):
    _write_profiles(tmp_path)

    status, content_type, body = handle(
        "POST",
        "/api/os/content-plan",
        {"start_date": "2026-09-02", "days": 120},
        str(tmp_path),
    )
    result = json.loads(body)

    assert status == 200
    assert content_type == "application/json; charset=utf-8"
    assert result["status"] == "TEXT_PREVIEW_READY"
    assert result["concept_count"] == 120
    assert result["image_count"] == 0
    assert not (tmp_path / "public_media").exists()
    assert not (tmp_path / "inventory.db").exists()