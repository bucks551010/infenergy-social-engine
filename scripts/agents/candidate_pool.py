"""Authenticated dispatcher entry point for building text-only candidate pools."""

from __future__ import annotations

from typing import Any


def run(data_dir: str, target_depth: int = 0, max_attempts: int = 0, **_: Any) -> dict:
    import build_candidate_pool

    kwargs = {}
    if target_depth:
        kwargs["target_depth"] = int(target_depth)
    if max_attempts:
        kwargs["max_attempts"] = int(max_attempts)
    return build_candidate_pool.build_pool(**kwargs)