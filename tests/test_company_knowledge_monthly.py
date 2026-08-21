from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from agents import carousel_slide_writer  # noqa: E402
from build_monthly_content import build_monthly_calendar, latest_monthly_calendar  # noqa: E402
from company_knowledge import compact_generation_context, load_company_knowledge  # noqa: E402
from content_operations import daily_status  # noqa: E402


def _seed_knowledge(data_dir: Path) -> None:
    marketing = data_dir / "marketing"
    marketing.mkdir(parents=True)
    shutil.copyfile(ROOT / "data" / "marketing" / "infenergy_company_knowledge.json", marketing / "infenergy_company_knowledge.json")


def test_company_knowledge_has_complete_generation_contract():
    knowledge = load_company_knowledge(str(ROOT / "data"))
    context = compact_generation_context(knowledge)

    assert knowledge["brand"]["mission"]
    assert knowledge["brand"]["vision"]
    assert knowledge["consumer_benefits"]["lifestyle_transformations"]
    assert len(knowledge["thought_library"]) >= 30
    assert len(knowledge["agent_specializations"]) >= 13
    assert context["central_human_truth"]
    assert context["product_truth_policy"]["never_claim"]


def test_thought_carousel_advances_one_idea_across_four_slides(tmp_path):
    payload = carousel_slide_writer.run(
        str(tmp_path),
        thought={
            "statement": "Preparedness over panic.",
            "expansion": "A clear plan creates room to think.",
            "prompt": "What will you protect first?",
        },
    )

    assert payload["content_mode"] == "company_thought"
    assert [slide["slide_role"] for slide in payload["slides"]] == [
        "thought",
        "meaning",
        "practical_application",
        "community_question",
    ]


def test_month_builder_persists_ready_assets_and_is_idempotent(tmp_path, monkeypatch):
    _seed_knowledge(tmp_path)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")

    first = build_monthly_calendar(
        data_dir=str(tmp_path),
        start_date="2026-09-01",
        days=2,
        enqueue=True,
    )

    assert first["status"] == "READY"
    assert first["queued"] == 2
    assert first["single_image_posts"] == 1
    assert first["carousel_posts"] == 1
    assert os.path.exists(first["calendar_path"])
    assert daily_status(str(tmp_path), "2026-09-01")["ready"] == 1
    assert daily_status(str(tmp_path), "2026-09-02")["ready"] == 1

    single = first["entries"][0]["package"]
    carousel = first["entries"][1]["package"]
    assert os.path.exists(single["generated_visuals"]["linkedin"])
    assert single["primary_publish_image_url"].startswith("https://example.test/media/")
    assert len(carousel["carousel_assets"]) == 4
    assert all(os.path.exists(asset["local_path"]) for asset in carousel["carousel_assets"])
    assert carousel["platform_posts"]["linkedin"]["final_caption_qa"]["status"] == "PRESENTATION_READY"

    second = build_monthly_calendar(
        data_dir=str(tmp_path),
        start_date="2026-09-01",
        days=2,
        enqueue=True,
    )
    assert second["queued"] == 0
    assert second["skipped_existing"] == 2

    saved = json.loads(Path(first["calendar_path"]).read_text(encoding="utf-8"))
    assert saved["knowledge_digest"] == first["knowledge_digest"]
    assert len(saved["entries"]) == 2
    assert latest_monthly_calendar(str(tmp_path))["entries"][1]["thought_id"] == "T02"


def test_month_builder_replaces_an_unpublished_slot_package(tmp_path, monkeypatch):
    _seed_knowledge(tmp_path)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    first = build_monthly_calendar(data_dir=str(tmp_path), start_date="2026-10-01", days=1, enqueue=True)

    knowledge_path = tmp_path / "marketing" / "infenergy_company_knowledge.json"
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    knowledge["schema_version"] = "1.0.1"
    knowledge_path.write_text(json.dumps(knowledge), encoding="utf-8")
    replacement = build_monthly_calendar(data_dir=str(tmp_path), start_date="2026-10-01", days=1, enqueue=True)

    assert first["entries"][0]["content_id"] != replacement["entries"][0]["content_id"]
    assert replacement["queued"] == 1
    assert daily_status(str(tmp_path), "2026-10-01")["ready"] == 1
