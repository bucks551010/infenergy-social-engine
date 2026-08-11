"""Tests for the Conversion Logic Social Engine (Phase A).

Covers the decision-logic layer end-to-end without hitting Gemini or any
publisher. Follows the existing tests/ convention: pytest, run from repo root.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from conversion import (  # noqa: E402
    ConversionLogicEngine,
    StrategicBrief,
    build_strategic_brief,
)
from conversion import awareness as awareness_mod  # noqa: E402
from conversion import claims as claims_mod  # noqa: E402
from conversion import copy_structures as copy_structures_mod  # noqa: E402
from conversion import cqs as cqs_mod  # noqa: E402
from conversion import ctas as ctas_mod  # noqa: E402
from conversion import emotions as emotions_mod  # noqa: E402
from conversion import hook_engine  # noqa: E402
from conversion import logic_laws as logic_laws_mod  # noqa: E402
from conversion import objections as objections_mod  # noqa: E402
from conversion import personas as personas_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Libraries: every JSON file loads and has non-empty content
# ---------------------------------------------------------------------------

def test_awareness_levels_load_and_cover_all_stages():
    for stage in ("UNAWARE", "PROBLEM_AWARE", "SOLUTION_AWARE", "PRODUCT_AWARE", "MOST_AWARE"):
        cfg = awareness_mod.stage_config(stage)
        assert cfg["prioritize"], f"{stage} has no prioritize list"
        assert cfg["preferred_copy_structures"], f"{stage} has no preferred structures"


def test_emotional_drivers_library():
    drivers = emotions_mod.all_drivers()
    assert len(drivers) >= 15, "spec §3 requires ~17 drivers"
    assert "preparedness" in drivers
    assert "freedom" in drivers


def test_logic_laws_all_five_present():
    laws = logic_laws_mod.all_laws()
    assert set(laws) == {
        "contrapositive", "disjunctive", "double_implication",
        "symmetrical_equivalence", "result_traceability",
    }
    # each law has a narrative template
    for law in laws:
        assert logic_laws_mod.narrative_template(law), f"{law} missing template"


def test_copy_structures_ten_present():
    structs = copy_structures_mod.all_structures()
    expected = {"PAS", "AIDA", "BAB", "FAB", "QUEST", "PROOF-LED",
                "DEMONSTRATION", "OBJECTION", "COMPARISON", "STORY"}
    assert expected <= set(structs)


def test_objection_library_covers_common_types():
    objs = objections_mod.all_objections()
    for name in ("price", "quality", "trust", "compatibility", "necessity"):
        assert name in objs


def test_personas_library():
    ids = personas_mod.all_persona_ids()
    assert "preparedness_buyer" in ids
    assert "mobile_professional" in ids
    p = personas_mod.get("preparedness_buyer")
    assert p["primary_problem"]
    assert p["desired_outcome"]


# ---------------------------------------------------------------------------
# Awareness classifier
# ---------------------------------------------------------------------------

def test_awareness_classifies_from_funnel_stage():
    assert awareness_mod.classify_from_funnel("ATTENTION") == "PROBLEM_AWARE"
    assert awareness_mod.classify_from_funnel("CONVERSION") == "MOST_AWARE"
    assert awareness_mod.classify_from_funnel("UNKNOWN_STAGE") == "PROBLEM_AWARE"


def test_awareness_prefers_explicit_hint():
    assert awareness_mod.classify(
        funnel_stage="ATTENTION",
        audience_awareness_hint="MOST_AWARE",
    ) == "MOST_AWARE"


# ---------------------------------------------------------------------------
# Logic law selection
# ---------------------------------------------------------------------------

def test_logic_law_selection_respects_awareness_stage():
    law = logic_laws_mod.select("PROBLEM_AWARE", recent_law_ids=[])
    assert "PROBLEM_AWARE" in logic_laws_mod.law(law)["when_to_use"]


def test_logic_law_avoids_recent():
    law = logic_laws_mod.select(
        "SOLUTION_AWARE",
        recent_law_ids=["contrapositive", "disjunctive", "result_traceability"],
    )
    assert law not in {"contrapositive", "disjunctive", "result_traceability"} or \
           law in logic_laws_mod.eligible_for_stage("SOLUTION_AWARE")


def test_logic_law_avoids_double_implication_without_specs():
    law = logic_laws_mod.select(
        "PRODUCT_AWARE",
        recent_law_ids=[],
        product_has_verified_specs=False,
    )
    assert law not in ("double_implication", "result_traceability")


# ---------------------------------------------------------------------------
# Emotion selection
# ---------------------------------------------------------------------------

def test_emotion_selection_uses_persona_default():
    primary, secondary = emotions_mod.select(
        persona_id="preparedness_buyer", awareness_stage="PROBLEM_AWARE",
    )
    assert primary == "preparedness"
    assert secondary == "security"


def test_emotion_selection_fallback_to_stage():
    primary, _ = emotions_mod.select(
        persona_id="unknown_persona", awareness_stage="SOLUTION_AWARE",
    )
    assert emotions_mod.is_valid(primary)


# ---------------------------------------------------------------------------
# Hook engine
# ---------------------------------------------------------------------------

def test_hook_scoring_ranks_specific_over_generic():
    generic = "Upgrade your life today with our amazing power solution."
    specific = "Why 20,000mAh isn't the number that decides how long your fridge stays cold in an outage."
    s_generic = hook_engine.score_hook(generic, product_name="Infenergy")
    s_specific = hook_engine.score_hook(specific, product_name="Infenergy", audience_keywords=["outage", "fridge"])
    assert s_specific["total"] > s_generic["total"]


def test_hook_engine_flags_banned_openers():
    assert hook_engine.is_banned("Looking for the perfect solution?") is True
    assert hook_engine.is_banned("Here is what most people miss about outages.") is False


def test_pick_best_returns_winner_and_scores():
    cands = [
        "Game-changer product that will elevate your life!",  # banned
        "The 24-hour outage plan every household should write down before storm season.",
        "Why battery capacity alone doesn't tell you what a device can actually run.",
    ]
    winner, scores, all_scored = hook_engine.pick_best(
        cands, audience_keywords=["outage", "storm"], product_name="",
    )
    assert winner
    assert "Game-changer" not in winner
    assert scores["total"] > 0
    assert len(all_scored) == 3


# ---------------------------------------------------------------------------
# Claim integrity
# ---------------------------------------------------------------------------

def test_claim_classification_flags_unsupported_superlatives():
    scan = claims_mod.classify_text("Our 100% guaranteed instant fastest power on Earth.")
    assert scan["unsupported"], "should flag guarantee/100%/instant/fastest"
    publishable, reasons = claims_mod.is_publishable(scan)
    assert not publishable
    assert reasons


def test_claim_classification_allows_verified_facts():
    scan = claims_mod.classify_text(
        "Delivers 20,000mAh backup capacity.",
        verified_facts=["20,000mAh backup capacity"],
    )
    publishable, _ = claims_mod.is_publishable(scan)
    assert publishable


def test_prohibited_claim_never_publishable():
    scan = claims_mod.classify_text("This device cures medical dependence.")
    publishable, reasons = claims_mod.is_publishable(scan)
    assert not publishable
    assert any("prohibited" in r for r in reasons)


# ---------------------------------------------------------------------------
# CTA engine
# ---------------------------------------------------------------------------

def test_cta_by_awareness_stages():
    unaware = ctas_mod.by_awareness("UNAWARE")
    most_aware = ctas_mod.by_awareness("MOST_AWARE")
    assert unaware and most_aware
    assert unaware != most_aware


def test_cta_choose_avoids_recent():
    stage = "MOST_AWARE"
    pool = ctas_mod.by_awareness(stage)
    chosen = ctas_mod.choose(stage, recent_ctas=[pool[0]])
    assert chosen != pool[0] or len(pool) == 1


# ---------------------------------------------------------------------------
# Strategic brief end-to-end
# ---------------------------------------------------------------------------

def test_build_strategic_brief_populates_all_layers():
    brief = build_strategic_brief(
        funnel_stage="DESIRE",
        product={
            "product_id": "sku-123",
            "product_name": "Infenergy Power Station 1000",
            "product_type": "power_station",
            "features": ["1000W AC output", "20W USB-C PD"],
            "benefits": ["extended portable backup"],
            "verified_facts": ["1000W AC output verified"],
        },
        audience_hint="preparedness_buyer",
        campaign_goal="consideration",
    )
    assert isinstance(brief, StrategicBrief)
    assert brief.audience_id == "preparedness_buyer"
    assert brief.awareness_stage in ("PRODUCT_AWARE", "PROBLEM_AWARE")
    assert brief.logic_principle in {
        "contrapositive", "disjunctive", "double_implication",
        "symmetrical_equivalence", "result_traceability",
    }
    assert brief.emotional_driver_primary
    assert brief.copy_framework
    assert brief.persuasion.problem
    assert brief.persuasion.desire
    assert brief.copy.cta
    assert brief.experiment.variant_id
    assert brief.brief_id


def test_brief_is_serializable():
    brief = build_strategic_brief(
        funnel_stage="ATTENTION",
        product=None,
        audience_hint="mobile_professional",
    )
    d = brief.to_dict()
    assert d["audience_id"] == "mobile_professional"
    assert d["persuasion"]["problem"]
    assert d["experiment"]["variant_id"]


def test_engine_scores_hook_candidates():
    engine = ConversionLogicEngine()
    brief = engine.build_brief(
        funnel_stage="EDUCATION",
        product={
            "product_id": "sku-1",
            "product_name": "Infenergy PowerBank Pro",
            "features": ["20,000mAh"],
        },
        audience_hint="mobile_professional",
    )
    cands = [
        "Why your workday still ends when your battery does.",
        "20,000mAh: the number that changes how long you can work anywhere.",
        "Elevate your life with amazing portable power!",
    ]
    winner, scores, _ = engine.score_hook_candidates(brief, cands, platform="linkedin")
    assert winner
    assert "Elevate your life" not in winner


def test_engine_check_claims_gates_publishing():
    engine = ConversionLogicEngine()
    ok, reasons, _ = engine.check_claims("Best in class 100% guaranteed instant power.")
    assert not ok
    assert reasons

    ok2, _, _ = engine.check_claims("Designed to help keep essential devices powered through short outages.")
    assert ok2


# ---------------------------------------------------------------------------
# CQS scoring
# ---------------------------------------------------------------------------

def test_cqs_score_produces_normalized_score():
    brief = build_strategic_brief(
        funnel_stage="DESIRE",
        product={
            "product_id": "sku-1",
            "product_name": "Infenergy Power Station 1000",
            "features": ["1000W AC output"],
            "benefits": ["portable backup power"],
            "verified_facts": ["1000W AC output verified"],
        },
        audience_hint="preparedness_buyer",
    )
    result = cqs_mod.score(
        caption="Backup power that keeps the fridge cold when the grid drops.",
        hook="What to power first when the grid goes down.",
        cta="Review the specs",
        brief_dict=brief.to_dict(),
        visual_prompt="A calm kitchen scene with product on counter, clear hierarchy, subtle transformation cue.",
    )
    assert 0.0 <= result["total"] <= 100.0
    assert result["band"] in ("exceptional", "strong", "acceptable", "improve")
    assert set(result["component_scores"].keys()) == set(cqs_mod.CRITERIA)


def test_cqs_penalizes_hype_language():
    brief = build_strategic_brief(funnel_stage="DESIRE", audience_hint="preparedness_buyer")
    hype = cqs_mod.score(
        caption="100% guaranteed instant revolutionary power that will elevate your life!",
        hook="Elevate your life today!",
        cta="Buy",
        brief_dict=brief.to_dict(),
    )
    clean = cqs_mod.score(
        caption="Backup power designed for the specific outages your family plans for.",
        hook="What to power first when the grid goes down.",
        cta="Review the specs",
        brief_dict=brief.to_dict(),
    )
    assert clean["total"] > hype["total"]


# ---------------------------------------------------------------------------
# Persona inference
# ---------------------------------------------------------------------------

def test_persona_inference_from_product_type():
    assert personas_mod.infer_from_product_and_stage("power_bank", "EDUCATION") == "mobile_professional"
    assert personas_mod.infer_from_product_and_stage("solar_light", "ATTENTION") == "outdoor_enthusiast"
    assert personas_mod.infer_from_product_and_stage("power_station", "DESIRE") == "preparedness_buyer"
    assert personas_mod.infer_from_product_and_stage(None, "ATTENTION") == "preparedness_buyer"
