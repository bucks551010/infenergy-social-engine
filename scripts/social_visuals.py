from __future__ import annotations

import io
import os
import re
import json
import base64
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


def _proof_banner_text(content: dict[str, Any]) -> str:
    """Keyword-derived proof/urgency phrase, distinct from the raw spec numbers in the badge rows."""
    topic = normalize_brand_text(str(content.get("topic") or ""))
    hook = normalize_brand_text(str(content.get("selected_hook") or ""))
    text = f"{topic} {hook}".lower()
    if any(k in text for k in ("outage", "backup", "blackout")):
        return "OUTAGE READY"
    if any(k in text for k in ("charge", "charging", "recharge")):
        return "FAST RECHARGE"
    if any(k in text for k in ("travel", "portable", "carry")):
        return "TRAVEL READY"
    return "SMART POWER"


def _spec_badge_rows(content: dict[str, Any], limit: int = 4) -> list[str]:
    """Real, verified specs first (accuracy); only fall back to generic phrasing when none exist."""
    metrics = content.get("product_metrics", []) if isinstance(content, dict) else []
    rows: list[str] = []
    if isinstance(metrics, list):
        for raw_metric in metrics:
            cleaned = re.sub(r"\s+", " ", normalize_brand_text(str(raw_metric or ""))).strip()
            if cleaned and cleaned not in rows:
                rows.append(cleaned)
            if len(rows) >= limit:
                break
    if not rows:
        rows = _benefit_rows(content)[:limit]
    return rows[:limit]


def _trust_badges(content: dict[str, Any]) -> list[str]:
    raw_badges = content.get("trust_badges", []) if isinstance(content, dict) else []
    if not isinstance(raw_badges, list):
        return []
    badges: list[str] = []
    for raw_badge in raw_badges:
        badge = re.sub(r"\s+", " ", normalize_brand_text(str(raw_badge or ""))).strip()
        if badge and badge.lower() not in {item.lower() for item in badges}:
            badges.append(badge)
    return badges[:4]


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
    product_image = str(content.get("product_image_url") or "").strip()
    if product_image:
        return product_image

    for key in ("product_image_candidates", "category_image_candidates"):
        candidates = content.get(key, []) if isinstance(content, dict) else []
        if isinstance(candidates, list):
            for raw_candidate in candidates:
                candidate = str(raw_candidate or "").strip()
                if candidate:
                    return candidate

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

    return ""


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


def _gemini_semantic_plate_quality(
    client: Any,
    types: Any,
    raw: bytes,
    platform: str,
    expected_headline: str = "",
    expected_cta: str = "",
) -> tuple[bool, list[str]]:
    enabled = str(os.environ.get("GEMINI_VISUAL_QA_ENABLED", "true")).strip().lower() not in {"0", "false", "no"}
    if not enabled:
        return True, []
    spec = _platform_visual_spec(platform)
    review_prompt = (
        "Review this finished social ad card. It must already contain rendered, legible on-image text: "
        "an \"Infenergy Power\" brand wordmark, a headline reading approximately "
        f"'{expected_headline}', a call-to-action reading approximately '{expected_cta}', and a real "
        f"product staged in the {spec['product_zone']}. Return JSON only with booleans for: "
        "text_missing_or_illegible, headline_mismatch, cta_missing, product_missing, "
        "gibberish_or_garbled_text, looks_like_generic_ai_poster. Treat misspelled, duplicated, or "
        "nonsensical letters as gibberish_or_garbled_text=true."
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
                "text_missing_or_illegible",
                "headline_mismatch",
                "cta_missing",
                "product_missing",
                "gibberish_or_garbled_text",
                "looks_like_generic_ai_poster",
            )
            reasons = [key for key in failure_keys if review.get(key) is True]
            return not reasons, reasons
        except Exception:
            continue
    return True, ["semantic_review_unavailable"]


_CONSUMER_STAGE_LABELS = {
    "ATTENTION": "Featured",
    "EDUCATION": "New Arrival",
    "DESIRE": "Popular Choice",
    "TRUST": "Verified Fit",
    "CONVERSION": "Ready to Ship",
}


