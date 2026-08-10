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

from url_safety import is_safe_http_url

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
    for name in (
        "Bahnschrift.ttf",
        "arialbd.ttf",
        "impact.ttf",
        "Montserrat-Bold.ttf",
        "Aptos-Display.ttf",
        "arial.ttf",
        "DejaVuSans.ttf",
        "segoeui.ttf",
    ):
        try:
            return font_module.truetype(name, size)
        except Exception:
            continue
    return font_module.load_default()


def _autocrop_transparent(image: Any) -> Any:
    try:
        bbox = image.getbbox()
        if not bbox:
            return image
        return image.crop(bbox)
    except Exception:
        return image


def _remove_near_white_bg(image: Any, threshold: int = 238):
    try:
        rgba = image.convert("RGBA")
        if hasattr(rgba, "get_flattened_data"):
            raw_pixels = list(rgba.get_flattened_data())
        else:
            raw_pixels = list(rgba.getdata())
        pixels = []
        for r, g, b, a in raw_pixels:
            near_white = r >= threshold and g >= threshold and b >= threshold
            low_saturation = max(r, g, b) - min(r, g, b) <= 18
            if near_white and low_saturation:
                pixels.append((r, g, b, 0))
            elif a > 0 and near_white and low_saturation:
                softened_alpha = max(0, int(a * 0.18))
                pixels.append((r, g, b, softened_alpha))
            else:
                pixels.append((r, g, b, a))
        rgba.putdata(pixels)
        return _autocrop_transparent(rgba)
    except Exception:
        return image


