from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_posts
from social import (
    claim_intelligence,
    libraries,
    living_intelligence,
    orchestrator,
    platform_presentation,
    publish_decision,
    quality_intelligence,
)


def _production_state():
    question = "Can your current power source support your laptop during travel?"
    facts = ["154Wh", "41,600mAh", "200W", "110V AC"]
    narrative = living_intelligence.product_expression_for_engine_a(
        campaign={},
        reader_job="HELP_ME_CHOOSE",
        question=question,
        human_reality="a mobile professional preparing before travel",
        practical_value="Compare the device requirement, output, connection, and reserve in that order.",
        takeaway="Check fit before capacity.",
        verified_facts=facts,
        product_name="PowerPulse Pro 200",
    )
    return question, facts, narrative


def test_engine_a_product_expression_uses_light_fit_demonstration():
    question, _, narrative = _production_state()

    assert narrative["role"] == "FIT_DEMONSTRATION"
    assert narrative["commercial_intensity"] == "LIGHT"
    assert narrative["cta_class"] == "COMPARE"
    assert narrative["product_entry_question"] == question


def test_engine_a_decision_support_caption_teaches_before_product_proof():
    question, facts, narrative = _production_state()
    components = generate_posts._build_post_components(
        topic="Power Stations",
        selected_hook=question,
        selected_cta="Compare options",
        product={
            "id": "PPP-200",
            "name": "PowerPulse Pro 200",
            "metrics": facts,
            "categories": ["Portable Power"],
        },
        funnel_stage="EDUCATION",
        product_narrative=narrative,
    )
    caption, _ = platform_presentation.format_caption(components, platform="facebook")

    assert "Start with the device's actual power requirement" in caption
    assert caption.index("Start with the device's actual power requirement") < caption.index("PowerPulse Pro 200")
    assert "emergency kit" not in caption.lower()
    assert "vehicle" not in caption.lower()
    assert "capable of sustaining professional devices" not in caption.lower()
    assert "standard phone bank might struggle" not in caption.lower()
    assert "154Wh" in caption and "200W" in caption and "110V AC" in caption
    assert components["product_narrative"]["commercial_intensity"] == "LIGHT"


def test_final_critic_remains_authoritative_over_legacy_score():
    decision = publish_decision.decide(
        legacy_score={"total": 97.0, "decision": "approve", "component_scores": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=100.0,
        orchestrator_quality={
            "overall": 78.08,
            "critic_findings": ["hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"],
        },
    )

    assert decision["publishable"] is False
    assert decision["decision"] == "revise"


def test_critic_score_at_threshold_after_operational_rounding_publishes():
    decision = publish_decision.decide(
        legacy_score={"total": 85.0, "component_scores": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=100.0,
        orchestrator_quality={"overall": 81.99285714285715, "critic_findings": []},
    )

    assert decision["orchestrator_critic_score"] == 82.0
    assert decision["publishable"] is True
    assert decision["decision"] == "publish"


def test_production_engine_a_state_replays_with_explained_decision_dependency():
    question, facts, narrative = _production_state()
    beats = orchestrator._engine_a_product_expression_beats(
        {"hook": question, "answer": "", "explanation": "", "example": "", "takeaway": ""}, narrative, facts
    )
    body = " ".join(value for key, value in beats.items() if key != "hook")
    ledger = claim_intelligence.build_ledger(beats["hook"] + " " + body, verified_facts=facts, forbidden_claims=[])
    response_contract = quality_intelligence.expected_response_contract(
        reader_job="HELP_ME_CHOOSE",
        cta_class=narrative["cta_class"],
        content_role=narrative["role"],
    )
    score = quality_intelligence.score(
        hook=beats["hook"],
        body=body,
        takeaway=beats["takeaway"],
        memory_anchor=beats["takeaway"],
        visual_concept_description="comparison method",
        platform="facebook",
        genre=dict(libraries.genres()["decision_guide"]),
        reader_job_config=dict(libraries.reader_jobs()["HELP_ME_CHOOSE"]),
        ledger=ledger,
        visual_prompt_humanness=1.0,
        caption_visual_relationship="VISUAL_EXPLAINS_CAPTION",
        engine="A",
        response_contract=response_contract,
    )
    decision = publish_decision.decide(
        legacy_score={"total": 97.0, "platform_results": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=100.0,
        orchestrator_quality=score.as_dict(),
    )

    assert narrative["role"] == "FIT_DEMONSTRATION"
    assert narrative["commercial_intensity"] == "LIGHT"
    assert "determine whether the device can be supported" in beats["answer"]
    assert "stored capacity describes reserve" in beats["answer"]
    assert "sustaining professional devices" not in body
    assert "runs laptops" not in body
    assert "supports your laptop" not in body
    assert "hook-payoff mismatch" not in decision["critic_findings"]
    assert score.semantic_evidence["novelty"]["type"] == "DECISION_DEPENDENCY"
    assert score.semantic_evidence["conversation"]["type"] == "SELF_DIAGNOSTIC"
    assert score.factors["conversation_potential"] == 0.35
    assert score.factors["response_value"] == 0.8
    assert score.response_contract["expected_response_type"] == "COMPARE_DECISION"
