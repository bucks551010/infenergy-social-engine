from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_engine
import social_visuals
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


def _pre_visual_content(*, validation_status="passed", duplicate_ok=True, duplicate_reasons=None, evidence=None, presentation_ready=True):
    caption = "Hook.\n\n- First point\n- Second point\n\nSave this.\n\nhttps://example.com\n\n#PortablePower"
    package = {
        "caption": caption,
        "final_caption": caption,
        "final_caption_qa": {"status": "PRESENTATION_READY", "metrics": {"final_caption": caption}},
    }
    if not presentation_ready:
        package["final_caption_qa"] = {"status": "PRESENTATION_BLOCKED", "metrics": {"final_caption": caption}}
    return {
        "post_id": "candidate-a",
        "candidate_attempt_id": "candidate-a:candidate-1",
        "validation_status": validation_status,
        "validation_errors": [] if validation_status == "passed" else ["copy_invalid"],
        "duplicate_check": {"ok": duplicate_ok, "reasons": duplicate_reasons or []},
        "copy": {"evidence_readiness": evidence or {"ready": True, "status": "READY"}},
        "platform_posts": {"facebook": package},
        "fb_caption": caption,
    }


def test_pre_visual_gate_blocks_evidence_and_duplicate_candidates_without_image_calls():
    blocked_cases = [
        _pre_visual_content(evidence={"ready": False, "status": "RESEARCH_REQUIRED"}),
        _pre_visual_content(duplicate_ok=False, duplicate_reasons=["duplicate_product_within_window"]),
        _pre_visual_content(duplicate_ok=False, duplicate_reasons=["semantic_duplicate_within_window"]),
    ]

    for content in blocked_cases:
        gate = run_engine._pre_visual_gate(content, {"facebook": True, "instagram": False, "linkedin": False}, {"total": 97.0, "platform_results": {}})
        assert gate["status"] == "FAIL"
        assert gate["flux_authorized"] is False
        assert gate["image_calls"] == 0


def test_pre_visual_gate_blocks_copy_presentation_and_campaign_without_image_calls():
    malformed = _pre_visual_content(presentation_ready=False)
    no_active_channel = _pre_visual_content()

    for content, channels in (
        (malformed, {"facebook": True, "instagram": False, "linkedin": False}),
        (no_active_channel, {"facebook": False, "instagram": False, "linkedin": False}),
    ):
        gate = run_engine._pre_visual_gate(content, channels, {"total": 97.0, "platform_results": {}})
        assert gate["status"] == "FAIL"
        assert gate["flux_authorized"] is False
        assert gate["image_calls"] == 0


def test_pre_visual_gate_authorizes_only_publishable_candidate():
    content = _pre_visual_content()
    content["publish_decision"] = {"publishable": True, "reasons": []}
    gate = run_engine._pre_visual_gate(content, {"facebook": True, "instagram": False, "linkedin": False}, {"total": 97.0, "platform_results": {}})

    assert gate["status"] == "PASS"
    assert gate["flux_authorized"] is True
    assert gate["image_calls"] == 0
    assert gate["selected_candidate"] == "candidate-a:candidate-1"


def test_blocked_powerpulse_candidate_cannot_reach_flux_but_retained_audience_value_candidate_can(monkeypatch, tmp_path):
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return False, "mock_provider", {"visual_generation_attempted": True, "visual_provider": "cloudflare"}

    monkeypatch.setenv("GENERATION_COST_MODE", "FREE_AI_ONLY")
    monkeypatch.setattr(social_visuals.cloudflare_visual, "generate", fake_generate)
    candidate_a = _pre_visual_content(evidence={"ready": False, "status": "RESEARCH_REQUIRED"})
    candidate_a.update({"post_id": "powerpulse-a", "candidate_attempt_id": "powerpulse-a:candidate-1", "product_id": "PPP-200"})
    candidate_a["publish_decision"] = {"publishable": False, "reasons": ["RESEARCH_REQUIRED"]}
    candidate_b = _pre_visual_content()
    candidate_b.update({"post_id": "audience-b", "candidate_attempt_id": "audience-b:candidate-2", "product_id": "", "topic": "Daily routine"})
    candidate_b["publish_decision"] = {"publishable": True, "reasons": []}

    candidate_a["pre_visual_gate"] = run_engine._pre_visual_gate(candidate_a, {"facebook": True, "instagram": False, "linkedin": False}, {"total": 97.0, "platform_results": {}})
    candidate_b["pre_visual_gate"] = run_engine._pre_visual_gate(candidate_b, {"facebook": True, "instagram": False, "linkedin": False}, {"total": 97.0, "platform_results": {}})

    assert candidate_a["pre_visual_gate"]["flux_authorized"] is False
    assert candidate_b["pre_visual_gate"]["flux_authorized"] is True
    social_visuals._generate_cloudflare_full_creative(candidate_b, "facebook", {}, str(tmp_path / "b.png"))

    assert len(calls) == 1
    assert calls[0]["candidate_id"] == "audience-b:candidate-2"

def test_incidental_medium_claim_does_not_block_and_verified_central_claim_can_proceed():
    incidental = claim_intelligence.build_ledger("The published output is 200W. Capacity is an important specification.", verified_facts=["200W"], forbidden_claims=[])
    incidental_readiness = claim_governance.assess(incidental, hook="Review the product.", decision_insight={"relationship": ""}, takeaway="Review the details.")
    verified = claim_intelligence.build_ledger("The published output is 200W.", verified_facts=["200W"], forbidden_claims=[])
    verified_readiness = claim_governance.assess(verified, hook="What output is published?", decision_insight={"relationship": "The published output is 200W."}, takeaway="Compare published output.")

    assert incidental_readiness["ready"] is True
    assert _decision(incidental_readiness)["publishable"] is True
    assert verified_readiness["ready"] is True
    assert _decision(verified_readiness)["publishable"] is True


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