def _resize_cover(image: Any, target: tuple[int, int], image_module: Any) -> Any:
    target_w, target_h = target
    src_w, src_h = image.size
    if not src_w or not src_h:
        return image.resize(target)

    scale = max(target_w / float(src_w), target_h / float(src_h))
    resized_w = max(1, int(round(src_w * scale)))
    resized_h = max(1, int(round(src_h * scale)))
    resampling = getattr(getattr(image_module, "Resampling", image_module), "LANCZOS", getattr(image_module, "LANCZOS", 1))
    resized = image.resize((resized_w, resized_h), resampling)

    left = max(0, (resized_w - target_w) // 2)
    top = max(0, (resized_h - target_h) // 2)
    right = left + target_w
    bottom = top + target_h
    return resized.crop((left, top, right, bottom))


def _fetch_product_image(image_module: Any, image_url: str):
    if not image_url:
        return None
    try:
        src = str(image_url).strip()
        if src.lower().startswith("file://"):
            src = src[7:]
        if os.path.exists(src):
            raw = image_module.open(src).convert("RGBA")
            return _remove_near_white_bg(raw)
        if not src.startswith("http"):
            return None
        if not is_safe_http_url(src):
            return None
        resp = requests.get(src, timeout=20)
        resp.raise_for_status()
        raw = image_module.open(io.BytesIO(resp.content)).convert("RGBA")
        return _remove_near_white_bg(raw)
    except Exception:
        return None


def _read_image_bytes_any(source: str) -> tuple[bytes, str]:
    src = str(source or "").strip()
    if not src:
        return b"", ""
    if src.lower().startswith("file://"):
        src = src[7:]
    try:
        if os.path.exists(src):
            with open(src, "rb") as f:
                data = f.read()
            ext = os.path.splitext(src)[1].lower()
            if ext in (".png",):
                return data, "image/png"
            if ext in (".webp",):
                return data, "image/webp"
            return data, "image/jpeg"
        if src.startswith("http"):
            if not is_safe_http_url(src):
                return b"", ""
            resp = requests.get(src, timeout=20)
            resp.raise_for_status()
            ctype = str(resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return resp.content, ctype
    except Exception:
        return b"", ""
    return b"", ""


def _primary_stat(content: dict[str, Any]) -> str:
    metrics = content.get("product_metrics", []) if isinstance(content, dict) else []
    if isinstance(metrics, list):
        for metric in metrics:
            token = re.sub(r"\s+", " ", str(metric or "")).strip()
            if not token:
                continue
            upper = token.upper().replace("MAH", "mAh")
            if any(unit in upper for unit in ("W", "WH", "KWH", "MAH", "V")):
                return upper
    topic = normalize_brand_text(str(content.get("topic") or ""))
    hook = normalize_brand_text(str(content.get("selected_hook") or ""))
    text = f"{topic} {hook}".lower()
    metric_match = re.search(r"\b\d+(?:\.\d+)?\s?(?:w|kw|kwh|wh|mah|v)\b", text)
    if metric_match:
        token = metric_match.group(0).upper().replace("MAH", "mAh")
        if "W" in token and "WH" not in token and "KWH" not in token:
            return f"{token} POWER"
        return token
    if any(k in text for k in ("outage", "backup", "blackout")):
        return "OUTAGE READY"
    if any(k in text for k in ("charge", "charging", "recharge")):
        return "FAST RECHARGE"
    return "SMART POWER"


def _benefit_rows(content: dict[str, Any]) -> list[str]:
    metrics = _metric_chips(content, limit=6)
    rows: list[str] = []
    for m in metrics:
        cleaned = re.sub(r"\s+", " ", normalize_brand_text(m)).strip()
        if cleaned and cleaned not in rows:
            rows.append(cleaned)
        if len(rows) >= 4:
            break
    topic = str(content.get("topic") or "").lower()
    product_name = str(content.get("product_name") or "").lower()
    categories = " ".join(str(x or "") for x in (content.get("product_categories") or [])).lower() if isinstance(content.get("product_categories"), list) else str(content.get("product_categories") or "").lower()
    defaults = [
        "Outage-ready backup",
        "Real-world device fit",
        "Spec-backed confidence",
        "Faster preparedness",
    ]
    if any(token in product_name or token in categories for token in ("power bank", "charger", "travel power")):
        defaults = [
            "Reliable backup charging",
            "Travel-ready power",
            "Device-safe recharge",
            "Everyday carry readiness",
        ]
    elif any(token in product_name or token in categories for token in ("jump starter", "car", "vehicle")):
        defaults = [
            "Roadside backup power",
            "Vehicle emergency support",
            "Portable emergency readiness",
            "Faster recovery on the road",
        ]
    elif any(token in topic or token in categories for token in ("outage", "backup", "home backup")):
        defaults = [
            "Must-run device backup",
            "Home outage readiness",
            "Spec-backed resilience",
            "Confidence before storms",
        ]
    for d in defaults:
        if len(rows) >= 4:
            break
        if d not in rows:
            rows.append(d)
    return rows[:4]


def _trust_badges(content: dict[str, Any]) -> list[str]:
    raw_badges = content.get("trust_badges", []) if isinstance(content, dict) else []
    if not isinstance(raw_badges, list):
        return []
    badges: list[str] = []
    for raw_badge in raw_badges:
        badge = re.sub(r"\s+", " ", normalize_brand_text(str(raw_badge or ""))).strip()
        if badge and badge.lower() not in {item.lower() for item in badges}:
            badges.append(badge)
    return badges[:3]


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


def _load_visual_repo_context() -> dict[str, Any]:
    context = {
        "references": [],
        "settings": {},
    }
    try:
        import inventory_db  # type: ignore

        inventory_db.init_inventory_db(DATA_DIR)
        refs = inventory_db.fetch_gemini_style_references(DATA_DIR, active_only=True, limit=200)
        settings = inventory_db.fetch_visual_generation_settings(DATA_DIR)
        ref_list = refs if isinstance(refs, list) else []
        if isinstance(settings, dict):
            active_keys = settings.get("active_style_keys", [])
            if isinstance(active_keys, list) and active_keys:
                active_key_set = {str(k).strip().lower() for k in active_keys if str(k).strip()}
                ref_list = [r for r in ref_list if str(r.get("style_key", "")).strip().lower() in active_key_set]
        context["references"] = ref_list
        context["settings"] = settings if isinstance(settings, dict) else {}
    except Exception as e:
        print(f"[Visuals] Warning: failed to load visual repo context, using empty context: {e}")
        return context
    return context


def _resolve_product_source(content: dict[str, Any], repo_context: dict[str, Any] | None = None) -> str:
    env_override = str(os.environ.get("VISUAL_PRODUCT_IMAGE_OVERRIDE") or "").strip()
    if env_override:
        return env_override

    ctx = repo_context or _load_visual_repo_context()
    settings = ctx.get("settings") if isinstance(ctx, dict) else {}
    if isinstance(settings, dict):
        db_override = str(settings.get("visual_product_image_override_url") or "").strip()
        if db_override:
            return db_override

    refs = ctx.get("references") if isinstance(ctx, dict) else []
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            candidate = str(ref.get("visual_product_image_override_url") or "").strip()
            if candidate:
                return candidate

    return str(content.get("product_image_url") or "").strip()


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


def _platform_visual_spec(platform: str) -> dict[str, Any]:
    if platform == "linkedin":
        return {
            "target": (1200, 627),
            "aspect_ratio": "16:9",
            "copy_zone": "left 46%",
            "product_zone": "right 36%, vertically centered",
            "scene": "credible modern workplace or small-business continuity setting",
        }
    if platform == "instagram":
        return {
            "target": (1200, 1200),
            "aspect_ratio": "1:1",
            "copy_zone": "left 42% and bottom 16%",
            "product_zone": "right 38%, grounded in the lower half",
            "scene": "bold mobile-first lifestyle setting with strong depth and one clear focal path",
        }
    return {
        "target": (1200, 1200),
        "aspect_ratio": "1:1",
        "copy_zone": "left 44% and bottom 16%",
        "product_zone": "right 38%, grounded in the lower half",
        "scene": "credible premium household preparedness setting with useful environmental context",
    }


def _gemini_plate_quality(image: Any, platform: str) -> tuple[bool, list[str]]:
    image_module, _, _ = _load_pillow()
    if image_module is None:
        return False, ["pillow_unavailable"]
    try:
        from PIL import ImageStat  # type: ignore
    except Exception:
        return False, ["pillow_stats_unavailable"]

    spec = _platform_visual_spec(platform)
    expected_ratio = spec["target"][0] / spec["target"][1]
    actual_ratio = image.width / max(1, image.height)
    reasons: list[str] = []
    if abs(actual_ratio - expected_ratio) / expected_ratio > 0.18:
        reasons.append("aspect_ratio")

    nearest = getattr(getattr(image_module, "Resampling", image_module), "NEAREST", 0)
    grayscale = image.convert("L").resize((240, 240), nearest)
    extrema = grayscale.getextrema()
    if not extrema or extrema[1] - extrema[0] < 24:
        reasons.append("low_dynamic_range")

    copy_fraction = 0.46 if platform == "linkedin" else 0.44
    copy_zone = grayscale.crop((0, 0, max(1, int(grayscale.width * copy_fraction)), grayscale.height))
    copy_zone_stddev = float(ImageStat.Stat(copy_zone).stddev[0])
    if copy_zone_stddev > float(os.environ.get("GEMINI_COPY_ZONE_MAX_STDDEV", "76")):
        reasons.append("busy_copy_zone")

    return not reasons, reasons


def _normalize_reference_image(raw: bytes) -> tuple[bytes, str]:
    image_module, _, _ = _load_pillow()
    if image_module is None or not raw or len(raw) > 8_000_000:
        return b"", ""
    try:
        reference = image_module.open(io.BytesIO(raw)).convert("RGB")
        reference.thumbnail((1280, 1280))
        output = io.BytesIO()
        reference.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue(), "image/jpeg"
    except Exception:
        return b"", ""


def _gemini_semantic_plate_quality(client: Any, types: Any, raw: bytes, platform: str) -> tuple[bool, list[str]]:
    enabled = str(os.environ.get("GEMINI_VISUAL_QA_ENABLED", "true")).strip().lower() not in {"0", "false", "no"}
    if not enabled:
        return True, []
    spec = _platform_visual_spec(platform)
    review_prompt = (
        "Review this candidate social background plate. Return JSON only with booleans for "
        "has_text_or_symbols, has_product_or_device, copy_zone_is_busy, product_zone_is_blocked, "
        "and scene_is_low_quality. Treat any readable or gibberish letters, numbers, logos, labels, "
        "screens, UI, badges, buttons, signs, watermarks, fake power products, device silhouettes, or "
        "placeholder boxes as failures. The required copy-safe zone is the "
        f"{spec['copy_zone']}; the required product landing zone is the {spec['product_zone']}."
    )
    model_candidates = [
        str(os.environ.get("GEMINI_VISUAL_QA_MODEL", "")).strip(),
        "gemini-2.5-flash",
    ]
    for model_name in model_candidates:
        if not model_name:
            continue
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[review_prompt, types.Part.from_bytes(data=raw, mime_type="image/png")],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            review = json.loads(str(response.text or "{}"))
            if not isinstance(review, dict):
                continue
            failure_keys = (
                "has_text_or_symbols",
                "has_product_or_device",
                "copy_zone_is_busy",
                "product_zone_is_blocked",
                "scene_is_low_quality",
            )
            reasons = [key for key in failure_keys if review.get(key) is True]
            return not reasons, reasons
        except Exception:
            continue
    return True, ["semantic_review_unavailable"]


def _build_gemini_image_prompt(content: dict[str, Any], platform: str, visual_plan: dict[str, Any]) -> str:
    spec = _platform_visual_spec(platform)
    platform_cfg = _safe_json_dict((visual_plan.get("platform_overrides") or {}).get(platform))
    style_intent = str(visual_plan.get("style_intent") or "premium retail ad board for power products").strip()
    mood = str(visual_plan.get("mood") or "bold, high-contrast, conversion-focused, premium").strip()
    composition = str(platform_cfg.get("composition") or visual_plan.get("composition") or "calm copy-safe zone left, grounded product landing zone right").strip()
    key_hook = normalize_brand_text(str(content.get("selected_hook") or content.get("topic") or "Power planning"))
    topic = normalize_brand_text(str(content.get("topic") or ""))
    product_name = normalize_brand_text(str(content.get("product_name") or ""))
    stage = normalize_brand_text(str(content.get("funnel_stage") or "ATTENTION"))
    cta = normalize_brand_text(str(content.get("selected_cta") or "Map your must-run devices and build your outage-ready setup."))
    stat = _primary_stat(content)
    benefits = _benefit_rows(content)
    product_label = re.sub(r"[\s\-|:]+$", "", product_name).strip()
    product_label = re.sub(r"\s+", " ", product_label)
    support_line = _headline_lockup(content)[1]
    if not product_label:
        product_label = "Infenergy backup power"
    copy_direction = (
        f"Design for the product story around '{product_label}', but do not render readable text into the image. "
        f"Use the support idea '{support_line}', the proof cue '{stat}', and the CTA intent '{cta}' only as composition guidance. "
        "The application will add the actual product cutout, numbers, headline, proof callout, and CTA afterward. "
    )
    plan_prompt = re.sub(
        r"\s+",
        " ",
        str(platform_cfg.get("scene_prompt") or visual_plan.get("gemini_image_prompt") or ""),
    ).strip()[:1600]
    style_refs = str(os.environ.get("GEMINI_STYLE_REFERENCES") or "").strip()
    repo_context = _load_visual_repo_context()
    repo_refs = repo_context.get("references", []) if isinstance(repo_context, dict) else []
    repo_reference_ideas: list[str] = []
    if isinstance(repo_refs, list):
        for ref in repo_refs:
            if not isinstance(ref, dict):
                continue
            name = str(ref.get("style_name") or "").strip()
            notes = str(ref.get("style_notes") or "").strip()
            idea = f"{name}: {notes}".strip(": ")
            if idea:
                repo_reference_ideas.append(idea)

    style_ref_line = ""
    if style_refs:
        style_ref_line = f"Style references: {style_refs}. "
    elif repo_reference_ideas:
        style_ref_line = f"Style reference ideas: {' | '.join(repo_reference_ideas[:6])}. "
    stage_direction = {
        "ATTENTION": "Prioritize interruption, surprise, tension, and high visual magnetism. The creative should stop the scroll immediately.",
        "EDUCATION": "Prioritize clarity, guided comparison, explainability, and structured insight so the creative teaches at a glance.",
        "DESIRE": "Prioritize aspiration, ownership, confidence, and product-fit desire without looking gimmicky or overhyped.",
        "TRUST": "Prioritize credibility, proof, engineering confidence, and factual reassurance with premium restraint.",
        "CONVERSION": "Prioritize urgency, clarity of next step, confidence-to-act, and unmistakable purchase momentum.",
    }.get(stage, "Prioritize premium persuasion with clarity and confidence.")
    material_direction = (
        "Use restrained commercial photography details: brushed metal, matte charcoal surfaces, warm amber practical light, soft reflections, "
        "natural depth haze, and controlled highlights. Keep materials physically believable. "
    )
    product_stage_direction = (
        "Reserve a grounded hero stage on the lower-right side for the real product cutout. "
        "The stage should feel premium and believable, with a base surface, shadow landing zone, and coherent lighting direction. "
        "Do not render a product, do not render a fake placeholder device, and do not leave a white box or empty frame. "
        "Leave enough clean space so the real product can occupy roughly one-third of the final composition without overlapping the copy zone. "
    )
    layout_guardrails = (
        f"Reserve the {spec['copy_zone']} as a low-detail, dark-to-mid-tone copy-safe zone. "
        f"Reserve the {spec['product_zone']} as a coherent product landing zone. "
        "Do not place high-contrast edges, bright hotspots, faces, or focal objects in the copy-safe zone."
    )
    atmosphere_direction = (
        "Build atmosphere with one coherent cinematic light direction, premium material textures, layered shadows, restrained reflections, and natural depth haze. "
        "The reserved copy zone must remain visually quiet even while the surrounding scene has depth. "
    )
    campaign_direction = (
        "This should feel like premium commercial photography prepared for a top-tier performance campaign. "
        "Be visually confident, physically credible, and restrained enough for the deterministic ad layer. "
    )
    negative_direction = (
        "Do not make it look like a flyer, template, ecommerce tile, infographic, cartoon, abstract wallpaper, or synthetic AI poster. "
        "Avoid random decoration, muddy contrast, excessive glow, impossible reflections, or visual clutter. "
    )
    return (
        "Create a premium social background plate for Infenergy Power. "
        f"Plan suggestions, subordinate to the scene contract and exclusions below: style '{style_intent}', mood '{mood}', composition '{composition}'. "
        f"{style_ref_line}"
        f"Platform: {platform}. Hook context: {key_hook}. Topic context: {topic}. "
        f"Product context: {product_name or 'portable/home power solution'}. Funnel stage: {stage}. "
        f"Product facts informing the mood only: {', '.join(benefits)}. "
        f"{copy_direction}"
        f"Optional approved scene brief, subordinate to every rule here: {plan_prompt or 'none'}. "
        "Use a restrained brand palette: charcoal #15191d, deep navy #112d44, amber #f7a30f, and warm gold #ffd469. Avoid neon colors and dominant purple. "
        f"Build a {spec['scene']}. "
        f"{stage_direction} "
        f"{material_direction}"
        f"{atmosphere_direction}"
        f"{campaign_direction}"
        "Generate only the atmospheric background plate and scene, not the final ad copy layer. "
        "ABSOLUTE EXCLUSIONS: no text, letters, numerals, symbols, logos, labels, signage, screens, interfaces, charts, badges, buttons, frames, product renders, device mockups, or placeholder objects. "
        f"{product_stage_direction}"
        f"{layout_guardrails} "
        "Keep the design modern, premium, clean, and conversion-focused, but leave negative space for post-composited text and product. "
        f"{negative_direction}"
        "No watermarks, gibberish marks, floating silhouettes, duplicate focal objects, or prominent distorted hands. Any people must look natural, emotionally credible, and remain secondary to the reserved copy and product zones. Output one finished background scene plate only."
    )


def _generate_gemini_background(content: dict[str, Any], platform: str, visual_plan: dict[str, Any], output_path: str) -> bool:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False

    prompt = _build_gemini_image_prompt(content, platform, visual_plan)
    repo_context = _load_visual_repo_context()
    repo_refs = repo_context.get("references", []) if isinstance(repo_context, dict) else []
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)
        model_candidates = [
            str(os.environ.get("GEMINI_IMAGE_MODEL", "")).strip(),
            "gemini-2.5-flash-image",
            "gemini-2.5-flash",
        ]
        seen_models: set[str] = set()
        spec = _platform_visual_spec(platform)
        reference_parts: list[Any] = []
        for reference in repo_refs[:3] if isinstance(repo_refs, list) else []:
            source = str(reference.get("reference_url") or "").strip() if isinstance(reference, dict) else ""
            image_bytes, mime_type = _read_image_bytes_any(source)
            image_bytes, mime_type = _normalize_reference_image(image_bytes)
            if not image_bytes:
                continue
            try:
                reference_parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg"))
            except Exception:
                continue

        for model_name in model_candidates:
            if not model_name or model_name in seen_models:
                continue
            seen_models.add(model_name)
            for attempt in range(2):
                retry_note = "" if attempt == 0 else " Previous plate failed automated composition checks. Make the copy-safe zone calmer and preserve the requested aspect ratio."
                contents: Any = [prompt + retry_note, *reference_parts] if reference_parts else prompt + retry_note
                try:
                    config_kwargs: dict[str, Any] = {"response_modalities": ["TEXT", "IMAGE"]}
                    try:
                        config_kwargs["image_config"] = types.ImageConfig(aspect_ratio=spec["aspect_ratio"])
                    except Exception:
                        pass
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(**config_kwargs),
                    )
                    raw = _extract_inline_image_bytes(response)
                    if not raw:
                        continue

                    image_module, _, _ = _load_pillow()
                    if image_module is None:
                        return False

                    generated = image_module.open(io.BytesIO(raw)).convert("RGB")
                    accepted, _ = _gemini_plate_quality(generated, platform)
                    if not accepted:
                        continue
                    accepted, _ = _gemini_semantic_plate_quality(client, types, raw, platform)
                    if not accepted:
                        continue
                    generated = _resize_cover(generated, spec["target"], image_module)
                    if generated.size != spec["target"]:
                        continue
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    generated.save(output_path, format="PNG", optimize=True)
                    return True
                except Exception:
                    continue
        return False
    except Exception:
        return False


def _compose_gemini_ad_overlay(content: dict[str, Any], platform: str, image_path: str, visual_plan: dict[str, Any] | None = None) -> bool:
    image_module, draw_module, font_module = _load_pillow()
    if image_module is None:
        return False
    try:
        canvas = image_module.open(image_path).convert("RGBA")
    except Exception:
        return False

    draw = draw_module.Draw(canvas)
    width, height = canvas.size

    # Stabilize contrast only where deterministic copy will be composited.
    overlay = image_module.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay_draw = draw_module.Draw(overlay)
    base_alpha = max(0, min(220, int(os.environ.get("VISUAL_OVERLAY_ALPHA", "154"))))
    overlay_draw.polygon([(0, 0), (int(width * 0.56), 0), (int(width * 0.45), height), (0, height)], fill=(6, 14, 22, base_alpha))
    overlay_draw.polygon([(0, height - int(height * 0.17)), (width, height - int(height * 0.12)), (width, height), (0, height)], fill=(20, 12, 8, 104))
    canvas = image_module.alpha_composite(canvas, overlay)
    draw = draw_module.Draw(canvas)

    brand_font = _font(font_module, 34 if platform in ("facebook", "instagram") else 24)
    stage_font = _font(font_module, 20 if platform in ("facebook", "instagram") else 15)
    body_font = _font(font_module, 28 if platform in ("facebook", "instagram") else 21)
    footer_font = _font(font_module, 30 if platform in ("facebook", "instagram") else 21)

    draw.text((88, 84), "Infenergy Power", font=brand_font, fill="#eef7ff")
    stage_text = normalize_brand_text(str(content.get("funnel_stage", "EDUCATION")))
    draw.rounded_rectangle((88, 130, 312 if platform in ("facebook", "instagram") else 272, 176 if platform in ("facebook", "instagram") else 166), radius=15, fill="#f2a81a", outline="#ffd469", width=1)
    draw.text((102, 142 if platform in ("facebook", "instagram") else 138), stage_text, font=stage_font, fill="#161616")

    headline_text, subline_text = _headline_lockup(content)
    body_bottom = _draw_headline_fit(
        draw,
        _trim_for_card(headline_text.upper(), 72 if platform in ("facebook", "instagram") else 82),
        font_module=font_module,
        x=88,
        y=196,
        max_width_px=430 if platform in ("facebook", "instagram") else 500,
        base_size=74 if platform in ("facebook", "instagram") else 52,
        min_size=42 if platform in ("facebook", "instagram") else 28,
        max_lines=3 if platform in ("facebook", "instagram") else 2,
        fill="#ffffff",
        line_gap=5,
    )
    body_bottom = _draw_wrapped(
        draw,
        _trim_for_card(subline_text, 82 if platform in ("facebook", "instagram") else 92),
        font=body_font,
        x=88,
        y=body_bottom + 12,
        width_chars=22 if platform in ("facebook", "instagram") else 32,
        fill="#d9ecff",
        line_gap=8,
    )

    stat_text = _primary_stat(content)
    stat_font = _font(font_module, 34 if platform in ("facebook", "instagram") else 22)
    stat_bbox = draw.textbbox((0, 0), stat_text, font=stat_font)
    stat_w = (stat_bbox[2] - stat_bbox[0]) + 26
    draw.rounded_rectangle((88, body_bottom + 10, 88 + stat_w, body_bottom + 56), radius=10, fill="#f7af20", outline="#ffd56a", width=1)
    draw.text((100, body_bottom + 20), stat_text, font=stat_font, fill="#151515")

    row_font = _font(font_module, 24 if platform in ("facebook", "instagram") else 17)
    benefit_y = body_bottom + 72
    for row in _benefit_rows(content):
        label = _trim_for_card(row, 30)
        draw.text((88, benefit_y), ">>", font=row_font, fill="#ffb62b")
        draw.text((126, benefit_y), label, font=row_font, fill="#ffe4ae")
        benefit_y += 36 if platform in ("facebook", "instagram") else 26

    cta = normalize_brand_text(str(content.get("selected_cta") or "Learn more"))
    if not cta.endswith("->"):
        cta = f"{cta} ->"
    cta_top = height - 126 if platform in ("facebook", "instagram") else height - 90
    cta_bottom = height - 54 if platform in ("facebook", "instagram") else height - 34
    cta_right = 548 if platform in ("facebook", "instagram") else 420
    draw.rounded_rectangle((88, cta_top, cta_right, cta_bottom), radius=18, fill="#c73613", outline="#ffcf52", width=1)
    draw.rounded_rectangle((88, cta_top, cta_right, cta_top + 4), radius=18, fill="#ffd13d")
    cta_bbox = draw.textbbox((0, 0), cta, font=footer_font)
    cta_x = 88 + max(0, ((cta_right - 88) - (cta_bbox[2] - cta_bbox[0])) // 2)
    draw.text((cta_x, cta_top + 20), cta, font=footer_font, fill="#f2fbff")

    badge_font = _font(font_module, 16 if platform in ("facebook", "instagram") else 12)
    badge_x = width - 286 if platform in ("facebook", "instagram") else width - 220
    badge_y = 760 if platform in ("facebook", "instagram") else 392
    for label in _trust_badges(content):
        clean = _trim_for_card(label, 20)
        bbox = draw.textbbox((0, 0), clean, font=badge_font)
        bw = (bbox[2] - bbox[0]) + 26
        draw.rounded_rectangle((badge_x, badge_y, badge_x + bw, badge_y + 30), radius=14, fill="#12191f", outline="#f8c24f", width=1)
        draw.text((badge_x + 12, badge_y + 8), clean, font=badge_font, fill="#f7f9ff")
        badge_y += 36

    product_source = _resolve_product_source(content)
    product_image = _fetch_product_image(image_module, product_source)
    if product_image is not None:
        target_w, target_h = (480, 500) if platform in ("facebook", "instagram") else (410, 430)
        pos = (width - target_w - 54, 286) if platform in ("facebook", "instagram") else (width - target_w - 42, 94)
        image_copy = product_image.copy()
        image_copy.thumbnail((target_w, target_h))
        frame = image_module.new("RGBA", (target_w, target_h), (13, 34, 48, 0))
        offset_x = (target_w - image_copy.width) // 2
        offset_y = (target_h - image_copy.height) // 2
        shadow_w = max(180, int(image_copy.width * 0.72))
        shadow_h = max(24, int(image_copy.height * 0.09))
        shadow_x = pos[0] + max(0, (target_w - shadow_w) // 2)
        shadow_y = pos[1] + offset_y + image_copy.height - int(shadow_h * 0.35)
        shadow_layer = image_module.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = draw_module.Draw(shadow_layer)
        shadow_draw.ellipse((shadow_x, shadow_y, shadow_x + shadow_w, shadow_y + shadow_h), fill=(4, 10, 15, 108))
        canvas = image_module.alpha_composite(canvas, shadow_layer)
        frame.paste(image_copy, (offset_x, offset_y), image_copy if image_copy.mode == "RGBA" else None)
        canvas.paste(frame, pos, frame)

    canvas.convert("RGB").save(image_path, format="PNG", optimize=True)
    return True


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
        target_w, target_h = 620, 620
        x, y = (canvas.width - target_w - 44, 118)
    else:
        target_w, target_h = 430, 430
        x, y = (canvas.width - target_w - 34, 84)

    product_copy = product_image.copy()
    product_copy.thumbnail((target_w, target_h))
    off_x = x + (target_w - product_copy.width) // 2
    off_y = y + (target_h - product_copy.height) // 2
    shadow_layer = image_module.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = draw_module.Draw(shadow_layer)
    shadow_width = max(140, int(product_copy.width * 0.58))
    shadow_height = max(36, int(product_copy.height * 0.10))
    shadow_left = off_x + max(0, (product_copy.width - shadow_width) // 2)
    shadow_top = off_y + product_copy.height - int(shadow_height * 0.2)
    shadow_draw.ellipse(
        (shadow_left, shadow_top, shadow_left + shadow_width, shadow_top + shadow_height),
        fill=(14, 22, 30, 74),
    )
    shadow_draw.ellipse(
        (shadow_left + 22, shadow_top + 6, shadow_left + shadow_width - 22, shadow_top + shadow_height - 2),
        fill=(32, 52, 68, 42),
    )
    canvas = image_module.alpha_composite(canvas, shadow_layer)
    canvas.paste(product_copy, (off_x, off_y), product_copy if product_copy.mode == "RGBA" else None)
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


def _headline_lockup(content: dict[str, Any]) -> tuple[str, str]:
    def _trim_line(text: str, limit: int) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3].rstrip() + "..."

    product_name = normalize_brand_text(str(content.get("product_name") or "")).strip()
    product_name = re.sub(r"[\s\-|:]+$", "", product_name)
    metrics = content.get("product_metrics", []) if isinstance(content, dict) else []
    metric_text = ""
    if isinstance(metrics, list) and metrics:
        metric_text = re.sub(r"\s+", " ", str(metrics[0] or "")).strip()
    hook_raw = normalize_brand_text(str(content.get("selected_hook") or "")).strip()
    topic_raw = normalize_brand_text(str(content.get("topic") or "")).strip()
    source = f"{hook_raw} {topic_raw}".lower()

    assigned_headline = normalize_brand_text(str(content.get("on_image_headline") or "")).strip()
    assigned_subline = normalize_brand_text(str(content.get("on_image_subline") or "")).strip()
    if assigned_headline:
        return _trim_line(assigned_headline.upper(), 34), _trim_line(assigned_subline, 74)

    if product_name:
        words = [word for word in re.split(r"\s+", product_name) if word]
        headline = " ".join(words[:4]).upper() if words else "INFENERGY POWER"
        headline = _trim_line(headline, 34)
        if metric_text:
            subline = f"Built around {metric_text} and real-world preparedness."
        elif any(k in source for k in ("outage", "backup", "storm")):
            subline = "Built for real outages, essential devices, and faster readiness."
        elif any(k in source for k in ("travel", "portable", "charge")):
            subline = "Built for portable power, daily carry, and backup charging confidence."
        else:
            subline = "Built for real-life readiness, mobility, and backup confidence."
        return headline, subline

    if any(k in source for k in ("outage", "blackout", "storm")):
        headline = "OUTAGE READY POWER"
        subline = "Keep your must-run devices online during outages."
    elif any(k in source for k in ("portable", "power station")):
        headline = "PORTABLE POWER READY"
        subline = "Choose capacity by runtime, not marketing claims."
    elif any(k in source for k in ("runtime", "battery life", "duration")):
        headline = "RUNTIME THAT LASTS"
        subline = "Match load demand to verified battery performance."
    elif any(k in source for k in ("solar", "charge", "charging")):
        headline = "SMART CHARGE CONTROL"
        subline = "Recharge faster with smarter battery planning."
    else:
        headline = "POWER WITHOUT GUESSWORK"
        subline = "Build a plan around real devices and real loads."
    return headline, subline


def _select_visual_template(visual_plan: dict[str, Any], platform: str) -> str:
    requested = str(visual_plan.get("visual_template") or os.environ.get("VISUAL_TEMPLATE", "")).strip().lower()
    if requested in {"premium_editorial", "premium_product_focus", "premium_minimal", "nike_premium", "power_shot"}:
        if requested == "power_shot" and platform in ("facebook", "instagram"):
            return "premium_product_focus"
        return requested
    strategy = str(visual_plan.get("image_strategy") or "").strip().lower()
    if strategy in {"gemini_generated", "hybrid"}:
        return "premium_product_focus" if platform in ("facebook", "instagram") else "power_shot"
    if strategy in {"product_photo_featured", "hybrid"}:
        return "premium_product_focus" if platform in ("facebook", "instagram") else "power_shot"
    if platform == "linkedin":
        return "premium_editorial"
    return "premium_product_focus" if platform in ("facebook", "instagram") else "power_shot"


def _draw_wrapped(draw: Any, text: str, *, font: Any, x: int, y: int, width_chars: int, fill: str, line_gap: int) -> int:
    wrapped = textwrap.wrap(normalize_brand_text(text), width=max(10, width_chars))
    current_y = y
    for line in wrapped:
        draw.text((x, current_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, current_y), line, font=font)
        current_y = bbox[3] + line_gap
    return current_y


def _wrap_to_pixel_width(draw: Any, text: str, font: Any, max_width_px: int) -> list[str]:
    words = [w for w in normalize_brand_text(text).split() if w]
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if (bbox[2] - bbox[0]) <= max_width_px or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _draw_headline_fit(
    draw: Any,
    text: str,
    *,
    font_module: Any,
    x: int,
    y: int,
    max_width_px: int,
    base_size: int,
    min_size: int,
    max_lines: int,
    fill: str,
    line_gap: int,
) -> int:
    size = base_size
    while size >= min_size:
        font = _font(font_module, size)
        lines = _wrap_to_pixel_width(draw, text, font, max_width_px)
        if lines and len(lines) <= max_lines:
            current_y = y
            for line in lines:
                draw.text((x, current_y), line, font=font, fill=fill)
                bbox = draw.textbbox((x, current_y), line, font=font)
                current_y = bbox[3] + line_gap
            return current_y
        size -= 2

    fallback = _font(font_module, min_size)
    lines = _wrap_to_pixel_width(draw, text, fallback, max_width_px)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [_trim_for_card(lines[max_lines - 1], 18)]
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=fallback, fill=fill)
        bbox = draw.textbbox((x, current_y), line, font=fallback)
        current_y = bbox[3] + line_gap
    return current_y


def _html_card(content: dict[str, Any], platform: str, visual_plan: dict[str, Any] | None = None) -> str:
    plan = _safe_json_dict(visual_plan)
    template = _select_visual_template(plan, platform)
    hook_limit = 72 if platform in ("facebook", "instagram") else 82
    topic_limit = 80 if platform in ("facebook", "instagram") else 90
    headline_text, subline_text = _headline_lockup(content)
    hook = html.escape(_trim_for_card(headline_text, hook_limit))
    topic = html.escape(_trim_for_card(subline_text, topic_limit))
    product_name = html.escape(_clean_product_name(str(content.get("product_name") or "")))
    cta = html.escape(normalize_brand_text(str(content.get("selected_cta") or "Learn more")))
    product_source = _resolve_product_source(content)
    product_image = html.escape(product_source)
    primary_stat = html.escape(_primary_stat(content))
    benefits_html = "".join([f'<div class="benefit"><span class="dot">&gt;&gt;</span><span>{html.escape(b)}</span></div>' for b in _benefit_rows(content)])
    badges_html = "".join([f'<span class="badge">{html.escape(b)}</span>' for b in _trust_badges(content)])
    proof_chips = _metric_chips(content, limit=2)
    chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in proof_chips])
    width = 1200
    height = 1200 if platform in ("facebook", "instagram") else 627
    is_square = platform in ("facebook", "instagram")
    is_nike = template == "nike_premium"
    is_power = template == "power_shot"
    hook_size = 82 if (is_power and is_square) else (48 if (is_power and not is_square) else (88 if (is_nike and is_square) else (52 if (is_nike and not is_square) else (92 if is_square else 56))))
    topic_size = 28 if (is_power and is_square) else (21 if (is_power and not is_square) else (33 if (is_nike and is_square) else (24 if (is_nike and not is_square) else (30 if is_square else 22))))
    media_size = 560 if (is_power and is_square) else (420 if (is_power and not is_square) else (540 if (is_nike and is_square) else (390 if (is_nike and not is_square) else (490 if is_square else 372))))
    cta_right = 300 if (is_power and is_square) else (250 if (is_power and not is_square) else (370 if (is_nike and is_square) else (280 if (is_nike and not is_square) else (330 if is_square else 260))))
    cta_bottom = 62 if is_power else (116 if (is_nike and is_square) else (36 if not is_nike else 72))
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>Infenergy Social Card</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; background: #070d14; font-family: 'Avenir Next Condensed', 'Oswald', 'Segoe UI', sans-serif; }}
        .card {{ width: {width}px; height: {height}px; margin: 0 auto; color: #f3f8ff; position: relative; overflow: hidden;
            background:
                radial-gradient(1600px 920px at -20% -10%, rgba(52,117,176,0.38), transparent 56%),
                radial-gradient(1200px 860px at 120% 120%, rgba(204,155,73,0.22), transparent 58%),
                linear-gradient(146deg, #07111c 0%, #112740 49%, #0a1624 100%);
        }}
        .edge {{ position:absolute; inset:20px; border:1px solid rgba(226,184,108,.54); border-radius:32px; }}
        .edge2 {{ position:absolute; inset:34px; border:1px solid rgba(130,205,255,.24); border-radius:28px; }}
        .slash-a {{ position:absolute; right:-120px; top:-80px; width:520px; height:260px; background: linear-gradient(140deg, rgba(89,157,221,.34), rgba(89,157,221,0)); transform: rotate(-18deg); }}
        .slash-b {{ position:absolute; left:-180px; bottom:-120px; width:620px; height:320px; background: linear-gradient(145deg, rgba(202,154,75,.28), rgba(202,154,75,0)); transform: rotate(21deg); }}
        .inner {{ position:absolute; inset:52px; border-radius:24px; padding:40px 42px 38px;
            background: linear-gradient(165deg, rgba(9,24,39,.84), rgba(16,44,72,.76));
            box-shadow: inset 0 1px 0 rgba(255,255,255,.07), 0 28px 54px rgba(0,0,0,.44);
        }}
        .brand {{ font-size:34px; font-weight:700; letter-spacing:.01em; }}
        .stage {{ margin-top:10px; display:inline-block; color:#e1bf80; border:1px solid rgba(223,179,95,.55);
            border-radius:999px; font-size:15px; letter-spacing:.16em; text-transform:uppercase; padding:7px 14px; }}
        .grid {{ margin-top:22px; display:grid; grid-template-columns: 1.02fr .98fr; gap:{30 if is_nike else 24}px; align-items:start; }}
        .hook {{ margin:0; font-size:{hook_size}px; line-height:.9; text-transform:uppercase; letter-spacing:.01em; font-weight:800; max-width:98%; }}
        .topic {{ margin-top:16px; color:#d4e8fb; font-size:{topic_size}px; line-height:1.2; max-width:88%; }}
        .stat {{ display:inline-block; margin-top:14px; background:linear-gradient(90deg,#f7a30f,#ffd034); color:#121212; font-size:{34 if is_square else 22}px;
            font-weight:820; letter-spacing:.03em; text-transform:uppercase; padding:8px 14px; border-radius:9px; }}
        .chips {{ margin-top:16px; display:flex; gap:10px; flex-wrap:wrap; }}
        .chip {{ font-size:15px; border:1px solid rgba(144,206,255,.5); border-radius:999px; padding:7px 12px; color:#cce6ff; background:rgba(11,33,52,.52); }}
        .product {{ margin-top:14px; color:#f0d5a0; font-size:24px; font-weight:640; max-width:88%; }}
        .benefits {{ margin-top:16px; display:grid; grid-template-columns:1fr; gap:8px; max-width:80%; }}
        .benefit {{ display:flex; align-items:center; gap:8px; color:#ffe3aa; font-size:{22 if is_square else 16}px; font-weight:620; }}
        .dot {{ color:#ffb11a; }}
        .media {{ justify-self:end; width:{media_size}px; height:{media_size}px;
            border-radius:22px; border:1px solid rgba(163,214,255,.75); background: linear-gradient(170deg, rgba(255,255,255,.12), rgba(14,35,55,.32));
            box-shadow: 0 30px 46px rgba(0,0,0,.46), inset 0 1px 0 rgba(255,255,255,.22);
            position:relative; overflow:hidden; display:flex; align-items:center; justify-content:center; }}
        .media::before {{ content:''; position:absolute; inset:0; background: radial-gradient(80% 80% at 70% 20%, rgba(129,197,255,.26), transparent 68%); pointer-events:none; }}
        .media img {{ max-width:92%; max-height:92%; object-fit:contain; filter: drop-shadow(0 18px 20px rgba(0,0,0,.42)); position:relative; z-index:2; }}
        .badges {{ position:absolute; right:38px; bottom:{158 if is_square else 124}px; display:flex; flex-direction:column; gap:8px; z-index:3; }}
        .badge {{ display:inline-block; background:rgba(10,18,25,.82); color:#f5f8ff; border:1px solid rgba(255,190,58,.68); border-radius:999px; padding:7px 11px; font-size:{14 if is_square else 12}px; font-weight:640; }}
        .cta {{ position:absolute; left:42px; right:{cta_right}px; bottom:{cta_bottom}px;
            font-size:{31 if platform in ('facebook','instagram') else 24}px; font-weight:700; letter-spacing:.01em;
            color:#f6fcff; border-radius:16px; border:1px solid rgba(183,226,255,.56);
            background: linear-gradient(90deg, #8f1e07, #c73412 52%, #e95d1f);
            padding:15px 20px; box-shadow:0 14px 28px rgba(0,0,0,.35); }}
        .cta::before {{ content:''; position:absolute; left:0; right:0; top:0; height:4px; border-radius:16px 16px 0 0; background:#ffd13d; }}
        .cta::after {{ content:' ->'; color:#d7eeff; }}
        .card.premium_minimal .topic {{ font-size:{26 if platform in ('facebook','instagram') else 20}px; }}
        .card.premium_minimal .chips {{ display:none; }}
        .card.premium_minimal .product {{ display:none; }}
        .card.premium_editorial .hook {{ text-transform:none; line-height:1.02; font-size:{72 if platform in ('facebook','instagram') else 46}px; }}
        .card.premium_editorial .media {{ border-radius:14px; }}
        .card.premium_product_focus .media {{ border:2px solid rgba(145,214,255,.92); }}
        .card.nike_premium .hook {{ font-family:'Avenir Next Condensed','Bahnschrift','Impact',sans-serif; }}
        .card.nike_premium .topic {{ max-width:74%; }}
        .card.nike_premium .chips {{ display:none; }}
        .card.nike_premium .product {{ display:none; }}
        .card.nike_premium .inner::after {{ content:''; position:absolute; left:-120px; right:-80px; bottom:82px; height:230px;
            background: linear-gradient(168deg, rgba(18,50,81,.9), rgba(18,50,81,.62)); transform: skewY(-6deg); z-index:0; }}
        .card.nike_premium .grid, .card.nike_premium .brand, .card.nike_premium .stage, .card.nike_premium .cta {{ position:relative; z-index:2; }}
        .card.power_shot {{
            background:
                radial-gradient(980px 700px at 98% 62%, rgba(235,101,20,0.35), transparent 58%),
                radial-gradient(760px 520px at 0% 0%, rgba(255,184,57,0.24), transparent 50%),
                linear-gradient(155deg, #0d0d0d 0%, #201307 55%, #0c0f14 100%);
        }}
        .card.power_shot .inner {{ background: linear-gradient(160deg, rgba(16,16,16,.9), rgba(47,23,8,.82)); }}
        .card.power_shot .hook {{ color:#ffd13d; }}
        .card.power_shot .topic {{ color:#fff2d0; max-width:70%; }}
        .card.power_shot .chips {{ display:none; }}
        .card.power_shot .product {{ display:none; }}
        .card.power_shot .media {{ border:2px solid rgba(255,186,52,.9); box-shadow: 0 34px 52px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.2); }}
    </style>
</head>
<body>
    <div class=\"card {template}\">
        <div class=\"slash-a\"></div>
        <div class=\"slash-b\"></div>
        <div class=\"edge\"></div>
        <div class=\"edge2\"></div>
        <div class=\"inner\">
            <div class=\"brand\">Infenergy Power</div>
            <div class=\"stage\">{html.escape(str(content.get('funnel_stage', 'EDUCATION')))}</div>
            <div class=\"grid\">
                <div>
                    <h1 class=\"hook\">{hook}</h1>
                    {f'<div class="stat">{primary_stat}</div>' if template == 'power_shot' else ''}
                    <div class=\"topic\">{topic}</div>
                    {f'<div class="benefits">{benefits_html}</div>' if template == 'power_shot' else ''}
                    {f'<div class="chips">{chips_html}</div>' if chips_html else ''}
                    {f'<div class="product">Featured product: {product_name}</div>' if product_name else ''}
                </div>
                {f'<div class="media"><img src="{product_image}" alt="Product visual" /></div>' if product_image else ''}
            </div>
            {f'<div class="badges">{badges_html}</div>' if template == 'power_shot' else ''}
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
    canvas = image_module.new("RGB", (width, height), "#08131f")
    draw = draw_module.Draw(canvas)

    for offset in range(height):
        ratio = offset / max(1, height - 1)
        r = int(7 + (21 - 7) * ratio)
        g = int(17 + (49 - 17) * ratio)
        b = int(30 + (84 - 30) * ratio)
        draw.line((0, offset, width, offset), fill=(r, g, b))

    draw.polygon([(-120, -50), (560, -50), (360, 220), (-260, 220)], fill=(57, 121, 181, 76))
    draw.polygon([(780, height - 120), (width + 220, height - 40), (width + 220, height + 240), (620, height + 40)], fill=(194, 149, 74, 58))

    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=30, outline="#d3b578", width=1)
    draw.rounded_rectangle((38, 38, width - 38, height - 38), radius=26, outline="#8fcff5", width=1)
    draw.rounded_rectangle((50, 50, width - 50, height - 50), radius=22, fill="#112d44")
    if template == "power_shot":
        draw.rounded_rectangle((50, 50, width - 50, height - 50), radius=22, fill="#1a1209")
        draw.polygon(
            [
                (-60, height - 320),
                (width + 50, height - 250),
                (width + 50, height - 38),
                (-60, height - 118),
            ],
            fill="#3e240f",
        )
    if template == "nike_premium" and platform in ("facebook", "instagram"):
        draw.polygon(
            [
                (-60, height - 310),
                (width + 40, height - 258),
                (width + 40, height - 38),
                (-60, height - 132),
            ],
            fill="#123251",
        )

    brand_font = _font(font_module, 34)
    stage_font = _font(font_module, 20 if platform in ("facebook", "instagram") else 15)
    if template == "power_shot":
        title_font = _font(font_module, 78 if platform in ("facebook", "instagram") else 50)
        body_font = _font(font_module, 28 if platform in ("facebook", "instagram") else 21)
    elif template == "nike_premium":
        title_font = _font(font_module, 82 if platform in ("facebook", "instagram") else 52)
        body_font = _font(font_module, 33 if platform in ("facebook", "instagram") else 24)
    else:
        title_font = _font(font_module, 76 if platform in ("facebook", "instagram") else 52)
        body_font = _font(font_module, 30 if platform in ("facebook", "instagram") else 22)
    chip_font = _font(font_module, 17 if platform in ("facebook", "instagram") else 13)
    footer_font = _font(font_module, 30 if platform in ("facebook", "instagram") else 21)

    brand_color = "#fbe7c4" if template == "power_shot" else "#e9f7ff"
    draw.text((88, 84), "Infenergy Power", font=brand_font, fill=brand_color)
    stage_text = normalize_brand_text(str(content.get("funnel_stage", "EDUCATION")))
    if template == "power_shot":
        draw.rounded_rectangle((88, 130, 316, 176), radius=14, fill="#f2a81a", outline="#ffd469", width=1)
        draw.text((102, 142), stage_text, font=stage_font, fill="#161616")
    else:
        draw.rounded_rectangle((88, 130, 282, 170), radius=16, outline="#d7b978", width=1)
        draw.text((102, 140), stage_text, font=stage_font, fill="#d7b978")

    hook_limit = 72 if platform in ("facebook", "instagram") else 82
    topic_limit = 80 if platform in ("facebook", "instagram") else 90
    headline_text, subline_text = _headline_lockup(content)
    hook = _trim_for_card(headline_text, hook_limit)
    topic = _trim_for_card(subline_text, topic_limit)
    product_name = _clean_product_name(str(content.get("product_name") or ""))
    cta = str(content.get("selected_cta") or "Learn more")

    if template == "power_shot":
        text_width = 14 if platform in ("facebook", "instagram") else 20
    elif template == "nike_premium":
        text_width = 12 if platform in ("facebook", "instagram") else 20
    else:
        text_width = 14 if platform in ("facebook", "instagram") else 22
    hook_up = hook.upper()
    hook_fill = "#ffd13d" if template == "power_shot" else "#ffffff"
    body_bottom = _draw_headline_fit(
        draw,
        hook_up,
        font_module=font_module,
        x=88,
        y=190,
        max_width_px=420 if template == "power_shot" and platform in ("facebook", "instagram") else 450 if platform in ("facebook", "instagram") else 500,
        base_size=82 if template == "nike_premium" and platform in ("facebook", "instagram") else 78 if platform in ("facebook", "instagram") else 52,
        min_size=44 if platform in ("facebook", "instagram") else 28,
        max_lines=3 if platform in ("facebook", "instagram") else 2,
        fill=hook_fill,
        line_gap=4,
    )
    topic_fill = "#ffefce" if template == "power_shot" else "#d6e8f9"
    body_bottom = _draw_wrapped(draw, topic, font=body_font, x=88, y=body_bottom + 14, width_chars=22 if platform in ("facebook", "instagram") else 32, fill=topic_fill, line_gap=8)

    if template == "power_shot":
        stat_text = _primary_stat(content)
        stat_font = _font(font_module, 34 if platform in ("facebook", "instagram") else 22)
        stat_bbox = draw.textbbox((0, 0), stat_text, font=stat_font)
        stat_w = (stat_bbox[2] - stat_bbox[0]) + 26
        draw.rounded_rectangle((88, body_bottom + 10, 88 + stat_w, body_bottom + 56), radius=10, fill="#f7af20", outline="#ffd56a", width=1)
        draw.text((100, body_bottom + 20), stat_text, font=stat_font, fill="#151515")
        row_font = _font(font_module, 24 if platform in ("facebook", "instagram") else 17)
        benefit_y = body_bottom + 72
        for row in _benefit_rows(content):
            label = _trim_for_card(row, 30)
            draw.text((88, benefit_y), ">>", font=row_font, fill="#ffb62b")
            draw.text((126, benefit_y), label, font=row_font, fill="#ffe4ae")
            benefit_y += 36 if platform in ("facebook", "instagram") else 26
        body_bottom = benefit_y

    if template not in ("premium_minimal", "power_shot"):
        chips = _metric_chips(content, limit=2)
        chip_y = body_bottom + 14
        chip_x = 88
        for chip in chips:
            label = _trim_for_card(chip, 36)
            bbox = draw.textbbox((0, 0), label, font=chip_font)
            w = (bbox[2] - bbox[0]) + 28
            draw.rounded_rectangle((chip_x, chip_y, chip_x + w, chip_y + 32), radius=14, outline="#8fcff5", width=1, fill="#153248")
            draw.text((chip_x + 14, chip_y + 8), label, font=chip_font, fill="#cde8ff")
            chip_x += w + 10
        body_bottom = chip_y + 42

    if product_name and template not in ("nike_premium", "power_shot"):
        body_bottom = _draw_wrapped(draw, f"Featured product: {product_name}", font=body_font, x=88, y=body_bottom + 10, width_chars=30 if platform in ("facebook", "instagram") else 38, fill="#f1dda9", line_gap=8)

    cta_right = width - (300 if template == "power_shot" and platform in ("facebook", "instagram") else 250 if template == "power_shot" else 380 if template == "nike_premium" and platform in ("facebook", "instagram") else 280 if template == "nike_premium" else 340 if platform in ("facebook", "instagram") else 260)
    if template == "power_shot" and platform in ("facebook", "instagram"):
        cta_top, cta_bottom = 944, 1022
    elif template == "power_shot":
        cta_top, cta_bottom = height - 120, height - 54
    elif template == "nike_premium" and platform in ("facebook", "instagram"):
        cta_top, cta_bottom = 842, 920
    elif platform in ("facebook", "instagram"):
        cta_top, cta_bottom = height - 130, height - 58
    elif template == "nike_premium":
        cta_top, cta_bottom = height - 126, height - 58
    else:
        cta_top, cta_bottom = height - 142, height - 76
    if template == "power_shot":
        draw.rounded_rectangle((88, cta_top, cta_right, cta_bottom), radius=18, fill="#c73613", outline="#ffcf52", width=1)
        draw.rounded_rectangle((88, cta_top, cta_right, cta_top + 4), radius=18, fill="#ffd13d")
    else:
        draw.rounded_rectangle((88, cta_top, cta_right, cta_bottom), radius=18, fill="#245e82", outline="#9bd7ff", width=1)
    cta_text = normalize_brand_text(cta)
    if not cta_text.endswith("->"):
        cta_text = f"{cta_text} ->"
    cta_bbox = draw.textbbox((0, 0), cta_text, font=footer_font)
    cta_x = 88 + max(0, ((cta_right - 88) - (cta_bbox[2] - cta_bbox[0])) // 2)
    draw.text((cta_x, cta_top + 21), cta_text, font=footer_font, fill="#f2fbff")

    if template == "power_shot":
        badge_font = _font(font_module, 16 if platform in ("facebook", "instagram") else 12)
        badge_x = width - 288 if platform in ("facebook", "instagram") else width - 220
        badge_y = 760 if platform in ("facebook", "instagram") else 392
        for label in _trust_badges(content):
            clean = _trim_for_card(label, 20)
            bbox = draw.textbbox((0, 0), clean, font=badge_font)
            bw = (bbox[2] - bbox[0]) + 26
            draw.rounded_rectangle((badge_x, badge_y, badge_x + bw, badge_y + 30), radius=14, fill="#12191f", outline="#f8c24f", width=1)
            draw.text((badge_x + 12, badge_y + 8), clean, font=badge_font, fill="#f7f9ff")
            badge_y += 36

    product_source = _resolve_product_source(content)
    product_image = _fetch_product_image(image_module, product_source)
    if product_image is not None:
        if template == "power_shot" and platform in ("facebook", "instagram"):
            target_w, target_h = 600, 600
            pos = (width - target_w - 56, 154)
        elif template == "nike_premium" and platform in ("facebook", "instagram"):
            target_w, target_h = 580, 580
            pos = (width - target_w - 64, 152)
        elif platform in ("facebook", "instagram"):
            target_w, target_h = 430, 430
            pos = (width - target_w - 72, 314)
        else:
            target_w, target_h = (420, 420) if template == "power_shot" else ((410, 410) if template == "nike_premium" else (384, 384))
            pos = (width - target_w - 48, 86)
        if platform in ("facebook", "instagram") and template not in ("power_shot", "nike_premium"):
            draw.rounded_rectangle((pos[0] - 18, pos[1] - 18, pos[0] + target_w + 18, pos[1] + target_h + 18), radius=28, fill="#152638")
            draw.rounded_rectangle((pos[0] - 8, pos[1] - 8, pos[0] + target_w + 8, pos[1] + target_h + 8), radius=22, fill="#1e3547")
        else:
            draw.rounded_rectangle((pos[0] - 14, pos[1] - 14, pos[0] + target_w + 14, pos[1] + target_h + 14), radius=24, fill="#17374e")
        if template == "power_shot":
            draw.rounded_rectangle((pos[0] - 14, pos[1] - 14, pos[0] + target_w + 14, pos[1] + target_h + 14), radius=24, fill="#1f1a16")
        image_copy = product_image.copy()
        image_copy.thumbnail((target_w, target_h))
        frame = image_module.new("RGBA", (target_w, target_h), (13, 34, 48, 0))
        offset_x = (target_w - image_copy.width) // 2
        offset_y = (target_h - image_copy.height) // 2
        if platform in ("facebook", "instagram"):
            shadow_w = max(180, int(image_copy.width * 0.70))
            shadow_h = max(26, int(image_copy.height * 0.10))
            shadow_x = pos[0] + max(0, (target_w - shadow_w) // 2)
            shadow_y = pos[1] + target_h - shadow_h - 10
            draw.ellipse((shadow_x, shadow_y, shadow_x + shadow_w, shadow_y + shadow_h), fill="#253746")
        frame.paste(image_copy, (offset_x, offset_y), image_copy if image_copy.mode == "RGBA" else None)
        canvas.paste(frame, pos, frame)
        border_color = "#ffbf3c" if template == "power_shot" else ("#93d8ff" if template in ("nike_premium", "premium_product_focus") else "#e0c48e")
        draw.rounded_rectangle((pos[0] - 10, pos[1] - 10, pos[0] + target_w + 10, pos[1] + target_h + 10), radius=22, outline=border_color, width=2)

    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    canvas.save(image_path, format="PNG", optimize=True)
    return True


def generate_visuals(content: dict[str, Any], visual_plan: dict[str, Any] | None = None) -> dict[str, str]:
    post_id = str(content.get("post_id") or "preview")
    visuals: dict[str, str] = {}
    plan = _safe_json_dict(visual_plan)
    template_name = _select_visual_template(plan, "facebook")
    image_strategy = str(plan.get("image_strategy") or os.environ.get("VISUAL_IMAGE_STRATEGY", "gemini_generated")).strip().lower()
    prefer_gemini = image_strategy in ("gemini_generated", "hybrid")
    prefer_product_overlay = image_strategy in ("product_photo_featured", "hybrid")
    gemini_available = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    render_engine = "local_render"
    repo_context = _load_visual_repo_context()
    repo_refs = repo_context.get("references", []) if isinstance(repo_context, dict) else []
    settings = repo_context.get("settings", {}) if isinstance(repo_context, dict) else {}
    resolved_override = _resolve_product_source(content, repo_context=repo_context)

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
            if rendered:
                render_engine = "gemini"
            if rendered:
                _compose_gemini_ad_overlay(content, platform, file_path, visual_plan=plan)

        if not rendered:
            rendered = _render_card(content, platform, file_path, visual_plan=plan)

        if rendered:
            visuals[platform] = file_path
    visuals["template"] = template_name
    visuals["image_strategy"] = image_strategy
    visuals["render_engine"] = render_engine
    visuals["gemini_available"] = str(gemini_available).lower()
    visuals["style_reference_count"] = str(len(repo_refs) if isinstance(repo_refs, list) else 0)
    visuals["db_visual_override_present"] = str(bool(str(settings.get("visual_product_image_override_url", "")).strip()) if isinstance(settings, dict) else False).lower()
    visuals["resolved_product_source_present"] = str(bool(str(resolved_override).strip())).lower()
    return visuals
