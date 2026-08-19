from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

import worker  # noqa: E402


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
