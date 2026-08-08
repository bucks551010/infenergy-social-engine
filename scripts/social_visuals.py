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


def _clean_product_name(value: str) -> str:
    text = normalize_brand_text(str(value or "")).strip()
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"\s+-\s+", text) if p.strip()]
    if len(parts) <= 1:
        return text
    deduped: list[str] = []
    seen = set()
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    if len(deduped) == 1:
        return deduped[0]
    return " | ".join(deduped[:2])


def _metric_chips(content: dict[str, Any], limit: int = 2) -> list[str]:
    metrics = content.get("product_metrics", []) if isinstance(content, dict) else []
    if not isinstance(metrics, list):
        metrics = []
    cleaned = []
    seen = set()
    for raw in metrics:
        text = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _select_visual_template(visual_plan: dict[str, Any], platform: str) -> str:
    requested = str(visual_plan.get("visual_template") or os.environ.get("VISUAL_TEMPLATE", "")).strip().lower()
    if requested in {"premium_editorial", "premium_product_focus", "premium_minimal"}:
        return requested
    strategy = str(visual_plan.get("image_strategy") or "").strip().lower()
    if strategy in {"product_photo_featured", "hybrid"}:
        return "premium_product_focus"
    if platform == "linkedin":
        return "premium_editorial"
    return "premium_product_focus"


def _draw_wrapped(draw: Any, text: str, *, font: Any, x: int, y: int, width_chars: int, fill: str, line_gap: int) -> int:
    wrapped = textwrap.wrap(normalize_brand_text(text), width=max(10, width_chars))
    current_y = y
    for line in wrapped:
        draw.text((x, current_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, current_y), line, font=font)
        current_y = bbox[3] + line_gap
    return current_y


