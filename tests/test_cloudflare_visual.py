from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import cloudflare_visual, generation_policy


def test_free_ai_only_blocks_paid_gemini(monkeypatch):
    monkeypatch.setenv("GENERATION_COST_MODE", "FREE_AI_ONLY")
    allowed, reason = generation_policy.paid_authorized("gemini", "image")
    assert not allowed
    assert reason == "cost_mode_free_ai_only"


def test_estimate_uses_output_and_reference_megapixels():
    estimate = cloudflare_visual.estimate_neurons(1024, 1280, [(511, 511)] * 4)
    assert estimate["output_mp"] == pytest.approx(1.31072)
    assert estimate["reference_input_mp"] < 1.05
    assert estimate["estimated_neurons"] > cloudflare_visual.FIRST_OUTPUT_MP_NEURONS


def test_budget_refuses_request_before_inference(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FREE_AI_DAILY_NEURON_LIMIT", "1")
    allowed, provenance = cloudflare_visual.reserve_budget(width=1024, height=1280, reference_sizes=[], retry_number=0)
    assert not allowed
    assert provenance["reason"] == "FREE_AI_BUDGET_EXHAUSTED"


def test_cloudflare_uses_multipart_and_decodes_original_response(monkeypatch, tmp_path):
    captured = {}
    output_path = tmp_path / "artifact.png"
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL9aQAAAABJRU5ErkJggg==")

    class Response:
        ok = True
        status_code = 200

        def json(self):
            return {"result": {"image": base64.b64encode(png).decode("ascii")}}

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setattr(cloudflare_visual.requests, "post", fake_post)
    success, reason, metadata = cloudflare_visual.generate(
        prompt="approved creative",
        output_path=str(output_path),
        width=1024,
        height=1280,
        references=[],
    )
    assert success and reason == "ok"
    assert output_path.read_bytes() == png
    assert captured["data"]["prompt"] == "approved creative"
    assert "files" in captured
    assert metadata["paid_api_used"] is False