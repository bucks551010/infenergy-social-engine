from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_gemini_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_USAGE_PATH", str(tmp_path / "gemini-usage.json"))