def _html_card(content: dict[str, Any], platform: str, visual_plan: dict[str, Any] | None = None) -> str:
    plan = _safe_json_dict(visual_plan)
    template = _select_visual_template(plan, platform)
    hook_limit = 96 if platform in ("facebook", "instagram") else 108
    topic_limit = 90 if platform in ("facebook", "instagram") else 100
    hook = html.escape(_trim_for_card(str(content.get("selected_hook") or content.get("topic") or content.get("wp_title") or "Power planning"), hook_limit))
    topic = html.escape(_trim_for_card(str(content.get("topic") or ""), topic_limit))
    product_name = html.escape(_clean_product_name(str(content.get("product_name") or "")))
    cta = html.escape(normalize_brand_text(str(content.get("selected_cta") or "Learn more")))
    product_image = html.escape(str(content.get("product_image_url") or ""))
    proof_chips = _metric_chips(content, limit=2)
    chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in proof_chips])
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
        body {{ margin: 0; background: #060b12; font-family: 'Avenir Next', 'Segoe UI', 'Montserrat', sans-serif; }}
        .card {{ width: {width}px; height: {height}px; margin: 0 auto; color: #f2f8ff; position: relative; overflow: hidden;
            background:
                radial-gradient(1300px 780px at -10% -20%, rgba(58,120,175,0.32), transparent 60%),
                radial-gradient(1100px 700px at 120% 120%, rgba(201,157,84,0.18), transparent 58%),
                linear-gradient(150deg, #07111c 0%, #12283e 48%, #0a1727 100%);
        }}
        .noise {{ position:absolute; inset:0; opacity:.05; background-image: radial-gradient(#fff 0.5px, transparent 0.5px); background-size: 3px 3px; }}
        .frame {{ position: absolute; inset: 22px; border: 1px solid rgba(214, 183, 109, 0.62); border-radius: 34px; }}
        .frame2 {{ position: absolute; inset: 36px; border: 1px solid rgba(140, 210, 255, 0.22); border-radius: 28px; }}
        .inner {{ position: absolute; inset: 48px; border-radius: 24px; padding: 44px;
            background: linear-gradient(165deg, rgba(9,22,36,0.85), rgba(16,42,68,0.78));
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 32px 60px rgba(0,0,0,0.44);
        }}
        .brand {{ color: #e9f4ff; font-size: 34px; font-weight: 700; letter-spacing: 0.02em; }}
        .stage {{ display: inline-block; margin-top: 12px; color: #e4c585; font-size: 16px; text-transform: uppercase; letter-spacing: .16em;
            border: 1px solid rgba(220,182,105,.45); border-radius: 999px; padding: 6px 14px; }}
        .layout {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 30px; margin-top: 28px; align-items: start; }}
        .hook {{ font-size: {62 if platform in ('facebook', 'instagram') else 46}px; line-height: 1.02; font-weight: 780; max-width: 100%; text-wrap: balance; }}
        .topic {{ margin-top: 16px; color: #d7e8fa; font-size: {40 if platform in ('facebook', 'instagram') else 28}px; line-height: 1.2; max-width: 95%; }}
        .chips {{ margin-top: 18px; display: flex; flex-wrap: wrap; gap: 10px; }}
        .chip {{ border: 1px solid rgba(151,206,255,.38); color: #cde8ff; padding: 8px 12px; border-radius: 999px; font-size: 16px; background: rgba(9,25,39,.45); }}
        .product {{ margin-top: 16px; color: #f1d8a2; font-size: 26px; font-weight: 650; max-width: 95%; }}
        .image-wrap {{ justify-self: end; width: {446 if platform in ('facebook', 'instagram') else 356}px; height: {446 if platform in ('facebook', 'instagram') else 356}px;
            border-radius: 30px; border: 1px solid rgba(145, 214, 255, 0.72);
            background: linear-gradient(170deg, rgba(255,255,255,0.12), rgba(11,24,38,0.24));
            display: flex; align-items: center; justify-content: center; padding: 22px;
            box-shadow: 0 26px 40px rgba(0,0,0,0.42), inset 0 1px 0 rgba(255,255,255,0.26);
        }}
        .image-wrap img {{ max-width: 100%; max-height: 100%; object-fit: contain; filter: drop-shadow(0 16px 16px rgba(0,0,0,.33)); }}
        .cta {{ position: absolute; left: 44px; right: 44px; bottom: 44px;
            background: linear-gradient(90deg, #1a4766, #2c7299 60%, #1f557a);
            border: 1px solid rgba(184, 226, 255, 0.5);
            border-radius: 18px; padding: 14px 22px; text-align: center; font-size: 28px; font-weight: 640; color: #f2fbff;
            box-shadow: 0 12px 26px rgba(0,0,0,0.36);
        }}
        .card.premium_minimal .chips {{ display:none; }}
        .card.premium_editorial .image-wrap {{ border-radius: 18px; }}
        .card.premium_product_focus .image-wrap {{ border: 2px solid rgba(145, 214, 255, 0.88); }}
    </style>
</head>
<body>
    <div class=\"card {template}\">
        <div class=\"noise\"></div>
        <div class=\"frame\"></div>
        <div class=\"frame2\"></div>
        <div class=\"inner\">
            <div class=\"brand\">Infenergy Power</div>
            <div class=\"stage\">{html.escape(str(content.get('funnel_stage', 'EDUCATION')))}</div>
            <div class=\"layout\">
                <div>
                    <div class=\"hook\">{hook}</div>
                    <div class=\"topic\">{topic}</div>
                    {f'<div class="chips">{chips_html}</div>' if chips_html else ''}
                    {f'<div class="product">Featured product: {product_name}</div>' if product_name else ''}
                </div>
                {f'<div class="image-wrap"><img src="{product_image}" alt="Product visual" /></div>' if product_image else ''}
            </div>
            <div class=\"cta\">{cta}</div>
        </div>
    </div>
</body>
</html>
"""


def _render_card(content: dict[str, Any], platform: str, image_path: str, visual_plan: dict[str, Any] | None = None) -> bool:
    image_module, draw_module, font_module = _load_pillow()
    if image_module is None:
        return False

    plan = _safe_json_dict(visual_plan)
    template = _select_visual_template(plan, platform)

    if platform in ("facebook", "instagram"):
        width, height = (1200, 1200)
    else:
        width, height = (1200, 627)
    canvas = image_module.new("RGB", (width, height), "#091523")
    draw = draw_module.Draw(canvas)

    for offset in range(height):
        ratio = offset / max(1, height - 1)
        r = int(7 + (24 - 7) * ratio)
        g = int(18 + (52 - 18) * ratio)
        b = int(29 + (88 - 29) * ratio)
        draw.line((0, offset, width, offset), fill=(r, g, b))

    draw.ellipse((-280, -220, 760, 520), fill=(44, 104, 158, 62))
    draw.ellipse((width - 760, height - 520, width + 290, height + 220), fill=(177, 136, 62, 46))

    draw.rounded_rectangle((28, 28, width - 28, height - 28), radius=34, outline="#d3b578", width=1)
    draw.rounded_rectangle((44, 44, width - 44, height - 44), radius=28, outline="#8fcff5", width=1)
    draw.rounded_rectangle((56, 56, width - 56, height - 56), radius=24, fill="#123149")

    brand_font = _font(font_module, 34)
    stage_font = _font(font_module, 20 if platform in ("facebook", "instagram") else 16)
    title_font = _font(font_module, 56 if platform in ("facebook", "instagram") else 42)
    body_font = _font(font_module, 26 if platform in ("facebook", "instagram") else 21)
    chip_font = _font(font_module, 18 if platform in ("facebook", "instagram") else 14)
    footer_font = _font(font_module, 28 if platform in ("facebook", "instagram") else 20)

    draw.text((92, 88), "Infenergy Power", font=brand_font, fill="#e9f7ff")
    stage_text = normalize_brand_text(str(content.get("funnel_stage", "EDUCATION")))
    draw.rounded_rectangle((92, 134, 280, 172), radius=16, outline="#d7b978", width=1)
    draw.text((106, 143), stage_text, font=stage_font, fill="#d7b978")

    hook_limit = 96 if platform in ("facebook", "instagram") else 108
    topic_limit = 90 if platform in ("facebook", "instagram") else 100
    hook = _trim_for_card(str(content.get("selected_hook") or content.get("topic") or content.get("wp_title") or "Power planning"), hook_limit)
    topic = _trim_for_card(str(content.get("topic") or ""), topic_limit)
    product_name = _clean_product_name(str(content.get("product_name") or ""))
    cta = str(content.get("selected_cta") or "Learn more")

    text_width = 22 if platform in ("facebook", "instagram") else 26
    body_bottom = _draw_wrapped(draw, hook, font=title_font, x=92, y=196, width_chars=text_width, fill="#ffffff", line_gap=8)
    body_bottom = _draw_wrapped(draw, topic, font=body_font, x=92, y=body_bottom + 16, width_chars=34 if platform in ("facebook", "instagram") else 40, fill="#d7e8fa", line_gap=8)

    if template != "premium_minimal":
        chips = _metric_chips(content, limit=2)
        chip_y = body_bottom + 14
        chip_x = 92
        for chip in chips:
            label = _trim_for_card(chip, 36)
            bbox = draw.textbbox((0, 0), label, font=chip_font)
            w = (bbox[2] - bbox[0]) + 28
            draw.rounded_rectangle((chip_x, chip_y, chip_x + w, chip_y + 34), radius=14, outline="#8fcff5", width=1, fill="#153248")
            draw.text((chip_x + 14, chip_y + 8), label, font=chip_font, fill="#cde8ff")
            chip_x += w + 10
        body_bottom = chip_y + 44

    if product_name:
        body_bottom = _draw_wrapped(draw, f"Featured product: {product_name}", font=body_font, x=92, y=body_bottom + 12, width_chars=34, fill="#f1dda9", line_gap=8)

    draw.rounded_rectangle((92, height - 146, width - 92, height - 80), radius=20, fill="#235f83", outline="#9bd7ff", width=1)
    cta_text = normalize_brand_text(cta)
    cta_bbox = draw.textbbox((0, 0), cta_text, font=footer_font)
    cta_x = 92 + max(0, ((width - 184) - (cta_bbox[2] - cta_bbox[0])) // 2)
    draw.text((cta_x, height - 124), cta_text, font=footer_font, fill="#f2fbff")

    product_image = _fetch_product_image(image_module, str(content.get("product_image_url", "")))
    if product_image is not None:
        if platform in ("facebook", "instagram"):
            target_w, target_h = 446, 446
            pos = (width - target_w - 84, 184)
        else:
            target_w, target_h = 356, 356
            pos = (width - target_w - 56, 104)
        draw.rounded_rectangle((pos[0] - 14, pos[1] - 14, pos[0] + target_w + 14, pos[1] + target_h + 14), radius=30, fill="#18374f")
        image_copy = product_image.copy()
        image_copy.thumbnail((target_w, target_h))
        frame = image_module.new("RGBA", (target_w, target_h), (13, 34, 48, 0))
        offset_x = (target_w - image_copy.width) // 2
        offset_y = (target_h - image_copy.height) // 2
        frame.paste(image_copy, (offset_x, offset_y), image_copy if image_copy.mode == "RGBA" else None)
        canvas.paste(frame, pos, frame)
        border_color = "#9ad7ff" if template != "premium_editorial" else "#e0c48e"
        draw.rounded_rectangle((pos[0] - 10, pos[1] - 10, pos[0] + target_w + 10, pos[1] + target_h + 10), radius=26, outline=border_color, width=2)

    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    canvas.save(image_path, format="PNG", optimize=True)
    return True


def generate_visuals(content: dict[str, Any], visual_plan: dict[str, Any] | None = None) -> dict[str, str]:
    post_id = str(content.get("post_id") or "preview")
    visuals: dict[str, str] = {}
    plan = _safe_json_dict(visual_plan)
    template_name = _select_visual_template(plan, "facebook")
    image_strategy = str(plan.get("image_strategy") or os.environ.get("VISUAL_IMAGE_STRATEGY", "local_render")).strip().lower()
    prefer_gemini = image_strategy in ("gemini_generated", "hybrid")
    prefer_product_overlay = image_strategy in ("product_photo_featured", "hybrid")

    os.makedirs(VISUAL_DIR, exist_ok=True)
    for platform in ("facebook", "instagram", "linkedin"):
        file_name = f"{post_id}_{platform}.png"
        file_path = os.path.join(VISUAL_DIR, file_name)
        html_path = os.path.join(VISUAL_DIR, f"{post_id}_{platform}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(_html_card(content, platform, visual_plan=plan))
        visuals[f"{platform}_html"] = html_path

        rendered = False
        if prefer_gemini:
            rendered = _generate_gemini_background(content, platform, plan, file_path)
            if rendered and prefer_product_overlay:
                _compose_product_photo_overlay(content, platform, file_path)

        if not rendered:
            rendered = _render_card(content, platform, file_path, visual_plan=plan)

        if rendered:
            visuals[platform] = file_path
    visuals["template"] = template_name
    visuals["image_strategy"] = image_strategy
    return visuals
