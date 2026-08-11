"""Regression tests for the audit fix: Gemini caption generation must retry and log
failures instead of silently swallowing them, and the deterministic fallback content
builders must honor the Conversion Logic Engine's strategic_brief (problem/objection/
transformation) instead of reverting to a brief-blind legacy template.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import generate_posts  # noqa: E402


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FlakyModels:
    """Fails the first `fail_times` calls, then returns valid JSON."""

    def __init__(self, fail_times: int, success_payload: dict) -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.success_payload = success_payload

    def generate_content(self, model, contents, config):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"transient error #{self.calls}")
        return _FakeResponse(json.dumps(self.success_payload))


class _AlwaysFailModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        raise RuntimeError("permanent outage")


class _FakeClient:
    def __init__(self, models) -> None:
        self.models = models


def test_generate_json_with_gemini_retries_within_same_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    flaky = _FlakyModels(fail_times=1, success_payload={"fb_caption": "hello"})
    monkeypatch.setattr(generate_posts.genai, "Client", lambda api_key: _FakeClient(flaky))

    result = generate_posts._generate_json_with_gemini("prompt", ["model-a", "model-b"])

    assert result == {"fb_caption": "hello"}
    # Succeeded on the 2nd attempt of the first model; never needed model-b.
    assert flaky.calls == 2


def test_generate_json_with_gemini_returns_none_and_logs_after_exhausting_all_attempts(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    always_fail = _AlwaysFailModels()
    monkeypatch.setattr(generate_posts.genai, "Client", lambda api_key: _FakeClient(always_fail))

    result = generate_posts._generate_json_with_gemini("prompt", ["model-a", "model-b"], attempts_per_model=2)

    assert result is None
    # 2 models x 2 attempts each = 4 calls total; never silently gives up early.
    assert always_fail.calls == 4
    captured = capsys.readouterr()
    assert "[Gemini]" in captured.out
    assert "model-b" in captured.out  # last error should name the final model that failed


def test_generate_json_with_gemini_returns_none_when_no_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = generate_posts._generate_json_with_gemini("prompt", ["model-a"])
    assert result is None


def _persuasion_brief(**overrides) -> dict:
    persuasion = {
        "problem": "Homeowners assume backup power just works until an outage proves otherwise.",
        "objection": "I already have a generator, why do I need this?",
        "transformation_from": "hoping their setup works",
        "transformation_to": "knowing exactly how long their critical devices stay powered",
        "proof": "verified runtime specs",
    }
    persuasion.update(overrides)
    return {"persuasion": persuasion}


def test_fallback_content_uses_strategic_brief_problem_and_transformation():
    product = {"name": "PowerFlex 500", "sku": "PF-500", "metrics": ["500W", "2h recharge"]}
    brief = _persuasion_brief()

    content = generate_posts._build_fallback_content(
        "morning", "Outage readiness", product, {}, talking_point={}, strategic_brief=brief
    )

    assert "Homeowners assume backup power just works" in content["fb_caption"]
    assert "hoping their setup works" in content["fb_caption"]
    assert "knowing exactly how long their critical devices stay powered" in content["fb_caption"]
    assert "already have a generator" in content["fb_caption"]
    # No blank-line artifacts left behind when segments are present.
    assert "\n\n\n" not in content["fb_caption"]
    assert "hoping their setup works" in content["li_text"]


def test_fallback_content_no_product_uses_strategic_brief():
    brief = _persuasion_brief()

    content = generate_posts._build_fallback_content_no_product(
        "morning", "Why backup power planning matters", "preparedness_education", {}, talking_point={}, strategic_brief=brief
    )

    assert "Homeowners assume backup power just works" in content["fb_caption"]
    assert "hoping their setup works" in content["fb_caption"]
    assert "\n\n\n" not in content["fb_caption"]


def test_fallback_content_still_works_without_strategic_brief():
    # Backward compatibility: no brief available should not raise or leave blank artifacts.
    product = {"name": "PowerFlex 500", "sku": "PF-500", "metrics": ["500W", "2h recharge"]}
    content = generate_posts._build_fallback_content("morning", "Outage readiness", product, {}, talking_point={})
    assert content["fb_caption"].strip()
    assert "\n\n\n" not in content["fb_caption"]

    content_no_product = generate_posts._build_fallback_content_no_product(
        "morning", "Why planning matters", "preparedness_education", {}, talking_point={}
    )
    assert content_no_product["fb_caption"].strip()
    assert "\n\n\n" not in content_no_product["fb_caption"]


def test_scenario_fingerprint_differs_for_same_category_products():
    # Regression: components["situation"] (category_pain) only has a handful of fixed
    # values across the whole catalog, so two different solar-panel products used to
    # collide on scenario_signature and trip a false-positive duplicate-scenario skip.
    same_category_components = {"situation": "Many buyers assume any solar panel will recharge their gear the way they need."}

    fingerprint_a = generate_posts._build_scenario_fingerprint(
        {"angle": "Comparing wattage before buying", "pain_point": "Buyers guess at solar output instead of checking it."},
        same_category_components,
    )
    fingerprint_b = generate_posts._build_scenario_fingerprint(
        {"angle": "Why panel compatibility matters more than price", "pain_point": "Cheap panels fail to match the power station they're paired with."},
        same_category_components,
    )

    assert fingerprint_a != fingerprint_b


def test_scenario_fingerprint_falls_back_to_situation_when_talking_point_empty():
    components = {"situation": "Fallback situation text."}
    assert generate_posts._build_scenario_fingerprint({}, components) == "Fallback situation text."
    assert generate_posts._build_scenario_fingerprint(None, components) == "Fallback situation text."

