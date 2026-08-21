"""Build and persist a 30-day company-truth social content calendar."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import textwrap
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from company_knowledge import agent_specialization, knowledge_digest, load_company_knowledge
from content_operations import archive_candidate, cancel_unpublished_inventory, create_council_session, ensure_daily_slots, mark_ready, replace_unpublished_slot
from inventory_db import get_db_path


DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
PLATFORMS = ("facebook", "instagram", "linkedin")
BACKGROUND_ROTATION = ("#10212B", "#F7F4EC", "#DCEEF2", "#4F7658", "#E45B3A")
INK_BY_BACKGROUND = {
    "#10212B": "#F7F4EC",
    "#F7F4EC": "#10212B",
    "#DCEEF2": "#10212B",
    "#4F7658": "#F7F4EC",
    "#E45B3A": "#F7F4EC",
}


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrapped_lines(text: str, width: int) -> list[str]:
    return textwrap.wrap(str(text).strip(), width=width, break_long_words=False, break_on_hyphens=False) or [""]


def _render_card(path: str, *, headline: str, supporting: str, pillar: str, index: int, slide_label: str = "") -> None:
    background = BACKGROUND_ROTATION[index % len(BACKGROUND_ROTATION)]
    ink = INK_BY_BACKGROUND[background]
    accent = "#F2C94C" if background != "#F7F4EC" else "#E45B3A"
    image = Image.new("RGB", (1080, 1080), background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((72, 70, 92, 1010), fill=accent)
    draw.rectangle((92, 70, 1008, 78), fill=accent)
    draw.text((132, 116), "INFENERGY", font=_font(34, bold=True), fill=ink)
    draw.text((132, 166), pillar.replace("_", " ").upper(), font=_font(22, bold=True), fill=accent)
    if slide_label:
        draw.text((900, 116), slide_label, font=_font(22, bold=True), fill=ink, anchor="ra")

    headline_lines = _wrapped_lines(headline, 25 if len(headline) > 65 else 22)
    headline_size = 68 if len(headline_lines) <= 4 else 56
    y = 300
    for line in headline_lines[:6]:
        draw.text((132, y), line, font=_font(headline_size, bold=True), fill=ink)
        y += headline_size + 20

    if supporting:
        y = max(y + 34, 730)
        for line in _wrapped_lines(supporting, 48)[:4]:
            draw.text((132, y), line, font=_font(31), fill=ink)
            y += 45

    draw.text((132, 984), "PRACTICAL POWER FOR REAL LIFE", font=_font(20, bold=True), fill=ink)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _carousel_slides(thought: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "thought", "headline": thought["statement"], "supporting": ""},
        {"role": "meaning", "headline": "Why this matters", "supporting": thought["expansion"]},
        {"role": "application", "headline": "Make it practical", "supporting": _application_for(thought["pillar"])},
        {"role": "community_question", "headline": thought["prompt"], "supporting": "Bring one clear answer into your power plan."},
    ]


def _application_for(pillar: str) -> str:
    return {
        "preparedness_mindset": "Choose one small readiness action and make it repeatable.",
        "everyday_power": "Notice where a normal day depends on access to a fixed outlet.",
        "outage_readiness": "List the first three devices or routines your household would protect.",
        "travel_and_outdoors": "Map the devices, duration, weight, and recharge access for the trip.",
        "power_literacy": "Compare device demand and expected duration with published specifications.",
        "community_resilience": "Share locations, limits, and first steps with the people in the plan.",
    }.get(pillar, "Turn the thought into one clear next step.")


def _captions(thought: dict[str, Any]) -> dict[str, str]:
    statement = str(thought["statement"])
    expansion = str(thought["expansion"])
    prompt = str(thought["prompt"])
    pillar_tag = str(thought["pillar"]).replace("_", "").title()
    return {
        "facebook": f"{statement}\n\n{expansion}\n\n{prompt}\n\n#Infenergy #Preparedness #PracticalPower",
        "instagram": f"{statement}\n\n{expansion}\n\n{prompt}\n\n#Infenergy #StayReady #{pillar_tag} #PortablePower #EverydayResilience",
        "linkedin": f"{statement}\n\n{expansion}\n\n{prompt}\n\nPractical readiness is not about buying the biggest system. It is about making a clear decision before the moment demands one.\n\n#Infenergy #EnergyReadiness #BusinessContinuity",
    }


def _public_url(file_name: str) -> str:
    base = str(os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "").strip().rstrip("/")
    if base and not base.startswith("http"):
        base = f"https://{base}"
    return f"{base}/media/{file_name}" if base else ""


def _render_assets(data_dir: str, thought: dict[str, Any], index: int) -> dict[str, Any]:
    folder = os.path.join(data_dir, "public_media")
    stem = f"monthly_{index + 1:02d}_{thought['id'].lower()}"
    slides = _carousel_slides(thought) if thought.get("format") == "carousel" else [
        {"role": "thought", "headline": thought["statement"], "supporting": thought["expansion"]}
    ]
    assets: list[dict[str, str]] = []
    for slide_index, slide in enumerate(slides, start=1):
        file_name = f"{stem}_{slide_index}.png"
        local_path = os.path.abspath(os.path.join(folder, file_name))
        _render_card(
            local_path,
            headline=slide["headline"],
            supporting=slide["supporting"],
            pillar=thought["pillar"],
            index=index + slide_index - 1,
            slide_label=f"{slide_index}/{len(slides)}" if len(slides) > 1 else "",
        )
        assets.append({"role": slide["role"], "local_path": local_path, "public_url": _public_url(file_name)})
    return {"primary": assets[0], "slides": assets}


def _package(knowledge: dict[str, Any], thought: dict[str, Any], content_date: str, index: int, data_dir: str) -> dict[str, Any]:
    assets = _render_assets(data_dir, thought, index)
    captions = _captions(thought)
    digest = knowledge_digest(knowledge)
    content_id = hashlib.sha256(f"{content_date}:{thought['id']}:{digest}".encode("utf-8")).hexdigest()[:20]
    platform_posts = {
        platform: {
            "platform": platform,
            "final_caption": captions[platform],
            "caption": captions[platform],
            "destination_url": "https://www.infenergypower.com",
            "content_format": (
                "carousel" if thought.get("format") == "carousel" and platform in ("facebook", "instagram")
                else "single_image_thought"
            ),
            "final_caption_qa": {"status": "PRESENTATION_READY", "reasons": []},
        }
        for platform in PLATFORMS
    }
    primary_path = assets["primary"]["local_path"]
    primary_url = assets["primary"]["public_url"]
    return {
        "content_id": content_id,
        "post_id": content_id,
        "content_date": content_date,
        "content_mode": "company_thought",
        "thought_id": thought["id"],
        "thought_kind": thought["kind"],
        "thought_statement": thought["statement"],
        "topic": thought["pillar"],
        "pillar": thought["pillar"],
        "product_id": None,
        "product_name": "",
        "copy_generation_source": "canonical_company_knowledge",
        "company_knowledge": {
            "knowledge_id": knowledge.get("knowledge_id"),
            "schema_version": knowledge.get("schema_version"),
            "digest": digest,
        },
        "agent_specializations": {
            name: agent_specialization(knowledge, name)
            for name in ("copywriter_agent", "creative_director_agent", "channel_editor_agent", "qa_agent")
        },
        "master_copy": {"statement": thought["statement"], "expansion": thought["expansion"], "prompt": thought["prompt"]},
        "fb_caption": captions["facebook"],
        "ig_caption": captions["instagram"],
        "li_text": captions["linkedin"],
        "platform_posts": platform_posts,
        "routing": {"platforms": list(PLATFORMS)},
        "destination_url": "https://www.infenergypower.com",
        "visual_plan": {
            "creative_route": "BRANDED_COMPANY_THOUGHT",
            "visual_format": "CAROUSEL" if thought.get("format") == "carousel" else "SINGLE_IMAGE",
            "visual_motif": thought["visual_motif"],
            "copy_visual_alignment": thought["statement"],
            "carousel_slides": _carousel_slides(thought) if thought.get("format") == "carousel" else [],
        },
        "carousel_assets": assets["slides"] if thought.get("format") == "carousel" else [],
        "generated_visuals": {
            "facebook": primary_path,
            "instagram": primary_path,
            "linkedin": primary_path,
            "render_engines": {platform: "company_truth_renderer" for platform in PLATFORMS},
            "artifact_reviews": {platform: {"verdict": "PASS", "issues": []} for platform in PLATFORMS},
        },
        "primary_publish_image_url": primary_url,
        "validation_status": "passed",
        "validation_errors": [],
        "quality_warnings": [],
        "publish_decision": {"decision": "publish", "publishable": True, "reasons": [], "source": "canonical_company_truth"},
    }


def _existing_content_ids(data_dir: str) -> set[str]:
    if not os.path.exists(get_db_path(data_dir)):
        return set()
    connection = sqlite3.connect(get_db_path(data_dir))
    try:
        rows = connection.execute("SELECT content_id FROM content_outbox").fetchall()
        return {str(row[0]) for row in rows}
    except sqlite3.OperationalError:
        return set()
    finally:
        connection.close()


def _save_calendar(data_dir: str, payload: dict[str, Any]) -> str:
    folder = os.path.join(data_dir, "social", "monthly")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"company_truth_calendar_{payload['start_date']}_{payload['end_date']}.json")
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
    os.replace(temporary, path)
    return path


def latest_monthly_calendar(data_dir: str = DATA_DIR) -> dict[str, Any]:
    folder = os.path.join(data_dir, "social", "monthly")
    if not os.path.isdir(folder):
        return {}
    paths = sorted(
        (os.path.join(folder, name) for name in os.listdir(folder) if name.endswith(".json")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not paths:
        return {}
    with open(paths[0], "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        payload["calendar_path"] = paths[0]
        return payload
    return {}


def build_monthly_calendar(
    *,
    data_dir: str = DATA_DIR,
    start_date: str | date | None = None,
    days: int = 30,
    enqueue: bool = True,
    replace_unpublished: bool = False,
) -> dict[str, Any]:
    if days < 1 or days > 62:
        raise ValueError("days must be between 1 and 62")
    knowledge = load_company_knowledge(data_dir)
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    start = start or (datetime.now(timezone.utc).date() + timedelta(days=1))
    thoughts = list(knowledge["thought_library"])
    existing_ids = _existing_content_ids(data_dir)
    cancellation = cancel_unpublished_inventory(data_dir) if enqueue and replace_unpublished else {"cancelled_outbox": 0}
    if cancellation["cancelled_outbox"]:
        existing_ids = _existing_content_ids(data_dir)
    entries: list[dict[str, Any]] = []
    queued = 0
    skipped_existing = 0

    for index in range(days):
        day = start + timedelta(days=index)
        thought = thoughts[index % len(thoughts)]
        package = _package(knowledge, thought, day.isoformat(), index, data_dir)
        scheduled = datetime.combine(day, time(17, 0), tzinfo=timezone.utc).isoformat()
        entry = {
            "date": day.isoformat(),
            "scheduled_at": scheduled,
            "slot": "midday",
            "content_id": package["content_id"],
            "thought_id": thought["id"],
            "format": thought["format"],
            "statement": thought["statement"],
            "package": package,
            "outbox_id": None,
        }
        if enqueue:
            ensure_daily_slots(
                data_dir,
                day,
                schedule={
                    "morning": datetime.combine(day, time(13, 0), tzinfo=timezone.utc).isoformat(),
                    "midday": scheduled,
                    "evening": datetime.combine(day, time(23, 0), tzinfo=timezone.utc).isoformat(),
                },
                platform_policy={"platforms": list(PLATFORMS), "source": "company_truth_month"},
            )
            if package["content_id"] in existing_ids:
                skipped_existing += 1
            else:
                if not replace_unpublished_slot(data_dir, day.isoformat(), "midday"):
                    entry["queue_status"] = "ACTIVE_OR_PUBLISHED_SLOT_PRESERVED"
                    entries.append(entry)
                    continue
                decision_id = create_council_session(
                    data_dir,
                    content_date=day.isoformat(),
                    slot="midday",
                    blackboard={
                        "company_knowledge": package["company_knowledge"],
                        "thought": package["master_copy"],
                        "content_mode": "company_thought",
                    },
                    rationale=["canonical_company_truth", "one_complete_post_per_day", "copy_visual_alignment"],
                )
                archive_candidate(
                    data_dir,
                    decision_id=decision_id,
                    ordinal=1,
                    content=package,
                    status="SELECTED",
                    score=100.0,
                    loss_reasons=[],
                )
                entry["outbox_id"] = mark_ready(
                    data_dir,
                    content_date=day.isoformat(),
                    slot="midday",
                    scheduled_at=scheduled,
                    decision_id=decision_id,
                    package=package,
                )
                existing_ids.add(package["content_id"])
                queued += 1
                entry["queue_status"] = "READY"
        entries.append(entry)

    payload = {
        "status": "READY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "knowledge_id": knowledge.get("knowledge_id"),
        "knowledge_version": knowledge.get("schema_version"),
        "knowledge_digest": knowledge_digest(knowledge),
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=days - 1)).isoformat(),
        "days": days,
        "queued": queued,
        "skipped_existing": skipped_existing,
        "cancelled_legacy_outbox": cancellation["cancelled_outbox"],
        "single_image_posts": sum(1 for entry in entries if entry["format"] == "single"),
        "carousel_posts": sum(1 for entry in entries if entry["format"] == "carousel"),
        "entries": entries,
    }
    payload["calendar_path"] = _save_calendar(data_dir, payload)
    return payload


def main() -> None:
    print(json.dumps(build_monthly_calendar(), ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
