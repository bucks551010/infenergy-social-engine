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

from company_knowledge import agent_specialization, knowledge_digest, load_company_knowledge, refresh_persistent_company_knowledge
from content_operations import archive_candidate, cancel_unpublished_inventory, create_council_session, ensure_daily_slots, mark_ready, replace_unpublished_slot
from agents.learning_context import load_operational_learning
from inventory_db import get_db_path


DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
ELITE_SLATE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "marketing", "elite_monthly_slate.json"))
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
    custom = thought.get("slides") if isinstance(thought.get("slides"), list) else []
    if len(custom) >= 2:
        return [
            {
                "role": str(slide.get("role") or f"slide_{index}"),
                "headline": str(slide.get("headline") or ""),
                "supporting": str(slide.get("supporting") or ""),
            }
            for index, slide in enumerate(custom[:10], start=1)
            if isinstance(slide, dict)
        ]
    return [
        {"role": "thought", "headline": thought["statement"], "supporting": ""},
        {"role": "meaning", "headline": "Why this matters", "supporting": thought["expansion"]},
        {"role": "application", "headline": "Make it practical", "supporting": _application_for(thought["pillar"])},
        {"role": "community_question", "headline": thought["prompt"], "supporting": "Bring one clear answer into your power plan."},
    ]


def _load_product_brief(data_dir: str, product_id: str) -> dict[str, Any]:
    candidates = (
        os.path.join(data_dir, "product_briefs", f"{product_id}.json"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "product_briefs", f"{product_id}.json")),
    )
    for path in candidates:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            brief = json.load(handle)
        if isinstance(brief, dict) and str(brief.get("product_id") or "") == product_id:
            return brief
    raise ValueError(f"verified product brief not found: {product_id}")


def _gemini_generation_plan(thought: dict[str, Any], product: dict[str, Any] | None = None) -> dict[str, Any]:
    slides = _carousel_slides(thought) if thought.get("format") == "carousel" else [
        {"role": "thought", "headline": thought["statement"], "supporting": thought["expansion"]}
    ]
    visual_execution = str(thought.get("visual_execution") or "editorial_scene")
    image_scene = str(thought.get("image_scene") or thought["visual_motif"]).strip()
    product_instruction = ""
    if product:
        product_instruction = (
            f"The attached reference image is the exact {product['name']}. Reproduce that exact product's shape, proportions, "
            "color, controls, ports, markings, and physical details without redesigning or substituting a generic device. "
            f"Stage it naturally as follows: {product['visual_direction']} "
        )
    prompts: list[dict[str, Any]] = []
    for slide_index, slide in enumerate(slides, start=1):
        overlay_copy = str(
            slide.get("headline")
            if len(slides) > 1
            else thought.get("overlay_text") or thought["statement"]
        ).strip()
        scene_prompt = (
            "Create one premium, photorealistic square editorial image for Infenergy Power about practical energy readiness. "
            f"The image must express this exact post and no generic substitute: {thought['statement']} "
            f"Authored scene: {image_scene} Scene meaning: {slide.get('headline', '')}. "
            f"Visual execution: {visual_execution}. {product_instruction}"
            f"This is slide {slide_index} of {len(slides)} with the role {slide['role']}. "
            "Show a believable real-life environment, natural human stakes, physically credible portable-energy context, "
            "cinematic directional light, rich material detail, and generous protected negative space in the upper third for an editorial overlay. "
            "Use a restrained palette of charcoal, deep navy, warm amber, clean white, and natural environmental colors. "
            "Do not render words, letters, logos, numbers, labels, watermarks, UI, badges, product claims, or fake specifications. "
            "Avoid generic stock-photo smiles, disaster sensationalism, dominant purple, floating devices, visual clutter, and synthetic poster styling. "
            "Output one finished 1:1 image only."
        )
        prompts.append({
            "slide_index": slide_index,
            "slide_count": len(slides),
            "role": slide["role"],
            "gemini_image_prompt": scene_prompt,
            "prompt_sha256": hashlib.sha256(scene_prompt.encode("utf-8")).hexdigest(),
            "v5_direction": {
                "text_overlay": {
                    "enabled": True,
                    "text": f"Infenergy | {overlay_copy}",
                    "placement": "upper third",
                    "safe_margin_ratio": 0.055,
                    "style": "editorial_truth_panel",
                }
            },
        })
    return {
        "provider": "gemini",
        "model_env": "GEMINI_IMAGE_MODEL",
        "generation_timing": "post_time_before_any_platform_publish",
        "strict_provider": True,
        "fallback_allowed": False,
        "reuse_across_platforms": True,
        "required_image_count": len(prompts),
        "prompts": prompts,
    }


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
    useful_detail = str(thought.get("useful_detail") or "").strip()
    action = str(thought.get("action") or _application_for(str(thought["pillar"]))).strip()
    prompt = str(thought["prompt"])
    humor = str(thought.get("humor") or "").strip()
    linkedin_lens = str(thought.get("linkedin_lens") or "").strip()
    instagram_hook = str(thought.get("instagram_hook") or statement).strip()
    tags = thought.get("hashtags") if isinstance(thought.get("hashtags"), list) else []
    facebook_tags = " ".join(f"#{tag}" for tag in (tags[:3] or ["Infenergy", "Preparedness", "PracticalPower"]))
    instagram_tags = " ".join(f"#{tag}" for tag in (tags[:5] or ["Infenergy", "StayReady", "PortablePower"]))
    linkedin_tags = " ".join(f"#{tag}" for tag in (tags[:3] or ["Infenergy", "EnergyReadiness", "Resilience"]))
    facebook_blocks = [statement, expansion, useful_detail, humor, f"Try this: {action}" if action else "", prompt, facebook_tags]
    instagram_blocks = [instagram_hook, expansion, humor, f"Save this move: {action}" if action else "", prompt, instagram_tags]
    linkedin_blocks = [statement, expansion, useful_detail, linkedin_lens, f"Practical next step: {action}" if action else "", prompt, linkedin_tags]
    return {
        "facebook": "\n\n".join(block for block in facebook_blocks if block),
        "instagram": "\n\n".join(block for block in instagram_blocks if block),
        "linkedin": "\n\n".join(block for block in linkedin_blocks if block),
    }


