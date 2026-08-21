from __future__ import annotations

import os
import sys
from types import SimpleNamespace
import subprocess

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

import worker  # noqa: E402
from scripts import run_engine  # noqa: E402
from social import living_intelligence  # noqa: E402


def test_monthly_api_summary_exposes_knowledge_refresh_audit():
    assert "knowledge_refresh" in worker.MONTHLY_SUMMARY_KEYS
    assert len(worker.MONTHLY_SUMMARY_KEYS) == len(set(worker.MONTHLY_SUMMARY_KEYS))


def test_post_requests_reach_the_existing_endpoint_handler():
    handler = object.__new__(worker.HealthHandler)
    calls = []
    handler.do_GET = lambda: calls.append("handled")

    handler.do_POST()

    assert calls == ["handled"]


def test_publication_clocks_dispatch_and_never_generate():
    os.environ.pop("CONTENT_DISPATCH_ENABLED", None)
    worker.register_scheduled_jobs()
    jobs = worker.schedule.jobs
    dispatch_jobs = [job for job in jobs if job.job_func.func is worker._start_dispatch_thread]
    factory_jobs = [job for job in jobs if job.job_func.func is worker._start_factory_thread]
    legacy_clock_jobs = [job for job in jobs if job.job_func.func is worker.run_slot]

    assert len(dispatch_jobs) == 4
    assert len(factory_jobs) == 1
    assert legacy_clock_jobs == []
    assert {job.job_func.args[0] for job in dispatch_jobs} == {"morning", "midday", "evening", "due_sweep"}


def test_dispatch_schedule_can_be_paused_while_month_is_built(monkeypatch):
    monkeypatch.setenv("CONTENT_DISPATCH_ENABLED", "false")

    worker.register_scheduled_jobs()

    dispatch_jobs = [job for job in worker.schedule.jobs if job.job_func.func is worker._start_dispatch_thread]
    assert dispatch_jobs == []


def test_factory_remains_scheduled_without_being_required_on_startup(monkeypatch):
    monkeypatch.delenv("RUN_FACTORY_ON_STARTUP", raising=False)
    monkeypatch.delenv("CONTENT_FACTORY_ENABLED", raising=False)
    worker.register_scheduled_jobs()

    factory_jobs = [job for job in worker.schedule.jobs if job.job_func.func is worker._start_factory_thread]

    assert len(factory_jobs) == 1
    assert os.environ.get("RUN_FACTORY_ON_STARTUP", "false") == "false"


def test_factory_schedule_can_be_disabled_when_month_is_prebuilt(monkeypatch):
    monkeypatch.setenv("CONTENT_FACTORY_ENABLED", "false")

    worker.register_scheduled_jobs()

    factory_jobs = [job for job in worker.schedule.jobs if job.job_func.func is worker._start_factory_thread]
    assert factory_jobs == []


def test_manual_no_product_override_is_scoped_to_one_run(monkeypatch):
    captured_env = {}

    def fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.delenv("CONTENT_BUCKET_OVERRIDE", raising=False)
    monkeypatch.setenv("CANDIDATE_POOL_TARGET_DEPTH", "0")
    monkeypatch.setattr(living_intelligence, "heartbeat", lambda *args, **kwargs: {})
    monkeypatch.setattr(worker, "_auto_bootstrap_visual_repo", lambda: {})
    monkeypatch.setattr(worker, "_auto_refresh_meta_if_due", lambda: (False, "not_due"))
    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    monkeypatch.setattr(worker, "_last_run_outcome", lambda: {"slot": "morning", "status": "skipped_no_eligible_platforms"})

    worker.run_slot("morning", force_live=True, no_product=True, funnel_stage_override="ATTENTION")

    assert captured_env["CONTENT_BUCKET_OVERRIDE"] == "no_product"
    assert captured_env["POST_FUNNEL_STAGE_OVERRIDE"] == "ATTENTION"
    assert captured_env["CANDIDATE_POOL_RUNTIME_ENABLED"] == "false"
    assert captured_env["POST_TEXT_ONLY"] == "true"
    assert "CONTENT_BUCKET_OVERRIDE" not in os.environ


def test_manual_run_never_refills_candidate_pool_before_seven_candidate_council(monkeypatch):
    captured_env = {}

    def fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(living_intelligence, "heartbeat", lambda *args, **kwargs: {})
    monkeypatch.setattr(worker, "_auto_bootstrap_visual_repo", lambda: {})
    monkeypatch.setattr(worker, "_auto_refresh_meta_if_due", lambda: (False, "not_due"))
    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    monkeypatch.setattr(worker, "_last_run_outcome", lambda: {"slot": "midday", "status": "skipped_no_eligible_platforms"})

    worker.run_slot("midday", force_live=True, product_id_override="CAMP-FAN-12K")

    assert captured_env["CANDIDATE_POOL_RUNTIME_ENABLED"] == "false"
    assert captured_env.get("POST_CANDIDATE_COUNT", "7") == "7"
    assert captured_env["POST_TEXT_ONLY"] == "true"


def test_run_slot_decodes_timeout_output_and_records_failure(monkeypatch):
    monkeypatch.delenv("RUN_SLOT_TIMEOUT_SEC", raising=False)
    monkeypatch.setattr(living_intelligence, "heartbeat", lambda *args, **kwargs: {})
    monkeypatch.setattr(worker, "_auto_bootstrap_visual_repo", lambda: {})
    monkeypatch.setattr(worker, "_auto_refresh_meta_if_due", lambda: (False, "not_due"))
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(args[0], kwargs["timeout"], output=b"partial stdout", stderr=b"partial stderr")
        ),
    )

    worker.run_slot("midday", force_live=True)

    assert worker.LAST_RUN["status"] == "generation_failed"
    assert worker.LAST_RUN["error"] == "run_timeout_after_900s"
    assert worker.LAST_RUN["finished_at_utc"]

def test_followup_council_candidates_skip_repeated_phase2_enrichment(monkeypatch):
    observed = []

    def fake_generate(slot, **kwargs):
        observed.append(os.environ.get("ENABLE_PHASE2_CREATIVE_STACK"))
        return {"slot": slot, **kwargs}

    monkeypatch.setenv("ENABLE_PHASE2_CREATIVE_STACK", "true")
    monkeypatch.setenv("COUNCIL_ENRICH_FIRST_CANDIDATE_ONLY", "true")
    monkeypatch.setattr(run_engine.generate_posts, "generate", fake_generate)

    result = run_engine._generate_followup_candidate("midday", product_id_override="CAMP-FAN-12K")

    assert observed == ["false"]
    assert os.environ["ENABLE_PHASE2_CREATIVE_STACK"] == "true"
    assert result["product_id_override"] == "CAMP-FAN-12K"


def test_final_evidence_ignores_out_of_scope_wordpress_copy():
    content = {
        "product_metrics": ["12000mAh"],
        "wp_content": "This unverified safety claim prevents heat distress.",
        "platform_posts": {
            "facebook": {"final_caption": "Published 12000mAh capacity. Compare it with your actual needs."},
            "instagram": {"final_caption": "Published 12000mAh capacity. Compare it with your actual needs."},
            "linkedin": {"final_caption": "Published 12000mAh capacity. Compare it with your actual needs."},
        },
    }

    readiness = run_engine._final_channel_evidence_readiness(
        content,
        {"wordpress": False, "facebook": True, "instagram": True, "linkedin": True},
    )

    claims = " ".join(item["claim"] for item in readiness["claims"])
    assert "heat distress" not in claims
    assert readiness["status"] != "HIGH_RISK_UNVERIFIED"
