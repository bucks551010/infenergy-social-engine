from __future__ import annotations

import importlib.util
import json
import os
import sys


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from business_intelligence.schemas import Offering
from business_intelligence import offerings
import generate_posts
from social import orchestrator


def _builder_module():
    path = os.path.join(SCRIPTS_DIR, "build_product_consumer_profiles.py")
    spec = importlib.util.spec_from_file_location("build_product_consumer_profiles", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_every_product_has_a_complete_consumer_profile():
    with open(os.path.join(REPO_ROOT, "data", "marketing", "product_consumer_profiles.json"), encoding="utf-8") as fh:
        catalog = json.load(fh)
    brief_paths = [name for name in os.listdir(os.path.join(REPO_ROOT, "data", "product_briefs")) if name.endswith(".json")]
    profiles = catalog["profiles"]

    assert len(profiles) == len(brief_paths)
    for product_id, profile in profiles.items():
        assert profile["product_id"] == product_id
        assert profile["positioning_statement"]
        assert profile["infenergy_reason_why"]
        assert profile["purchase_triggers"]
        assert profile["decision_criteria"]
        assert profile["objections"]
        assert profile["content_mandates"]
        assert profile["content_boundaries"]
        assert profile["primary_call_to_action"]
        assert profile["personas"]
        for persona in profile["personas"]:
            assert persona["identity"]
            assert persona["life_context"]
            assert persona["use_case"]
            assert persona["why_it_matters"]
            assert persona["desired_outcome"]
            assert persona["objections"]
            assert persona["message_angles"]
            assert persona["call_to_action"]


def test_use_case_matching_connects_persona_to_real_life_context():
    builder = _builder_module()
    uses = ["daily carry", "commuting", "travel", "small-device outage backup"]

    assert builder._choose_use_case("travelers", uses, 1) == "travel"
    assert builder._choose_use_case("commuters", uses, 0) == "commuting"
    assert builder._choose_use_case("households", ["camping", "home outage backup"], 0) == "home outage backup"


def test_selected_persona_is_preserved_in_product_strategy(monkeypatch):
    persona = {
        "name": "Mobile professionals",
        "identity": "mobile professionals",
        "life_context": "A client deadline continues while wall power is unavailable.",
        "problem": "Work stops when required devices cannot be powered.",
        "desired_outcome": "Keep the essential workflow moving.",
        "purchase_triggers": ["a missed deadline exposed the gap"],
        "objections": ["I am unsure it supports my devices"],
        "call_to_action": "Map your work devices before choosing capacity.",
    }
    offering = Offering(
        offering_id="TEST-POWER",
        offering_type="PRODUCT",
        name="Test Power Station",
        customer_fit=["mobile professionals"],
        verified_facts=["verified output"],
        consumer_profile={
            "infenergy_reason_why": "Keep real life moving with honestly matched capability.",
            "personas": [persona],
        },
    )
    selected = orchestrator._select_consumer_persona(offering.__dict__, "mobile professionals")

    assert selected == persona
    assert selected["life_context"].startswith("A client deadline")
    assert selected["call_to_action"].startswith("Map your work devices")


def test_real_profile_reaches_bi_offering_and_legacy_prompt():
    product = {"id": "catalog-row", "sku": "AF-S200", "name": "Aferiy Solar Panels - 200W"}
    legacy_context = generate_posts._product_consumer_context(product, "campers and RV users")
    prompt_context = generate_posts._product_consumer_prompt_context(legacy_context)
    af_s200 = next(item for item in offerings.build_from_csv() if item.sku == "AF-S200")

    assert legacy_context["profile"]["product_type"] == "solar_panel"
    assert legacy_context["persona"]["identity"] == "campers and RV users"
    assert legacy_context["persona"]["use_case"] == "camping and RV charging"
    assert "Write to exactly this one person" in prompt_context
    assert "Infenergy reason why" in prompt_context
    assert af_s200.consumer_profile == legacy_context["profile"]