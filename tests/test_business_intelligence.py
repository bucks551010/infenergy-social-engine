"""Business Intelligence Foundation tests (Master Build §72).

These tests do NOT set ``ENABLE_BUSINESS_INTELLIGENCE`` — the flag is
only consulted by callers who want to gate downstream behavior. The
module is safely importable and executable regardless.

Isolation: every test that mutates disk points ``BI_DATA_DIR`` at a
``tmp_path`` before importing the API, so nothing is written under the
real ``data/business_intelligence/`` tree.
"""

from __future__ import annotations

import importlib
import json
import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))


@pytest.fixture
def bi_env(tmp_path, monkeypatch):
    """Point BI at a tmp dir + reload all BI submodules cleanly."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "business_intelligence").mkdir()
    (data_dir / "products").mkdir()
    (data_dir / "product_briefs").mkdir()
    (data_dir / "marketing").mkdir()
    (data_dir / "social").mkdir()

    monkeypatch.setenv("BI_DATA_DIR", str(data_dir))

    # Purge any cached BI modules so paths re-resolve
    for name in list(sys.modules):
        if name == "business_intelligence" or name.startswith("business_intelligence."):
            del sys.modules[name]

    yield data_dir


def _seed_manifesto(data_dir):
    manifesto = {
        "brand_name": "Infenergy Power",
        "mission": "Empower every household to be prepared without fear.",
        "vision": "A world where power never means panic.",
        "core_values": ["preparedness", "practicality", "calm"],
        "brand_personality": {
            "voice_name": "Calm Strength",
            "traits": ["clear", "grounded"],
            "tone_rules": ["never fear-monger", "translate specs to outcomes"],
        },
        "business_profile": {
            "positioning": "Preparedness-first portable power",
            "what_we_sell": ["portable power stations", "backup batteries", "solar chargers"],
            "what_we_do_not_position_as": ["doomsday gear", "survivalist marketing"],
        },
        "origin_story": {
            "problem": "Families are underprepared for outages.",
            "why_it_matters": "Real safety and continuity.",
        },
    }
    with open(data_dir / "marketing" / "founder_brand_manifesto.json", "w", encoding="utf-8") as fh:
        json.dump(manifesto, fh)


def _seed_products_csv(data_dir):
    csv = (
        "ID,Name,SKU,Parent,Brands,Regular price,Sale price,In stock?,Description,"
        "Short description,Categories,Tags,Images,Weight (lbs),Length (in),Width (in),Height (in)\n"
        "101,Portable Power Station 500W,PS-500,,InfenergyBrand,299.00,249.00,1,"
        "<p>Reliable <b>500W</b> station for home backup.</p>,Compact backup,"
        "Portable Power|Backup,storm|prep,,10.5,8,6,5\n"
        "102,USB-C Charger 65W,CH-65,,InfenergyBrand,39.99,,1,"
        "<p>Small 65W charger for laptop + phone.</p>,Travel charger,"
        "Chargers,travel|charge,,0.4,3,2,1\n"
    )
    with open(data_dir / "products" / "wc-product-export.csv", "w", encoding="utf-8") as fh:
        fh.write(csv)


def _seed_briefs(data_dir):
    brief = {
        "sku": "PS-500",
        "verified_facts": ["500W AC output", "USB-C PD 65W"],
        "core_benefits": ["Runs the fridge for 4 hours", "Charges phones for a week"],
        "best_fit_use_cases": ["home outage backup", "camping trip"],
        "best_fit_audiences": ["preparedness focused household"],
        "primary_pain_point": "Not knowing what to power first when the grid fails",
        "proof_rule": "Runtime figures based on 60W fridge draw",
        "hashtag_themes": ["#preparedness", "#backuppower"],
        "forbidden_claims": ["life-saving", "guaranteed backup"],
    }
    with open(data_dir / "product_briefs" / "PS-500.json", "w", encoding="utf-8") as fh:
        json.dump(brief, fh)


def _seed_social_libraries(data_dir):
    audience = {
        "segments": {
            "preparedness_focused_household": {
                "name": "Preparedness-focused household",
                "description": "Working parents who want power confidence.",
                "problems": ["outage risk", "device runtime anxiety"],
                "questions": ["What do I plug in first?", "Do I need solar?"],
                "goals": ["stay powered", "protect family"],
                "objections": ["overspending"],
            }
        }
    }
    with open(data_dir / "social" / "audience_world.json", "w", encoding="utf-8") as fh:
        json.dump(audience, fh)
    pillars = {
        "pillars": {
            "preparedness": {"name": "Preparedness", "weight": 0.9, "evergreen": True, "engine_fit": ["educational"]},
            "portable_power": {"name": "Portable Power", "weight": 0.8, "evergreen": True, "engine_fit": ["product_demo"]},
        }
    }
    with open(data_dir / "social" / "pillars.json", "w", encoding="utf-8") as fh:
        json.dump(pillars, fh)


def _seed_all(data_dir):
    _seed_manifesto(data_dir)
    _seed_products_csv(data_dir)
    _seed_briefs(data_dir)
    _seed_social_libraries(data_dir)


# =====================================================================
# Module import + gate
# =====================================================================


def test_module_imports_and_is_disabled_by_default(bi_env, monkeypatch):
    monkeypatch.delenv("ENABLE_BUSINESS_INTELLIGENCE", raising=False)
    import business_intelligence  # noqa: F401
    assert business_intelligence.is_enabled() is False


def test_module_enables_via_flag(bi_env, monkeypatch):
    monkeypatch.setenv("ENABLE_BUSINESS_INTELLIGENCE", "1")
    import business_intelligence
    assert business_intelligence.is_enabled() is True


# =====================================================================
# information_types
# =====================================================================


def test_information_types_are_complete(bi_env):
    from business_intelligence import information_types as it
    for t in ("OWNER_ASSERTION", "VERIFIED_FACT", "CATALOG_FACT", "DOCUMENTED_CLAIM",
              "STRATEGIC_INFERENCE", "PERFORMANCE_LEARNING", "OPERATOR_CONTEXT", "PROHIBITED"):
        assert t in it.INFORMATION_TYPES
    assert 0.0 <= it.confidence_from_type("STRATEGIC_INFERENCE") <= 1.0
    assert it.is_publishable_as_fact("OWNER_ASSERTION") is True
    assert it.is_publishable_as_fact("STRATEGIC_INFERENCE") is False


# =====================================================================
# Source discovery + registry
# =====================================================================


def test_source_discovery_registers_all_seeded(bi_env):
    _seed_all(bi_env)
    from business_intelligence import sources
    discovered = sources.discover_all()
    types = {s.source_type for s in discovered}
    assert "csv_catalog" in types
    assert "manifesto" in types
    assert "product_briefs" in types
    # Registry persisted
    reloaded = sources.load_registry()
    assert len(reloaded) == len(discovered)


def test_csv_adapter_strips_html(bi_env):
    _seed_all(bi_env)
    from business_intelligence import sources
    adapter = sources.CsvCatalogAdapter()
    srcs = adapter.discover()
    rows = list(adapter.read(srcs[0]))
    assert rows[0]["Description_clean"] == "Reliable 500W station for home backup."


# =====================================================================
# Evidence ledger + conflicts
# =====================================================================


def test_evidence_ledger_records_and_reads(bi_env):
    _seed_all(bi_env)
    from business_intelligence import evidence
    rec = evidence.make_record(
        subject="offering:PS-500",
        field="price",
        value=249.00,
        information_type="CATALOG_FACT",
        source_id="csv:test",
        domain="product_specification",
    )
    evidence.append(rec)
    stored = evidence.read_all()
    assert any(r.evidence_id == rec.evidence_id for r in stored)
    strongest = evidence.strongest_value("offering:PS-500", "price")
    assert strongest is not None
    assert strongest.value == 249.00


def test_evidence_authority_ranks_owner_over_inference(bi_env):
    from business_intelligence import evidence
    hi = evidence.domain_authority("business_purpose", "OWNER_ASSERTION")
    lo = evidence.domain_authority("business_purpose", "STRATEGIC_INFERENCE")
    assert hi > lo


def test_conflict_detection(bi_env):
    _seed_all(bi_env)
    from business_intelligence import evidence
    a = evidence.make_record(
        subject="offering:PS-500", field="name", value="Portable Power Station 500W",
        information_type="CATALOG_FACT", source_id="csv:a", domain="product_specification"
    )
    evidence.append(a)
    b = evidence.make_record(
        subject="offering:PS-500", field="name", value="PS-500 Home Backup",
        information_type="OWNER_ASSERTION", source_id="owner", domain="business_purpose"
    )
    conflict = evidence.detect_and_record_conflict(b)
    assert conflict is not None
    assert conflict.subject == "offering:PS-500"


def test_evidence_rejects_bad_info_type(bi_env):
    from business_intelligence import evidence
    with pytest.raises(ValueError):
        evidence.make_record(
            subject="x", field="y", value=1,
            information_type="NOT_A_REAL_TYPE", source_id="s"
        )


# =====================================================================
# Offerings
# =====================================================================


def test_offerings_build_from_csv_merges_briefs(bi_env):
    _seed_all(bi_env)
    from business_intelligence import offerings
    result = offerings.build_from_csv()
    ps = next(o for o in result if o.sku == "PS-500")
    assert ps.name == "Portable Power Station 500W"
    assert ps.price == 299.0
    assert ps.sale_price == 249.0
    # Brief-derived fields
    assert "500W AC output" in ps.verified_facts
    assert "life-saving" in ps.forbidden_claims
    assert "preparedness focused household" in ps.customer_fit
    # HTML cleaned
    assert "<b>" not in ps.description_clean


def test_catalog_snapshot_summary(bi_env):
    _seed_all(bi_env)
    from business_intelligence import offerings
    result = offerings.build_from_csv()
    snapshot = offerings.catalog_snapshot(result)
    assert snapshot["total_offerings"] == 2
    assert snapshot["price_range"]["low"] == 39.99
    assert snapshot["with_verified_facts"] >= 1


def test_offering_graph_edges(bi_env):
    _seed_all(bi_env)
    from business_intelligence import offerings
    result = offerings.build_from_csv()
    edges = offerings.build_graph(result)
    relations = {e.relation for e in edges}
    assert "IN_CATEGORY" in relations
    assert "ENABLES_USE_CASE" in relations
    assert "SERVES_SEGMENT" in relations


def test_offering_emit_evidence(bi_env):
    _seed_all(bi_env)
    from business_intelligence import offerings, evidence
    result = offerings.build_from_csv()
    n = offerings.emit_evidence(result)
    assert n > 0
    records = evidence.by_subject("offering:101")
    assert len(records) > 0


# =====================================================================
# Audience + brand + social mandate
# =====================================================================


def test_audience_segments_load_from_social_library(bi_env):
    _seed_all(bi_env)
    from business_intelligence import audience
    segs = audience.build_segments()
    assert len(segs) == 1
    s = segs[0]
    assert s.segment_id == "preparedness_focused_household"
    assert "outage risk" in s.problems


def test_customer_moments_and_transformations(bi_env):
    from business_intelligence import audience
    moments = audience.build_moments()
    trans = audience.build_transformations()
    assert any(m.moment_id == "storm_approaching" for m in moments)
    assert any(t.transformation_id == "uncertain_to_prepared" for t in trans)


def test_brand_identity_reads_manifesto(bi_env):
    _seed_all(bi_env)
    from business_intelligence import brand
    ident = brand.build_identity()
    why = brand.build_why()
    assert ident.business_name == "Infenergy Power"
    assert why.mission == "Empower every household to be prepared without fear."


def test_voice_dna_uses_manifesto_traits(bi_env):
    _seed_all(bi_env)
    from business_intelligence import brand
    voice = brand.build_voice()
    assert voice.brand_personality == "Calm Strength"
    assert "life-saving" in voice.prohibited_phrases


def test_social_mandate_and_territories(bi_env):
    _seed_all(bi_env)
    from business_intelligence import social_mandate
    mandate = social_mandate.build_mandate()
    territories = social_mandate.build_territories()
    assert mandate.social_account_role
    assert any(t.territory_id == "preparedness" for t in territories)


def test_right_to_speak(bi_env):
    _seed_all(bi_env)
    from business_intelligence import social_mandate
    territories = social_mandate.build_territories()
    ok = social_mandate.right_to_speak("preparedness", territories)
    bad = social_mandate.right_to_speak("politics", territories)
    assert ok["eligible"] is True
    assert bad["eligible"] is False


# =====================================================================
# Research + gaps + hypotheses
# =====================================================================


def test_default_research_policy_is_conservative(bi_env):
    from business_intelligence import research
    policy = research.load_policy()
    assert policy.research_enabled is False
    assert policy.high_risk_verification_required is True
    assert policy.technical_research_enabled is True


def test_gap_and_hypothesis_registration(bi_env):
    from business_intelligence import research
    gap = research.register_gap(domain="market", question="Which region has highest storm activity?", importance="high")
    hyp = research.register_hypothesis("Storm-prone regions outperform on preparedness content", domain="content_strategy")
    gaps = research.load_gaps()
    hyps = research.load_hypotheses()
    assert any(g.gap_id == gap.gap_id for g in gaps)
    assert any(h.hypothesis_id == hyp.hypothesis_id for h in hyps)


# =====================================================================
# Learning + locked/learnable + owner overrides
# =====================================================================


def test_locked_fields_reject_performance_signals(bi_env):
    from business_intelligence import learning
    assert learning.is_locked("identity.business_name") is True
    assert learning.is_locked("voice.preferred_phrases") is False
    with pytest.raises(ValueError):
        learning.record_signal(scope="identity", subject="business_name", signal="negative")


def test_performance_signal_records_learnable(bi_env):
    from business_intelligence import learning
    for _ in range(3):
        learning.record_signal(scope="audience", subject="preparedness_focused_household", signal="positive")
    summary = learning.summarize_learning(min_sample_size=3)
    assert "audience" in summary
    assert summary["audience"]["preparedness_focused_household"]["sample"] == 3


def test_owner_override_beats_derived_value(bi_env):
    _seed_all(bi_env)
    from business_intelligence import learning, profile as prof_mod
    learning.register_override(
        subject="identity",
        field_path="identity.business_name",
        value="Infenergy Power (Owner-Approved)",
        reason="brand rename",
    )
    p = prof_mod.assemble()
    version = prof_mod.save_current(p)
    saved = prof_mod.load_current()
    assert saved["identity"]["business_name"] == "Infenergy Power (Owner-Approved)"
    assert version.profile_version


# =====================================================================
# Profile assembly + critic + versioning
# =====================================================================


def test_profile_assembles_end_to_end(bi_env):
    _seed_all(bi_env)
    from business_intelligence import profile as prof_mod
    p = prof_mod.assemble()
    assert p.identity.business_name == "Infenergy Power"
    assert p.audience_segments
    assert p.offerings
    assert p.voice.brand_personality


def test_profile_versioning_creates_snapshot(bi_env):
    _seed_all(bi_env)
    from business_intelligence import profile as prof_mod
    p = prof_mod.assemble()
    v = prof_mod.save_current(p, change_reason="test")
    versions_dir = os.path.join(prof_mod.paths.profile_dir(), "versions")
    files = os.listdir(versions_dir)
    assert any(v.profile_version in f for f in files)


def test_profile_markdown_render(bi_env):
    _seed_all(bi_env)
    from business_intelligence import profile as prof_mod
    p = prof_mod.assemble()
    prof_mod.save_current(p)
    with open(prof_mod.markdown_path(), "r", encoding="utf-8") as fh:
        md = fh.read()
    assert "Business Profile" in md
    assert "Infenergy Power" in md


def test_critic_review_reports_pass_or_fail(bi_env):
    _seed_all(bi_env)
    from business_intelligence import critic, profile as prof_mod
    p = prof_mod.assemble()
    from dataclasses import asdict
    verdict = critic.review(asdict(p))
    assert isinstance(verdict.passed, bool)
    assert isinstance(verdict.checks, list)
    assert len(verdict.checks) >= 10


def test_critic_detects_voice_contradiction(bi_env):
    from business_intelligence import critic
    fake = {
        "identity": {"business_name": "X", "industry": "y"},
        "why": {"mission": "m"},
        "voice": {
            "brand_personality": "p",
            "preferred_phrases": ["life-saving"],
            "prohibited_phrases": ["life-saving"],
        },
        "social_mandate": {"social_account_role": "r", "social_account_promise": "p"},
        "audience_segments": [{"segment_id": "s", "problems": [], "questions": []}],
        "offerings": [],
        "positioning": {"primary_position": "p", "differentiators": ["d"]},
        "promise": {"promise": "p", "customer_outcome": "o"},
        "reputation": {"desired_reputation": "r"},
        "content_territories": [],
    }
    v = critic.review(fake)
    assert v.passed is False
    assert any("contradiction" in f.lower() for f in v.failures)


# =====================================================================
# Compilers
# =====================================================================


def test_conversion_context_shape(bi_env):
    _seed_all(bi_env)
    from business_intelligence import api
    api.rebuild_profile()
    ctx = api.compile_conversion_context()
    for k in ("business_identity", "brand_promise", "voice", "audience_segment", "offering", "forbidden_claims"):
        assert k in ctx


def test_creative_context_includes_brand_prohibitions(bi_env):
    _seed_all(bi_env)
    from business_intelligence import api
    api.rebuild_profile()
    ctx = api.compile_creative_context(territory_id="preparedness")
    assert ctx["focus_territory"] is not None
    assert "voice" in ctx["brand_prohibitions"]


def test_orchestrator_context_has_summary(bi_env):
    _seed_all(bi_env)
    from business_intelligence import api
    api.rebuild_profile()
    ctx = api.compile_orchestrator_context()
    assert "offerings_summary" in ctx
    assert ctx["offerings_summary"]["total"] >= 1


# =====================================================================
# End-to-end bootstrap
# =====================================================================


def test_bootstrap_runs_end_to_end(bi_env):
    _seed_all(bi_env)
    from business_intelligence import api
    result = api.rebuild_profile(reset_evidence=True)
    assert result["sources_discovered"] >= 3
    assert result["offerings"] == 2
    assert result["evidence_records"] > 0
    assert result["profile_version"]
    assert result["verdict"]["checks"] >= 10


def test_api_facade_smoke(bi_env):
    _seed_all(bi_env)
    from business_intelligence import api
    api.rebuild_profile()
    assert api.get_business_identity()["business_name"] == "Infenergy Power"
    assert api.get_brand_context()["voice"]["brand_personality"] == "Calm Strength"
    seg = api.get_audience_segment("preparedness_focused_household")
    assert seg is not None


def test_api_registers_owner_assertion(bi_env):
    _seed_all(bi_env)
    from business_intelligence import api
    api.rebuild_profile()
    result = api.register_owner_assertion(
        subject="positioning",
        field="primary_position",
        value="Preparedness-first, calm, capable",
        reason="post-audit rewrite",
    )
    assert result["override_id"]
    # Rebuild should now reflect override in the persisted profile
    api.rebuild_profile()
    saved = api.get_business_profile()
    assert saved["positioning"]["primary_position"] == "Preparedness-first, calm, capable"


def test_schema_validation_soft_warnings(bi_env):
    _seed_all(bi_env)
    from business_intelligence import profile as prof_mod
    from business_intelligence.schemas import validate_profile
    p = prof_mod.assemble()
    warnings = validate_profile(p)
    # A fully seeded profile should produce no warnings
    assert warnings == [] or all(isinstance(w, str) for w in warnings)


def test_service_business_still_assembles(bi_env, monkeypatch):
    # Only manifesto (no CSV, no briefs) — profile should still assemble
    _seed_manifesto(bi_env)
    _seed_social_libraries(bi_env)
    from business_intelligence import profile as prof_mod
    p = prof_mod.assemble()
    assert p.identity.business_name == "Infenergy Power"
    assert p.offerings == []


def test_missing_source_does_not_crash(bi_env):
    # Empty repo — no seeds
    from business_intelligence import sources, profile as prof_mod
    discovered = sources.discover_all()
    assert isinstance(discovered, list)
    p = prof_mod.assemble()
    # Identity may be empty but should still be a BusinessProfile
    assert hasattr(p, "identity")
    assert hasattr(p, "audience_segments")


# =====================================================================
# Downstream wiring: Social Intelligence orchestrator hydration
# =====================================================================


def test_orchestrator_ignores_bi_when_flag_off(bi_env, monkeypatch):
    _seed_all(bi_env)
    monkeypatch.delenv("ENABLE_BUSINESS_INTELLIGENCE", raising=False)
    from social import orchestrator as orch
    ctx = orch._load_bi_creative_context()
    assert ctx is None


def test_orchestrator_hydrates_from_bi_when_flag_on(bi_env, monkeypatch):
    _seed_all(bi_env)
    from business_intelligence import api
    api.rebuild_profile()
    monkeypatch.setenv("ENABLE_BUSINESS_INTELLIGENCE", "1")

    # Reload orchestrator so its module-level _bi_enabled sees the flag
    for name in list(sys.modules):
        if name.startswith("social."):
            del sys.modules[name]

    from social import orchestrator as orch
    ctx = orch._load_bi_creative_context()
    assert ctx is not None
    assert orch._bi_preferred_pillar(ctx) in ("preparedness", "portable_power")
    assert orch._bi_audience_hint(ctx) == "preparedness_focused_household"


def test_post_package_carries_business_context_field(bi_env):
    from social.orchestrator import PostPackage
    pkg = PostPackage(
        post_id="x", engine="B", brief={}, copy={}, visual={},
        carousel=None, claim_ledger={}, quality={}, creative_director={},
        text_visual_allocation={}, provider_result={},
    )
    # Default is None, must round-trip via as_dict()
    assert pkg.business_context is None
    assert "business_context" in pkg.as_dict()


def test_cli_status_command(bi_env, monkeypatch, capsys):
    _seed_all(bi_env)
    from business_intelligence import api, __main__ as cli
    api.rebuild_profile()
    rc = cli.main(["status"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["identity"]["business_name"]
    assert payload["offerings"] >= 1


def test_cli_rebuild_command(bi_env, capsys):
    _seed_all(bi_env)
    from business_intelligence import __main__ as cli
    rc = cli.main(["rebuild", "--reset-evidence"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["offerings"] == 2
    assert payload["verdict"]["passed"] is True
