from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_engine
import publish_facebook
from social import claim_governance, claim_intelligence, orchestrator, platform_presentation, publish_decision, recovery


def _final_decision(readiness: dict) -> dict:
    return publish_decision.decide(
        legacy_score={"total": 97.0, "platform_results": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=100.0,
        orchestrator_quality={"overall": 90.0, "critic_findings": []},
        evidence_readiness=readiness,
    )


def test_research_required_original_stays_blocked_and_requests_one_new_supported_angle():
    ledger = claim_intelligence.build_ledger(
        "Available output determines whether the work can proceed; capacity describes reserve after fit is established.",
        verified_facts=[],
        forbidden_claims=[],
    )
    readiness = claim_governance.assess(
        ledger,
        hook="Can this source support the work?",
        decision_insight={"relationship": "Available output determines whether the work can proceed; capacity describes reserve after fit is established."},
        takeaway="Establish fit before reserve.",
    )
    decision = _final_decision(readiness)
    feedback = run_engine._evidence_safe_remediation_feedback({"product_name": "PowerPulse Pro 200"})

    assert readiness["status"] == "RESEARCH_REQUIRED"
    assert decision["publishable"] is False
    assert decision["decision"] == "do_not_publish"
    assert len(feedback) == 4
    assert "materially new" in feedback[1]
    assert "only verified product facts" in feedback[1]


def test_verified_fact_remediation_is_ready_without_erasing_centrality_policy():
    ledger = claim_intelligence.build_ledger(
        "PowerPulse Pro 200 has published 154Wh and 200W specifications.",
        verified_facts=["154Wh", "200W"],
        forbidden_claims=[],
    )
    readiness = claim_governance.assess(
        ledger,
        hook="Pack published power details before travel.",
        decision_insight={},
        takeaway="Use published details as a packing reference.",
    )

    assert readiness["status"] == "READY"
    assert _final_decision(readiness)["publishable"] is True


def test_remediation_attempt_is_bounded_and_research_findings_stay_terminal_after_it():
    decision = {"decision": "do_not_publish", "reasons": ["RESEARCH_REQUIRED"]}

    assert run_engine._retryability_classification(decision, []) == "TERMINAL"
    assert "RESEARCH_REQUIRED" not in run_engine._evidence_safe_remediation_feedback({"product_id": "PPP-200"})[-1]


def test_paraphrase_of_blocked_concept_is_not_a_remediation():
    original = {"question": "Can I trust airport outlets?", "angle": "Establish fit before reserve.", "decision_thesis": "Output and connection determine support before stored capacity.", "payoff": "Compare output before reserve.", "human_reality": "before a trip"}
    paraphrase = {"question": "Will this airport outlet support my gear?", "angle": "Check compatibility before battery reserve.", "decision_thesis": "Output and connection decide support before capacity.", "payoff": "Compare available output before stored reserve.", "human_reality": "airport travel"}
    assert run_engine._semantic_difference(original, paraphrase) == (False, "replacement_semantically_overlaps_blocked_concept")


def test_different_supported_concept_and_final_memory_are_auditable():
    original = {"question": "Can I trust airport outlets?", "angle": "Establish fit before reserve.", "decision_thesis": "Output and connection determine support before stored capacity.", "payoff": "Compare output before reserve.", "human_reality": "before a trip"}
    replacement = {"question": "Which published details belong on your packing list?", "angle": "Keep published details handy.", "decision_thesis": "", "payoff": "154Wh and 200W are published details.", "human_reality": "packing"}
    assert run_engine._semantic_difference(original, replacement)[0] is True
    content = {"selected_hook": replacement["question"], "copy": {"hook": replacement["question"], "takeaway": "Keep published details handy.", "strategy_lock": {"angle": replacement["angle"], "customer_moment": "packing"}, "evidence_readiness": {"status": "READY"}}, "evidence_remediation": {"original_concept": original}}
    memory = run_engine._final_memory_record(content, "publish")
    assert memory["question"] == replacement["question"]
    assert memory["original_blocked_concept"] == original
    assert memory["final_outcome"] == "publish"


def test_final_caption_qa_rejects_malformed_phrase_and_remediation_suppresses_engine_a_thesis(tmp_path, monkeypatch):
    caption = "PowerPulse Pro 200.\n\nFor before a trip, keep details nearby.\n\nSave this.\n\nhttps://example.com\n\n#PortablePower"
    assert "broken_phrase" in platform_presentation.final_caption_qa(caption, platform="facebook", components={"product_name": "PowerPulse Pro 200", "benefit_fragment": "backup", "feature_bullets": [], "cta": "Save this."})["reasons"]
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args, **kwargs: None)
    post = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path)).create_post(preferred_engine="A", record_memory=False, remediation_context={"exclude_engine_a_decision_thesis": True})
    assert post.copy["decision_insight"] == {}