def _build_gemini_image_prompt(content: dict[str, Any], platform: str, visual_plan: dict[str, Any]) -> str:
    spec = _platform_visual_spec(platform)
    platform_cfg = _safe_json_dict((visual_plan.get("platform_overrides") or {}).get(platform))
    style_intent = str(visual_plan.get("style_intent") or "premium retail ad board for power products").strip()
    mood = str(visual_plan.get("mood") or "bold, high-contrast, conversion-focused, premium").strip()
    composition = str(platform_cfg.get("composition") or visual_plan.get("composition") or "structured copy column left, grounded product staging right").strip()
    key_hook = normalize_brand_text(str(content.get("selected_hook") or content.get("topic") or "Power planning"))
    topic = normalize_brand_text(str(content.get("topic") or ""))
    product_name = normalize_brand_text(str(content.get("product_name") or ""))
    stage = normalize_brand_text(str(content.get("funnel_stage") or "ATTENTION")).strip().upper()
    stage_label = _CONSUMER_STAGE_LABELS.get(stage, "Featured")
    cta = normalize_brand_text(str(content.get("selected_cta") or "Map your must-run devices and build your outage-ready setup."))
    headline_text, subline_text = _headline_lockup(content)
    banner_text = _proof_banner_text(content)
    spec_rows = _spec_badge_rows(content, limit=4)
    trust_badges = _trust_badges(content)

    exact_copy_lines = [
        "Render exactly this on-image copy, spelled exactly as given, and nothing else. Do not invent, "
        "alter, translate, or add any other text, numbers, specs, badges, or claims:",
        "- Brand wordmark (top-left, small and understated): \"Infenergy Power\"",
        f"- Small consumer-facing status tag pill (beneath the wordmark, never show internal marketing-funnel jargon): \"{stage_label}\"",
        f"- Headline (the single largest, boldest element on the entire canvas, filling most of the copy column's width): \"{headline_text}\"",
        f"- Subheading (directly below the headline, one line, do not wrap): \"{subline_text}\"",
        f"- Proof/urgency banner pill: \"{banner_text}\"",
    ]
    for i, row in enumerate(spec_rows, start=1):
        exact_copy_lines.append(f"- Spec badge row {i} (bordered pill with a small chevron mark): \"{row}\"")
    for i, badge in enumerate(trust_badges, start=1):
        exact_copy_lines.append(f"- Trust badge {i} (small pill in a horizontal row): \"{badge}\"")
    exact_copy_lines.append(f"- Call-to-action banner (bottom of the copy column): \"{cta}\"")
    exact_copy_block = "\n".join(exact_copy_lines)

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
        f"Stage the real product physically and to true scale in the {spec['product_zone']}, integrated into the scene as a real "
        "object someone could touch — never as a floating listing card, phone screenshot, marketplace thumbnail, or boxed-in UI panel. "
        "If a reference product photo is attached as an input image, reproduce that exact real product's true shape, proportions, "
        "color, ports, and physical details from the attached photo — do not invent a different or generic device. However, you "
        "must strip and replace any third-party manufacturer logo, competitor brand name, model badge, or printed text visible on "
        "the reference photo's product surface with a clean, unbranded matte surface (or, if a small logo is unavoidable, the "
        "Infenergy Power wordmark only) — the published creative must never display any competitor or OEM brand name. If no "
        "reference photo is attached, render a plausible, physically credible device consistent with the product context below, "
        "with clean unbranded surfaces. "
    )
    layout_direction = (
        f"Compose a finished, ready-to-publish premium social ad card that uses 100% of the canvas — every corner and edge must "
        "carry deliberate visual weight, with zero flat, empty, or unfinished-looking space anywhere in the frame, for the "
        f"{spec['copy_zone']}. This is a complete creative, not a background plate. "
        "Structure the copy column top-to-bottom exactly as listed above: brand wordmark, status tag pill, headline, subheading, "
        "proof banner pill, a vertical stack of bordered spec badge rows each with a small chevron mark, a horizontal row of "
        "small trust badge pills (only if any are listed above), and a wide call-to-action banner. The headline must dominate the "
        "copy column as the single largest, heaviest-weight typographic element on the entire canvas — noticeably larger than "
        "every other text element, filling nearly the full available width. Give every text element strong contrast, generous "
        "padding, and crisp, legible, correctly kerned typography — no overlapping or clipped letters. Add one continuous visual "
        "connector (a light shaft, reflection line, or material accent) that bridges the copy column and the product zone so the "
        "whole canvas reads as a single unified image rather than two separate halves. "
    )
    atmosphere_direction = (
        "Build atmosphere with one coherent cinematic light direction, premium material textures, layered shadows, restrained "
        "reflections, and rich in-focus environmental detail filling the product zone completely — the background scene behind "
        "and around the product must feel alive and specific to the setting described below, never generic, plain, or blank. "
    )
    campaign_direction = (
        "This should feel like a premium, top-tier performance-campaign creative: visually confident, physically credible, "
        "and fully finished — this exact image will be published as-is with no further editing. "
    )
    negative_direction = (
        "Do not make it look like a cheap flyer, Canva template, ecommerce tile, generic infographic, cartoon, or synthetic "
        "AI poster. Do not render the product inside a phone mockup, marketplace listing card, floating UI panel, price tag, or "
        "screenshot-style frame. Do not show any competitor or third-party manufacturer logo, brand name, or model number on the "
        "product or anywhere in the frame. Avoid misspellings, garbled or duplicated letters, invented specs, extra claims, "
        "random decoration, muddy contrast, excessive glow, impossible reflections, or visual clutter. "
    )
    return (
        "Create a finished, ready-to-publish premium social ad creative for Infenergy Power — the complete image, "
        "including all on-image text, badges, and the product, not a background plate for later editing. "
        f"Plan suggestions, subordinate to the exact copy and layout rules below: style '{style_intent}', mood '{mood}', composition '{composition}'. "
        f"{style_ref_line}"
        f"Platform: {platform}. Hook context: {key_hook}. Topic context: {topic}. "
        f"Product context: {product_name or 'portable/home power solution'}. Funnel stage: {stage}. "
        f"{exact_copy_block}\n"
        f"Optional approved scene brief, subordinate to every rule here: {plan_prompt or 'none'}. "
        "Use a restrained brand palette: charcoal #15191d, deep navy #112d44, amber #f7a30f, and warm gold #ffd469. Avoid neon colors and dominant purple. "
        f"Build a {spec['scene']}. "
        f"{stage_direction} "
        f"{material_direction}"
        f"{product_stage_direction}"
        f"{layout_direction} "
        f"{atmosphere_direction}"
        f"{campaign_direction}"
        f"{negative_direction}"
        "No watermarks, floating silhouettes, duplicate focal objects, or prominent distorted hands. Any people must look "
        "natural, emotionally credible, and remain secondary to the copy column and product. Output one finished, fully "
        "composited social ad image only."
    )


