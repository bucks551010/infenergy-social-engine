from __future__ import annotations

import os
import sys
from types import SimpleNamespace

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

import worker  # noqa: E402
from social import living_intelligence  # noqa: E402


def test_publication_clocks_dispatch_and_never_generate():
    worker.register_scheduled_jobs()
    jobs = worker.schedule.jobs
    dispatch_jobs = [job for job in jobs if job.job_func.func is worker._start_dispatch_thread]
    factory_jobs = [job for job in jobs if job.job_func.func is worker._start_factory_thread]
    legacy_clock_jobs = [job for job in jobs if job.job_func.func is worker.run_slot]

    assert len(dispatch_jobs) == 4
    assert len(factory_jobs) == 1
    assert legacy_clock_jobs == []
    assert {job.job_func.args[0] for job in dispatch_jobs} == {"morning", "midday", "evening", "due_sweep"}


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
    assert "CONTENT_BUCKET_OVERRIDE" not in os.environ