def test_final_caption_lock_blocks_malformed_publisher_input():
    caption = "PowerPulse Pro 200 backup.\n\nFor before a trip, compare the details.\n\nSave this.\n\nhttps://example.com\n\n#PortablePower"
    content = {
        "post_components": {
            "product_name": "PowerPulse Pro 200",
            "benefit_fragment": "backup",
            "feature_bullets": [],
            "cta": "Save this.",
        },
        "platform_posts": {"facebook": {"caption": caption}},
        "fb_caption": caption,
    }

    errors = run_engine._lock_final_captions(content)
    decision = publish_decision.decide(
        legacy_score={"total": 97.0, "platform_results": {}},
        validation={"passed": not errors, "errors": errors},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=100.0,
        orchestrator_quality={"overall": 90.0, "critic_findings": []},
        evidence_readiness={"ready": True, "status": "READY"},
    )

    assert "facebook_final_presentation_not_ready" in errors
    assert decision["publishable"] is False
    assert content["platform_posts"]["facebook"]["final_caption"] == content["fb_caption"]
    assert content["platform_posts"]["facebook"]["final_caption_qa"]["metrics"]["final_caption"] == content["fb_caption"]


def test_final_caption_lock_persists_exact_flat_facebook_caption():
    caption = "Hook.\n\n- First point\n- Second point\n\nSave this.\n\nhttps://example.com\n\n#PortablePower"
    content = {
        "post_components": {
            "product_name": "PowerPulse Pro 200",
            "benefit_fragment": "backup",
            "feature_bullets": [],
            "cta": "Save this.",
        },
        "platform_posts": {"facebook": {"caption": caption}},
    }

    run_engine._lock_final_captions(content, {"facebook": True, "instagram": False, "linkedin": False})
    diagnostics = run_engine._generation_diagnostics(content)

    assert content["platform_posts"]["facebook"]["final_caption"] == content["fb_caption"]
    assert content["platform_posts"]["facebook"]["final_caption_lock"] == content["fb_caption"]
    assert diagnostics["fb_caption"] == caption


def test_remediation_context_clears_candidate_a_state_and_advances_selection():
    content = {
        "post_id": "candidate-a",
        "candidate_attempt_id": "candidate-a:candidate-1",
        "selection_rotation_index": 0,
        "product_id": "PPP-200",
        "copy": {
            "hook": "Can I trust airport outlets?",
            "takeaway": "Establish fit before reserve.",
            "strategy_lock": {"angle": "Check output before reserve.", "customer_moment": "before a trip"},
            "decision_insight": {"relationship": "Output determines fit before reserve."},
            "evidence_readiness": {
                "status": "RESEARCH_REQUIRED",
                "claims": [{"claim": "Output determines fit before reserve.", "centrality": "CENTRAL", "research_status": "RESEARCH_REQUIRED"}],
            },
        },
    }

    remediation = run_engine._remediation_context(content, {"decision": "do_not_publish"}, {"ok": False})

    assert remediation["original_candidate_attempt_id"] == "candidate-a:candidate-1"
    assert remediation["candidate_attempt_id"] == "candidate-a:candidate-2"
    assert remediation["selection_rotation_index"] == 1
    assert remediation["excluded_product_ids"] == ["PPP-200"]
    assert remediation["exclude_engine_a_decision_thesis"] is True
    assert "Check output before reserve." in remediation["excluded_concepts"]


def test_verified_facts_only_recovery_uses_same_product_without_reusing_blocked_premise():
    content = {
        "post_id": "candidate-a",
        "product_id": "PF-150W",
        "product_name": "PowerFlex 150W Portable Laptop Charger",
        "product_metrics": ["Published 150W output", "Published 177.6Wh stored energy"],
        "copy": {
            "hook": "What does mAh actually mean?",
            "takeaway": "Check output and connection before reserve.",
            "strategy_lock": {"angle": "Check output before reserve.", "customer_moment": "before a trip"},
            "decision_insight": {"relationship": "Output and connection determine support before stored capacity."},
        },
    }
    remediation = run_engine._remediation_context(content, {"decision": "do_not_publish"}, {"ok": True})

    recovered = run_engine._verified_facts_only_recovery_context(content, remediation)

    assert recovered["recovery_mode"] == "VERIFIED_FACTS_ONLY_RECOVERY"
    assert recovered["verified_fact_opportunity"]["product_id"] == "PF-150W"
    assert recovered["verified_fact_opportunity"]["verified_fact"] == "Published 150W output"
    assert recovered["verified_fact_opportunities_considered"][0]["result"] == "selected"
    assert recovered["excluded_concepts"] == []


