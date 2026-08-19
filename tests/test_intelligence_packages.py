from __future__ import annotations

import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import intelligence_packages  # noqa: E402
import inventory_db  # noqa: E402
from content_operations import ensure_daily_slots  # noqa: E402
from social.blocker_transformation_registry import registry, transformation_for  # noqa: E402


def _seed_data(tmp_path):
    data_dir = str(tmp_path)
    os.makedirs(tmp_path / "marketing" / "human_truth", exist_ok=True)
    os.makedirs(tmp_path / "social", exist_ok=True)
    constitution = {
        "source_authority_order": ["OWNER_CONSTITUTIONAL_TRUTH", "OWNED_VERIFIED_FACT", "SYSTEM_HYPOTHESIS"],
        "core_mandates": [{"id": "truth", "text": "Truth before hype"}],
        "founder_origin": {"summary": "Power became personal during an outage."},
        "worldview": {"business_role": "Help people build practical capability."},
        "reputation_destination": "A trusted source for power decisions.",
        "voice": {"name": "Calm Strength", "anti_language": ["guaranteed safety"]},
        "trust_boundaries": {"fear_rule": "Never manufacture fear."},
        "content_jobs": ["teach", "help_plan"],
        "moment_worlds": [{
            "id": "outage_moment",
            "person": "A household hearing the house become quiet.",
            "decision_state": "Normal routines need a plan.",
            "responsibility": "Prioritize clearly.",
            "human_question": "What matters first?",
            "capability_goal": "Know what can be done next.",
            "product_role": "optional_or_downstream",
        }],
        "scene_library": [{"id": "home_scene", "product_role": "optional_or_downstream", "setting": "lived-in home"}],
    }
    audience = {"segments": {"household": {
        "name": "Household", "problems": ["outages"], "questions": ["what matters"],
        "goals": ["continuity"], "decisions": ["priorities"], "objections": ["cost"],
        "lifestyle_context": ["home"], "emotional_drivers": ["clarity"], "purchase_context": ["before storms"],
    }}}
    creative = {
        "brand_colors": {"primary": "#000000"},
        "photography_style": {"mood_words": ["honest"]},
        "must_avoid_in_generated_imagery": ["generic AI poster"],
    }
    (tmp_path / "marketing" / "human_truth" / "constitution.json").write_text(json.dumps(constitution), encoding="utf-8")
    (tmp_path / "social" / "audience_world.json").write_text(json.dumps(audience), encoding="utf-8")
    (tmp_path / "social" / "brand_design_tokens.json").write_text(json.dumps(creative), encoding="utf-8")
    (tmp_path / "social" / "living_intelligence.json").write_text(json.dumps({"campaign_state": {"decision": "ignore"}}), encoding="utf-8")
    inventory_db.init_inventory_db(data_dir)
    inventory_db.upsert_brand_profile(data_dir, {"brand_name": "Infenergy Power", "mission": "Help people prepare", "positioning": "trusted guidance"})
    inventory_db.upsert_products(data_dir, [{
        "id": "PPP-200", "name": "PowerPulse Pro 200", "product_url": "https://example.com/powerpulse",
        "metrics": ["154Wh", "200W"], "fact_snippet": "Published 154Wh capacity.",
        "image_url": "https://example.com/powerpulse.jpg", "image_candidates": ["https://example.com/powerpulse.jpg"],
        "categories": ["Portable Power"], "in_stock": "true",
    }])
    ensure_daily_slots(data_dir, "2026-08-20", {
        "morning": "2026-08-20T13:00:00+00:00",
        "midday": "2026-08-20T17:00:00+00:00",
        "evening": "2026-08-20T23:00:00+00:00",
    }, {"source": "owner_schedule"})
    return data_dir


def test_compiler_populates_required_intelligence_packages_and_reserve(tmp_path):
    data_dir = _seed_data(tmp_path)
    coverage = intelligence_packages.compile_packages(data_dir)

    required_types = {
        "BUSINESS_CONSTITUTION", "AUDIENCE_WORLD", "PRODUCT_INTELLIGENCE",
        "PRODUCT_VISUAL_TRUTH", "TRUTH_CABINET", "CONTENT_READINESS",
        "BRAND_CREATIVE_GRAMMAR", "PLATFORM_PRESENTATION", "CAMPAIGN_CONTINUITY",
        "DAILY_SLOT", "BLOCKER_TRANSFORMATION_REGISTRY",
    }
    assert required_types.issubset(set(coverage["package_types"]))
    assert coverage["ready_reserve_available"] >= 1
    assert coverage["counts"]["COMPLETE"] >= 10
    assert intelligence_packages.ready_reserve(data_dir)[0]["human_realities"]


def test_blocker_registry_maps_old_vetoes_to_nonterminal_specialists():
    records = registry()
    assert len(records) >= 10
    assert transformation_for("duplicate_exact_caption")["owner"] == "FRESHNESS_NAVIGATOR"
    assert transformation_for("runtime quality below floor")["owner"] == "QUALITY_DOCTOR"
    assert transformation_for("packshot visual failure")["owner"] == "CREATIVE_RECOVERY_SPECIALIST"
    assert all(record["may_stop_content_creation"] is False for record in records)
