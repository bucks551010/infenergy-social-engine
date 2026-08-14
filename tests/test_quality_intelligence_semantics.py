from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import claim_intelligence, quality_intelligence


def _score(hook: str, body: str):
    return quality_intelligence.score(
        hook=hook,
        body=body,
        takeaway="A practical takeaway.",
        memory_anchor="A practical takeaway.",
        visual_concept_description="A practical visual.",
        platform="facebook",
        genre={"avg_information_density": 0.5, "cta_preferences": ["COMMENT", "REFLECT"]},
        reader_job_config={"typical_emotion": "uncertainty"},
        ledger=claim_intelligence.build_ledger(body, verified_facts=[], forbidden_claims=[]),
        visual_prompt_humanness=1.0,
        caption_visual_relationship="VISUAL_EXPLAINS_CAPTION",
        engine="A",
    )


def test_keyword_and_imperative_gaming_do_not_earn_novelty():
    base = _score("Review your options.", "Review your options.")
    stuffed = _score("Review your options.", "First check and compare your options before you decide.")
    imperative = _score("Review your options.", "Check your setup before buying.")

    assert base.factors["novelty"] == stuffed.factors["novelty"] == imperative.factors["novelty"] == 0.55
    assert stuffed.semantic_evidence["novelty"]["type"] == "NONE"


def test_ordering_and_fake_rationale_do_not_earn_novelty():
    score = _score("Review the indicators.", "Check the blue number before the red number because the blue number comes first.")

    assert score.factors["novelty"] == 0.55
    assert score.semantic_evidence["novelty"]["type"] == "NONE"


def test_explained_decision_dependency_earns_novelty_without_power_vocabulary_rules():
    score = _score(
        "Can this source support the work?",
        "Available output and connection determine whether the device can be supported in the first place; stored capacity describes the energy reserve available after compatibility is established.",
    )

    assert score.factors["novelty"] == 0.8
    assert score.semantic_evidence["novelty"]["type"] == "DECISION_DEPENDENCY"


def test_cross_domain_distinctions_and_counterintuitive_insight_earn_novelty():
    software = _score(
        "Where does automation move work?",
        "Automating more steps does not always reduce review work. If exception handling is poor, automation can move effort from execution into manual cleanup.",
    )
    service = _score(
        "What actually resolves the issue?",
        "A faster first response and a faster resolution are not the same thing; optimizing one can still leave the customer's actual problem open.",
    )
    common_sense = _score("Respond quickly.", "A faster response helps customers.")

    assert software.factors["novelty"] == 0.8
    assert software.semantic_evidence["novelty"]["type"] == "COUNTERINTUITIVE_RELATIONSHIP"
    assert service.factors["novelty"] == 0.8
    assert service.semantic_evidence["novelty"]["type"] == "USEFUL_DISTINCTION"
    assert common_sense.factors["novelty"] == 0.55


def test_generic_questions_and_question_mark_gaming_stay_low():
    statement = _score("Think about your setup.", "Review your options.")
    question = _score("What do you think about your setup?", "Review your options.")
    rhetorical = _score("Does this matter?", "Review your options.")

    assert statement.factors["conversation_potential"] == question.factors["conversation_potential"] == 0.35
    assert rhetorical.factors["conversation_potential"] == 0.35
    assert question.semantic_evidence["conversation"]["type"] == "NONE"


def test_self_diagnostic_is_not_public_conversation_and_experience_tradeoff_is():
    diagnostic = _score("Can your current power source support your laptop during travel?", "Review your setup before buying.")
    experience = _score(
        "When you work away from an outlet, which device becomes essential first and what makes that one the priority?",
        "Different workdays create different device priorities.",
    )

    assert diagnostic.factors["conversation_potential"] == 0.35
    assert diagnostic.semantic_evidence["conversation"]["type"] == "SELF_DIAGNOSTIC"
    assert experience.factors["conversation_potential"] == 0.8
    assert experience.semantic_evidence["conversation"]["type"] == "EXPERIENCE_TRADEOFF"


def test_engagement_bait_does_not_earn_conversation():
    score = _score("Comment YES if you agree.", "Drop your answer below.")

    assert score.factors["conversation_potential"] == 0.35
    assert score.semantic_evidence["conversation"]["type"] == "GENERIC_ENGAGEMENT"


def test_thresholds_and_claim_safety_policy_are_unchanged():
    assert quality_intelligence.DEFAULT_THRESHOLDS["publish"] == 82.0
    assert quality_intelligence.DEFAULT_THRESHOLDS["revise"] == 75.0
    ledger = claim_intelligence.build_ledger("This battery guarantees safety.", verified_facts=[], forbidden_claims=[])

    assert ledger.unverified_high_risk