from __future__ import annotations

import io
import os
import re
import html
import json
import base64
import textwrap
from typing import Any

import requests

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "..", "data"))
VISUAL_DIR = os.path.join(DATA_DIR, "generated_visuals")


_BRAND_REPLACEMENTS = (
    ("INF Energy Power", "Infenergy Power"),
    ("INF Energy", "Infenergy"),
    ("INF energy", "Infenergy"),
    ("Inf Energy", "Infenergy"),
    ("InfEnergyPower", "InfenergyPower"),
)


def normalize_brand_text(value: str) -> str:
    text = str(value or "")
    for old, new in _BRAND_REPLACEMENTS:
        text = text.replace(old, new)
    text = re.sub(r"#InfEnergyPower\b", "#InfenergyPower", text)
    text = re.sub(r"\bINFENERGY\b", "Infenergy", text)
    return text


def normalize_brand_content(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_brand_text(value)
    if isinstance(value, list):
        return [normalize_brand_content(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_brand_content(v) for k, v in value.items()}
    return value


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        return Image, ImageDraw, ImageFont
    except Exception:
        return None, None, None


def _font(font_module: Any, size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return font_module.truetype(name, size)
        except Exception:
            continue
    return font_module.load_default()


def _fetch_product_image(image_module: Any, image_url: str):
    if not image_url or not str(image_url).startswith("http"):
        return None
    try:
        resp = requests.get(image_url, timeout=20)
        resp.raise_for_status()
        return image_module.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception:
        return None


def _safe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_inline_image_bytes(response: Any) -> bytes:
    # Handle evolving SDK response formats by scanning candidate parts.
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if not inline_data:
                continue
            data = getattr(inline_data, "data", None)
            if isinstance(data, bytes):
                return data
            if isinstance(data, str) and data:
                try:
                    return base64.b64decode(data)
                except Exception:
                    continue
    return b""


def _build_gemini_image_prompt(content: dict[str, Any], platform: str, visual_plan: dict[str, Any]) -> str:
    platform_cfg = _safe_json_dict((visual_plan.get("platform_overrides") or {}).get(platform))
    style_intent = str(visual_plan.get("style_intent") or "premium practical energy brand visual").strip()
    mood = str(visual_plan.get("mood") or "credible, modern, trustworthy").strip()
    composition = str(platform_cfg.get("composition") or visual_plan.get("composition") or "clean composition with room for text").strip()
    key_hook = normalize_brand_text(str(content.get("selected_hook") or content.get("topic") or "Power planning"))
    topic = normalize_brand_text(str(content.get("topic") or ""))
    product_name = normalize_brand_text(str(content.get("product_name") or ""))
    return (
        "Create a photorealistic branded social background image for Infenergy Power. "
        f"Style intent: {style_intent}. Mood: {mood}. Composition: {composition}. "
        f"Platform: {platform}. Hook context: {key_hook}. Topic context: {topic}. "
        f"Product context: {product_name or 'portable/home power solution'}. "
        "Do not include any logos, no watermarks, no misspelled text, no UI elements, no people with deformed hands. "
        "Use cinematic but realistic lighting and leave negative space where headline and CTA can be overlaid cleanly."
    )


def _generate_gemini_background(content: dict[str, Any], platform: str, visual_plan: dict[str, Any], output_path: str) -> bool:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False

    model_name = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image").strip() or "gemini-2.5-flash-image"
    prompt = _build_gemini_image_prompt(content, platform, visual_plan)
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        raw = _extract_inline_image_bytes(response)
        if not raw:
            return False

        image_module, _, _ = _load_pillow()
        if image_module is None:
            return False

        generated = image_module.open(io.BytesIO(raw)).convert("RGB")
        if platform in ("facebook", "instagram"):
            target = (1200, 1200)
        else:
            target = (1200, 627)
        generated = generated.resize(target)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        generated.save(output_path, format="PNG", optimize=True)
        return True
    except Exception:
        return False


def _compose_product_photo_overlay(content: dict[str, Any], platform: str, image_path: str) -> bool:
    image_module, draw_module, _ = _load_pillow()
    if image_module is None:
        return False
    try:
        canvas = image_module.open(image_path).convert("RGBA")
    except Exception:
        return False

    product_image = _fetch_product_image(image_module, str(content.get("product_image_url", "")))
    if product_image is None:
        return False

    if platform in ("facebook", "instagram"):
        target_w, target_h = 420, 420
        x, y = (canvas.width - target_w - 90, 230)
    else:
        target_w, target_h = 320, 320
        x, y = (canvas.width - target_w - 70, 130)

    product_copy = product_image.copy()
    product_copy.thumbnail((target_w, target_h))
    frame = image_module.new("RGBA", (target_w, target_h), (14, 34, 48, 110))
    off_x = (target_w - product_copy.width) // 2
    off_y = (target_h - product_copy.height) // 2
    frame.paste(product_copy, (off_x, off_y), product_copy if product_copy.mode == "RGBA" else None)
    canvas.paste(frame, (x, y), frame)

    draw = draw_module.Draw(canvas)
    draw.rounded_rectangle((x - 10, y - 10, x + target_w + 10, y + target_h + 10), radius=24, outline="#9ad7ff", width=2)
    canvas.convert("RGB").save(image_path, format="PNG", optimize=True)
    return True


def _trim_for_card(value: str, max_chars: int) -> str:
    text = normalize_brand_text(str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _draw_wrapped(draw: Any, text: str, *, font: Any, x: int, y: int, width_chars: int, fill: str, line_gap: int) -> int:
    wrapped = textwrap.wrap(normalize_brand_text(text), width=max(10, width_chars))
    current_y = y
    for line in wrapped:
        draw.text((x, current_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, current_y), line, font=font)
        current_y = bbox[3] + line_gap
    return current_y


def _html_card(content: dict[str, Any], platform: str) -> str:
    hook_limit = 112 if platform in ("facebook", "instagram") else 124
    topic_limit = 86 if platform in ("facebook", "instagram") else 96
    hook = html.escape(_trim_for_card(str(content.get("selected_hook") or content.get("topic") or content.get("wp_title") or "Power planning"), hook_limit))
    topic = html.escape(_trim_for_card(str(content.get("topic") or ""), topic_limit))
    product_name = html.escape(normalize_brand_text(str(content.get("product_name") or "")))
    cta = html.escape(normalize_brand_text(str(content.get("selected_cta") or "Learn more")))
    product_image = html.escape(str(content.get("product_image_url") or ""))
    width = 1200
    height = 1200 if platform in ("facebook", "instagram") else 627
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>Infenergy Social Card</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; background: #070d16; font-family: 'Segoe UI', 'Montserrat', sans-serif; }}
        .card {{ width: {width}px; height: {height}px; margin: 0 auto; color: #fff; position: relative; overflow: hidden;
            background:
                radial-gradient(1200px 700px at 10% 5%, rgba(56,126,180,0.28), transparent 60%),
                radial-gradient(900px 600px at 88% 90%, rgba(196,152,73,0.20), transparent 60%),
                linear-gradient(150deg, #09131f 0%, #13283f 46%, #0b1828 100%);
        }}
        .noise {{ position:absolute; inset:0; opacity:.06; background-image: radial-gradient(#fff 0.6px, transparent 0.6px); background-size: 4px 4px; }}
        .frame {{ position: absolute; inset: 24px; border: 2px solid rgba(220, 187, 110, 0.72); border-radius: 34px; }}
        .frame2 {{ position: absolute; inset: 44px; border: 1px solid rgba(146, 208, 255, 0.35); border-radius: 26px; }}
        .inner {{ position: absolute; inset: 52px; border-radius: 22px; padding: 42px;
            background: linear-gradient(160deg, rgba(10,24,37,0.86), rgba(19,47,72,0.80));
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 24px 50px rgba(0,0,0,0.42);
        }}
        .brand {{ color: #e8f6ff; font-size: 34px; font-weight: 700; letter-spacing: 0.03em; }}
        .stage {{ color: #d7b978; font-size: 18px; margin-top: 10px; text-transform: uppercase; letter-spacing: .12em; }}
        .hook {{ margin-top: 28px; font-size: {50 if platform in ('facebook', 'instagram') else 40}px; line-height: 1.1; font-weight: 780; max-width: {620 if platform in ('facebook', 'instagram') else 680}px; text-wrap: balance; }}
        .topic {{ margin-top: 18px; color: #d7e8f8; font-size: 27px; line-height: 1.28; max-width: 700px; }}
        .product {{ margin-top: 18px; color: #f0d9a1; font-size: 27px; font-weight: 600; max-width: 700px; }}
        .cta {{ position: absolute; left: 42px; right: 42px; bottom: 42px;
            background: linear-gradient(90deg, #1a4868, #2b7097 58%, #1c5278);
            border: 1px solid rgba(186, 226, 255, 0.45);
            border-radius: 24px; padding: 16px 24px; text-align: center; font-size: 30px; font-weight: 620; color: #f2fbff;
            box-shadow: 0 10px 24px rgba(0,0,0,0.35);
        }}
        .image-wrap {{ position: absolute; right: 42px; top: {188 if platform in ('facebook', 'instagram') else 106}px; width: {440 if platform in ('facebook', 'instagram') else 340}px; height: {440 if platform in ('facebook', 'instagram') else 340}px;
            border-radius: 28px; border: 2px solid rgba(145, 213, 255, 0.82);
            background: linear-gradient(170deg, rgba(255,255,255,0.09), rgba(10,20,30,0.18));
            display: flex; align-items: center; justify-content: center; padding: 22px;
            box-shadow: 0 24px 34px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.25);
        }}
        .image-wrap img {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
    </style>
</head>
<body>
    <div class=\"card\">
        <div class=\"noise\"></div>
        <div class=\"frame\"></div>
        <div class=\"frame2\"></div>
        <div class=\"inner\">
            <div class=\"brand\">Infenergy Power</div>
            <div class=\"stage\">{html.escape(str(content.get('funnel_stage', 'EDUCATION')))}</div>
            <div class=\"hook\">{hook}</div>
            <div class=\"topic\">{topic}</div>
            {f'<div class="product">Featured product: {product_name}</div>' if product_name else ''}
            <div class=\"cta\">{cta}</div>
            {f'<div class="image-wrap"><img src="{product_image}" alt="Product visual" /></div>' if product_image else ''}
        </div>
    </div>
</body>
</html>
"""


def _render_card(content: dict[str, Any], platform: str, image_path: str) -> bool:
    image_module, draw_module, font_module = _load_pillow()
    if image_module is None:
        return False

    if platform in ("facebook", "instagram"):
        width, height = (1200, 1200)
    else:
        width, height = (1200, 627)
    canvas = image_module.new("RGB", (width, height), "#0b1f2a")
    draw = draw_module.Draw(canvas)

    for offset in range(height):
        ratio = offset / max(1, height - 1)
        r = int(8 + (28 - 8) * ratio)
        g = int(18 + (56 - 18) * ratio)
        b = int(30 + (92 - 30) * ratio)
        draw.line((0, offset, width, offset), fill=(r, g, b))

    draw.ellipse((-260, -210, 760, 520), fill=(39, 96, 150, 58))
    draw.ellipse((width - 760, height - 520, width + 280, height + 210), fill=(180, 138, 64, 48))

    draw.rounded_rectangle((40, 40, width - 40, height - 40), radius=38, outline="#d7b978", width=2)
    draw.rounded_rectangle((58, 58, width - 58, height - 58), radius=30, outline="#8fd3ff", width=1)
    draw.rounded_rectangle((70, 70, width - 70, height - 70), radius=24, fill="#123247")

    brand_font = _font(font_module, 34)
    title_font = _font(font_module, 58 if platform in ("facebook", "instagram") else 44)
    body_font = _font(font_module, 31 if platform in ("facebook", "instagram") else 24)
    footer_font = _font(font_module, 30 if platform in ("facebook", "instagram") else 21)

    draw.text((96, 96), "Infenergy Power", font=brand_font, fill="#e9f7ff")
    draw.text((96, 138), normalize_brand_text(str(content.get("funnel_stage", "EDUCATION"))), font=footer_font, fill="#d7b978")

    hook_limit = 112 if platform in ("facebook", "instagram") else 124
    topic_limit = 86 if platform in ("facebook", "instagram") else 96
    hook = _trim_for_card(str(content.get("selected_hook") or content.get("topic") or content.get("wp_title") or "Power planning"), hook_limit)
    topic = _trim_for_card(str(content.get("topic") or ""), topic_limit)
    product_name = str(content.get("product_name") or "")
    cta = str(content.get("selected_cta") or "Learn more")

    body_bottom = _draw_wrapped(draw, hook, font=title_font, x=96, y=196, width_chars=22 if platform in ("facebook", "instagram") else 26, fill="#ffffff", line_gap=10)
    body_bottom = _draw_wrapped(draw, topic, font=body_font, x=96, y=body_bottom + 20, width_chars=32 if platform in ("facebook", "instagram") else 38, fill="#d9edf8", line_gap=9)
    if product_name:
        body_bottom = _draw_wrapped(draw, f"Featured product: {product_name}", font=body_font, x=96, y=body_bottom + 18, width_chars=34, fill="#f1dda9", line_gap=9)

    draw.rounded_rectangle((96, height - 150, width - 96, height - 80), radius=24, fill="#205f83", outline="#9bd7ff", width=1)
    cta_text = normalize_brand_text(cta)
    cta_bbox = draw.textbbox((0, 0), cta_text, font=footer_font)
    cta_x = 96 + max(0, ((width - 192) - (cta_bbox[2] - cta_bbox[0])) // 2)
    draw.text((cta_x, height - 128), cta_text, font=footer_font, fill="#f2fbff")

    product_image = _fetch_product_image(image_module, str(content.get("product_image_url", "")))
    if product_image is not None:
        if platform in ("facebook", "instagram"):
            target_w, target_h = 440, 440
            pos = (width - target_w - 90, 208)
        else:
            target_w, target_h = 340, 340
            pos = (width - target_w - 62, 120)
        image_copy = product_image.copy()
        image_copy.thumbnail((target_w, target_h))
        frame = image_module.new("RGBA", (target_w, target_h), (13, 34, 48, 0))
        offset_x = (target_w - image_copy.width) // 2
        offset_y = (target_h - image_copy.height) // 2
        frame.paste(image_copy, (offset_x, offset_y), image_copy if image_copy.mode == "RGBA" else None)
        canvas.paste(frame, pos, frame)
        draw.rounded_rectangle((pos[0] - 10, pos[1] - 10, pos[0] + target_w + 10, pos[1] + target_h + 10), radius=24, outline="#9ad7ff", width=2)

    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    canvas.save(image_path, format="PNG", optimize=True)
    return True


def generate_visuals(content: dict[str, Any], visual_plan: dict[str, Any] | None = None) -> dict[str, str]:
    post_id = str(content.get("post_id") or "preview")
    visuals: dict[str, str] = {}
    plan = _safe_json_dict(visual_plan)
    image_strategy = str(plan.get("image_strategy") or os.environ.get("VISUAL_IMAGE_STRATEGY", "local_render")).strip().lower()
    prefer_gemini = image_strategy in ("gemini_generated", "hybrid")
    prefer_product_overlay = image_strategy in ("product_photo_featured", "hybrid")

    os.makedirs(VISUAL_DIR, exist_ok=True)
    for platform in ("facebook", "instagram", "linkedin"):
        file_name = f"{post_id}_{platform}.png"
        file_path = os.path.join(VISUAL_DIR, file_name)
        html_path = os.path.join(VISUAL_DIR, f"{post_id}_{platform}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(_html_card(content, platform))
        visuals[f"{platform}_html"] = html_path

        rendered = False
        if prefer_gemini:
            rendered = _generate_gemini_background(content, platform, plan, file_path)
            if rendered and prefer_product_overlay:
                _compose_product_photo_overlay(content, platform, file_path)

        if not rendered:
            rendered = _render_card(content, platform, file_path)

        if rendered:
            visuals[platform] = file_path
    return visuals
