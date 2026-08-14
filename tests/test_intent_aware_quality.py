from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import claim_intelligence, quality_intelligence


def _score(*, hook: str, body: str, takeaway: str = "Use this method.", reader_job: str, cta: str = "", role: str = ""):
    contract = quality_intelligence.expected_response_contract(reader_job=reader_job, cta_class=cta, content_role=role)
    return quality_intelligence.score(
        hook=hook, body=body, takeaway=takeaway, memory_anchor=takeaway,
        visual_concept_description="A useful visual.", platform="facebook",
        genre={"avg_information_density": 0.7, "cta_preferences": []},
        reader_job_config={"id": reader_job, "typical_emotion": "confidence"},
        ledger=claim_intelligence.build_ledger(body, verified_facts=[], forbidden_claims=[]),
        visual_prompt_humanness=1.0, caption_visual_relationship="VISUAL_EXPLAINS_CAPTION",
        engine="A", response_contract=contract,
    )


def test_weak_compare_copy_does_not_earn_response_value_or_role_escape():
    weak = _score(hook="Is your setup right for you?", body="Check your options and compare before deciding.", reader_job="HELP_ME_CHOOSE", cta="COMPARE", role="FIT_DEMONSTRATION")
    switched = _score(hook="Is your setup right for you?", body="Check your options and compare before deciding.", reader_job="START_A_CONVERSATION", cta="COMMENT", role="COMMUNITY")

    assert weak.factors["response_value"] == 0.35
    assert switched.factors["response_value"] == 0.35


def test_strong_decision_support_earns_compare_response_without_conversation():
    score = _score(
        hook="Can this source fit the work?",
        body="Available output and connection determine whether the device can be supported; stored capacity describes reserve after compatibility is established. Compare the actual requirement with both published criteria before choosing.",
        reader_job="HELP_ME_CHOOSE", cta="COMPARE", role="FIT_DEMONSTRATION",
    )

    assert score.factors["conversation_potential"] == 0.35
    assert score.factors["response_value"] == 0.8
    assert score.response_contract["expected_response_type"] == "COMPARE_DECISION"


def test_community_job_requires_real_conversation():
    weak = _score(hook="What do you think?", body="Consider your setup.", reader_job="START_A_CONVERSATION", cta="COMMENT", role="COMMUNITY")
    strong = _score(hook="When your team works away from the office, which task becomes hardest first and why?", body="Different workflows create different priorities.", reader_job="START_A_CONVERSATION", cta="COMMENT", role="COMMUNITY")

    assert weak.factors["response_value"] == 0.35
    assert "conversation_potential_weak" in weak.reasons
    assert strong.factors["response_value"] == 0.8


def test_reflection_save_and_offer_each_require_delivered_value():
    reflection = _score(hook="What changes when speed hides cleanup?", body="Automating more steps does not always reduce review work. If exceptions are poor, work shifts into cleanup.", reader_job="MAKE_ME_THINK", cta="REFLECT")
    generic_reflection = _score(hook="Keep going.", body="Believe in yourself.", reader_job="MAKE_ME_THINK", cta="REFLECT")
    save = _score(hook="Keep this reference.", body="First identify the requirement. Then compare the constraint. Finally record the consequence.", reader_job="GIVE_ME_A_REFERENCE", cta="SAVE")
    weak_save = _score(hook="Save this.", body="Useful advice.", reader_job="GIVE_ME_A_REFERENCE", cta="SAVE")
    offer = _score(hook="Explore the right plan.", body="Review your actual need, then compare the available options before you choose.", reader_job="HELP_ME", cta="EXPLORE", role="DIRECT_OFFER")

    assert reflection.factors["response_value"] == 0.8
    assert generic_reflection.factors["response_value"] == 0.35
    assert save.factors["response_value"] == 0.8
    assert weak_save.factors["response_value"] == 0.35
    assert offer.factors["response_value"] == 0.8