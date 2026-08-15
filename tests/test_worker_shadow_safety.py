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