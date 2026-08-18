from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import claim_governance, claim_intelligence, publish_decision, quality_intelligence


def _decision(readiness: dict):
    return publish_decision.decide(
        legacy_score={"total": 97.0, "platform_results": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=100.0,
        orchestrator_quality={"overall": 92.0, "critic_findings": []},
        evidence_readiness=readiness,
    )


def _central_ledger() -> claim_intelligence.ClaimLedger:
    return claim_intelligence.build_ledger(
        "Available output determines whether the work can proceed; capacity describes reserve after fit is established.",
        verified_facts=[],
        forbidden_claims=[],
    )


def _medium_claim_ledger(claim_text: str, source_concept_ids: tuple[str, ...] = ()) -> claim_intelligence.ClaimLedger:
    return claim_intelligence.ClaimLedger(
        claims=[
            claim_intelligence.Claim(
                claim_text=claim_text,
                claim_type="general_informational",
                confidence=0.7,
                risk=claim_intelligence.MEDIUM_RISK,
                verification_required=True,
                source_concept_ids=source_concept_ids,
            )
        ]
    )


def test_response_contract_authority_resolves_conflicts_before_copy_scoring():
    cases = [
        ("HELP_ME_CHOOSE", "RESPOND", "COMMUNITY_CONVERSATION", "COMPARE_DECISION", "reader_job"),
        ("REFLECT", "SAVE", "EDUCATION", "REFLECTION", "reader_job"),
        ("START_A_CONVERSATION", "COMPARE", "FIT_DEMONSTRATION", "PUBLIC_CONVERSATION", "reader_job"),
        ("HELP_ME_CHOOSE", "COMPARE", "DIRECT_OFFER", "COMPARE_DECISION", "reader_job"),
    ]
    for reader_job, cta, role, expected, source in cases:
        contract = quality_intelligence.expected_response_contract(reader_job=reader_job, cta_class=cta, content_role=role)
        assert contract["expected_response_type"] == expected
        assert contract["response_contract_source"] == source
        assert "before copy scoring" in contract["response_contract_resolution"]


def test_central_research_required_claim_blocks_quality_and_legacy_overrides():
    ledger = _central_ledger()
    readiness = claim_governance.assess(
        ledger,
        hook="Can this source support the work?",
        decision_insight={"relationship": "Available output determines whether the work can proceed; capacity describes reserve after fit is established."},
        takeaway="Establish fit before reserve.",
    )
    decision = _decision(readiness)

    assert readiness["status"] == "RESEARCH_REQUIRED"
    assert readiness["research_needs"]
    assert decision["publishable"] is False
    assert decision["decision"] == "do_not_publish"
    assert "RESEARCH_REQUIRED" in decision["reasons"]


def test_incidental_medium_claim_does_not_block_and_verified_central_claim_can_proceed():
    incidental = claim_intelligence.build_ledger("The published output is 200W. Capacity is an important specification.", verified_facts=["200W"], forbidden_claims=[])
    incidental_readiness = claim_governance.assess(incidental, hook="Review the product.", decision_insight={"relationship": ""}, takeaway="Review the details.")
    verified = claim_intelligence.build_ledger("The published output is 200W.", verified_facts=["200W"], forbidden_claims=[])
    verified_readiness = claim_governance.assess(verified, hook="What output is published?", decision_insight={"relationship": "The published output is 200W."}, takeaway="Compare published output.")

    assert incidental_readiness["ready"] is True
    assert _decision(incidental_readiness)["publishable"] is True
    assert verified_readiness["ready"] is True
    assert _decision(verified_readiness)["publishable"] is True


def test_absent_conversion_score_is_not_recorded_as_a_perfect_score():
    decision = publish_decision.decide(
        legacy_score={"total": 97.0, "platform_results": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=None,
        orchestrator_quality={"overall": 92.0, "critic_findings": []},
    )

    assert decision["publishable"] is True
    assert decision["conversion_quality_score"] is None
    assert decision["conversion_quality_available"] is False


def test_supported_rewrite_and_abstention_are_available_without_weakening_high_risk_policy():
    rewritten = claim_intelligence.build_ledger("The published output is 200W. Compare that published fact with your device requirement.", verified_facts=["200W"], forbidden_claims=[])
    rewrite_readiness = claim_governance.assess(rewritten, hook="What output is published?", decision_insight={"relationship": ""}, takeaway="Compare the published fact.")
    high_risk = claim_intelligence.build_ledger("This product guarantees safety.", verified_facts=[], forbidden_claims=[])
    high_risk_readiness = claim_governance.assess(high_risk, hook="Stay safe.", decision_insight={}, takeaway="")
    abstention = claim_governance.assess(claim_intelligence.build_ledger("", verified_facts=[], forbidden_claims=[]), hook="", decision_insight={}, takeaway="")

    assert rewrite_readiness["ready"] is True
    assert high_risk_readiness["status"] == "HIGH_RISK_UNVERIFIED"
    assert abstention["ready"] is True


def test_centrality_is_invariant_when_the_core_dependency_is_paraphrased():
    ledger = _central_ledger()
    readiness = claim_governance.assess(
        ledger,
        hook="Will this source support the work?",
        decision_insight={
            "relationship": "Wattage establishes operational feasibility; stored energy represents endurance only after compatibility has been confirmed."
        },
        takeaway="Confirm operational feasibility before estimating endurance.",
    )

    assert readiness["claims"][0]["centrality"] == "CENTRAL"


def test_incidental_lexical_overlap_does_not_create_centrality():
    ledger = claim_intelligence.build_ledger(
        "Available output and capacity are specification fields.",
        verified_facts=[],
        forbidden_claims=[],
    )
    readiness = claim_governance.assess(
        ledger,
        hook="Can available output support the work?",
        decision_insight={"relationship": "Available output determines whether the work can proceed; capacity describes reserve after fit is established."},
        takeaway="Establish fit before reserve.",
    )

    assert readiness["claims"][0]["centrality"] == "INCIDENTAL"


def test_structured_source_concept_is_authoritative_over_surface_wording():
    claim = "Wattage establishes operational feasibility; stored energy represents endurance only after compatibility has been confirmed."
    ledger = _medium_claim_ledger(claim, ("decision_relationship",))
    readiness = claim_governance.assess(ledger, hook="", decision_insight={}, takeaway="")

    assert readiness["claims"][0]["centrality"] == "CENTRAL"


def test_relation_aware_centrality_generalizes_across_domains_without_lexical_false_positives():
    cases = [
        (
            "Power availability determines whether equipment can operate; stored energy only describes endurance after compatibility is confirmed.",
            "Wattage establishes operational feasibility; stored energy represents endurance only after compatibility has been confirmed.",
            "Available output and capacity are specification fields.",
        ),
        (
            "Execution speed determines whether the workflow advances; cleanup effort matters after exception handling is confirmed.",
            "Throughput establishes whether work can move forward; review effort follows once exceptions are handled.",
            "Workflow execution and exception review are operational activities.",
        ),
        (
            "Resolution determines whether the customer problem is closed; response speed matters after the outcome is confirmed.",
            "A solved outcome establishes closure; acknowledgement timing follows after the issue is resolved.",
            "Customer response and resolution are service measurements.",
        ),
    ]
    for dependency, paraphrase, incidental in cases:
        central = _medium_claim_ledger(dependency)
        central_readiness = claim_governance.assess(
            central,
            hook="",
            decision_insight={"relationship": paraphrase},
            takeaway="",
        )
        noncentral = _medium_claim_ledger(incidental)
        noncentral_readiness = claim_governance.assess(
            noncentral,
            hook="",
            decision_insight={"relationship": dependency},
            takeaway="",
        )

        assert central_readiness["claims"][0]["centrality"] == "CENTRAL"
        assert noncentral_readiness["claims"][0]["centrality"] == "INCIDENTAL"