from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(ROOT / "scripts"))


def test_constitution_is_valid_and_historical_language_is_not_public_copy() -> None:
    from business_intelligence.constitution import (
        compile_constitutional_context,
        validate_constitution_integrity,
    )

    validation = validate_constitution_integrity()
    context = compile_constitutional_context(
        segment_id="family_parent",
        moment_id="outage_or_power_interruption",
        job="help_prepare",
    )

    assert validation["valid"], validation["errors"]
    assert context["source_authority"] == "OWNER_CONSTITUTIONAL_TRUTH"
    assert context["audience_world"]["id"] == "family_parent"
    assert context["buying_moment"] == "outage_or_power_interruption"
    assert context["moment_world"]["id"] == "outage_or_power_interruption"
    assert context["moment_world"]["capability_goal"]
    assert context["content_job"] == "help_prepare"
    creation_logic = context["preemptive_creation_logic"]
    assert creation_logic["purpose"] == "Use Human Brain + Human Heart upstream to prevent weak, unsupported, repetitive, manipulative, product-forced, or emotionally incoherent content from being created in the first place."
    assert creation_logic["before_generation"]["brain_movement"]["acceptable_movements"] == ["NOTICE", "QUESTION", "UNDERSTAND", "DISTINGUISH", "REFRAME", "COMPARE", "PRIORITIZE", "RECONSIDER", "PLAN", "DECIDE", "DISCOVER"]
    assert creation_logic["preemptive_failure_patterns"]["PRODUCT_FIRST"]
    assert creation_logic["handling_rule"].startswith("These patterns should usually trigger premise improvement")
    assert [principle["id"] for principle in context["operating_principles"]] == [
        "moments_over_demographics",
        "responsibility_over_fear",
        "capability_over_gadgets",
        "relationship_over_transaction",
    ]
    assert context["approved_historical_language"] == []
    assert context["constitution_checksum"]
    assert context["manifesto_checksum"]


def test_manifesto_checksum_state_preserves_product_rows(tmp_path: Path) -> None:
    import inventory_db

    data_dir = os.fspath(tmp_path)
    inventory_db.init_inventory_db(data_dir)
    inventory_db.upsert_products(data_dir, [{"id": "product-1", "name": "Existing Product"}])
    inventory_db.upsert_brand_profile(data_dir, {"brand_name": "Before"})
    inventory_db.set_brand_profile_manifesto_checksum(data_dir, "before")

    inventory_db.upsert_brand_profile(data_dir, {"brand_name": "After", "mission": "Owner truth wins."})
    inventory_db.set_brand_profile_manifesto_checksum(data_dir, "after")

    assert inventory_db.get_brand_profile_manifesto_checksum(data_dir) == "after"
    assert inventory_db.fetch_brand_profile(data_dir)["brand_name"] == "After"
    assert inventory_db.products_count(data_dir) == 1


def test_changed_manifesto_propagates_without_replacing_catalog(tmp_path: Path, monkeypatch) -> None:
    import generate_posts
    import inventory_db

    data_dir = os.fspath(tmp_path)
    inventory_db.init_inventory_db(data_dir)
    inventory_db.upsert_products(data_dir, [{"id": "product-1", "name": "Existing Product"}])
    monkeypatch.setattr(generate_posts, "DATA_DIR", data_dir)
    strategy = {"brand": {}, "founder": {}, "voice": {}}
    first = {
        "brand_name": "Infenergy Power",
        "mission": "Prepare with clarity.",
        "business_profile": {"positioning": "Personal power preparedness"},
        "brand_personality": {"voice_name": "Calm Strength"},
    }
    second = {**first, "mission": "Prepare with calm, practical clarity."}

    initial_seeded, initial_changed, _ = generate_posts._sync_manifesto_brand_profile(first, strategy)
    changed_seeded, changed, affected_fields = generate_posts._sync_manifesto_brand_profile(second, strategy)

    assert initial_seeded is True
    assert initial_changed is True
    assert changed_seeded is True
    assert changed is True
    assert "mission" in affected_fields
    assert inventory_db.fetch_brand_profile(data_dir)["mission"] == second["mission"]
    assert inventory_db.products_count(data_dir) == 1


def test_weather_radar_parent_compiles_as_a_responsibility_moment() -> None:
    from business_intelligence.constitution import compile_constitutional_context

    context = compile_constitutional_context(
        segment_id="family_parent",
        moment_id="weather_forecast_changes",
        job="help_plan",
    )

    moment = context["moment_world"]
    assert moment["person"] == "A parent watching a changing weather forecast in the evening."
    assert "phones, flashlights, refrigerator, children" in moment["decision_state"]
    assert moment["responsibility"]
    assert moment["capability_goal"]
    assert moment["product_role"] == "optional_or_downstream"


def test_constitution_resolves_live_language_to_a_canonical_moment() -> None:
    from business_intelligence.constitution import resolve_moment_id

    assert resolve_moment_id("Can this work with my laptop port?") == "device_compatibility_question"
    assert resolve_moment_id("A traveler without a dependable outlet") == "limited_outlet_access_for_work_or_school"


def test_human_connection_review_reports_brain_and_heart_outcomes() -> None:
    from social.human_connection_review import review

    result = review(
        strategy={
            "customer_moment": "weather forecast",
            "human_need": "clarity",
            "benefit": "prioritize essentials",
            "human_connection": {
                "moment_world": {
                    "person": "A parent watching a changing weather forecast in the evening.",
                    "decision_state": "Checking phones and flashlights before pressure arrives.",
                    "responsibility": "Decide what deserves attention.",
                    "human_question": "What would we actually need to keep working?",
                }
            },
        },
        copy={
            "hook": "What should you check before a changing weather forecast becomes urgent?",
            "body": "First, prioritize phones and flashlights so you can decide what matters before pressure arrives.",
        },
        visual={"scene": "A parent checking phones and flashlights before evening weather changes."},
    )

    assert result["human_brain"]["passed"] is True
    assert result["human_heart"]["passed"] is True
    assert result["human_heart"]["fear_tactics"] == []
    assert result["preemptive_recovery_guidance"]["terminal_gate"] is False