def _generate_gemini_full_creative(content: dict[str, Any], platform: str, visual_plan: dict[str, Any], output_path: str) -> bool:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False

    prompt = _build_gemini_image_prompt(content, platform, visual_plan)
    expected_headline, _ = _headline_lockup(content)
    expected_cta = normalize_brand_text(str(content.get("selected_cta") or "Learn more"))
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

        product_source = _resolve_product_source(content, repo_context=repo_context)
        if product_source:
            product_bytes, product_mime = _read_image_bytes_any(product_source)
            product_bytes, product_mime = _normalize_reference_image(product_bytes)
            if product_bytes:
                try:
                    reference_parts.append(types.Part.from_bytes(data=product_bytes, mime_type=product_mime or "image/jpeg"))
                except Exception:
                    pass

        for model_name in model_candidates:
            if not model_name or model_name in seen_models:
                continue
            seen_models.add(model_name)
            for attempt in range(2):
                retry_note = "" if attempt == 0 else " Previous attempt failed automated quality checks. Keep every listed text string exact, legible, and correctly spelled, and preserve the requested aspect ratio."
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
                    accepted, _ = _gemini_semantic_plate_quality(client, types, raw, platform, expected_headline, expected_cta)
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


def generate_visuals(content: dict[str, Any], visual_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    post_id = str(content.get("post_id") or "preview")
    visuals: dict[str, Any] = {}
    plan = _safe_json_dict(visual_plan)
    template_name = _select_visual_template(plan, "facebook")
    image_strategy = str(plan.get("image_strategy") or os.environ.get("VISUAL_IMAGE_STRATEGY", "gemini_generated")).strip().lower()
    gemini_available = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    render_engines: dict[str, str] = {}
    product_overlay_applied: dict[str, bool] = {}
    fallback_reasons: dict[str, str] = {}
    repo_context = _load_visual_repo_context()
    repo_refs = repo_context.get("references", []) if isinstance(repo_context, dict) else []
    settings = repo_context.get("settings", {}) if isinstance(repo_context, dict) else {}
    resolved_override = _resolve_product_source(content, repo_context=repo_context)
    product_specific_source_present = bool(
        str(content.get("product_image_url") or "").strip()
        or any(str(item or "").strip() for item in (content.get("product_image_candidates", []) or []))
    )

    os.makedirs(VISUAL_DIR, exist_ok=True)
    for platform in ("facebook", "instagram", "linkedin"):
        file_name = f"{post_id}_{platform}.png"
        file_path = os.path.join(VISUAL_DIR, file_name)

        # Gemini generates the entire finished creative directly. There is no HTML
        # preview and no local PIL fallback: if Gemini fails, the platform gets no visual.
        rendered = _generate_gemini_full_creative(content, platform, plan, file_path)
        if rendered:
            render_engines[platform] = "gemini"
            product_overlay_applied[platform] = product_specific_source_present
            visuals[platform] = file_path
        else:
            render_engines[platform] = "failed"
            product_overlay_applied[platform] = False
            fallback_reasons[platform] = "gemini_unavailable_or_rejected_no_fallback"

    visuals["template"] = template_name
    visuals["image_strategy"] = image_strategy
    unique_engines = set(render_engines.values())
    visuals["render_engine"] = next(iter(unique_engines)) if len(unique_engines) == 1 else "mixed"
    visuals["render_engines"] = render_engines
    visuals["product_overlay_applied"] = product_overlay_applied
    visuals["fallback_reasons"] = fallback_reasons
    visuals["gemini_available"] = str(gemini_available).lower()
    visuals["style_reference_count"] = str(len(repo_refs) if isinstance(repo_refs, list) else 0)
    visuals["db_visual_override_present"] = str(bool(str(settings.get("visual_product_image_override_url", "")).strip()) if isinstance(settings, dict) else False).lower()
    visuals["resolved_product_source_present"] = str(bool(str(resolved_override).strip())).lower()
    visuals["product_specific_source_present"] = str(product_specific_source_present).lower()
    return visuals
