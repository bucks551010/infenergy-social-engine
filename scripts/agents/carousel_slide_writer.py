"""Tier-1 #5: carousel_slide_writer_agent.

Given a formal-logic principle_key, an archetype_key, and a product, returns 5
slides each with on_image_headline, on_image_subline, slide_role.

Uses Gemini when GEMINI_API_KEY is set; deterministic template fallback otherwise.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ._base import utc_now, write_snapshot


SLIDE_ROLES = ("hook", "logical_contrast", "product_and_verified_proof", "emotional_result", "single_next_step")


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


def _fallback(principle_key: str, archetype_key: str, product: dict) -> list[dict]:
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
    slides = [
        {"slide_role": "hook", "on_image_headline": headline, "on_image_subline": subline},
        {
            "slide_role": "logical_contrast",
            "on_image_headline": "Cheap watts ≠ real backup",
            "on_image_subline": "Match your must-run devices to actual output",
        },
        {
            "slide_role": "product_and_verified_proof",
            "on_image_headline": name,
            "on_image_subline": primary_metric,
        },
        {
            "slide_role": "emotional_result",
            "on_image_headline": "Lights stay on. Phones stay charged",
            "on_image_subline": "The plan does the work when you can't",
        },
        {
            "slide_role": "single_next_step",
            "on_image_headline": f"Get {name}",
            "on_image_subline": "One step. Backup handled",
        },
    ]
    return slides


def _gemini_slides(principle_key: str, archetype_key: str, product: dict) -> list[dict] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        prompt = (
            "Return JSON with a top-level 'slides' array of exactly 5 objects. Each object must have "
            "keys slide_role (from: hook, logical_contrast, product_and_verified_proof, "
            "emotional_result, single_next_step), on_image_headline (<=8 words), on_image_subline "
            "(<=14 words). Use formal-logic principle "
            f"'{principle_key}' and audience archetype '{archetype_key}'. Product: "
            f"{json.dumps({'name': product.get('name', ''), 'metrics': product.get('metrics', [])[:3]})}. "
            "No emojis. No hashtags. No product-name repetition across slides beyond slide 3 and slide 5."
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
        if not isinstance(slides, list) or len(slides) != 5:
            return None
        cleaned: list[dict] = []
        for role, item in zip(SLIDE_ROLES, slides):
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
) -> dict:
    product = product or {}
    slides = _thought_slides(thought) if thought else (
        _gemini_slides(principle_key, archetype_key, product) or _fallback(principle_key, archetype_key, product)
    )
    payload = {
        "agent": "carousel_slide_writer",
        "time_utc": utc_now(),
        "principle_key": principle_key,
        "archetype_key": archetype_key,
        "product_name": str(product.get("name", "")),
        "content_mode": "company_thought" if thought else "product",
        "slides": slides,
    }
    write_snapshot(data_dir, "carousel_slide_writer", payload)
    return payload
