"""Tier-1 #5: carousel_slide_writer_agent.

Given a formal-logic principle_key, an archetype_key, and a product, returns a
platform-safe caller-selected number of slides with on-image copy and roles.

Uses Gemini when GEMINI_API_KEY is set; deterministic template fallback otherwise.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ._base import utc_now, write_snapshot


SLIDE_ROLES = (
    "hook",
    "problem",
    "logical_contrast",
    "mechanism",
    "product_and_verified_proof",
    "real_world_application",
    "objection_answer",
    "emotional_result",
    "summary",
    "single_next_step",
)
PLATFORM_LIMITS = {
    "facebook": 10,
    "facebook_feed": 10,
    "instagram": 10,
    "instagram_feed": 10,
    "linkedin": 10,
    "linkedin_feed": 10,
    "instagram_story": 1,
}


def _thought_slides(thought: dict[str, Any]) -> list[dict]:
    statement = str(thought.get("statement") or "Preparedness over panic.").strip()
    expansion = str(thought.get("expansion") or "Make one clear decision before the urgent moment.").strip()
    prompt = str(thought.get("prompt") or "What will you prepare first?").strip()
    return [
        {"slide_role": "thought", "on_image_headline": statement, "on_image_subline": ""},
        {"slide_role": "meaning", "on_image_headline": "Why this matters", "on_image_subline": expansion},
        {"slide_role": "practical_application", "on_image_headline": "Make it practical", "on_image_subline": "Choose one useful action and make it repeatable."},
        {"slide_role": "community_question", "on_image_headline": prompt, "on_image_subline": "Bring one clear answer into your power plan."},
    ]


def _short_text(value: str, word_limit: int) -> str:
    words = str(value or "").strip().split()
    return " ".join(words[:word_limit]).strip(" ,.;:-")


def _fallback(
    principle_key: str,
    archetype_key: str,
    product: dict,
    slide_count: int,
    creative_brief: str = "",
) -> list[dict]:
    name = str((product or {}).get("name", "") or "your backup power kit").strip()
    metrics = [str(m).strip() for m in (product or {}).get("metrics", []) if str(m).strip()]
    primary_metric = metrics[0] if metrics else "verified specs"
    hook_map = {
        "contrapositive": ("If you can't run it, you didn't back it up", "Backup is the load, not the label"),
        "disjunctive_syllogism": ("Two paths. One works", f"{name} takes the outage path off the table"),
        "double_implication": ("Real backup means real runtime", f"{primary_metric} that's proven, not promised"),
        "symmetrical_equivalence": ("Prepared equals powered", f"{name} keeps you both"),
        "implication_of_result": ("Plug it in tonight. Sleep tomorrow", f"{name} shifts the whole plan"),
    }
    headline, subline = hook_map.get(principle_key, (f"{name}: prepared, not panicked", primary_metric))
    if creative_brief:
        headline = _short_text(creative_brief, 8)
        subline = "Keep swiping for the complete idea"
    templates = {
        "hook": (headline, subline),
        "problem": ("The outage is not the surprise", "An untested plan is"),
        "logical_contrast": ("Cheap watts ≠ real backup", "Match must-run devices to actual output"),
        "mechanism": ("Start with the load", "Then match output, runtime, and recharge"),
        "product_and_verified_proof": (name, primary_metric),
        "real_world_application": ("Build around real routines", "Lights, phones, work, and the next recharge"),
        "objection_answer": ("More capacity is not always better", "The right fit is easier to use"),
        "emotional_result": ("Lights stay on. Phones stay charged", "The plan works when you cannot improvise"),
        "summary": ("Load. Runtime. Recharge", "Three checks before backup becomes a plan"),
        "single_next_step": (f"Get {name}", "One clear next step. Backup handled"),
    }
    if creative_brief:
        brief_headline = _short_text(creative_brief, 8)
        brief_subline = _short_text(creative_brief, 14)
        templates.update({
            "hook": (brief_headline, "The complete idea starts here"),
            "problem": ("What is really at stake", brief_subline),
            "logical_contrast": ("The assumption versus reality", brief_subline),
            "mechanism": ("Follow the turning point", brief_subline),
            "product_and_verified_proof": ("The proof inside the story", brief_subline),
            "real_world_application": ("Bring the idea into real life", brief_subline),
            "objection_answer": ("Answer the doubt directly", brief_subline),
            "emotional_result": ("This is what changes", brief_subline),
            "summary": ("The idea in one frame", brief_headline),
            "single_next_step": ("Carry the idea forward", brief_headline),
        })
    selected_roles = list(SLIDE_ROLES[:slide_count])
    if slide_count > 1:
        selected_roles[-1] = "single_next_step"
    slides = [
        {
            "slide_role": role,
            "on_image_headline": templates[role][0],
            "on_image_subline": templates[role][1],
        }
        for role in selected_roles
    ]
    return slides


def _gemini_slides(
    principle_key: str,
    archetype_key: str,
    product: dict,
    slide_count: int,
    creative_brief: str = "",
) -> list[dict] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        prompt = (
            f"Return JSON with a top-level 'slides' array of exactly {slide_count} objects. Each object must have "
            f"keys slide_role (use these in this narrative order: {', '.join(SLIDE_ROLES)}), "
            "on_image_headline (<=8 words), on_image_subline "
            "(<=14 words). Use formal-logic principle "
            f"'{principle_key}' and audience archetype '{archetype_key}'. Product: "
            f"{json.dumps({'name': product.get('name', ''), 'metrics': product.get('metrics', [])[:3]})}. "
            f"The owner's exact creative brief is: {json.dumps(creative_brief)}. Every slide must advance that brief; "
            "do not substitute a generic product or preparedness story. "
            "No emojis. No hashtags. Use the product name on no more than two slides."
        )
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = (resp.text or "").strip()
        if not text:
            return None
        data = json.loads(text)
        slides = data.get("slides") if isinstance(data, dict) else None
        if not isinstance(slides, list) or len(slides) != slide_count:
            return None
        cleaned: list[dict] = []
        for role, item in zip(SLIDE_ROLES[:slide_count], slides):
            if not isinstance(item, dict):
                return None
            cleaned.append(
                {
                    "slide_role": str(item.get("slide_role") or role).strip() or role,
                    "on_image_headline": str(item.get("on_image_headline", "")).strip(),
                    "on_image_subline": str(item.get("on_image_subline", "")).strip(),
                }
            )
        return cleaned
    except Exception:
        return None


def run(
    data_dir: str,
    principle_key: str = "",
    archetype_key: str = "",
    product: dict | None = None,
    thought: dict | None = None,
    creative_brief: str = "",
    platform: str = "instagram_feed",
    slide_count: int | None = None,
) -> dict:
    product = product or {}
    platform_key = str(platform or "instagram_feed").strip().lower()
    platform_limit = PLATFORM_LIMITS.get(platform_key, 10)
    requested_count = int(slide_count if slide_count is not None else (4 if thought else 5))
    if platform_limit < 2:
        raise ValueError(f"carousel_not_supported_on_{platform_key}")
    if requested_count < 2 or requested_count > platform_limit:
        raise ValueError(f"slide_count_must_be_between_2_and_{platform_limit}_for_{platform_key}")
    slides = _thought_slides(thought) if thought and requested_count == 4 else (
        _gemini_slides(principle_key, archetype_key, product, requested_count, creative_brief)
        or _fallback(principle_key, archetype_key, product, requested_count, creative_brief)
    )
    payload = {
        "agent": "carousel_slide_writer",
        "time_utc": utc_now(),
        "principle_key": principle_key,
        "archetype_key": archetype_key,
        "product_name": str(product.get("name", "")),
        "content_mode": "company_thought" if thought else "product",
        "creative_brief": creative_brief,
        "platform": platform_key,
        "slide_count": len(slides),
        "platform_limit": platform_limit,
        "slides": slides,
    }
    write_snapshot(data_dir, "carousel_slide_writer", payload)
    return payload
