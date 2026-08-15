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
        authorization={"status": "PASS", "flux_authorized": True, "selected_candidate": "candidate-1"},
        candidate_id="candidate-1",
    )
    assert success and reason == "ok"
    assert output_path.read_bytes() == png
    assert captured["data"]["prompt"] == "approved creative"
    assert "files" in captured
    assert metadata["paid_api_used"] is False


def test_failed_previsual_gate_never_reserves_or_calls_provider(monkeypatch, tmp_path):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Cloudflare must not be called without authorization")

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setattr(cloudflare_visual.requests, "post", fake_post)
    success, reason, metadata = cloudflare_visual.generate(
        prompt="blocked research claim",
        output_path=str(tmp_path / "artifact.png"),
        width=1024,
        height=1280,
        references=[],
        authorization={"status": "FAIL", "flux_authorized": False, "selected_candidate": "candidate-a", "reasons": ["RESEARCH_REQUIRED"]},
        candidate_id="candidate-a",
    )
    assert not success
    assert reason == "VISUAL_NOT_AUTHORIZED_PREVISUAL_GATE"
    assert metadata["visual_generation_attempted"] is False
    assert calls == []
    assert cloudflare_visual._load_ledger() == {}


def test_reservation_is_not_counted_as_request_until_http_starts(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    allowed, reservation = cloudflare_visual.reserve_budget(
        width=1024,
        height=1280,
        reference_sizes=[],
        retry_number=0,
    )
    assert allowed
    daily = cloudflare_visual._load_ledger()[cloudflare_visual._utc_day()]
    assert daily["requests"] == 0
    assert daily["estimated_neurons"] == 0
    assert daily["reserved_neurons"] == reservation["estimated_neurons"]
    cloudflare_visual._update_reservation(reservation["reservation_id"], started=True)
    daily = cloudflare_visual._load_ledger()[cloudflare_visual._utc_day()]
    assert daily["requests"] == 1
    assert daily["estimated_neurons"] == reservation["estimated_neurons"]
    assert daily["reserved_neurons"] == 0