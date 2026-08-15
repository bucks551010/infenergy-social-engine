from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_engine
import social_visuals
import generate_posts
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


def test_product_free_gemini_artifact_uses_normalized_visual_handoff(tmp_path):
    artifact = tmp_path / "engine-b-facebook.png"
    from PIL import Image
    Image.new("RGB", (1200, 1200), "#224466").save(artifact)
    content = _pre_visual_content()
    content.update({
        "post_id": "engine-b-product-free",
        "candidate_attempt_id": "engine-b-product-free:candidate-1",
        "strategy_lock": {"product_relevance": "NOT_RELEVANT", "product_role": "NONE"},
        "generated_visuals": {
            "facebook": str(artifact),
            "render_engines": {"facebook": "gemini"},
            "product_overlay_applied": {"facebook": False},
            "visual_generation": {"facebook": {"visual_generation_attempted": True, "visual_provider": "gemini", "visual_model": "gemini-2.5-flash-image"}},
        },
        "publish_decision": {"publishable": True, "reasons": []},
    })
    reviews = run_engine._ensure_final_artifact_qa(content, {"facebook": True, "instagram": False, "linkedin": False})

    assert content["generated_visuals"]["render_engines"]["facebook"] == "gemini"
    assert reviews["facebook"]["verdict"] == "PASS"
    assert "facebook_product_overlay_missing" not in run_engine._live_visual_gate_errors(content, {"facebook": True}, dry_run=False)


def test_presentation_repair_replaces_stale_final_caption_before_locking():
    components = {
        "product_role": "NONE",
        "logic_hook": "Define the job before comparing tools.",
        "logic_bridge": "Write the device, connection, time window, and constraint first.",
        "emotional_outcome": "The requirement becomes clearer when you describe the task first.",
        "cta": "Save this planning prompt.",
    }
    content = {
        "destination_url": "https://www.infenergypower.com",
        "post_components": components,
        "platform_posts": {
            "facebook": {
                "caption": "Stale flattened caption.",
                "final_caption": "Stale flattened caption.",
                "final_caption_qa": {"status": "REVISE_PRESENTATION"},
            }
        },
    }

    repaired = run_engine._repair_final_presentations(
        content, {"facebook": True, "instagram": False, "linkedin": False}
    )
    package = content["platform_posts"]["facebook"]

    assert repaired == ["facebook"]
    assert package["caption"] == package["final_caption"] == content["fb_caption"]
    assert package["final_caption_lock"] == package["final_caption"]
    assert package["final_caption_qa"]["status"] == "PRESENTATION_READY"
    assert "https://www.infenergypower.com" in package["final_caption"]


def test_product_free_orchestrator_package_uses_homepage_without_catalog_injection(monkeypatch):
    product_free_copy = {
        "hook": "Define the job before comparing tools.",
        "body_text": "Write the device, connection, time window, and constraint first.",
        "takeaway": "The requirement becomes clearer when you describe the task first.",
        "cta": "Save this planning prompt.",
        "strategy_lock": {"positioning": "product-free audience value"},
    }
    candidate = {
        "post_id": "product-free-candidate",
        "copy": product_free_copy,
        "visual": {},
        "quality": {"overall": 90},
        "anchored_offering": {"offering_id": "PPP-200", "name": "PowerPulse Pro 200", "sku": "PPP-200"},
        "brief": {"audience_segment": "mobile_professional", "topic_path": {"topic": "Preparedness"}},
        "creative_decision_packet": {},
    }
    monkeypatch.setattr(generate_posts, "run_social_intelligence", lambda **_: [candidate])
    monkeypatch.setattr(generate_posts, "load_products", lambda: [{"id": "PPP-200", "product_url": "https://www.infenergypower.com/products/ppp-200"}])

    package = generate_posts._route_generate_orchestrator(defer_visuals=True)

    assert package["product_id"] is None
    assert package["product_name"] == ""
    assert package["product_url"] == ""
    assert package["destination_url"] == generate_posts.SITE_URL
    assert package["post_components"]["product_role"] == "NONE"
    assert "PowerPulse" not in package["platform_posts"]["facebook"]["final_caption"]

    original_caption = package["platform_posts"]["facebook"]["final_caption"]
    assert run_engine._enforce_candidate_claim_boundary(package) == []
    assert package["platform_posts"]["facebook"]["final_caption"] == original_caption
    assert run_engine._lock_final_captions(
        package, {"facebook": True, "instagram": False, "linkedin": False}
    ) == []


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