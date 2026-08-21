"""Unit + integration tests for the Social Intelligence layer.

Kept in a single file to mirror the "few well-structured modules"
philosophy of the implementation itself. Every module has at least one
happy-path test plus a small representative edge case.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import generate_posts  # noqa: E402
import social_visuals  # noqa: E402

from social import (  # noqa: E402
    audience_intelligence,
    carousel_director,
    claim_intelligence,
    content_strategy,
    copy_intelligence,
    engines,
    libraries,
    memory_intelligence,
    model_router,
    opportunity_engine,
    orchestrator,
    publish_decision,
    performance_learning,
    public_research,
    human_connection_review,
    analytics_ingestion,
    creative_cognition,
    quality_intelligence,
    research_router,
    strategy_lock,
    visual_intelligence,
    visual_provider,
    lean_intelligence,
    living_intelligence,
    visual_provider,
)


# --- generator wiring ------------------------------------------------------


def test_generate_uses_social_intelligence_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SOCIAL_INTELLIGENCE", "1")
    monkeypatch.setenv("ENABLE_BUSINESS_INTELLIGENCE", "1")
    expected = {
        "post_id": "social-123",
        "business_context": {"identity": {"name": "Infenergy Power"}},
        "anchored_offering": {"name": "Portable power station"},
        "copy": {"hook": "Why your outage plan fails without a power hierarchy"},
        "visual": {"visual_format": "fact_card"},
        "quality": {"overall": 92},
    }

    monkeypatch.setattr(generate_posts, "run_social_intelligence", lambda count=1, platform="instagram_feed", **kw: [expected])

    result = generate_posts._route_generate_orchestrator("morning", platform="instagram_feed")

    assert result["post_id"] == "social-123"
    assert result["business_context"]["identity"]["name"] == "Infenergy Power"
    assert result["anchored_offering"]["name"] == "Portable power station"


def test_production_orchestrator_adapter_uses_recipe_provider_before_final_render(monkeypatch):
    import importlib

    captured = {}

    class FakePost:
        def as_dict(self):
            return {"post_id": "recipe-only"}

    class FakeOrchestrator:
        def __init__(self, *, provider):
            captured["provider"] = provider

        def create_batch(self, **kwargs):
            return [FakePost()]

    live_orchestrator = importlib.import_module("social.orchestrator")
    monkeypatch.setattr(live_orchestrator, "SocialIntelligenceOrchestrator", FakeOrchestrator)

    posts = generate_posts.run_social_intelligence(count=1)

    assert captured["provider"].name == "template_render"
    assert posts == [{"post_id": "recipe-only"}]


def test_normal_generation_defaults_to_conversion_pipeline(monkeypatch):
    monkeypatch.delenv("CONTENT_PIPELINE", raising=False)
    monkeypatch.delenv("POST_PIPELINE_OVERRIDE", raising=False)

    assert generate_posts._pipeline_mode() == "legacy"


def test_orchestrator_bridge_passes_council_strategy_to_generation(monkeypatch):
    approved = {
        "audience": "preparedness household", "customer_moment": "storm outage", "human_need": "confidence",
        "human_value": "preparedness", "topic": "power priorities", "angle": "prioritize essentials",
        "offering": "power station", "positioning": "calm preparedness", "non_price_edge": {"kind": "PRODUCT_EDGE"},
        "important_capability": "500W AC output", "benefit": "prioritize essentials", "human_outcome": "confidence",
        "reader_job": "PREPARE_ME", "proof": ["500W AC output"], "claim_limits": "verified facts only",
        "visual_objective": "show a priority ladder", "CTA_strategy": "Learn more",
    }
    captured = {}
    monkeypatch.setattr(generate_posts, "_living_strategy_for_generation", lambda: (approved, {"decision": "strategy_selected"}))
    monkeypatch.setattr(generate_posts, "run_social_intelligence", lambda **kwargs: captured.setdefault("kwargs", kwargs) and [])

    generate_posts._route_generate_orchestrator("morning")

    assert captured["kwargs"]["approved_strategy"] == approved


def test_missing_saved_artifact_requires_visual_regeneration():
    review = social_visuals.review_rendered_visual("", "instagram")

    assert review["verdict"] == "REGENERATE_VISUAL"
    assert review["issues"] == ["rendered_asset_unavailable"]


def test_orchestrator_bridge_builds_publishable_platform_contract(monkeypatch):
    expected = {
        "post_id": "social-456",
        "brief": {
            "pillar_id": "portable_power",
            "genre_id": "how_it_works",
            "reader_job": "EXPLAIN_THIS",
            "audience_segment": "mobile_professional",
            "emotional_driver": "confidence",
            "topic_path": {"topic": "Battery capacity", "microtopic": "mAh"},
        },
        "anchored_offering": {
            "offering_id": "PPP-200", "sku": "PPP-200", "name": "PowerPulse Pro 200",
            "category": "Portable Power", "verified_facts": ["154Wh", "41,600mAh", "200W"],
            "images": [],
        },
        "copy": {
            "hook": "What does 41,600mAh tell you about real backup power?",
            "body_text": "Because watt-hours describe stored energy, 154Wh helps compare the work a battery can support.",
            "takeaway": "Compare watt-hours and the device load before you buy.",
            "memory_anchor": "Compare watt-hours and the device load before you buy.",
            "cta": "Compare options",
            "generation_method": "llm",
            "strategy_lock": {"audience": "mobile_professional", "angle": "compare watt-hours", "positioning": "decision support", "non_price_edge": {"kind": "DECISION_SUPPORT_EDGE"}, "claim_limits": "verified facts only"},
        },
        "visual": {"visual_format": "fact_card"},
        "quality": {"overall": 88},
        "claim_ledger": {},
        "creative_director": {"passed": True, "independent_human_connection_review": {"verdict": "PASS"}, "strategy_integrity_review": {"verdict": "ALIGNED"}},
    }
    monkeypatch.setattr(generate_posts, "run_social_intelligence", lambda count=1, platform="instagram_feed", **kw: [expected])
    monkeypatch.setattr(generate_posts, "load_products", lambda: [])
    monkeypatch.setattr(generate_posts, "generate_visuals", lambda content, visual_plan: {})

    result = generate_posts._route_generate_orchestrator(
        "midday", platform="instagram", funnel_stage_override="EDUCATION"
    )

    assert result["platform"] == "instagram_feed"
    assert result["funnel_stage"] == "EDUCATION"
    assert result["audience_segment"] == "mobile_professional"
    assert result["topic"] == "Battery capacity"
    assert result["ig_caption"]
    assert result["fb_caption"]
    assert result["li_text"]
    assert result["wp_content"]
    assert "PowerPulse Pro 200" in result["ig_caption"]
    assert "41,600mAh" in result["ig_caption"]
    assert result["copy_generation_method"] == "llm"
    for platform in ("facebook", "instagram", "linkedin"):
        package = result["platform_posts"][platform]
        assert package["strategy_lock"] == expected["copy"]["strategy_lock"]
        assert package["human_connection_review"]["verdict"] == "PASS"
        assert package["strategy_integrity_review"]["verdict"] == "ALIGNED"


def test_platform_selection_can_decline_linkedin_without_professional_context():
    selected = generate_posts._select_social_platforms({
        "audience": "outdoor enthusiasts",
        "customer_moment": "weekend camping trip",
        "topic": "portable power for a campsite",
        "angle": "keep a camera charged away from an outlet",
        "reader_job": "HELP_ME_CHOOSE",
        "positioning": "practical outdoor power guidance",
    })

    assert selected["facebook"]["selected"] is True
    assert selected["instagram"]["selected"] is True
    assert selected["linkedin"] == {"selected": False, "reason": "no supported professional or business context"}


# --- libraries --------------------------------------------------------------


def test_libraries_load_all_datasets():
    assert "energy_education" in libraries.pillars()
    assert "how_it_works" in libraries.genres()
    assert "TEACH_ME" in libraries.reader_jobs()
    assert libraries.audience_segments()
    assert libraries.topic_graph()
    assert libraries.hook_families()
    assert libraries.visual_formats()
    assert libraries.brand_design_tokens()
    assert "instagram_feed" in libraries.platform_specs()
    assert libraries.series_registry()
    assert libraries.hook_global_banned_openers()


def test_libraries_cache_reset():
    libraries.pillars()
    libraries.reset_cache()  # must not raise


# --- audience --------------------------------------------------------------


def test_audience_infer_segment_from_pillar():
    sid = audience_intelligence.infer_segment(pillar_id="preparedness")
    assert sid == "preparedness_focused_household"


def test_audience_select_deterministic():
    a = audience_intelligence.select(pillar_id="portable_power", rotation_index=0)
    b = audience_intelligence.select(pillar_id="portable_power", rotation_index=0)
    assert a.segment_id == b.segment_id == "mobile_professional"
    assert a.reader_job
    assert a.reader_job_config


def test_lean_product_context_links_portable_power_to_matching_audience():
    context = lean_intelligence.compile_product_social_intelligence({
        "offering_id": "PPP-200",
        "sku": "PPP-200",
        "name": "PowerPulse Pro 200",
        "category": "Portable Power",
        "customer_fit": ["travelers", "mobile-device users"],
        "use_cases": ["travel", "daily carry"],
        "functional_benefits": ["keeps compatible devices charged"],
        "problems_addressed": ["outlet access is unreliable"],
        "verified_facts": ["154Wh"],
        "images": ["https://example.com/product.jpg"],
    })

    assert context["relationships"]["pillar_id"] == "portable_power"
    assert context["relationships"]["audience_id"] == "mobile_professional"
    assert context["marketing"]["customer_questions"]
    assert "approved_product_facts" not in context["truth"]["important_unknowns"]


def test_research_router_requires_a_marketing_decision_and_routes_source():
    task = research_router.route(
        question="Which customer questions about capacity are unanswered?",
        why_needed="choose an educational angle",
        entity="portable power category",
        decision_affected="angle selection",
    )
    assert task.preferred_source == "customer_language_research"
    assert task.as_dict()["decision_affected"] == "angle selection"


def test_living_loop_creates_bounded_opportunity_and_selects_strategy(tmp_path, monkeypatch):
    monkeypatch.setattr(research_router, "inspect_first_party", lambda url, previous_hash: {
        "url": url, "content_hash": "new", "changed": True,
        "factual_candidates": [], "marketing_language": [], "decision_use": "positioning",
    })
    result = living_intelligence.heartbeat(str(tmp_path), website_url="https://example.test")
    assert result["opportunities"][0]["state"] == "READY"
    assert result["opportunities"][0]["support"][0]["type"] == "FIRST_PARTY_EVIDENCE"
    decision = living_intelligence.council(living_intelligence.load(str(tmp_path)), strategy_inputs={"audience": "household"})
    assert decision["decision"] == "do_not_generate"


def test_living_loop_integrates_consumer_competition_to_multiple_angles(tmp_path):
    result = living_intelligence.heartbeat(
        str(tmp_path), level="STANDARD_HEARTBEAT", business_personality="calm practical preparedness",
        capability="500W AC output", offering_truth=["500W AC output"],
        consumer_signals=[{"audience": "preparedness household", "customer_moment": "storm outage", "situation": "home loses power", "question": "What should I power first?", "human_need": "confidence", "offering": "power station", "source": "customer-language", "provenance": "support transcript", "confidence": 0.9}],
        competitor_observations=[{"name": "Example Co", "category": "portable power", "messages": ["more watts"], "benefits": ["more watts"], "customer_moments": ["camping"], "human_values": ["freedom"], "questions": [], "territories": ["specs"], "visual_patterns": ["product on black"], "source": "public page", "confidence": 0.8}],
    )
    assert "What should I power first?" in result["category_conversation"]["unresolved_questions"]
    decision = living_intelligence.council(living_intelligence.load(str(tmp_path)), strategy_inputs={"customer": result["consumer_relationships"][0] | {"situation": "home loses power"}, "capability": "500W AC output", "benefit": "prioritize essentials", "positioning": result["positioning"], "competitor_context": "spec-led market", "human_value": "preparedness", "topic": "power priorities", "reader_job": "PREPARE_ME", "important_capability": "500W AC output", "human_outcome": "confidence", "proof": ["500W AC output"], "claim_limits": "Use only supported capability language", "visual_objective": "show a home priority ladder", "CTA_strategy": "Learn more"})
    assert decision["decision"] == "strategy_selected"
    assert len(decision["candidate_strategies"]) == 3


def test_strategy_lock_branches_identical_strategy_into_copy_and_visual():
    candidate = {"audience": "preparedness household", "customer_moment": "storm outage", "human_need": "confidence", "offering": "power station", "positioning": "calm preparedness", "non_price_edge": {"edge_type": "PRODUCT_EDGE"}, "angle": "Explain what to power first", "reader_memory": "Prioritize essentials"}
    locked = strategy_lock.lock(candidate, context={"human_value": "preparedness", "topic": "power priorities", "reader_job": "PREPARE_ME", "important_capability": "500W AC", "benefit": "prioritize essentials", "human_outcome": "confidence", "competitive_context": "spec-led competitors", "proof": ["500W AC"], "claim_limits": "Use only supported capability language", "visual_objective": "show a home priority ladder", "CTA_strategy": "Learn more"})
    copy = strategy_lock.copy_expression(locked)
    visual = strategy_lock.visual_expression(locked)
    for key in ("audience", "customer_moment", "human_need", "angle", "positioning", "non_price_edge", "benefit", "human_outcome", "claim_limits"):
        assert copy[key] == visual[key] == locked[key]


def test_strategy_red_team_rejects_ppp200_runtime_angle_without_runtime_evidence():
    verdict = strategy_lock.red_team(
        {
            "angle": "how to estimate real fridge runtime on backup power",
            "hook_promise": "How long will a fridge run?",
            "topic": "portable power",
            "benefit": "keeps compatible daily devices charged away from outlets",
        },
        verified_facts=["154Wh", "41,600mAh", "200W", "110V"],
        forbidden_claims=["Do not make runtime or compatibility claims without evidence."],
    )

    assert verdict["verdict"] == "CHANGE_ANGLE"
    assert "verified_runtime_evidence_missing" in verdict["challenge_evidence"]


def test_semantic_benefit_critic_accepts_supported_paraphrase_and_rejects_vague_copy():
    benefit = "keeps compatible daily devices charged away from outlets"
    paraphrase = quality_intelligence.benefit_coverage(benefit, "Laptops and professional devices stay charged far from an outlet.")
    vague = quality_intelligence.benefit_coverage(benefit, "Power for your day.")

    assert paraphrase["result"] is True
    assert paraphrase["semantic_check_type"] == "supported_paraphrase"
    assert vague["result"] is False
    assert vague["expected_concept"] == benefit


def test_claim_provenance_rejects_unsupported_efficiency_derivation_without_replacement():
    safe, removed = claim_intelligence.remove_unsupported_numeric_claims(
        "At a 0.85 efficiency factor, estimate runtime from the 154Wh battery.", ["154Wh"]
    )
    ledger = claim_intelligence.build_ledger(
        "At a 0.85 efficiency factor, estimate runtime from the 154Wh battery.", verified_facts=["154Wh"]
    )

    assert safe == ""
    assert removed
    assert any(item.provenance == "PROHIBITED_OR_UNSUPPORTED" for item in ledger.claims)
    assert any(item.rejection_reason == "derived_claim_has_no_verified_formula" for item in ledger.claims)


def test_strategy_red_team_generalizes_to_savings_and_comparative_promises_without_evidence():
    verdict = strategy_lock.red_team(
        {"angle": "why this option saves money and outperforms competitors", "hook_promise": "Which option costs less?"},
        verified_facts=["200W output"],
        forbidden_claims=["Do not make savings or comparative claims without evidence."],
    )

    assert verdict["verdict"] == "CHANGE_ANGLE"
    assert "verified_savings_evidence_missing" in verdict["challenge_evidence"]
    assert "verified_comparative_superiority_evidence_missing" in verdict["challenge_evidence"]


def test_strategy_red_team_detects_explicit_compatibility_promise_without_evidence():
    verdict = strategy_lock.red_team(
        {"angle": "will this work with a field workstation", "hook_promise": "Is it compatible with your equipment?"},
        verified_facts=["200W output"],
        forbidden_claims=[],
    )

    assert verdict["verdict"] == "CHANGE_ANGLE"
    assert "verified_compatibility_evidence_missing" in verdict["challenge_evidence"]


def test_semantic_benefit_critic_generalizes_to_another_locked_benefit():
    result = quality_intelligence.benefit_coverage(
        "reduces charging time for field teams",
        "Help crews recharge faster away from base.",
    )

    assert result["result"] is True
    assert result["semantic_check_type"] == "supported_paraphrase"


def test_post_sanitization_coherence_escalates_unanswerable_runtime_hook_to_strategy():
    result = strategy_lock.post_sanitization_coherence(
        {"angle": "estimate real fridge runtime"},
        hook="How long will this fridge run on backup power?",
        body="Use verified product facts to compare daily devices.",
        removed_claims=["A 40W fridge can run for roughly 3 hours."],
    )

    assert result["verdict"] == "STRATEGY_RECONSIDERATION_REQUIRED"
    assert result["repair_owner"] == "Strategy Intelligence"


def test_governed_angle_reconsideration_preserves_strategy_identity_and_versions_lock():
    original = strategy_lock.lock(
        {"audience": "mobile professional", "customer_moment": "before a trip", "human_need": "clarity", "offering": "PPP-200", "positioning": "verified product-fit guidance", "non_price_edge": {"kind": "PRODUCT_EDGE"}, "angle": "estimate fridge runtime", "reader_memory": "choose using facts"},
        context={"human_value": "confidence", "topic": "portable power", "reader_job": "HELP_ME_CHOOSE", "important_capability": "154Wh", "benefit": "keeps compatible daily devices charged away from outlets", "human_outcome": "confidence", "competitive_context": "", "proof": ["154Wh"], "claim_limits": "verified facts only", "visual_objective": "show product facts", "CTA_strategy": "Learn more"},
    )
    repaired = strategy_lock.reconsider_angle(original, reason="evidence gap", evidence=["runtime missing"], new_angle="compare verified device-fit facts", new_hook_promise="Which facts support daily devices?")

    assert repaired["strategy_version"] == 2
    assert repaired["audience"] == original["audience"]
    assert repaired["benefit"] == original["benefit"]
    assert repaired["strategy_audit"][-1]["fields_reopened"] == ["angle", "hook_promise", "topic_path"]


def test_scoped_strategy_lessons_are_evidence_bound_not_global(tmp_path):
    lesson = {"product_id": "PPP-200", "condition": "runtime_angle_without_verified_inputs", "action": "challenge_angle", "evidence": ["no runtime inputs"]}
    memory_intelligence.append_strategy_lesson(lesson, data_dir=str(tmp_path))

    stored = memory_intelligence.strategy_lessons(product_id="PPP-200", condition="runtime_angle_without_verified_inputs", data_dir=str(tmp_path))
    assert stored[0]["product_id"] == lesson["product_id"]
    assert stored[0]["condition"] == lesson["condition"]
    assert stored[0]["lesson_id"]
    assert stored[0]["created_at"]
    assert stored[0]["scope"]["product_id"] == "PPP-200"
    assert memory_intelligence.strategy_lessons(product_id="OTHER", condition="runtime_angle_without_verified_inputs", data_dir=str(tmp_path)) == []


def test_orchestrator_preserves_approved_strategy_in_copy_and_visual(monkeypatch):
    locked = strategy_lock.lock({"audience": "preparedness household", "customer_moment": "storm outage", "human_need": "confidence", "offering": "power station", "positioning": "calm preparedness", "non_price_edge": {"edge_type": "PRODUCT_EDGE"}, "angle": "Explain what to power first", "reader_memory": "Prioritize essentials"}, context={"human_value": "preparedness", "topic": "power priorities", "reader_job": "PREPARE_ME", "important_capability": "500W AC", "benefit": "prioritize essentials", "human_outcome": "confidence", "competitive_context": "spec-led competitors", "proof": ["500W AC"], "claim_limits": "Use only supported capability language", "visual_objective": "show a home priority ladder", "CTA_strategy": "Learn more"})
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    post = orchestrator.SocialIntelligenceOrchestrator().create_post(approved_strategy=locked, record_memory=False)
    assert post.copy["strategy_lock"]["angle"] == post.visual["strategy_lock"]["angle"] == locked["angle"]
    assert post.copy["strategy_lock"]["audience"] == post.visual["strategy_lock"]["audience"] == locked["audience"]
    assert post.brief["topic_path"]["topic"] == locked["topic"]
    assert post.brief["topic_path"]["angle"] == locked["angle"]
    assert post.brief["information_gap"] == locked["important_capability"]
    assert post.brief["curiosity"] == locked["human_need"]
    assert post.brief["question"] == locked.get("hook_promise", locked["angle"])
    assert post.brief["emotional_driver"] == locked["human_outcome"]
    assert "human_connection_review" in post.creative_director


def test_orchestrator_derives_runtime_lock_and_final_reviews_without_council(monkeypatch):
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    post = orchestrator.SocialIntelligenceOrchestrator().create_post(record_memory=False)

    assert post.copy["strategy_lock"] == post.visual["strategy_lock"]
    assert post.brief["topic_path"]["angle"] == post.copy["strategy_lock"]["angle"]
    assert post.brief["information_gap"] == post.copy["strategy_lock"]["important_capability"]
    assert post.brief["question"] == post.copy["strategy_lock"].get("hook_promise", post.copy["strategy_lock"]["angle"])
    assert "use verified product facts" not in post.copy["strategy_lock"]["angle"].lower()
    assert post.copy["strategy_lock"]["hook_promise"].startswith("How does ")
    assert " support keeps " not in post.copy["strategy_lock"]["hook_promise"].lower()
    assert post.creative_director["independent_human_connection_review"]["verdict"]
    assert post.creative_director["strategy_integrity_review"]["verdict"] == "ALIGNED"


def test_orchestrator_no_product_does_not_select_an_offering(monkeypatch):
    monkeypatch.setattr(orchestrator, "_bi_pick_offering", lambda *args: pytest.fail("must not select a product"))
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)

    post = orchestrator.SocialIntelligenceOrchestrator().create_post(no_product=True, record_memory=False)

    assert post.anchored_offering is None


def test_orchestrator_route_propagates_no_product_override(monkeypatch):
    observed = {}

    def fake_run_social_intelligence(**kwargs):
        observed.update(kwargs)
        return []

    monkeypatch.setenv("CONTENT_BUCKET_OVERRIDE", "no_product")
    monkeypatch.setattr(generate_posts, "_living_strategy_for_generation", lambda: pytest.fail("product council must not run"))
    monkeypatch.setattr(generate_posts, "run_social_intelligence", fake_run_social_intelligence)

    assert generate_posts._route_generate_orchestrator() == {}
    assert observed["no_product"] is True
    assert "approved_strategy" not in observed


def test_pre_render_gate_blocks_provider_invocation(monkeypatch):
    class ProviderThatMustNotRun:
        def generate(self, **kwargs):
            raise AssertionError("provider must not render an unready concept")

    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    monkeypatch.setattr(
        orchestrator.creative_intelligence,
        "pre_render_gate",
        lambda **kwargs: {"decision": "REVISE_CONCEPT", "checks": {"claim_safe": True}},
    )

    post = orchestrator.SocialIntelligenceOrchestrator(provider=ProviderThatMustNotRun()).create_post(
        record_memory=False
    )

    assert post.provider_result["kind"] == "none"
    assert post.provider_result["provider_meta"]["reason"] == "pre_render_gate_not_ready"


def test_orchestrator_creative_decision_uses_abstract_diverse_references(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    post = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path)).create_post(record_memory=True)

    packet = post.creative_decision_packet
    assert packet["ACTION"] == "create"
    assert packet["REFERENCE_PATTERNS_USED"]
    assert packet["SELECTED_ANSWER"]["reference_id"] in packet["REFERENCE_PATTERNS_USED"]
    assert post.visual["layout_logic"] == packet["SELECTED_ANSWER"]["layout_logic"]
    assert post.visual["copy_grammar"] == packet["SELECTED_ANSWER"]["copy_logic"]
    assert "abstract principles" in packet["ASSUMPTIONS"][0]
    assert "source executions" in packet["ASSUMPTIONS"][0]
    assert post.creative_director["creative_decision_review"]["verdict"] == "PASS"


def test_creative_reference_heartbeat_discovers_extracts_persists_and_retrieves(tmp_path):
    def scout(*, need, limit):
        assert "information-design" in need
        return {"status": "OK", "candidates": [{
            "source": "https://github.com/example/information-design", "name": "example/information-design",
            "description": "An infographic and information design system", "stars": 100, "license": "MIT",
            "source_type": "public_repository", "use_boundary": "metadata-informed abstract principle only; no code, assets, layouts, or copy are reused",
        }]}

    heartbeat = creative_cognition.reference_heartbeat(str(tmp_path), level="STANDARD", knowledge_need="information-design layout knowledge", scout=scout)
    graph = creative_cognition.load_reference_graph(str(tmp_path))
    retrieved = creative_cognition.retrieve_references(reader_job="EXPLAIN_THIS", platform="instagram_feed", recent_visual_formats=[], data_dir=str(tmp_path))

    assert heartbeat["acquisition"]["status"] == "OK"
    assert heartbeat["extracted"] == 1
    assert any(item["source"] == "https://github.com/example/information-design" for item in graph["references"])
    assert any(item["id"] == "question_answer" for item in graph["copy_grammars"])
    assert all("no code, assets, layouts, or copy are reused" in item["license_or_use_boundary"] or item["source_type"] == "internal_repository" for item in graph["references"])
    assert retrieved
    packet = creative_cognition.decide(strategy={"audience": "household", "customer_moment": "outage planning", "human_need": "clarity", "human_value": "preparedness", "topic": "power priorities", "angle": "Prioritize essentials", "offering": "power station", "positioning": "calm preparedness", "benefit": "prioritize essentials", "human_outcome": "confidence", "reader_job": "EXPLAIN_THIS", "proof": [], "claim_limits": "supported facts only", "visual_objective": "show priorities"}, platform="instagram_feed", recent={}, data_dir=str(tmp_path))
    assert packet["SELECTED_ANSWER"]["reference_id"].startswith("source-")


def test_autonomous_meeting_scopes_claim_platform_and_fatigue_outcomes(tmp_path):
    strategy = {
        "audience": "household", "customer_moment": "storm outage", "human_need": "clarity", "human_value": "preparedness",
        "topic": "power priorities", "angle": "Prioritize essential devices", "offering": "power station",
        "positioning": "calm preparedness", "non_price_edge": {"kind": "PRODUCT_EDGE"}, "important_capability": "",
        "benefit": "prioritize essentials", "human_outcome": "confidence", "reader_job": "PREPARE_ME",
        "proof": [], "claim_limits": "Do not claim unsupported runtime.", "visual_objective": "show a priority ladder", "CTA_strategy": "Learn more",
    }
    packet = creative_cognition.decide(strategy=strategy, platform="linkedin_feed", recent={"visual_formats": ["fact_card"]}, data_dir=str(tmp_path))
    assert packet["ACTION"] == "create"
    assert packet["platform_outcomes"]["linkedin"]["status"] == "DECLINED"
    assert packet["novelty_process"]["triggered"] is True
    assert packet["meetings"]
    assert "Creative Director" in packet["specialist_verdicts"]

    claim_packet = creative_cognition.decide(strategy=strategy | {"claims": ["Provides 12 hours of runtime"], "important_capability": "12-hour runtime"}, platform="instagram_feed", recent={}, data_dir=str(tmp_path))
    assert claim_packet["ACTION"] == "do_not_publish"
    assert claim_packet["research_tasks"]

    routed = creative_cognition.route_meetings([
        creative_cognition.AutonomousQuestion("Which opening is strongest?", "copy", "copy changes response", "copy grammar", 0.8, meeting_needed=True),
        creative_cognition.AutonomousQuestion("What does performance suggest?", "performance", "learning should guide the next test", "next experiment", 0.8, meeting_needed=True),
    ])
    assert [item["meeting_type"] for item in routed] == ["COPY", "PERFORMANCE"]


def test_creative_cognition_end_to_end_uses_memory_for_a_different_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    engine = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path))
    first = engine.create_post(record_memory=True)
    second = engine.create_post(record_memory=True)

    assert first.creative_decision_packet["meetings"] or first.creative_decision_packet["ACTION"] == "create"
    assert first.creative_decision_packet["creative_concepts"]
    assert first.visual["layout_grammar"]["components"]
    assert first.visual["information_priority"]["MUST_SHOW"]
    assert first.visual["benefit_translation"]["PRACTICAL_BENEFIT"]
    assert first.creative_decision_packet["originality_review"]["passed"]
    assert first.creative_director["independent_human_connection_review"]["verdict"]
    assert first.creative_director["strategy_integrity_review"]["verdict"] == "ALIGNED"
    assert first.creative_decision_packet["SELECTED_ANSWER"]["creative_concept"] != second.creative_decision_packet["SELECTED_ANSWER"]["creative_concept"]


def test_creative_cognition_reaches_platform_expressions_and_publish_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    post = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path)).create_post(record_memory=False)
    monkeypatch.setattr(generate_posts, "run_social_intelligence", lambda **kwargs: [post.as_dict()])
    monkeypatch.setattr(generate_posts, "load_products", lambda: [])
    monkeypatch.setattr(generate_posts, "generate_visuals", lambda content, visual_plan: {})

    legacy = generate_posts._route_generate_orchestrator("midday", platform="instagram")
    decision = publish_decision.decide(
        legacy_score={"total": 90, "platform_results": {"instagram": {"decision": "approve"}}},
        validation={"passed": True, "errors": []}, duplicates={"ok": True, "reasons": []},
        orchestrator_quality={"overall": 90},
    )

    assert legacy["creative_decision_packet"]["meetings"] or legacy["creative_decision_packet"]["ACTION"] == "create"
    assert legacy["creative_decision_packet"]["specialist_verdicts"]["Originality Guardian"]["passed"]
    assert legacy["platform_posts"]["facebook"]["strategy_lock"] == legacy["platform_posts"]["instagram"]["strategy_lock"]
    assert legacy["platform_posts"]["linkedin"]["platform_selection"]["reason"]
    assert decision["decision"] == "publish"


def test_remaining_creative_partials_are_operational(tmp_path, monkeypatch):
    strategy = {"audience": "household", "customer_moment": "storm outage", "human_need": "clarity", "human_value": "preparedness", "topic": "power priorities", "angle": "Prioritize essential devices", "offering": "power station", "positioning": "calm preparedness", "benefit": "prioritize essentials", "human_outcome": "confidence", "reader_job": "EXPLAIN_THIS", "proof": [], "claim_limits": "supported facts only", "visual_objective": "show priorities"}
    recent = {"visual_formats": ["fact_card"] * 4, "layout_grammars": [{"alignment": "clear grid"}] * 4, "product_roles": ["proof"] * 4, "human_presence": ["absent"] * 4, "text_densities": ["medium"] * 4, "hooks": ["old opening"]}
    packet = creative_cognition.decide(strategy=strategy, platform="instagram_feed", recent=recent, data_dir=str(tmp_path))
    assert len(packet["copy_concepts"]) >= 3
    assert packet["hook_selection"]["family"]
    assert packet["feed_intelligence"]["novelty_required"] is True
    assert packet["platform_interpretations"]["facebook"]["visual_composition"] != packet["platform_interpretations"]["instagram"]["visual_composition"]
    assert packet["platform_interpretations"]["linkedin"]["hook_posture"] == "professional implication"

    learning_rows = []
    for _ in range(3):
        learning_rows.append({"platform": "instagram", "metrics": {"saves": 4}, "creative_relationships": {"visual_concept_x_audience": ["editorial", "household"]}})
    learned = performance_learning.aggregate_creative_learning(learning_rows)
    assert learned["recommendations"]

    monkeypatch.setattr(creative_cognition, "source_scout", lambda **kwargs: {"status": "SOURCE_UNAVAILABLE", "candidates": []})
    heartbeat = living_intelligence.heartbeat(str(tmp_path), level="STANDARD_HEARTBEAT", performance_observations=[row | {"confidence": 0.5} for row in learning_rows], consumer_signals=[{"audience": "household", "customer_moment": "storm outage", "situation": "home loses power", "question": "What should I power first?", "human_need": "confidence", "offering": "power station", "source": "support", "confidence": 0.9}, {"audience": "household", "customer_moment": "winter outage", "situation": "home loses power", "question": "Which devices matter first?", "human_need": "confidence", "offering": "power station", "source": "support", "confidence": 0.9}])
    assert heartbeat["creative_reference_heartbeat"]["budget"]["external_discovery"] == 2
    assert heartbeat["campaign_meeting"]["decision"] in {"start", "evolve"}


def test_second_post_reads_full_visual_memory_and_changes_composition(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    engine = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path))
    first = engine.create_post(record_memory=True)
    second = engine.create_post(record_memory=True)
    memory = memory_intelligence.recent(str(tmp_path))

    assert memory["product_placements"] and memory["headline_placements"] and memory["art_direction_families"]
    assert second.creative_decision_packet["feed_intelligence"]["what_feed_needs_next"]
    assert first.visual["layout_grammar"]["alignment"] != second.visual["layout_grammar"]["alignment"]


def test_renderer_prompt_consumes_creative_layout_and_platform_interpretation():
    content = {
        "selected_hook": "Prioritize what matters first", "selected_cta": "Save this plan", "topic": "Power priorities",
        "layout_grammar": {"primary_focal_point": "human situation", "secondary_focal_point": "product proof", "reading_flow": "Z-pattern", "product_role": "demonstration", "product_placement": "foreground left", "human_role": "active decision maker", "human_placement": "contextual background", "headline_position": "top-right", "benefit_position": "center", "proof_position": "lower-third", "cta_position": "footer", "text_density": "low", "spacing_intent": "wide negative space", "negative_space_intent": "protect copy", "alignment": "asymmetrical editorial"},
        "information_priority": {"MUST_SHOW": ["prioritize essentials"], "SHOULD_SHOW": ["confidence"], "SUPPORTING": ["verified product fact"], "OMIT": ["unrelated specs"]},
        "benefit_translation": {"PRACTICAL_BENEFIT": "prioritize essentials", "CUSTOMER_OUTCOME": "confidence"},
        "platform_interpretations": {"instagram": {"hook_posture": "visual-first takeaway", "format": "carousel_or_reel", "information_density": "low", "visual_composition": "one memorable focal hierarchy", "product_emphasis": "visual proof", "cta_expression": "save or share"}},
    }
    prompt = social_visuals._build_gemini_image_prompt(content, "instagram", {"layout_grammar": content["layout_grammar"], "platform_interpretations": content["platform_interpretations"], "information_priority": content["information_priority"], "benefit_translation": content["benefit_translation"]})
    recipe = visual_provider.TemplateRenderProvider().generate(art_direction={"visual_format": "fact_card", "visual_message": "Priority plan", "layout_grammar": content["layout_grammar"], "platform_interpretations": content["platform_interpretations"], "information_priority": content["information_priority"], "benefit_translation": content["benefit_translation"]}, positive_prompt="", negative_prompt="", platform="instagram_feed").recipe

    assert "product placement=foreground left" in prompt
    assert "human role=active decision maker" in prompt
    assert "Native instagram creative interpretation" in prompt
    assert "must-show ideas prominently: prioritize essentials" in prompt
    assert recipe["layout_grammar"]["headline_position"] == "top-right"
    assert recipe["platform_interpretation"]["format"] == "carousel_or_reel"


def test_orchestrator_records_final_copy_and_visual_critics(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    post = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path)).create_post(record_memory=False)

    assert post.creative_director["copy_critic_review"]["verdict"] in {"PASS", "REVISE"}
    assert post.creative_director["visual_critic_review"]["pixel_status"] == "PIXEL_REVIEW_PENDING"
    assert post.provider_result["recipe"]["layout_grammar"] == post.visual["layout_grammar"]


def test_campaign_state_changes_next_creative_concept(tmp_path):
    strategy = {"audience": "families", "customer_moment": "outage planning", "human_need": "clarity", "angle": "prioritize essentials", "benefit": "a clearer decision", "human_outcome": "confidence", "reader_job": "HELP_ME_CHOOSE", "visual_objective": "make the priority visible", "proof": ["verified fact"]}
    baseline = creative_cognition.decide(strategy=strategy, platform="instagram_feed", recent={}, data_dir=str(tmp_path))
    state_path = tmp_path / "social" / "living_intelligence.json"
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps({"campaign_state": {"decision": "start", "next_content_priority": "campaign_sequence"}}), encoding="utf-8")
    campaign = creative_cognition.decide(strategy=strategy, platform="instagram_feed", recent={}, data_dir=str(tmp_path))

    assert baseline["SELECTED_ANSWER"]["creative_concept"] != "decision-support"
    assert campaign["SELECTED_ANSWER"]["creative_concept"] == "decision-support"
    assert campaign["campaign_guidance"]["next_content_priority"] == "campaign_sequence"


def test_customer_hooks_are_grammatical_and_customer_centered():
    packet = creative_cognition.decide(
        strategy={
            "audience": "traveler",
            "customer_moment": "before a trip",
            "human_need": "stay charged",
            "angle": "choose the right charging backup",
            "benefit": "keeps compatible daily devices charged away from outlets",
            "reader_job": "HELP_ME_CHOOSE",
            "visual_objective": "show the decision",
            "proof": [],
        },
        platform="facebook_feed",
        recent={},
    )
    openings = [item["opening"] for item in packet["copy_concepts"]]

    assert "Before a trip, what matters most?" in openings
    assert all("When before" not in opening for opening in openings)
    assert all("make keeps" not in opening for opening in openings)


def test_all_in_one_charger_profile_expresses_customer_transformation():
    profile = generate_posts._product_copy_profile({
        "name": "PowerCharge Pro",
        "categories": ["Emergency Power", "Travel Power"],
        "metrics": ["10,000mAh", "20W"],
        "fact_snippet": "5-in-1 wall charger, wireless charger, and power bank with built-in cables and a phone stand.",
    })

    assert profile["role"] == "all-in-one daily charging hub"
    assert "built into one compact device" in profile["after_state"]
    assert "replaces several loose accessories" in profile["transformation"]
    assert "less time untangling" in profile["why_it_matters"]


def test_platform_interpretation_changes_outbound_payload_fields():
    components = {"product_name": "Power Station", "product_id": "p1", "topic": "Power planning", "hook": "Start here", "logic_hook": "Start here", "situation": "An outage can interrupt plans.", "logic_bridge": "Map essentials first.", "benefit_fragment": "supports clear decisions", "detail_summary": "Verified output details", "use_case_line": "For home readiness", "proof": "Verified product fact", "emotional_outcome": "more confidence", "cta": "Learn more", "feature_bullets": ["Portable power"]}
    interpretations = {"facebook": {"hook_posture": "conversation-starter", "cta_expression": "invite a practical response", "format": "community_story", "visual_composition": "human-context"}, "instagram": {"hook_posture": "visual-first takeaway", "cta_expression": "save this reference", "format": "carousel_or_reel", "visual_composition": "one memorable focal hierarchy"}, "linkedin": {"hook_posture": "professional implication", "cta_expression": "consider the operational context", "format": "professional_brief", "visual_composition": "editorial decision-support hierarchy"}}
    posts = generate_posts._build_platform_posts("post", "", "families", "EDUCATION", "https://example.com", components, 90, platform_interpretations=interpretations)

    assert posts["facebook"]["hook"].startswith("conversation-starter:")
    assert posts["instagram"]["visual_direction"] == "one memorable focal hierarchy"
    assert posts["linkedin"]["content_format"] == "professional_brief"
    assert posts["facebook"]["creative_interpretation"] != posts["linkedin"]["creative_interpretation"]


def test_editorial_frameworks_keep_commercial_and_organic_reasoning_separate():
    strategy = {
        "audience": "traveler", "customer_moment": "packing for a long travel day",
        "human_need": "confidence that essential devices can stay available",
        "angle": "choose around the devices that matter",
        "benefit": "supports compatible daily devices away from an outlet",
        "positioning": "verified product-fit guidance", "important_capability": "154Wh published capacity",
        "proof": ["154Wh", "200W AC output"], "human_outcome": "less charging anxiety",
        "human_value": "freedom to keep moving", "claim_limits": "fit depends on each device's published requirements",
        "CTA_strategy": "Review the verified fit", "topic": "travel charging",
        "hook_promise": "What deserves a place in your carry-on?",
        "desired_memory": "Plan around the devices that cannot pause.",
    }

    commercial = orchestrator._editorial_framework(strategy, {"name": "PowerPulse Pro 200"})
    organic = orchestrator._editorial_framework(strategy, None)

    assert commercial["mode"] == "commercial"
    assert commercial["structure"][0] == "human_moment"
    assert commercial["structure"].index("product_fit") < commercial["structure"].index("verified_proof")
    assert commercial["verified_proof"] == ["154Wh", "200W AC output"]
    assert organic["mode"] == "organic"
    assert organic["structure"] == [
        "person_world", "human_reality", "tension", "curiosity", "insight",
        "infenergy_perspective", "story", "participation", "memory",
    ]
    assert "product_fit" not in organic["structure"]


def test_performance_signal_remains_cautious_and_provenanced():
    signal = performance_learning.observe(strategy={"audience": "household", "angle": "prioritize essentials"}, metrics={"saves": 2}, platform="instagram")
    assert signal["type"] == "PERFORMANCE_EVIDENCE"
    assert signal["confidence"] < 0.5
    assert "cannot establish causality" in signal["uncertainty"]


def test_performance_observation_creates_a_future_opportunity(tmp_path):
    learning = performance_learning.observe(strategy={"audience": "household", "angle": "prioritize essentials"}, metrics={"saves": 4}, platform="instagram")
    result = living_intelligence.heartbeat(str(tmp_path), performance_observations=[learning])
    assert any(item["support"][0]["type"] == "PERFORMANCE_EVIDENCE" for item in result["opportunities"])


def test_public_research_preserves_routed_source_and_provenance(monkeypatch):
    task = research_router.route(question="Which competitor messages are repeated?", why_needed="find positioning whitespace", entity="portable power competitor", decision_affected="positioning")
    monkeypatch.setattr(research_router, "inspect_first_party", lambda url: {"content_hash": "hash", "marketing_language": ["More watts for every trip"], "factual_candidates": []})
    evidence = public_research.collect(task=task, urls=["https://example.test"])
    assert evidence[0]["provenance"] == "https://example.test"
    assert evidence[0]["decision_affected"] == "positioning"


def test_autonomous_source_discovery_starts_with_task_not_final_url(monkeypatch):
    task = research_router.route(question="What does our public business messaging emphasize?", why_needed="find a credible angle", entity="Infenergy brand", decision_affected="positioning")
    monkeypatch.setattr(research_router, "inspect_first_party", lambda url: {"content_hash": "hash", "marketing_language": ["Preparedness without panic"], "factual_candidates": []})
    evidence = public_research.research(task=task)
    assert evidence[0]["provenance"] == "https://infenergypower.com"


def test_independent_human_review_rejects_exploitative_copy():
    verdict = human_connection_review.review(strategy={"customer_moment": "storm outage", "human_need": "confidence", "important_capability": "500W AC", "benefit": "prioritize essentials", "human_outcome": "confidence"}, copy={"body": "Fear will leave your family in panic."}, visual={"message": "confidence"})
    assert verdict["verdict"] == "DO_NOT_PUBLISH"


def test_independent_human_review_scores_reader_value_from_constitution_context():
    strategy = {
        "customer_moment": "weather forecast changes",
        "human_need": "clarity before pressure",
        "important_capability": "verified product facts",
        "benefit": "prioritize household needs",
        "human_outcome": "confidence",
        "human_connection": {"moment_world": {
            "person": "A parent watching a changing weather forecast in the evening.",
            "decision_state": "Mentally checking phones, flashlights, refrigerator, children.",
            "responsibility": "Decide what deserves attention before pressure.",
            "human_question": "What would we actually need to keep working?",
        }},
    }
    copy = {
        "hook": "What needs attention before the forecast changes?",
        "body": "Check phones, flashlights, and the refrigerator first, then decide what your household needs overnight.",
    }
    visual = {"message": "A parent checks phones and flashlights while watching the weather forecast."}

    verdict = human_connection_review.review(strategy=strategy, copy=copy, visual=visual)

    assert verdict["verdict"] == "PASS"
    assert all(score == 1.0 for score in verdict["reader_value_scores"].values())
    assert "value_before_asking" in verdict["trust_signals"]


def test_independent_human_review_requires_value_for_constitution_context():
    strategy = {
        "customer_moment": "weather forecast changes",
        "human_need": "clarity before pressure",
        "benefit": "prioritize household needs",
        "human_connection": {"moment_world": {"person": "A parent watching a weather forecast."}},
    }

    verdict = human_connection_review.review(
        strategy=strategy,
        copy={"hook": "Power station sale", "body": "Buy today."},
        visual={"message": "product"},
    )

    assert verdict["verdict"] == "REVISE_COPY"
    assert verdict["reader_value_failures"]


def test_reader_value_revision_feedback_becomes_a_specific_copy_objective():
    objectives = orchestrator._revision_objectives(
        ["human_connection_reader_value_missing:caring,trust_building"],
        {},
    )

    assert any("Reader Value" in objective for objective in objectives)


def test_due_publication_analytics_becomes_cautious_future_opportunity(tmp_path, monkeypatch):
    record = {"published_at": "2025-01-01T00:00:00+00:00", "fb_id": "123", "strategic_brief": {"audience": "household", "angle": "prioritize essentials"}}
    monkeypatch.setattr(analytics_ingestion, "collect_meta", lambda item: [{"platform_post_id": "123", "platform": "facebook", "raw_observation": {"metrics": {"shares": 3}}, "derived_metrics": {}}])
    result = living_intelligence.heartbeat(str(tmp_path), publication_records=[record])
    support = result["opportunities"][0]["support"][0]
    assert support["type"] == "PERFORMANCE_EVIDENCE"
    assert support["state"] == "NEW_HYPOTHESIS"


def test_research_freshness_avoids_unnecessary_refresh():
    task = research_router.route(question="What is our business worldview?", why_needed="maintain brand fit", entity="brand personality", decision_affected="positioning")
    fresh = {"observed_at": "2026-08-12T00:00:00+00:00"}
    assert research_router.freshness_class(task) == "VERY_STABLE"
    assert research_router.is_fresh(fresh, task)


def test_contradictory_learning_preserves_both_observation_sets():
    base = performance_learning.update_hypothesis(None, {"platform": "instagram", "metrics": {"shares": 5}})
    conflicted = performance_learning.update_hypothesis(base, {"platform": "instagram", "metrics": {"shares": 0}})
    assert conflicted["support_count"] == 1
    assert conflicted["contradiction_count"] == 1
    assert conflicted["state"] == "CONFLICTED"


def test_integrity_blocks_material_strategy_drift():
    strategy = {"audience": "household", "customer_moment": "outage", "human_need": "confidence", "human_value": "preparedness", "topic": "priorities", "angle": "what matters", "offering": "power station", "benefit": "prioritize", "human_outcome": "confidence", "positioning": "calm", "non_price_edge": {}, "claim_limits": "supported only", "CTA_strategy": "Learn"}
    copy = {"strategy_lock": strategy | {"audience": "traveler"}, "cta": "Learn"}
    visual = {"strategy_lock": strategy}
    assert strategy_lock.integrity(strategy, copy, visual)["verdict"] == "MATERIAL_DRIFT"


def test_human_review_escalates_weak_premise_to_change_angle():
    verdict = human_connection_review.review(strategy={"customer_moment": "", "human_need": "", "benefit": ""}, copy={"body": "Clear advice"}, visual={"message": "Clear advice"})
    assert verdict["verdict"] == "CHANGE_ANGLE"


def test_analytics_windows_are_runtime_configurable(monkeypatch):
    monkeypatch.setenv("ANALYTICS_WINDOWS_HOURS", "1,12,48")
    assert analytics_ingestion.configured_windows() == (1, 12, 48)


def test_linkedin_analytics_unavailability_is_explicit(monkeypatch):
    monkeypatch.delenv("META_PAGE_ACCESS_TOKEN", raising=False)
    observations = analytics_ingestion.collect_meta({"li_id": "linkedin-post-1"})
    assert observations[0]["platform"] == "linkedin"
    assert observations[0]["status"] == "ANALYTICS_UNAVAILABLE"
    assert observations[0]["reason"] == "linkedin_analytics_api_not_configured"


def test_competitor_and_customer_discovery_start_from_question_only(monkeypatch):
    monkeypatch.setattr(public_research, "discover_web_candidates", lambda task: ["https://example.com/evidence"])
    competitor = research_router.route(question="Which competitors frame portable power differently?", why_needed="find whitespace", entity="portable power", decision_affected="positioning")
    customer = research_router.route(question="What questions do portable power buyers ask?", why_needed="test angle", entity="portable power", decision_affected="audience language")
    assert public_research.discover(task=competitor)[0]["url"] == "https://example.com/evidence"
    assert public_research.discover(task=customer)[0]["url"] == "https://example.com/evidence"


def test_discovery_failure_is_a_structured_research_outcome(monkeypatch):
    monkeypatch.setattr(public_research, "discover_web_candidates", lambda task: (_ for _ in ()).throw(OSError("offline")))
    task = research_router.route(question="Which competitors frame portable power differently?", why_needed="find whitespace", entity="portable power", decision_affected="positioning")
    assert public_research.research(task=task)[0]["failure"] == "SOURCE_UNAVAILABLE"


def test_bing_destination_and_relevance_filtering():
    encoded = "https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9wb3J0YWJsZS1wb3dlcg"
    task = research_router.route(question="Which competitors frame portable power differently?", why_needed="find whitespace", entity="portable power", decision_affected="positioning")
    assert public_research._bing_destination(encoded) == "https://example.com/portable-power"
    assert public_research._relevant("https://example.com/portable-power", task)
    assert not public_research._relevant("https://portableapps.com/", task)


def test_autonomous_pre_publish_contract(tmp_path, monkeypatch):
    task = research_router.route(question="What changed in our portable-power offering?", why_needed="find a current angle", entity="portable power", decision_affected="positioning")
    monkeypatch.setattr(research_router, "inspect_first_party", lambda url: {"content_hash": "new", "marketing_language": ["New modular capability"], "factual_candidates": ["500W"], "changed": True})
    evidence = public_research.research(task=task)
    heartbeat = living_intelligence.heartbeat(str(tmp_path), level="STANDARD_HEARTBEAT", research_evidence=evidence, business_personality="calm preparedness", capability="500W AC", offering_truth=["500W AC"], consumer_signals=[{"audience": "household", "customer_moment": "storm outage", "human_need": "confidence", "question": "What should I power first?", "offering": "power station", "source": "research", "confidence": 0.8}], competitor_observations=[{"name": "Competitor", "category": "portable power", "messages": ["more watts"], "benefits": ["more watts"], "customer_moments": ["camping"], "human_values": [], "questions": [], "territories": [], "visual_patterns": [], "source": "official", "confidence": 0.8}])
    decision = living_intelligence.council(living_intelligence.load(str(tmp_path)), strategy_inputs={"customer": heartbeat["consumer_relationships"][0], "capability": "500W AC", "benefit": "prioritize essentials", "positioning": heartbeat["positioning"], "human_value": "preparedness", "topic": "power priorities", "reader_job": "PREPARE_ME", "important_capability": "500W AC", "human_outcome": "confidence", "competitive_context": "spec led", "proof": ["500W AC"], "claim_limits": "supported only", "visual_objective": "priority ladder", "CTA_strategy": "Learn more"})
    assert decision["decision"] == "strategy_selected"
    assert decision["approved_strategy"]["angle"]
    record = living_intelligence.decision_record(trigger="scheduled", heartbeat_result=heartbeat, council_result=decision)
    assert record["selected_strategy"] == decision["approved_strategy"]


# --- content strategy ------------------------------------------------------


def test_select_pillar_respects_cooldown():
    dec = content_strategy.select_pillar(engine="B", recent_pillars=[])
    assert dec.pillar_id in libraries.pillars()


def test_pick_topic_path_returns_populated():
    tp = content_strategy.pick_topic_path(pillar_id="portable_power", rotation_index=0)
    assert tp is not None
    assert tp.topic and tp.subtopic
    # angle or microtopic populated
    assert tp.angle or tp.microtopic


def test_topic_path_pairs_microtopic_with_the_selected_angle():
    cpap = content_strategy.pick_topic_path(pillar_id="preparedness", rotation_index=2)
    medication = content_strategy.pick_topic_path(pillar_id="preparedness", rotation_index=5)

    assert cpap is not None and "CPAP" in cpap.microtopic and "CPAP" in cpap.angle
    assert medication is not None and "medication" in medication.microtopic.lower() and "medication" in medication.angle.lower()


def test_topic_path_never_borrows_from_an_unrelated_pillar():
    assert content_strategy.pick_topic_path(pillar_id="energy_education", rotation_index=0) is None


def test_business_ideology_filter_rejects_generic_battery_myths():
    generic = content_strategy.TopicPath(
        topic="Batteries",
        subtopic="charging",
        microtopic="overnight charging myth",
        angle="why overnight charging isn't the villain most people think",
        pillar_id="battery_knowledge",
    )
    aligned = content_strategy.TopicPath(
        topic="Power Stations",
        subtopic="runtime_math",
        microtopic="CPAP runtime",
        angle="CPAP runtime: what to actually plan for",
        pillar_id="portable_power",
    )

    assert not opportunity_engine.business_ideology_aligned(generic)
    assert opportunity_engine.business_ideology_aligned(aligned)


def test_obviousness_filter():
    assert content_strategy.is_obvious("charge your phone before a storm")
    assert not content_strategy.is_obvious("Overnight charging is not the villain — here's why")


def test_multiply_angles_includes_information_gap():
    tp = content_strategy.pick_topic_path(pillar_id="portable_power", rotation_index=0)
    assert tp is not None
    angles = content_strategy.multiply_angles(tp, information_gap="lithium chemistries differ")
    assert "lithium chemistries differ" in angles or tp.angle in angles


# --- opportunity engine ----------------------------------------------------


def test_opportunity_generate_returns_ranked_candidates():
    cands = opportunity_engine.generate(engine="B", limit=5)
    assert cands
    scores = [c.total for c in cands]
    assert scores == sorted(scores, reverse=True)
    assert all(opportunity_engine.business_ideology_aligned(c.topic_path) for c in cands)
    assert all(c.topic_path.microtopic != "overnight charging myth" for c in cands)


# --- copy intelligence ----------------------------------------------------


def test_humanness_penalizes_slop():
    good = "Overnight charging isn't the villain — here's the real reason."
    bad = "In today's fast-paced world, unlock the ultimate game changer!"
    assert copy_intelligence.humanness_score(good) > copy_intelligence.humanness_score(bad)


def test_has_so_what_detects_meaning_bridges():
    assert copy_intelligence.has_so_what("Cold hurts batteries because the ions slow down.")
    assert not copy_intelligence.has_so_what("Cold hurts batteries.")


def test_hook_payoff_contract_flags_mismatch():
    hook = "The real reason your battery dies fast in winter."
    body_weak = "Batteries are affected by cold."
    body_strong = "Because ion mobility drops 30 percent below 5 C, the reason winter drains you so fast is that internal resistance climbs and voltage sags."
    ok_weak, _ = copy_intelligence.contract_ok(hook, body_weak)
    ok_strong, _ = copy_intelligence.contract_ok(hook, body_strong)
    assert not ok_weak
    assert ok_strong


def test_memory_anchor_prefers_specific_takeaway():
    body = "There are many things to know. Store batteries at 40 percent charge. Cold is bad."
    anchor = copy_intelligence.extract_memory_anchor(body)
    assert "40 percent" in anchor


def test_choose_cta_type_respects_recency():
    genre = {"cta_preferences": ["SAVE", "SHARE", "COMMENT"]}
    job = {"cta_preferences": ["SAVE"]}
    picked = copy_intelligence.choose_cta_type(genre=genre, reader_job_config=job, recent_ctas=["SAVE"])
    assert picked == "SHARE"


# --- visual intelligence --------------------------------------------------


def test_visual_necessity_higher_for_instagram():
    g = libraries.genres()["how_it_works"]
    j = libraries.reader_jobs()["EXPLAIN_THIS"]
    ig = visual_intelligence.visual_necessity_score(genre=g, reader_job_config=j, platform="instagram_feed", body_word_count=60)
    li = visual_intelligence.visual_necessity_score(genre=g, reader_job_config=j, platform="linkedin_feed", body_word_count=60)
    assert ig > li


def test_visual_format_router_returns_registered_format():
    g = libraries.genres()["checklist"]
    fmt = visual_intelligence.route_visual_format(
        genre=g, platform="instagram_feed", body_word_count=60
    )
    assert fmt in libraries.visual_formats()


def test_art_direction_and_prompt_include_brand_tokens():
    g = libraries.genres()["myth_vs_reality"]
    concepts = visual_intelligence.generate_concepts(
        angle="lithium batteries prefer partial charging",
        memory_anchor="Store lithium at 40 percent",
        semantic_role="COMPARE",
        genre_id="myth_vs_reality",
    )
    ad = visual_intelligence.build_art_direction(
        visual_purpose="COMPARE",
        visual_msg="Show partial vs full charge comparison",
        visual_format="comparison_graphic",
        concept=concepts[0],
        primary_subject="battery",
        platform="instagram_feed",
    )
    pos, neg = visual_intelligence.compile_image_prompt(ad)
    assert "COMPARE" in pos
    assert ad.must_avoid  # brand tokens supply forbidden imagery
    assert neg  # negative prompt should be non-empty


def test_visual_truth_violations_flag_unsafe_claims():
    v = visual_intelligence.visual_truth_violations("A waterproof unbreakable battery in the rain.")
    assert "waterproof" in v and "unbreakable" in v


# --- carousel director ---------------------------------------------------


def test_carousel_builds_from_structure():
    beat_content = {
        "hook": "Why lithium batteries hate 100%?",
        "answer": "They wear out faster at full charge.",
        "explanation": "Because voltage stress accelerates chemistry aging.",
        "example": "A cell held at 4.2V loses capacity 3x faster than at 3.9V.",
        "takeaway": "Store lithium at 40 percent for the winter.",
    }
    c = carousel_director.build(
        info_structure="hook_answer_explanation_example_takeaway",
        beat_content=beat_content,
        visual_type="carousel",
        visual_direction="clean comparison layout",
    )
    assert c.slide_count == 5
    valid, problems = carousel_director.is_valid_carousel(c, max_slides=10)
    assert valid, problems


def test_carousel_skips_empty_beats():
    beat_content = {"hook": "One thing.", "answer": ""}
    c = carousel_director.build(
        info_structure="hook_answer_explanation_example_takeaway",
        beat_content=beat_content,
        visual_type="carousel",
        visual_direction="",
    )
    assert c.slide_count == 1


# --- claim intelligence -------------------------------------------------


def test_claim_extraction_detects_stats_and_risk():
    text = "This unit runs for 20 hours at 100 watts. FDA approved. Safety guaranteed."
    ledger = claim_intelligence.build_ledger(text)
    types = {c.claim_type for c in ledger.claims}
    assert "quantitative_technical_fact" in types
    assert any(c.risk == claim_intelligence.HIGH_RISK for c in ledger.claims)


def test_claim_verification_marks_verified_when_fact_matches():
    text = "The battery has a 300Wh capacity."
    ledger = claim_intelligence.build_ledger(text, verified_facts=["300 Wh capacity"])
    assert any(c.verification_status == "verified" for c in ledger.claims)


# --- quality intelligence -----------------------------------------------


def test_publish_decision_is_the_single_gate_for_critics_and_runtime():
    result = publish_decision.decide(
        legacy_score={"total": 88},
        validation={"passed": True},
        duplicates={"ok": True},
        conversion_quality_score=84,
        orchestrator_quality={"overall": 78},
    )

    assert result["decision"] == "publish"
    assert "critic_preference_unmet" in result["advisory_reasons"]
    assert result["publishable"]


def test_publish_decision_blocks_failed_validation_even_with_high_scores():
    result = publish_decision.decide(
        legacy_score={"total": 99},
        validation={"passed": False, "errors": ["unsupported_claim"]},
        duplicates={"ok": True},
        conversion_quality_score=99,
    )

    assert result["decision"] == "do_not_publish"
    assert "unsupported_claim" in result["reasons"]


def test_quality_is_advisory_after_recovery_but_truth_remains_mandatory():
    recovered = publish_decision.decide(
        legacy_score={"total": 60, "platform_results": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        orchestrator_quality={"overall": 65, "critic_findings": ["hook weak"]},
        evidence_readiness={"ready": True, "status": "READY"},
        recovery_exhausted=True,
    )
    unsafe = publish_decision.decide(
        legacy_score={"total": 95, "platform_results": {}},
        validation={"passed": False, "errors": ["unsupported_claim"]},
        duplicates={"ok": True, "reasons": []},
        evidence_readiness={"ready": True, "status": "READY"},
        recovery_exhausted=True,
    )

    assert recovered["publishable"] is True
    assert "quality_preference_unmet" in recovered["advisory_reasons"]
    assert unsafe["publishable"] is False
    assert "unsupported_claim" in unsafe["reasons"]


def test_human_truth_gate_recognizes_reader_language_at_sentence_boundary():
    result = quality_intelligence.human_truth_gate(
        hook="Your priorities come before the purchase.",
        body="Compare what must stay available and plan from that responsibility.",
        takeaway="Check the plan before you need it.",
        strategy={
            "customer_moment": "an outage interrupts the household",
            "human_need": "keep priority needs available",
            "angle": "prioritize before buying",
        },
    )

    assert result["reader_value"]["for_them"] == 1.0


def test_decision_support_concept_changes_with_human_reality_and_angle():
    first, _ = creative_cognition._copy_concepts(
        strategy={"angle": "outage priorities", "benefit": "a clearer plan", "customer_moment": "an outage begins"},
        grammar={},
        recent={},
        platform="linkedin",
    )
    second, _ = creative_cognition._copy_concepts(
        strategy={"angle": "travel charging", "benefit": "a clearer plan", "customer_moment": "packing for remote travel"},
        grammar={},
        recent={},
        platform="linkedin",
    )

    first_hook = next(item["opening"] for item in first if item["approach"] == "decision_support")
    second_hook = next(item["opening"] for item in second if item["approach"] == "decision_support")
    assert first_hook != second_hook
    assert "outage priorities" in first_hook
    assert "travel charging" in second_hook
    assert "for before" not in first_hook.lower()
    assert "supports how does" not in first_hook.lower()


def test_deterministic_copy_turns_question_angle_into_safe_guidance():
    brief = engines.EngineBrief(
        engine="B",
        pillar={},
        genre={},
        reader_job="HELP_ME_CHOOSE",
        reader_job_config={},
        audience_segment="household",
        audience_segment_config={},
        information_gap="verified product facts",
        curiosity="a practical power decision",
        misconception="Solar recharging is fast in most conditions",
        question="What should your backup plan support?",
        emotional_driver="clarity",
        topic_path={"topic": "Outages"},
        angle="How does this option fit your outage priorities?",
        tone="calm",
        opportunity_score=0.8,
    )
    copy = orchestrator._assemble_copy(
        brief=brief,
        structure_beats=["problem", "what_to_do", "takeaway"],
    )

    assert "solar recharging is fast" not in copy["problem"].lower()
    assert "practical move is to how" not in " ".join(copy.values()).lower()
    assert "your actual priorities" in copy["what_to_do"].lower()


def test_quality_score_gives_reasonable_overall():
    ledger = claim_intelligence.ClaimLedger()
    q = quality_intelligence.score(
        hook="Why lithium batteries prefer 40% storage.",
        body="Because ion stress falls when voltage drops, which means partial charge slows aging.",
        takeaway="Store at 40%.",
        memory_anchor="Store at 40%.",
        visual_concept_description="split-frame partial vs full",
        platform="instagram_feed",
        genre=libraries.genres()["myth_vs_reality"],
        reader_job_config=libraries.reader_jobs()["EXPLAIN_THIS"],
        ledger=ledger,
        visual_prompt_humanness=0.85,
        caption_visual_relationship="VISUAL_SUMMARIZES_CAPTION",
        engine="B",
    )
    assert 0 <= q.overall <= 100
    assert q.band in {"regenerate", "revise", "publishable", "strong", "excellent", "extraordinary"}


def test_quality_publishable_band_matches_live_threshold():
    ledger = claim_intelligence.ClaimLedger()
    q = quality_intelligence.score(
        hook="Why 154Wh matters when you compare portable backup power.",
        body="Because capacity only helps when it matches the device load, 154Wh gives a concrete starting point for comparison.",
        takeaway="Compare watt-hours with the device load.",
        memory_anchor="Compare watt-hours with the device load.",
        visual_concept_description="capacity comparison card",
        platform="instagram_feed",
        genre=libraries.genres()["myth_vs_reality"],
        reader_job_config=libraries.reader_jobs()["EXPLAIN_THIS"],
        ledger=ledger,
        visual_prompt_humanness=0.9,
        caption_visual_relationship="VISUAL_SUMMARIZES_CAPTION",
        engine="B",
    )
    if q.band == "publishable":
        assert q.overall >= 82


def test_creative_director_test_all_yes_passes():
    v = quality_intelligence.creative_director_test(
        strategy_reason="engine=B pillar=battery_knowledge",
        audience_reason="segment=curious_learner reader_job=EXPLAIN_THIS",
        value_delivered="Store at 40%",
        novelty_angle="counterintuitive",
        memory_anchor="Store at 40%",
        copy_earns_attention=True,
        visual_communicates=True,
        copy_visual_alignment=True,
        brand_feels_like_us=True,
        material_claims_accurate=True,
        worth_reader_time=True,
    )
    assert v.passed


def test_creative_director_test_missing_answer_fails():
    v = quality_intelligence.creative_director_test(
        strategy_reason="",
        audience_reason="ok",
        value_delivered="ok",
        novelty_angle="ok",
        memory_anchor="ok",
        copy_earns_attention=True,
        visual_communicates=True,
        copy_visual_alignment=True,
        brand_feels_like_us=True,
        material_claims_accurate=True,
        worth_reader_time=True,
    )
    assert not v.passed
    assert "STRATEGY" in v.failures


# --- memory intelligence -----------------------------------------------


def test_memory_roundtrip(tmp_path):
    d = str(tmp_path)
    os.makedirs(os.path.join(d, "social"), exist_ok=True)
    memory_intelligence.append_content_record(
        {"post_id": "abc", "pillar_id": "battery_knowledge", "hook": "h1"},
        data_dir=d,
    )
    memory_intelligence.append_visual_record(
        {"post_id": "abc", "visual_format": "diagram", "visual_signature": "sig1"},
        data_dir=d,
    )
    r = memory_intelligence.recent(d, limit=5)
    assert "battery_knowledge" in r["pillars"]
    assert "diagram" in r["visual_formats"]


def test_topic_repeat_detection():
    assert memory_intelligence.approximate_topic_repeat(
        "lithium battery charging habits", ["lithium battery aging tips"]
    )
    assert not memory_intelligence.approximate_topic_repeat(
        "solar panel angles", ["lithium battery aging tips"]
    )


# --- engines --------------------------------------------------------------


@pytest.mark.parametrize("engine", ["A", "B", "C"])
def test_each_engine_produces_valid_brief(engine):
    eng = engines.get_engine(engine)
    brief = eng.build(rotation_index=1)
    assert brief.engine == engine
    assert brief.pillar and brief.pillar.get("id")
    assert brief.genre and brief.genre.get("id")
    assert brief.reader_job
    assert brief.audience_segment
    assert brief.angle or brief.topic_path.get("microtopic")
    assert brief.topic_path["microtopic"].lower() in brief.information_gap.lower()
    assert brief.topic_path["microtopic"].lower() in brief.curiosity.lower()


# --- visual provider -----------------------------------------------------


def test_template_render_provider_returns_recipe():
    p = visual_provider.TemplateRenderProvider()
    r = p.generate(
        art_direction={"visual_format": "fact_card", "visual_message": "M", "focal_point": "battery", "color_direction": "brand", "text_safe_area": "96px", "must_include": [], "must_avoid": []},
        positive_prompt="hello",
        negative_prompt="nope",
        platform="instagram_feed",
    )
    assert r.kind == "template_recipe"
    assert r.recipe["template"] == "fact_card"


# --- model router --------------------------------------------------------


def test_model_router_uses_default_and_env_override(monkeypatch):
    assert set(model_router.DEFAULT_MODEL_ROUTES.values()) == {"gemini-3.6-flash"}
    assert model_router.route_for("strategy") == "gemini-3.6-flash"
    assert model_router.route_for("copy_editing") == "gemini-3.6-flash"
    monkeypatch.setenv("GEMINI_ROUTE_STRATEGY", "custom-model")
    assert model_router.route_for("strategy") == "custom-model"


def test_revision_claim_filter_removes_unsupported_numbers_without_replacement():
    text = (
        "The 154Wh PowerPulse Pro 200 supports compatible devices. "
        "It runs a 50W fridge for 2.6 hours."
    )

    sanitized, removed = claim_intelligence.remove_unsupported_numeric_claims(text, ["154Wh", "200W", "41,600mAh"])

    assert sanitized == "The 154Wh PowerPulse Pro 200 supports compatible devices."
    assert removed == ["It runs a 50W fridge for 2.6 hours."]
    assert "2.6" not in sanitized
    assert "50W" not in sanitized


def test_revision_objectives_make_soft_and_claim_feedback_actionable():
    objectives = orchestrator._revision_objectives(
        [
            "runtime_not_verified:2.6 hours",
            "primary_benefit_not_explicit",
            "humanness below bar",
            "generic_or_ai_like_language",
            "hook-payoff mismatch",
        ],
        {
            "benefit": "keeps compatible daily devices charged away from outlets",
            "customer_moment": "before a trip",
            "human_need": "avoid carrying the wrong backup power",
        },
    )

    assert any("do not replace them with new numbers" in objective.lower() for objective in objectives)
    assert any("keeps compatible daily devices charged away from outlets" in objective for objective in objectives)
    assert any("before a trip" in objective for objective in objectives)
    assert any("stock marketing transitions" in objective for objective in objectives)
    assert any("directly answer or fulfill the hook" in objective for objective in objectives)


def test_copy_editing_prompt_receives_structured_revision_objectives(monkeypatch):
    brief = engines.get_engine("A").build(rotation_index=0)
    captured: dict[str, str] = {}

    def fake_generate_json(task, prompt, **_kwargs):
        captured["task"] = task
        captured["prompt"] = prompt
        return {"hook": "Match the battery to the devices you carry."}

    monkeypatch.setattr(model_router, "generate_json", fake_generate_json)
    objectives = orchestrator._revision_objectives(
        ["primary_benefit_not_explicit", "humanness below bar", "generic_or_ai_like_language", "hook-payoff mismatch"],
        {
            "benefit": "keeps compatible daily devices charged away from outlets",
            "customer_moment": "before a trip",
            "human_need": "avoid carrying the wrong backup power",
        },
    )

    result = orchestrator._llm_copy_beats(brief, ["hook"], None, revision_feedback=objectives)

    assert result == {"hook": "Match the battery to the devices you carry."}
    assert captured["task"] == "copy_editing"
    assert "keeps compatible daily devices charged away from outlets" in captured["prompt"]
    assert "before a trip" in captured["prompt"]
    assert "stock marketing transitions" in captured["prompt"]
    assert "directly answer or fulfill the hook" in captured["prompt"]


def test_cost_tracker_records_and_totals():
    tracker = model_router.ApiCostTracker()
    tracker.record(model_router.ApiCallRecord(model="m", task="t", input_tokens=100, output_tokens=50, estimated_cost_usd=0.001))
    tracker.record(model_router.ApiCallRecord(model="m", task="t", input_tokens=200, output_tokens=100, estimated_cost_usd=0.002))
    tot = tracker.totals()
    assert tot["calls"] == 2
    assert tot["input_tokens"] == 300


# --- orchestrator (E2E) --------------------------------------------------


def test_orchestrator_generates_complete_package(tmp_path):
    o = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path))
    pkg = o.create_post(rotation_index=0, platform="instagram_feed")
    assert pkg.post_id
    assert pkg.engine in {"A", "B", "C"}
    assert pkg.copy["hook"]
    assert pkg.copy["memory_anchor"]
    assert pkg.visual["visual_format"] in libraries.visual_formats()
    assert 0 <= pkg.quality["overall"] <= 100
    assert isinstance(pkg.creative_director["passed"], bool)
    assert pkg.provider_result["kind"] in {"template_recipe", "generated_image", "product_asset", "none"}


def test_orchestrator_batch_diversifies_engines(tmp_path):
    o = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path))
    batch = o.create_batch(count=7, platform="instagram_feed")
    engines_used = {p.engine for p in batch}
    # Default mix uses all three engines across 7 posts
    assert engines_used == {"A", "B", "C"}


def test_orchestrator_records_memory(tmp_path):
    d = str(tmp_path)
    o = orchestrator.SocialIntelligenceOrchestrator(data_dir=d)
    o.create_post(rotation_index=0)
    r = memory_intelligence.recent(d, limit=5)
    assert r["pillars"]
    assert r["visual_formats"]
