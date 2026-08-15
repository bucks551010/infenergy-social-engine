from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_engine
from social import living_intelligence, public_research


def _research_blocked_content() -> dict:
    claim = "Published output and connection determine whether the required device can be supported."
    return {
        "post_id": "candidate-a",
        "candidate_attempt_id": "candidate-a:candidate-1",
        "topic": "Portable power",
        "product_name": "PowerPulse Pro 200",
        "copy": {
            "strategy_lock": {"topic": "Portable power"},
            "evidence_readiness": {
                "status": "RESEARCH_REQUIRED",
                "research_needs": [{
                    "claim_to_verify": claim,
                        "claim_type": "general_informational",
                    "research_question": f"What official documentation supports: {claim}",
                    "why_needed": "The claim carries the decision payoff.",
                }],
            },
        },
    }


def test_research_recovery_accepts_matched_authoritative_evidence_and_persists_it(monkeypatch, tmp_path):
    content = _research_blocked_content()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    claim = content["copy"]["evidence_readiness"]["research_needs"][0]["claim_to_verify"]
    monkeypatch.setattr(public_research, "research", lambda **_: [{
        "confidence": 0.9,
        "authority": "PRIMARY_TECHNICAL",
        "extract": [claim],
        "provenance": "https://manufacturer.example/manual",
        "observed_at": "2026-08-15T00:00:00+00:00",
        "last_verified_at": "2026-08-15T00:00:00+00:00",
    }])

    outcome = run_engine._research_recovery(content)

    assert outcome["status"] == "RESOLVED"
    assert outcome["source"] == "public_research"
    assert outcome["verified_facts"] == [claim]
    saved = living_intelligence.load(str(tmp_path))["research_evidence"]
    assert saved[-1]["claim"] == claim


def test_research_recovery_reuses_fresh_persisted_evidence_without_public_request(monkeypatch, tmp_path):
    content = _research_blocked_content()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    claim = content["copy"]["evidence_readiness"]["research_needs"][0]["claim_to_verify"]
    living_intelligence.save(str(tmp_path), {"research_evidence": [{
        "claim": claim,
        "confidence": 0.9,
        "authority": "PRIMARY_TECHNICAL",
        "last_verified_at": "2026-08-15T00:00:00+00:00",
    }]})
    monkeypatch.setattr(public_research, "research", lambda **_: (_ for _ in ()).throw(AssertionError("should reuse evidence")))

    outcome = run_engine._research_recovery(content)

    assert outcome["status"] == "RESOLVED"
    assert outcome["source"] == "evidence_memory"


def test_research_recovery_returns_structured_failure_without_upgrading_claim(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(public_research, "research", lambda **_: [{"failure": "NO_RELEVANT_SOURCE"}])

    outcome = run_engine._research_recovery(_research_blocked_content())

    assert outcome["status"] == "INSUFFICIENT_EVIDENCE"
    assert outcome["failure"] == "NO_RELEVANT_SOURCE"


def test_research_recovery_rejects_matched_unverified_public_evidence(monkeypatch, tmp_path):
    content = _research_blocked_content()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    claim = content["copy"]["evidence_readiness"]["research_needs"][0]["claim_to_verify"]
    monkeypatch.setattr(public_research, "research", lambda **_: [{
        "confidence": 0.55,
        "extract": [claim],
        "provenance": "https://unverified.example/article",
    }])

    outcome = run_engine._research_recovery(content)

    assert outcome["status"] == "INSUFFICIENT_EVIDENCE"
    assert outcome["failure"] == "CLAIM_NOT_SUPPORTED"


def test_collect_marks_known_first_party_evidence_as_candidate_not_automatic_authority(monkeypatch):
    from social import research_router

    task = research_router.route(
        question="Which site claim supports product guidance?",
        why_needed="Verify a central claim.",
        entity="Infenergy Power",
        decision_affected="social_claim_verification",
    )
    monkeypatch.setattr(research_router, "inspect_first_party", lambda _: {
        "content_hash": "known-first-party",
        "marketing_language": ["Published output and connection determine device support."],
        "factual_candidates": [],
    })

    evidence = public_research.collect(task=task, urls=["https://infenergypower.com/guides/power"])

    assert evidence[0]["authority"] == "FIRST_PARTY_CANDIDATE"
    assert evidence[0]["confidence"] == 0.55


def test_first_party_business_fact_can_satisfy_owned_scope():
    outcome = public_research.validate_claim_authority(
        claim="Infenergy Power is a company focused on portable power.",
        claim_type="general_informational",
        evidence={"provenance": "https://infenergypower.com/about", "confidence": 0.55},
    )

    assert outcome["claim_authority_class"] == "OWNED_BUSINESS_FACT"
    assert outcome["accepted"] is True
    assert outcome["support_confidence"] == 0.8


def test_verified_first_party_product_fact_can_satisfy_owned_scope():
    outcome = public_research.validate_claim_authority(
        claim="The product has a published 500 Wh capacity.",
        claim_type="quantitative_technical_fact",
        verified_product_fact=True,
        evidence={"provenance": "https://infenergypower.com/products/example", "confidence": 0.55},
    )

    assert outcome["claim_authority_class"] == "OWNED_PRODUCT_FACT"
    assert outcome["accepted"] is True


def test_first_party_technical_safety_and_compatibility_claims_remain_unaccepted():
    evidence = {"provenance": "https://infenergypower.com/guides/example", "confidence": 0.55}
    cases = [
        ("Electrical output determines device operation.", "quantitative_technical_fact", "TECHNICAL_CATEGORY_FACT"),
        ("This setup is safe for every device.", "safety_claim", "SAFETY_FACT"),
        ("This power station is compatible with every CPAP workload.", "general_informational", "COMPATIBILITY_FACT"),
    ]

    for claim, claim_type, expected_class in cases:
        outcome = public_research.validate_claim_authority(claim=claim, claim_type=claim_type, evidence=evidence)
        assert outcome["claim_authority_class"] == expected_class
        assert outcome["accepted"] is False
        assert outcome["reason"] == "source_not_authoritative_for_claim_type"


def test_primary_manufacturer_evidence_can_support_compatibility_but_not_generic_public_page():
    claim = "The power station is compatible with the documented device workload."
    primary = public_research.validate_claim_authority(
        claim=claim,
        claim_type="general_informational",
        evidence={"provenance": "https://manufacturer.example/manual", "authority": "PRIMARY_MANUFACTURER", "confidence": 0.9},
    )
    generic = public_research.validate_claim_authority(
        claim=claim,
        claim_type="general_informational",
        evidence={"provenance": "https://unverified.example/article", "confidence": 0.55},
    )

    assert primary["accepted"] is True
    assert generic["accepted"] is False


def test_current_external_fact_does_not_gain_authority_from_first_party_page():
    outcome = public_research.validate_claim_authority(
        claim="Current market availability is unchanged today.",
        claim_type="general_informational",
        evidence={"provenance": "https://infenergypower.com/guides/example", "confidence": 0.55},
    )

    assert outcome["claim_authority_class"] == "CURRENT_EXTERNAL_FACT"
    assert outcome["accepted"] is False
    assert outcome["support_confidence"] == 0.55