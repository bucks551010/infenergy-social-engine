import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from social import creative_intelligence


def _attempt(score, findings, owner="Copy Intelligence"):
    return {
        "orchestrator_critic_score": score,
        "current_candidate_findings": findings,
        "cognitive_diagnosis": {"repair_owner": owner},
    }


def test_decreasing_repeated_local_repairs_escalate_concept():
    review = creative_intelligence.metacognitive_review([
        _attempt(81.1536, ["hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"]),
        _attempt(81.0136, ["hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"]),
        _attempt(80.3886, ["hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"]),
    ])
    assert review["action"] == "ESCALATE_CREATIVE_CONCEPT"
    assert review["reason"] == "LOCAL_REPAIR_DIMINISHING_RETURNS"


def test_one_bad_attempt_does_not_escalate_concept():
    assert creative_intelligence.metacognitive_review([_attempt(70, ["novelty_angle_weak"])])["action"] == "CONTINUE_LOCAL_REPAIR"


def test_improving_scores_continue_local_repair():
    review = creative_intelligence.metacognitive_review([
        _attempt(76, ["novelty_angle_weak"]),
        _attempt(79, ["novelty_angle_weak"]),
        _attempt(81, ["novelty_angle_weak"]),
    ])
    assert review["action"] == "CONTINUE_LOCAL_REPAIR"


def test_concepts_are_distinct_and_preserve_strategy_lock():
    strategy = {"product": "PPP-200", "audience": "mobile professional", "benefit": "keep compatible devices charged", "claim_limits": "verified facts only"}
    concepts = creative_intelligence.concept_competition(strategy)
    assert len({item["id"] for item in concepts}) == 3
    assert all(item["protected_strategy"] == strategy for item in concepts)


def test_pre_render_gate_rejects_hook_payoff_mismatch_and_generic_bait():
    concept = creative_intelligence.concept_competition({"benefit": "keep devices charged"})[0]
    gate = creative_intelligence.pre_render_gate(
        concept=concept,
        hook="What do you think about portable power?",
        body="Learn about a product.",
        visual_thesis="generic product hero",
        claim_safe=True,
    )
    assert gate["decision"] == "REVISE_CONCEPT"
    assert not gate["checks"]["conversation"]
    assert gate["hook_payoff_result"] == "FAIL"


def test_pre_render_gate_accepts_a_supported_shared_thesis():
    concept = creative_intelligence.concept_competition(
        {"customer_moment": "before a trip", "benefit": "keep compatible devices charged"}
    )[0]
    gate = creative_intelligence.pre_render_gate(
        concept=concept,
        hook="Before a trip, decide what needs power.",
        body="Before a trip, decide which compatible devices need power using verified product facts.",
        visual_thesis="Start in the supported customer moment and make the product a supporting proof.",
        claim_safe=True,
    )
    assert gate["decision"] == "CONCEPT_READY"
    assert gate["hook_payoff_result"] == "PASS"


def test_concept_selection_uses_feed_memory_for_layout_repetition():
    concepts = creative_intelligence.concept_competition({"benefit": "keep compatible devices charged"})
    winner = creative_intelligence.select_concept(concepts, feed_intelligence={"what_feed_needs_next": ["a different layout and visual rhythm"]})
    assert winner["id"] == "decision_support"


def test_replay_of_711998afe10_trajectory_escalates_without_external_operations():
    strategy = {
        "product": "PPP-200",
        "audience": "mobile professional",
        "customer_moment": "before a trip",
        "benefit": "keeps compatible devices charged",
        "claim_limits": "verified facts only",
        "reader_job": "HELP_ME_CHOOSE",
    }
    replay = creative_intelligence.replay_attempt_history(
        strategy=strategy,
        attempts=[
            _attempt(81.1536, ["hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"]),
            _attempt(81.0136, ["hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"]),
            _attempt(80.3886, ["hook-payoff mismatch", "novelty_angle_weak", "conversation_potential_weak"]),
        ],
        hook="Before a trip, decide what needs power.",
        body="Before a trip, decide which compatible devices need power using verified product facts.",
        visual_thesis="Start in the supported customer moment and make the product a supporting proof.",
        claim_safe=True,
        feed_intelligence={"what_feed_needs_next": ["a different human/product balance"]},
    )
    assert replay["metacognition"]["action"] == "ESCALATE_CREATIVE_CONCEPT"
    assert replay["winner"]["id"] == "customer_moment"
    assert replay["pre_render_gate"]["decision"] == "CONCEPT_READY"
    assert replay["external_operations"] == []