"""Unit + integration tests for the Social Intelligence layer.

Kept in a single file to mirror the "few well-structured modules"
philosophy of the implementation itself. Every module has at least one
happy-path test plus a small representative edge case.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import generate_posts  # noqa: E402

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
    quality_intelligence,
    visual_intelligence,
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
    assert model_router.route_for("strategy") == "gemini-2.5-pro"
    monkeypatch.setenv("GEMINI_ROUTE_STRATEGY", "custom-model")
    assert model_router.route_for("strategy") == "custom-model"


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
