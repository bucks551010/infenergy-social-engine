from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social.gemini_budget import GeminiBudgetExceeded, budget_snapshot, preflight_gemini_workflow, reserve_gemini_call  # noqa: E402


def test_daily_budget_blocks_excess_image_and_total_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "2")
    monkeypatch.setenv("GEMINI_DAILY_IMAGE_LIMIT", "1")

    reserve_gemini_call("image", "image-model", "first image")
    with pytest.raises(GeminiBudgetExceeded, match="daily image budget exhausted"):
        reserve_gemini_call("image", "image-model", "second image")

    reserve_gemini_call("reasoning", "reasoning-model", "copy")
    with pytest.raises(GeminiBudgetExceeded, match="daily call budget exhausted"):
        reserve_gemini_call("reasoning", "reasoning-model", "review")

    snapshot = budget_snapshot()
    assert snapshot["total"] == {"used": 2, "limit": 2, "remaining": 0}
    assert snapshot["image"] == {"used": 1, "limit": 1, "remaining": 0}
    assert snapshot["ledger_path"] == os.path.abspath(os.environ["GEMINI_USAGE_PATH"])


def test_workflow_preflight_blocks_before_consuming_when_repairs_cannot_fit(monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "2")
    monkeypatch.setenv("GEMINI_DAILY_IMAGE_LIMIT", "2")
    reserve_gemini_call("image", "image-model", "existing image")

    with pytest.raises(GeminiBudgetExceeded, match="requires 2 image calls"):
        preflight_gemini_workflow(image_calls=2)

    assert budget_snapshot()["image"]["used"] == 1


def test_budget_reservations_are_atomic_under_concurrency(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "2")
    monkeypatch.setenv("GEMINI_DAILY_IMAGE_LIMIT", "2")

    def reserve(index):
        try:
            reserve_gemini_call("image", "image-model", f"attempt {index}")
            return "reserved"
        except GeminiBudgetExceeded:
            return "blocked"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))

    assert results.count("reserved") == 2
    assert results.count("blocked") == 6
    assert budget_snapshot()["image"]["used"] == 2