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
    pregeneration_jobs = [job for job in jobs if job.job_func.func is worker._start_pregeneration_thread]
    factory_jobs = [job for job in jobs if job.job_func.func is worker._start_factory_thread]
    legacy_clock_jobs = [job for job in jobs if job.job_func.func is worker.run_slot]
    watchdog_jobs = [job for job in jobs if job.job_func.func is worker.run_delivery_watchdog]

    assert len(dispatch_jobs) == 4
    assert len(pregeneration_jobs) == 1
    assert len(factory_jobs) == 1
    assert legacy_clock_jobs == []
    assert len(watchdog_jobs) == 1
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


def test_delivery_watchdog_requests_factory_when_today_has_no_publishable_inventory(monkeypatch):
    recoveries = []
    monkeypatch.setattr(worker, "_data_dir", lambda: "unused")
    monkeypatch.setattr(worker, "daily_status", lambda *_: {
        "published": 0,
        "ready": 0,
        "missing": 3,
        "slots": [],
    })
    monkeypatch.setattr(worker, "_start_factory_thread", lambda: recoveries.append("requested"))

    result = worker.run_delivery_watchdog()

    assert result["recovery_requested"] is True
    assert recoveries == ["requested"]


def test_delivery_watchdog_does_not_replace_covered_inventory(monkeypatch):
    recoveries = []
    monkeypatch.setattr(worker, "_data_dir", lambda: "unused")
    monkeypatch.setattr(worker, "daily_status", lambda *_: {
        "published": 1,
        "ready": 2,
        "missing": 0,
        "slots": [{"status": "PUBLISHED"}, {"status": "READY"}, {"status": "READY"}],
    })
    monkeypatch.setattr(worker, "_start_factory_thread", lambda: recoveries.append("requested"))

    result = worker.run_delivery_watchdog()

    assert result["recovery_requested"] is False
    assert recoveries == []


def test_main_runs_due_sweep_immediately_on_startup(monkeypatch):
    dispatches = []
    pregenerations = []
    monkeypatch.setenv("CONTENT_DISPATCH_ENABLED", "true")
    monkeypatch.setattr(worker, "start_health_server", lambda: None)
    monkeypatch.setattr(worker, "_load_meta_runtime_from_state", lambda: (False, "not_configured"))
    monkeypatch.setattr(worker, "_auto_bootstrap_visual_repo", lambda: {"status": "ok", "summary": {}})
    monkeypatch.setattr(worker, "run_intelligence_enrichment", lambda: None)
    monkeypatch.setattr(worker, "_start_dispatch_thread", dispatches.append)
    monkeypatch.setattr(worker, "_start_pregeneration_thread", lambda: pregenerations.append("started"))
    monkeypatch.setattr(worker.schedule, "run_pending", lambda: (_ for _ in ()).throw(KeyboardInterrupt))

    try:
        worker.main()
    except KeyboardInterrupt:
        pass

    assert dispatches == ["startup_sweep"]
    assert pregenerations == ["started"]


def test_dispatch_sweep_records_publication_result(monkeypatch):
    result = {
        "status": "COMPLETE",
        "processed": 1,
        "published": 1,
        "failed": 0,
        "results": [{
            "status": "PUBLISHED",
            "outbox_id": "outbox-1",
            "platforms": {"facebook": {"state": "CONFIRMED_SUCCESS", "external_id": "fb-1"}},
        }],
    }
    monkeypatch.setattr(worker, "RUN_LOCK", worker.threading.Lock())
    monkeypatch.setattr(worker, "_data_dir", lambda: "unused")
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=worker.json.dumps(result),
            stderr="provider deprecation warning",
        ),
    )

    worker.dispatch_scheduled_slot("startup_sweep")

    assert worker.LAST_DISPATCH["status"] == "complete"
    assert worker.LAST_DISPATCH["trigger"] == "startup_sweep"
    assert worker.LAST_DISPATCH["exit_code"] == 0
    assert worker.LAST_DISPATCH["result"] == result
    assert worker.LAST_DISPATCH["started_at_utc"]
    assert worker.LAST_DISPATCH["finished_at_utc"]


def test_manual_monthly_generation_builds_prepares_and_pregenerates_to_idle(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(worker, "build_monthly_calendar", lambda **kwargs: {
        "queued": 2, "calendar_path": "calendar.json", "single_image_posts": 1, "carousel_posts": 1,
    })
    monkeypatch.setattr(worker, "prepare_monthly_gemini_prompts", lambda data_dir: {
        "prepared_entries": 2, "prepared_prompts": 5,
    })
    results = iter([
        {"status": "PREGENERATED", "outbox_id": "one"},
        {"status": "PREGENERATED", "outbox_id": "two"},
        {"status": "IDLE"},
    ])
    monkeypatch.setattr(worker, "_pregenerate_one_package", lambda: next(results))

    worker.run_manual_monthly_generation("job-1", days=2, start_date=None, replace_unpublished=True)

    status = worker._monthly_generation_status()
    assert status["status"] == "COMPLETE"
    assert status["phase"] == "COMPLETE"
    assert status["queued"] == 2
    assert status["prepared_prompts"] == 5
    assert status["pregenerated_packages"] == 2


def test_manual_monthly_generation_propagates_weekly_brand_mix(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    captured = {}
    monkeypatch.setattr(worker, "build_monthly_calendar", lambda **kwargs: captured.update(kwargs) or {
        "queued": 0, "calendar_path": "calendar.json", "single_image_posts": 103, "carousel_posts": 17,
    })
    monkeypatch.setattr(worker, "prepare_monthly_gemini_prompts", lambda data_dir: {
        "prepared_entries": 0, "prepared_prompts": 0,
    })

    worker.run_manual_monthly_generation(
        "job-120", days=120, start_date="2026-09-01", replace_unpublished=True, content_plan="weekly_brand_mix",
    )

    assert captured["days"] == 120
    assert captured["replace_unpublished"] is True
    assert captured["content_plan"] == "weekly_brand_mix"
    assert worker._monthly_generation_status()["status"] == "COMPLETE"


def test_manual_monthly_generation_rejects_second_request_while_first_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    worker._save_monthly_generation_status(job_id="job-1", status="ACCEPTED", phase="QUEUED")

    accepted, status = worker._start_manual_monthly_generation(
        days=30, start_date=None, replace_unpublished=True,
    )

    assert accepted is False
    assert status["job_id"] == "job-1"
    assert status["status"] == "ACCEPTED"


def test_manual_monthly_generation_completes_without_dispatch_when_nothing_new_was_queued(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(worker, "build_monthly_calendar", lambda **kwargs: {
        "queued": 0, "calendar_path": "calendar.json", "single_image_posts": 1, "carousel_posts": 0,
    })
    monkeypatch.setattr(worker, "prepare_monthly_gemini_prompts", lambda data_dir: {
        "prepared_entries": 0, "prepared_prompts": 0,
    })
    monkeypatch.setattr(worker, "_pregenerate_one_package", lambda: pytest.fail("unrelated outbox work was dispatched"))

    worker.run_manual_monthly_generation("job-1", days=1, start_date=None, replace_unpublished=False)

    status = worker._monthly_generation_status()
    assert status["status"] == "COMPLETE"
    assert status["queued"] == 0
    assert status["pregenerated_packages"] == 0


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
