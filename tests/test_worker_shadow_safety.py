from __future__ import annotations

import os
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import worker


def test_deployment_metadata_exposes_only_non_secret_railway_identity(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "cef265a")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deployment-123")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")

    assert worker._deployment_metadata() == {
        "git_commit_sha": "cef265a",
        "deployment_id": "deployment-123",
        "environment": "production",
    }


def _run_slot(monkeypatch, *, force_live: bool, shadow_mode: bool, platforms: str = "facebook"):
    refresh = Mock(return_value=(True, {"ok": True}))
    bootstrap = Mock()
    heartbeat = Mock()
    completed = Mock(return_value=CompletedProcess(args=[], returncode=0, stdout="", stderr=""))

    monkeypatch.setattr(worker, "_refresh_meta_tokens", refresh)
    monkeypatch.setattr(worker, "_auto_bootstrap_visual_repo", bootstrap)
    monkeypatch.setattr(worker.subprocess, "run", completed)
    monkeypatch.setitem(sys.modules, "social.living_intelligence", type("Living", (), {"heartbeat": heartbeat}))
    monkeypatch.setenv("META_AUTO_REFRESH_ENABLED", "true")
    monkeypatch.setenv("META_REFRESH_EVERY_RUN", "true")
    monkeypatch.setenv("SOCIAL_DRY_RUN", "true")
    monkeypatch.delenv("SOCIAL_SHADOW_MODE", raising=False)

    worker.run_slot(
        "morning",
        force_live=force_live,
        shadow_mode=shadow_mode,
        platforms_override=platforms,
        pipeline_override="orchestrator",
        engine_override="product",
        readiness_block_override="true",
    )
    return refresh, completed


def test_shadow_forbids_meta_refresh_even_when_refresh_is_forced(monkeypatch):
    refresh, completed = _run_slot(monkeypatch, force_live=False, shadow_mode=True)

    refresh.assert_not_called()
    assert completed.call_args.kwargs["env"]["SOCIAL_SHADOW_MODE"] == "true"
    assert completed.call_args.kwargs["env"]["SOCIAL_DRY_RUN"] == "true"
    assert completed.call_args.kwargs["env"]["POST_PLATFORMS"] == "facebook"
    assert completed.call_args.kwargs["env"]["POST_PIPELINE_OVERRIDE"] == "orchestrator"
    assert completed.call_args.kwargs["env"]["POST_ENGINE_OVERRIDE"] == "product"