def _public_url(file_name: str) -> str:
    base = str(os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "").strip().rstrip("/")
    if base and not base.startswith("http"):
        base = f"https://{base}"
    return f"{base}/media/{file_name}" if base else ""


def _render_assets(data_dir: str, thought: dict[str, Any], index: int) -> dict[str, Any]:
    folder = os.path.join(data_dir, "public_media")
    stem = f"monthly_{index + 1:02d}_{thought['id'].lower()}"
    if thought.get("format") == "carousel":
        slides = _carousel_slides(thought)
    elif thought.get("visual_execution") == "statement_graphic":
        slides = [{"role": "statement", "headline": thought["overlay_text"], "supporting": ""}]
    else:
        slides = [{"role": "thought", "headline": thought["statement"], "supporting": thought["expansion"]}]
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
    thought_digest = hashlib.sha256(json.dumps(thought, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    content_id = hashlib.sha256(f"{content_date}:{thought['id']}:{digest}:{thought_digest}".encode("utf-8")).hexdigest()[:20]
    product_id = str(thought.get("product_id") or "").strip()
    product = _load_product_brief(data_dir, product_id) if product_id else None
    platform_posts = {
        platform: {
            "platform": platform,
            "final_caption": captions[platform],
            "caption": captions[platform],
            "destination_url": "https://www.infenergypower.com",
            "content_format": (
                "carousel" if thought.get("format") == "carousel" and platform in ("facebook", "instagram")
                else "single_image_product" if product
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
        "content_mode": "product_education" if product else "company_thought",
        "thought_id": thought["id"],
        "thought_kind": thought["kind"],
        "thought_statement": thought["statement"],
        "content_type": str(thought.get("content_type") or "editorial"),
        "event_series": str(thought.get("event_series") or ""),
        "editorial_sources": [str(thought.get("source_note"))] if thought.get("source_note") else [],
        "topic": thought["pillar"],
        "pillar": thought["pillar"],
        "product_id": product_id or None,
        "product_name": str(product.get("name") or "") if product else "",
        "product_image_url": str(product.get("source_image_url") or "") if product else "",
        "product_verified_facts": list(product.get("verified_facts") or []) if product else [],
        "product_proof_rule": str(product.get("proof_rule") or "") if product else "",
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
        "operational_learning": load_operational_learning(data_dir),
        "master_copy": {
            key: thought.get(key)
            for key in ("statement", "expansion", "useful_detail", "action", "prompt", "humor", "linkedin_lens", "editorial_mode", "audience", "source_note", "overlay_text")
            if thought.get(key)
        },
        "fb_caption": captions["facebook"],
        "ig_caption": captions["instagram"],
        "li_text": captions["linkedin"],
        "platform_posts": platform_posts,
        "routing": {"platforms": list(PLATFORMS)},
        "destination_url": "https://www.infenergypower.com",
        "visual_plan": {
            "creative_route": "PREMIUM_PRODUCT_HERO" if product else "BRANDED_COMPANY_THOUGHT",
            "visual_format": "CAROUSEL" if thought.get("format") == "carousel" else "SINGLE_IMAGE",
            "visual_execution": str(thought.get("visual_execution") or "editorial_scene"),
            "visual_motif": thought["visual_motif"],
            "image_scene": str(thought.get("image_scene") or thought["visual_motif"]),
            "copy_visual_alignment": thought["statement"],
            "carousel_slides": _carousel_slides(thought) if thought.get("format") == "carousel" else [],
        },
        "gemini_generation": _gemini_generation_plan(thought, product),
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
        rows = connection.execute("SELECT content_id FROM content_outbox WHERE status != 'CANCELLED'").fetchall()
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


def _load_editorial_slate() -> dict[str, Any]:
    with open(ELITE_SLATE_PATH, "r", encoding="utf-8") as handle:
        slate = json.load(handle)
    posts = slate.get("posts") if isinstance(slate, dict) else None
    if not isinstance(posts, list) or len(posts) != 30:
        raise ValueError("elite monthly slate must contain exactly 30 posts")
    identifiers = [str(post.get("id") or "") for post in posts if isinstance(post, dict)]
    if len(identifiers) != 30 or len(set(identifiers)) != 30:
        raise ValueError("elite monthly slate post identifiers must be complete and unique")
    return slate


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


def prepare_monthly_gemini_prompts(data_dir: str = DATA_DIR) -> dict[str, Any]:
    calendar = latest_monthly_calendar(data_dir)
    entries = calendar.get("entries") if isinstance(calendar.get("entries"), list) else []
    if not entries:
        raise RuntimeError("monthly_content_not_found")
    slate = _load_editorial_slate()
    thoughts = {
        str(thought.get("id") or ""): thought
        for thought in slate["posts"]
        if isinstance(thought, dict)
    }
    connection = sqlite3.connect(get_db_path(data_dir), timeout=30)
    prepared_entries = 0
    prepared_prompts = 0
    prepared_at = datetime.now(timezone.utc).isoformat()
    try:
        connection.execute("BEGIN IMMEDIATE")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            thought = thoughts.get(str(entry.get("thought_id") or ""))
            package = entry.get("package") if isinstance(entry.get("package"), dict) else {}
            outbox_id = str(entry.get("outbox_id") or "")
            if not thought or not package or not outbox_id:
                continue
            product_id = str(thought.get("product_id") or "").strip()
            product = _load_product_brief(data_dir, product_id) if product_id else None
            generation = _gemini_generation_plan(thought, product)
            generation["status"] = "PROMPTS_READY"
            generation["prompts_prepared_at_utc"] = prepared_at
            package["gemini_generation"] = generation
            linkedin = ((package.get("platform_posts") or {}).get("linkedin") or {})
            if isinstance(linkedin, dict):
                linkedin["content_format"] = "single_image_thought"
            changed = connection.execute(
                "UPDATE content_outbox SET package_json=? WHERE outbox_id=? AND status IN ('READY', 'DUE')",
                (json.dumps(package, ensure_ascii=True, separators=(",", ":"), default=str), outbox_id),
            ).rowcount
            if changed != 1:
                continue
            entry["package"] = package
            prepared_entries += 1
            prepared_prompts += int(generation["required_image_count"])
        if prepared_entries != len(entries):
            raise RuntimeError(f"monthly_prompt_preparation_incomplete:{prepared_entries}/{len(entries)}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    calendar["gemini_prompt_status"] = "READY"
    calendar["gemini_prompts_prepared_at_utc"] = prepared_at
    calendar["gemini_prompt_count"] = prepared_prompts
    calendar_path = _save_calendar(data_dir, calendar)
    return {
        "status": "READY",
        "prepared_entries": prepared_entries,
        "prepared_prompts": prepared_prompts,
        "calendar_path": calendar_path,
        "prepared_at_utc": prepared_at,
    }


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
    knowledge_refresh = (
        refresh_persistent_company_knowledge(data_dir)
        if replace_unpublished
        else {"status": "USED_EXISTING", "path": None, "backup_path": None}
    )
    knowledge = load_company_knowledge(data_dir)
    slate = _load_editorial_slate()
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    start = start or (datetime.now(timezone.utc).date() + timedelta(days=1))
    thoughts = list(slate["posts"])
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
                        "content_mode": package["content_mode"],
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
        "campaign_id": slate.get("campaign_id"),
        "editorial_standard": slate.get("editorial_standard"),
        "knowledge_refresh": knowledge_refresh,
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=days - 1)).isoformat(),
        "days": days,
        "queued": queued,
        "skipped_existing": skipped_existing,
        "cancelled_legacy_outbox": cancellation["cancelled_outbox"],
        "single_image_posts": sum(1 for entry in entries if entry["format"] == "single"),
        "carousel_posts": sum(1 for entry in entries if entry["format"] == "carousel"),
        "product_posts": sum(1 for thought in thoughts[:days] if thought.get("content_type") == "product"),
        "statement_graphics": sum(1 for thought in thoughts[:days] if thought.get("visual_execution") == "statement_graphic"),
        "current_event_posts": sum(1 for thought in thoughts[:days] if thought.get("event_series")),
        "entries": entries,
    }
    payload["calendar_path"] = _save_calendar(data_dir, payload)
    return payload


def main() -> None:
    print(json.dumps(build_monthly_calendar(), ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
