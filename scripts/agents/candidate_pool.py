"""Authenticated dispatcher entry point for building text-only candidate pools."""

from __future__ import annotations

from typing import Any


def _inspect(data_dir: str) -> dict:
    from social.candidate_pool import CandidatePool

    pool = CandidatePool(data_dir)
    payload = pool._load()
    candidates = [
        candidate
        for candidate in payload.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    return {
        "pool_depth": pool.depth(),
        "candidates": candidates,
        "latest_batch_report": (payload.get("batch_reports") or [None])[-1],
    }


def run(data_dir: str, action: str = "build", target_depth: int = 0, max_attempts: int = 0, **_: Any) -> dict:
    if str(action).strip().lower() == "inspect":
        return _inspect(data_dir)
    import build_candidate_pool

    kwargs = {}
    if target_depth:
        kwargs["target_depth"] = int(target_depth)
    if max_attempts:
        kwargs["max_attempts"] = int(max_attempts)
    return build_candidate_pool.build_pool(**kwargs)