from __future__ import annotations

import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import worker
from social.platform_presentation import final_caption_qa


def test_content_preview_forces_text_only_generation(monkeypatch) -> None:
    observed: list[str | None] = []

    def fake_generate(*args, **kwargs):
        observed.append(os.environ.get("POST_TEXT_ONLY"))
        return {"post_id": "preview"}

    monkeypatch.delenv("POST_TEXT_ONLY", raising=False)
    monkeypatch.setattr(worker.generate_posts, "generate", fake_generate)

    preview = worker._content_preview({"slot": "morning", "funnel_stage": "", "product_id": "", "pipeline": "", "platform": ""})

    assert observed == ["true"]
    assert "POST_TEXT_ONLY" not in os.environ
    assert preview["preview_only"] is True


def test_content_preview_can_force_non_product_bucket(monkeypatch) -> None:
    observed: list[tuple[str | None, str | None]] = []

    def fake_generate(*args, **kwargs):
        observed.append((os.environ.get("POST_TEXT_ONLY"), os.environ.get("CONTENT_BUCKET_OVERRIDE")))
        return {"post_id": "preview"}

    monkeypatch.delenv("POST_TEXT_ONLY", raising=False)
    monkeypatch.delenv("CONTENT_BUCKET_OVERRIDE", raising=False)
    monkeypatch.setattr(worker.generate_posts, "generate", fake_generate)

    preview = worker._content_preview(
        {"slot": "morning", "funnel_stage": "", "product_id": "", "pipeline": "", "platform": "", "no_product": True}
    )

    assert observed == [("true", "no_product")]
    assert "POST_TEXT_ONLY" not in os.environ
    assert "CONTENT_BUCKET_OVERRIDE" not in os.environ
    assert preview["preview_only"] is True


def test_plan_caption_requires_actionable_steps() -> None:
    components = {"product_id": "", "product_name": "", "feature_bullets": []}

    missing_steps = final_caption_qa(
        "24-hour outage plan\n\nSave this checklist.",
        platform="instagram",
        components=components,
    )
    complete_plan = final_caption_qa(
        "24-hour outage plan:\n1. List must-run needs.\n2. Stage supplies.\n3. Test the plan.\n\n"
        "Why this matters: it reduces confusion.\n\nSave this checklist.",
        platform="instagram",
        components=components,
    )

    assert "promised_plan_missing_actionable_steps" in missing_steps["reasons"]
    assert "promised_plan_missing_actionable_steps" not in complete_plan["reasons"]