def test_manual_run_scopes_product_exclusion_and_product_free_contract(monkeypatch):
    refresh = Mock(return_value=(True, {"ok": True}))
    completed = Mock(return_value=CompletedProcess(args=[], returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(worker, "_refresh_meta_tokens", refresh)
    monkeypatch.setattr(worker, "_auto_bootstrap_visual_repo", Mock())
    monkeypatch.setattr(worker.subprocess, "run", completed)
    monkeypatch.setitem(sys.modules, "social.living_intelligence", type("Living", (), {"heartbeat": Mock()}))
    monkeypatch.setenv("SOCIAL_DRY_RUN", "true")

    worker.run_slot("morning", shadow_mode=True, engine_override="b", excluded_product_ids="PPP-200", require_product_free=True)

    env = completed.call_args.kwargs["env"]
    assert env["POST_EXCLUDED_PRODUCT_IDS"] == "PPP-200"
    assert env["POST_REQUIRE_PRODUCT_FREE"] == "true"
    assert env["POST_PIPELINE_OVERRIDE"] == "orchestrator"


def test_non_live_run_forbids_meta_refresh(monkeypatch):
    refresh, completed = _run_slot(monkeypatch, force_live=False, shadow_mode=False)

    refresh.assert_not_called()
    assert completed.called


def test_live_facebook_retains_meta_refresh(monkeypatch):
    refresh, completed = _run_slot(monkeypatch, force_live=True, shadow_mode=False, platforms="facebook")

    refresh.assert_called_once_with()
    assert completed.call_args.kwargs["env"]["SOCIAL_DRY_RUN"] == "false"


def test_live_instagram_retains_meta_refresh(monkeypatch):
    refresh, completed = _run_slot(monkeypatch, force_live=True, shadow_mode=False, platforms="instagram")

    refresh.assert_called_once_with()
    assert completed.call_args.kwargs["env"]["POST_PLATFORMS"] == "instagram"


def test_external_social_policy_requires_live_non_shadow_mode():
    assert not worker._external_social_access_allowed(force_live=False, shadow_mode=True)
    assert not worker._external_social_access_allowed(force_live=False, shadow_mode=False)
    assert not worker._external_social_access_allowed(force_live=True, shadow_mode=True)
    assert worker._external_social_access_allowed(force_live=True, shadow_mode=False)


def test_frozen_promotion_shadow_mode_never_enables_external_access(monkeypatch):
    promote = Mock(return_value={"ok": True, "status": "shadow_promoted_not_published"})
    refresh = Mock(return_value=(True, "refreshed"))
    monkeypatch.setattr(worker.run_engine, "promote_approved_frozen_artifact", promote)
    monkeypatch.setattr(worker, "_auto_refresh_meta_if_due", refresh)

    worker.promote_frozen_artifact("approved-shadow", platforms=["facebook"], live=False, shadow_mode=True)

    promote.assert_called_once_with(
        "approved-shadow", platforms=["facebook"], dry_run=True, shadow_mode=True
    )
    refresh.assert_not_called()
    assert worker.LAST_RUN["status"] == "success"


def test_frozen_promotion_live_forwards_explicit_live_intent(monkeypatch):
    promote = Mock(return_value={"ok": True, "status": "promoted"})
    refresh = Mock(return_value=(False, "not_due"))
    monkeypatch.setattr(worker.run_engine, "promote_approved_frozen_artifact", promote)
    monkeypatch.setattr(worker, "_auto_refresh_meta_if_due", refresh)

    worker.promote_frozen_artifact("approved-shadow", platforms=["linkedin"], live=True, shadow_mode=False)

    promote.assert_called_once_with(
        "approved-shadow", platforms=["linkedin"], dry_run=False, shadow_mode=False
    )
    refresh.assert_called_once_with()
    assert worker.LAST_RUN["status"] == "success"


def test_engine_a_product_field_excludes_products_without_generating_content(monkeypatch):
    class Candidate:
        pillar_id = "preparedness"
        genre_id = "checklist"
        topic_path = type("TopicPath", (), {"topic": "Outages"})()

    from business_intelligence import api as bi_api
    from social import engines, memory_intelligence, opportunity_engine

    monkeypatch.setattr(bi_api, "get_business_profile", lambda: {"offerings": [
        {"offering_id": "PPP-200"},
        {"offering_id": "PF-150W"},
        {"offering_id": "OTHER-1"},
    ]})
    monkeypatch.setattr(worker, "_data_dir", lambda: "data")
    monkeypatch.setattr(memory_intelligence, "recent", lambda *args, **kwargs: {"pillars": [], "genres": [], "topics": [], "microtopics": []})
    monkeypatch.setattr(opportunity_engine, "generate", lambda **kwargs: [Candidate()])
    monkeypatch.setattr(engines, "get_engine", lambda _name: type("Engine", (), {"build": lambda self, **kwargs: object()})())
    from social import orchestrator
    monkeypatch.setattr(orchestrator, "_build_engine_brief", lambda engine, **kwargs: engine.build(**kwargs))

    field = worker._engine_a_product_field({"PPP-200"})

    assert field["catalog_count"] == 3
    assert field["eligible_product_count"] == 2
    assert field["products_considered"] > 1
    assert field["non_ppp_opportunity_count"] == 1
    assert field["brief_stage_opportunity_count"] == 1
    assert field["brief_build_status"] == "pass"
    assert field["selected_product_id"] == "PF-150W"