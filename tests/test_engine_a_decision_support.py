from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import claim_intelligence, living_intelligence, orchestrator


def _narrative() -> dict:
    return living_intelligence.product_expression_for_engine_a(
        campaign={},
        reader_job="HELP_ME_CHOOSE",
        question="Can the available source fit the required work?",
        human_reality="a mobile professional preparing before travel",
        practical_value="Compare the actual requirement with published details.",
        takeaway="Fit before reserve.",
        verified_facts=["154Wh", "200W", "110V AC"],
        product_name="PowerPulse Pro 200",
    )


def test_decision_insight_maps_verified_facts_to_roles_and_boundary():
    insight = orchestrator._engine_a_decision_insight(_narrative(), ["154Wh", "200W", "110V AC"])

    assert insight["structure"] == "DEPENDENCY"
    assert insight["decision_question"] == "Can the available source fit the required work?"
    assert "determine whether" in insight["relationship"]
    assert "actual device requirement" in insight["limitation_or_boundary"]
    assert {item["decision_role"] for item in insight["verified_product_evidence"]} == {
        "available_output", "connection_access", "stored_reserve"
    }


def test_engine_a_rendered_copy_teaches_relationship_without_broad_compatibility_claims():
    narrative = _narrative()
    beats = orchestrator._engine_a_product_expression_beats(
        {"hook": "", "answer": "", "explanation": "", "example": "", "takeaway": ""},
        narrative,
        ["154Wh", "200W", "110V AC"],
    )
    body = " ".join(value for key, value in beats.items() if key != "hook")
    ledger = claim_intelligence.build_ledger(body, verified_facts=["154Wh", "200W", "110V AC"], forbidden_claims=[])

    assert "determine whether the device can be supported" in body
    assert "cannot establish fit" in body
    assert "runs laptops" not in body
    assert "supports professional devices" not in body
    assert "mobile professional preparing before travel" in body
    assert narrative["role"] == "FIT_DEMONSTRATION"
    assert narrative["commercial_intensity"] == "LIGHT"
    assert narrative["cta_class"] == "COMPARE"
    assert not ledger.unverified_high_risk


def test_different_reasoning_structures_do_not_collapse_into_one_template():
    narrative = _narrative()
    base = {"hook": "Question", "answer": "", "explanation": "", "example": "", "takeaway": ""}
    dependency = orchestrator._render_engine_a_decision_beats(
        base,
        narrative,
        {
            "decision_question": "Can the work be supported?",
            "relationship": "The first constraint determines whether the work can proceed; the second describes reserve after fit.",
            "why_relationship_matters": "Reserve cannot repair a missing fit.",
            "decision_consequence": "establish fit before estimating reserve",
            "verified_product_evidence": [],
            "limitation_or_boundary": "the reader must verify the actual requirement",
            "human_application": "a mobile professional preparing before travel",
            "memory_anchor": "Establish fit before estimating reserve.",
        },
    )
    tradeoff = orchestrator._render_engine_a_decision_beats(
        base,
        narrative,
        {
            "decision_question": "Where does automation move work?",
            "relationship": "Faster execution can shift effort into manual cleanup when exceptions remain unresolved.",
            "why_relationship_matters": "Throughput alone can hide review work.",
            "decision_consequence": "compare execution speed with exception handling",
            "verified_product_evidence": [],
            "limitation_or_boundary": "the team must inspect its exception path",
            "human_application": "a software operations team",
            "memory_anchor": "Count cleanup, not just throughput.",
        },
    )
    resolution = orchestrator._render_engine_a_decision_beats(
        base,
        narrative,
        {
            "decision_question": "What actually resolves the issue?",
            "relationship": "A fast first response can acknowledge a problem while resolution remains open.",
            "why_relationship_matters": "Response speed is not the same outcome as resolution.",
            "decision_consequence": "measure the customer's solved problem, not acknowledgement alone",
            "verified_product_evidence": [],
            "limitation_or_boundary": "the service team must verify the issue is closed",
            "human_application": "a service team",
            "memory_anchor": "Measure resolution, not acknowledgement.",
        },
    )

    assert dependency["answer"] != tradeoff["answer"] != resolution["answer"]
    assert dependency["takeaway"] != tradeoff["takeaway"] != resolution["takeaway"]