def test_verified_facts_exhaustion_retires_only_current_product_and_keeps_campaign_exclusions():
    content = {"post_id": "candidate-a", "product_id": "PF-150W", "selection_rotation_index": 2}
    remediation = {"excluded_product_ids": ["PPP-200"], "selection_rotation_index": 2}

    next_product = run_engine._next_product_recovery_context(
        content,
        remediation,
        "no_viable_verified_fact_opportunity",
    )

    assert next_product["recovery_mode"] == "NEXT_ELIGIBLE_PRODUCT"
    assert next_product["excluded_product_ids"] == ["PPP-200", "PF-150W"]
    assert next_product["retired_products"] == [{"product_id": "PF-150W", "reason": "no_viable_verified_fact_opportunity"}]
    assert next_product["selection_rotation_index"] == 3


def test_replacement_selector_rejects_powerpulse_before_trip_fit_reserve_paraphrase():
    blocked = {
        "product_id": "PPP-200", "question": "Can I trust airport outlets?", "angle": "Establish fit before reserve.",
        "human_reality": "before a trip", "decision_thesis": "Output and connection determine support before stored capacity.",
    }
    shortlist = [
        {"rank": 1, **blocked},
        {"rank": 2, "product_id": "PPP-200", "question": "Will airport power support my gear?", "angle": "Check compatibility before battery capacity.", "human_reality": "airport travel"},
        {"rank": 3, "product_id": "OTHER", "question": "Which published details belong on a packing list?", "angle": "Keep published details handy.", "human_reality": "packing"},
    ]
    selected, considered = recovery.select_replacement(shortlist, blocked_fingerprint=blocked)
    assert selected and selected["rank"] == 3
    assert considered[0]["reason"] == "blocked_opportunity_fingerprint"


def test_blocked_candidate_a_retains_distinct_candidate_b_before_any_visual_generation(tmp_path, monkeypatch):
    generated = []
    pool = [
        {"rank": 1, "candidate_id": "A:blocked", "opportunity_id": "blocked", "engine": "A", "product_id": "PPP-200", "topic": "PowerPulse", "question": "Can it fit before a trip?", "angle": "Establish fit before reserve.", "human_reality": "before a trip"},
        {"rank": 2, "candidate_id": "B:distinct", "opportunity_id": "distinct", "engine": "B", "product_id": "", "topic": "Daily routine", "question": "Which routine depends on the next outlet?", "angle": "Map the job before choosing what to protect.", "human_reality": "a normal workday"},
    ]
    content = {
        "post_id": "candidate-a", "candidate_attempt_id": "candidate-a:candidate-1", "product_id": "PPP-200",
        "strategic_brief": {"opportunity_shortlist": pool},
        "copy": {"hook": "Can it fit before a trip?", "takeaway": "Establish fit before reserve.", "strategy_lock": {"angle": "Establish fit before reserve.", "customer_moment": "before a trip"}, "decision_insight": {"relationship": "Output determines fit before reserve."}, "evidence_readiness": {"status": "RESEARCH_REQUIRED", "claims": [{"claim": "Output determines fit before reserve.", "centrality": "CENTRAL", "research_status": "RESEARCH_REQUIRED"}]}}
    }

    remediation = run_engine._remediation_context(content, {"decision": "do_not_publish"}, {"ok": True})

    assert remediation["replacement_candidate"]["candidate_id"] == "B:distinct"
    assert remediation["replacement_candidate"]["engine"] == "B"
    assert generated == []


