"""Tier-2 #10: alt_text_accessibility_agent.

Generates per-platform alt text for a scene plate + product overlay. Uses
Gemini when available with strict length caps, deterministic template
otherwise.
"""

from __future__ import annotations

import os

from ._base import utc_now, write_snapshot


def _fallback(platform: str, product_name: str, scene_prompt: str) -> str:
    scene = str(scene_prompt or "").strip().split(".")[0].strip()
    if not scene:
        scene = "practical backup-power scene"
    name = str(product_name or "").strip() or "a portable backup power product"
    base = f"{scene}. {name} shown in a real preparedness context on {platform}."
    return base[:280]


def _gemini_alt(platform: str, product_name: str, scene_prompt: str) -> str | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        prompt = (
            f"Write a single alt-text sentence (max 220 characters) for a {platform} social image "
            f"showing the scene: {scene_prompt}. The product overlaid is: {product_name}. "
            "The sentence must be plain descriptive text, no marketing language, no emojis, no hashtags."
        )
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="text/plain"),
        )
        text = (resp.text or "").strip().replace("\n", " ")
        if 20 <= len(text) <= 280:
            return text
    except Exception:
        return None
    return None


def run(
    data_dir: str,
    platform: str = "facebook",
    product_name: str = "",
    scene_prompt: str = "",
) -> dict:
    alt = _gemini_alt(platform, product_name, scene_prompt) or _fallback(platform, product_name, scene_prompt)
    payload = {
        "agent": "alt_text_accessibility",
        "time_utc": utc_now(),
        "platform": platform,
        "product_name": product_name,
        "alt_text": alt,
    }
    write_snapshot(data_dir, "alt_text_accessibility", payload)
    return payload
