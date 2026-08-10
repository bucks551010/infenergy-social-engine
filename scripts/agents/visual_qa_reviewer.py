"""Tier-2 #6: visual_qa_reviewer_agent.

Wraps the semantic plate quality review as a schema-validated agent. Thin
wrapper around social_visuals._gemini_semantic_plate_quality that also produces
a JSON-serializable output.
"""

from __future__ import annotations

import os
from typing import Any

from ._base import utc_now, write_snapshot


def _default_report() -> dict:
    return {
        "has_text": False,
        "has_fake_products": False,
        "busy_copy_zone": False,
        "off_brand": False,
        "retry_note": "",
        "acceptable": True,
        "confidence": 0.5,
    }


def review(image_bytes: bytes, platform: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or not image_bytes:
        return _default_report()
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        model = os.environ.get("GEMINI_VISUAL_QA_MODEL", "gemini-2.5-flash")
        prompt = (
            "You are a strict social ad QA reviewer. Look at the image and return JSON with fields: "
            "has_text (bool: any legible text/logos/badges/watermarks anywhere), "
            "has_fake_products (bool: any invented product-looking objects with fake screens/branding), "
            "busy_copy_zone (bool: true if the copy_zone region is too visually busy to hold overlaid text), "
            f"off_brand (bool: any elements clashing with a preparedness/backup-power brand on {platform}), "
            "retry_note (short string, empty if none), "
            "acceptable (bool), confidence (0.0-1.0). Reply JSON only."
        )
        resp = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        import json
        data = json.loads((resp.text or "").strip())
        if not isinstance(data, dict):
            return _default_report()
        report = _default_report()
        report.update({k: data[k] for k in report.keys() if k in data})
        return report
    except Exception:
        return _default_report()


def run(data_dir: str, image_path: str = "", platform: str = "facebook") -> dict:
    raw = b""
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                raw = f.read()
        except Exception:
            raw = b""
    report = review(raw, platform)
    payload = {
        "agent": "visual_qa_reviewer",
        "time_utc": utc_now(),
        "image_path": image_path,
        "platform": platform,
        **report,
    }
    write_snapshot(data_dir, "visual_qa_reviewer", payload)
    return payload