def test_remediation_semantic_reuse_abstains_before_provider_generation(tmp_path, monkeypatch):
    generated = []

    class Provider:
        def generate(self, **kwargs):
            generated.append(kwargs)
            raise AssertionError("a semantically blocked remediation candidate must not render")

    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "_runtime_strategy_lock", lambda brief, *args: {
        "customer_moment": "before a trip",
        "human_need": "airport outlet compatibility",
        "angle": brief.angle,
        "audience": brief.audience_segment,
        "topic": brief.topic_path["topic"],
        "reader_job": brief.reader_job,
        "CTA_strategy": "Compare options",
    })
    monkeypatch.setattr(orchestrator.engines, "_pick_engine", lambda *args: "A", raising=False)

    service = orchestrator.SocialIntelligenceOrchestrator(provider=Provider(), data_dir=str(tmp_path))
    remediation = {
        "excluded_concepts": ["before a trip", "airport outlet compatibility"],
        "excluded_product_ids": ["PPP-200"],
        "exclude_engine_a_decision_thesis": True,
    }

    try:
        service.create_post(preferred_engine="A", record_memory=False, remediation_context=remediation)
    except RuntimeError as exc:
        assert str(exc) == "no viable opportunities generated"
    else:
        raise AssertionError("semantic reuse entered copy or visual generation")
    assert generated == []


def test_facebook_rejects_caption_mutated_after_final_lock():
    content = {
        "fb_caption": "different text",
        "platform_posts": {"facebook": {
            "final_caption": "approved text",
            "final_caption_lock": "approved text",
            "final_caption_qa": {"metrics": {"final_caption": "approved text"}},
        }},
    }
    content["platform_posts"]["facebook"]["final_caption_lock"] = "mutated text"

    try:
        publish_facebook.publish(content, "", dry_run=True)
    except RuntimeError as exc:
        assert str(exc) == "facebook_final_caption_authority_mismatch"
    else:
        raise AssertionError("publisher accepted a caption changed after final lock")


def test_no_viable_opportunity_is_a_persisted_abstention_not_a_scheduler_failure(monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(run_engine.generate_posts, "ensure_runtime_data", lambda: None)
    monkeypatch.setattr(
        run_engine.generate_posts,
        "generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no viable opportunities generated")),
    )
    monkeypatch.setattr(run_engine.generate_posts, "load_history", lambda: {"posts": []})
    monkeypatch.setattr(run_engine.generate_posts, "save_history", lambda history: saved.append(history))
    monkeypatch.setenv("SOCIAL_DRY_RUN", "true")
    monkeypatch.setenv("POST_SLOT", "morning")

    run_engine.main()

    record = saved[-1]["posts"][-1]
    assert record["status"] == "abstained_no_viable_opportunity"
    assert record["error"] == "no_viable_opportunities"
    assert record["platform_records"] == []
    assert record["final_memory"]["final_outcome"] == "abstain"


def test_no_viable_replacement_preserves_the_original_remediation_audit():
    content = {
        "validation_status": "passed",
        "validation_errors": [],
        "evidence_remediation": {
            "original_candidate_id": "candidate-a",
            "original_concept": {"angle": "blocked method"},
            "original_evidence_readiness": {"status": "RESEARCH_REQUIRED"},
        },
    }

    run_engine._mark_no_viable_replacement_abstention(content)

    assert content["validation_status"] == "failed"
    assert "no_viable_replacement_opportunity" in content["validation_errors"]
    assert content["evidence_remediation"]["status"] == "ABSTAINED_NO_VIABLE_REPLACEMENT"
    assert content["evidence_remediation"]["original_candidate_id"] == "candidate-a"
    assert content["evidence_remediation"]["semantic_difference_reason"] == "no_viable_replacement_opportunity"


def test_no_viable_replacement_is_not_reclassified_as_candidate_a_reuse():
    content = {
        "post_id": "candidate-a",
        "candidate_attempt_id": "candidate-a:candidate-1",
        "validation_status": "failed",
        "validation_errors": ["no_viable_replacement_opportunity"],
        "copy": {"hook": "Blocked question", "strategy_lock": {"angle": "Blocked angle"}},
        "evidence_remediation": {
            "status": "ABSTAINED_NO_VIABLE_REPLACEMENT",
            "semantic_difference_reason": "no_viable_replacement_opportunity",
        },
    }
    remediation = {"original_concept": {"question": "Blocked question", "angle": "Blocked angle"}}

    run_engine._finalize_evidence_remediation(content, remediation)

    assert content["evidence_remediation"]["status"] == "ABSTAINED_NO_VIABLE_REPLACEMENT"
    assert content["evidence_remediation"]["semantic_difference_reason"] == "no_viable_replacement_opportunity"
    assert "remediation_reused_blocked_concept" not in content["validation_errors"]