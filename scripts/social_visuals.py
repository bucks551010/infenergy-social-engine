from __future__ import annotations

import io
import os
from datetime import datetime, timezone
import hashlib
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


def _category_benefit_defaults(content: dict[str, Any]) -> list[str]:
    topic = str(content.get("topic") or "").lower()
    product_name = str(content.get("product_name") or "").lower()
    categories = " ".join(str(x or "") for x in (content.get("product_categories") or [])).lower() if isinstance(content.get("product_categories"), list) else str(content.get("product_categories") or "").lower()
    if any(token in product_name or token in categories for token in ("power bank", "charger", "travel power")):
        return [
            "Reliable backup charging",
            "Travel-ready power",
            "Device-safe recharge",
            "Everyday carry readiness",
        ]
    if any(token in product_name or token in categories for token in ("jump starter", "car", "vehicle")):
        return [
            "Roadside backup power",
            "Vehicle emergency support",
            "Portable emergency readiness",
            "Faster recovery on the road",
        ]
    if any(token in topic or token in categories for token in ("outage", "backup", "home backup")):
        return [
            "Must-run device backup",
            "Home outage readiness",
            "Spec-backed resilience",
            "Confidence before storms",
        ]
    return [
        "Outage-ready backup",
        "Real-world device fit",
        "Spec-backed confidence",
        "Faster preparedness",
    ]


def _benefit_rows(content: dict[str, Any]) -> list[str]:
    metrics = _metric_chips(content, limit=6)
    rows: list[str] = []
    for m in metrics:
        cleaned = re.sub(r"\s+", " ", normalize_brand_text(m)).strip()
        if cleaned and cleaned not in rows:
            rows.append(cleaned)
        if len(rows) >= 4:
            break
    for d in _category_benefit_defaults(content):
        if len(rows) >= 4:
            break
        if d not in rows:
            rows.append(d)
    return rows[:4]


def _benefit_chip_rows(content: dict[str, Any], exclude: list[str] | None = None, limit: int = 3) -> list[str]:
    """Qualitative outcome benefits, kept distinct from the numeric spec badge rows."""
    exclude_lower = {str(item or "").strip().lower() for item in (exclude or [])}
    rows: list[str] = []
    for benefit in _category_benefit_defaults(content):
        if benefit.lower() in exclude_lower or benefit in rows:
            continue
        rows.append(benefit)
        if len(rows) >= limit:
            break
    return rows


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
    if expected_headline == "" and expected_cta == "":
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
    v5_direction = _safe_json_dict(visual_plan.get("v5_direction"))
    v5_prompt = str(visual_plan.get("gemini_image_prompt") or "").strip()
    if v5_direction and v5_prompt:
        return v5_prompt[:3200]
    spec = _platform_visual_spec(platform)
    platform_key = platform.split("_", 1)[0]
    platform_cfg = _safe_json_dict((visual_plan.get("platform_overrides") or {}).get(platform))
    layout = _safe_json_dict(content.get("layout_grammar") or visual_plan.get("layout_grammar"))
    interpretation = _safe_json_dict((content.get("platform_interpretations") or visual_plan.get("platform_interpretations") or {}).get(platform_key))
    information = _safe_json_dict(content.get("information_priority") or visual_plan.get("information_priority"))
    benefit = _safe_json_dict(content.get("benefit_translation") or visual_plan.get("benefit_translation"))
    style_intent = str(visual_plan.get("style_intent") or "premium retail ad board for power products").strip()
    mood = str(visual_plan.get("mood") or "bold, high-contrast, conversion-focused, premium").strip()
    composition = str(layout.get("alignment") or platform_cfg.get("composition") or visual_plan.get("composition") or "structured copy column left, grounded product staging right").strip()
    key_hook = normalize_brand_text(str(content.get("selected_hook") or content.get("topic") or "Power planning"))
    topic = normalize_brand_text(str(content.get("topic") or ""))
    product_name = normalize_brand_text(str(content.get("product_name") or ""))
    stage = normalize_brand_text(str(content.get("funnel_stage") or "ATTENTION")).strip().upper()
    stage_label = _CONSUMER_STAGE_LABELS.get(stage, "Featured")
    cta = normalize_brand_text(str(content.get("selected_cta") or "Map your must-run devices and build your outage-ready setup."))
    headline_text, subline_text = _headline_lockup(content)
    banner_text = _proof_banner_text(content)
    spec_rows = _spec_badge_rows(content, limit=4)
    benefit_rows = _benefit_chip_rows(content, exclude=spec_rows, limit=3)
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
        exact_copy_lines.append(f"- Spec badge row {i} (bordered pill with a small matching icon glyph and a chevron mark): \"{row}\"")
    for i, benefit_item in enumerate(benefit_rows, start=1):
        exact_copy_lines.append(f"- Benefit chip {i} (small rounded pill directly beneath the spec badges, with a checkmark icon glyph, visually distinct in shape or fill from the spec badges): \"{benefit_item}\"")
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
        "proof banner pill, a vertical stack of bordered spec badge rows each with a small icon glyph and chevron mark, a row of "
        "benefit chips each with a checkmark icon glyph directly beneath the spec badges (only if any are listed above), a "
        "horizontal row of small trust badge pills (only if any are listed above), and a wide call-to-action banner. The headline "
        "must dominate the copy column as the single largest, heaviest-weight typographic element on the entire canvas — "
        "noticeably larger than every other text element, filling nearly the full available width. Give every text element "
        "strong contrast, generous padding, and crisp, legible, correctly kerned typography — no overlapping or clipped letters. "
        "Add one continuous visual connector (a light shaft, reflection line, or material accent) that bridges the copy column "
        "and the product zone so the whole canvas reads as a single unified image rather than two separate halves. "
    )
    cognition_layout_direction = (
        "Creative-decision layout rules are authoritative over generic template conventions: "
        f"primary focal point={layout.get('primary_focal_point', 'headline and benefit')}; "
        f"secondary focal point={layout.get('secondary_focal_point', 'product')}; "
        f"reading flow={layout.get('reading_flow', 'top-to-bottom')}; "
        f"product role={layout.get('product_role', 'supporting proof')}; "
        f"product placement={layout.get('product_placement', spec['product_zone'])}; "
        f"human role={layout.get('human_role', 'absent')}; human placement={layout.get('human_placement', 'none')}; "
        f"headline position={layout.get('headline_position', 'top-left')}; benefit position={layout.get('benefit_position', 'adjacent to focal proof')}; "
        f"proof position={layout.get('proof_position', 'supporting lower-third')}; CTA position={layout.get('cta_position', 'footer')}; "
        f"text density={layout.get('text_density', 'medium')}; spacing={layout.get('spacing_intent', 'generous separation')}; "
        f"negative space={layout.get('negative_space_intent', 'protect headline legibility')}. "
    )
    if layout.get("human_role") not in {"", "absent", "none"}:
        cognition_layout_direction += "Show a believable, task-relevant person only when they clarify the supported customer moment; never use generic smiling stock imagery or artificial emergency emotion. "
    else:
        cognition_layout_direction += "Do not add a person merely for decoration; let product, environment, and information carry the idea. "
    priority_direction = (
        f"Show only these must-show ideas prominently: {', '.join(map(str, information.get('MUST_SHOW', [])[:3])) or 'the approved headline and benefit'}. "
        f"Secondary visual support may use: {', '.join(map(str, information.get('SHOULD_SHOW', [])[:2])) or 'one supporting outcome'}. "
        f"Keep supporting facts subordinate: {', '.join(map(str, information.get('SUPPORTING', [])[:2])) or 'none'}. "
        "Do not render omitted information or add unapproved specifications. "
    )
    platform_direction = (
        f"Native {platform_key} creative interpretation: hook posture={interpretation.get('hook_posture', 'platform-appropriate')}; "
        f"format={interpretation.get('format', spec['aspect_ratio'])}; information density={interpretation.get('information_density', layout.get('text_density', 'medium'))}; "
        f"visual composition={interpretation.get('visual_composition', layout.get('alignment', 'clear hierarchy'))}; "
        f"product emphasis={interpretation.get('product_emphasis', layout.get('product_role', 'supporting'))}; "
        f"CTA expression={interpretation.get('cta_expression', 'clear next step')}. "
    )
    benefit_direction = f"The graphic should make the primary practical benefit '{benefit.get('PRACTICAL_BENEFIT', '')}' legible and imply the supported customer outcome '{benefit.get('CUSTOMER_OUTCOME', '')}', without printing abstract emotional slogans literally. "
    design_element_direction = (
        "Enrich the copy column with deliberate, restrained design elements beyond plain text blocks: give the spec badges and "
        "benefit chips small, simple line-icon glyphs matched to their meaning (a bolt for power output, a clock for runtime, a "
        "shield for durability/protection, a battery for capacity, a droplet for weather resistance, a leaf for solar/eco), a thin "
        "accent rule or gradient divider separating the headline block from the badge stack, and one subtle geometric accent "
        "motif (a faint diagonal light beam, a soft radial glow, or a thin corner chevron pattern) layered behind the copy column "
        "for depth. These accents must stay secondary and never compete with or crowd the text for attention. "
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
        f"{cognition_layout_direction}"
        f"{priority_direction}"
        f"{platform_direction}"
        f"{benefit_direction}"
        f"{design_element_direction}"
        f"{atmosphere_direction}"
        f"{campaign_direction}"
        f"{negative_direction}"
        "No watermarks, floating silhouettes, duplicate focal objects, or prominent distorted hands. Any people must look "
        "natural, emotionally credible, and remain secondary to the copy column and product. Output one finished, fully "
        "composited social ad image only."
    )


def _apply_v5_text_overlay(image: Any, direction: dict[str, Any]) -> tuple[Any, str]:
    """Composite approved text after image generation so model typography never reaches publication."""
    overlay = direction.get("text_overlay") if isinstance(direction.get("text_overlay"), dict) else {}
    text = normalize_brand_text(str(overlay.get("text") or "")).strip()
    if not overlay.get("enabled") or not text:
        return image, ""
    image_module, draw_module, font_module = _load_pillow()
    if image_module is None or draw_module is None or font_module is None:
        return image, "pillow_unavailable_for_overlay"
    width, height = image.size
    margin = max(24, int(min(width, height) * float(overlay.get("safe_margin_ratio") or 0.08)))
    max_width = width - margin * 2
    font_size = max(28, int(min(width, height) * 0.072))
    try:
        font = font_module.truetype("DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = font_module.load_default()
    draw = draw_module.Draw(image, "RGBA")
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > 4:
        return image, "overlay_text_exceeds_line_budget"
    line_height = int(font_size * 1.2)
    block_height = len(lines) * line_height + margin
    if block_height > height * 0.45:
        return image, "overlay_text_exceeds_safe_area"
    placement = str(overlay.get("placement") or "upper third").lower()
    y_start = height - margin - block_height if "bottom" in placement else margin
    draw.rounded_rectangle((margin // 2, y_start - margin // 2, width - margin // 2, y_start + block_height), radius=12, fill=(10, 18, 26, 190))
    for index, line in enumerate(lines):
        draw.text((margin, y_start + index * line_height), line, font=font, fill=(255, 255, 255, 255))
    return image, ""


def _generate_gemini_full_creative(content: dict[str, Any], platform: str, visual_plan: dict[str, Any], output_path: str) -> tuple[bool, str, dict[str, Any]]:
    started_at = datetime.now(timezone.utc).isoformat()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    metadata: dict[str, Any] = {
        "visual_generation_attempted": True,
        "visual_generation_mode": "gemini_generated",
        "visual_provider": "gemini",
        "visual_model": "",
        "render_target_platform": platform,
        "candidate_id": str(content.get("post_id") or ""),
        "final_post_id": str(content.get("post_id") or ""),
        "generation_started_at": started_at,
        "retry_count": 0,
        "fallback_used": False,
    }

    def completed(success: bool, reason: str, *, model: str = "", retry_count: int = 0) -> tuple[bool, str, dict[str, Any]]:
        artifact_exists = os.path.isfile(output_path)
        dimensions: list[int] | None = None
        if artifact_exists:
            image_module, _, _ = _load_pillow()
            if image_module is not None:
                try:
                    with image_module.open(output_path) as image:
                        dimensions = list(image.size)
                except Exception:
                    pass
        sanitized_reason = re.sub(r"\s+", " ", str(reason or "unknown_render_failure")).strip()[:240]
        sanitized_reason = sanitized_reason.replace(api_key, "[redacted]") if api_key else sanitized_reason
        lower_reason = sanitized_reason.lower()
        if success:
            error_class = ""
        elif "no_image_bytes" in lower_reason:
            error_class = "EMPTY_RESPONSE"
        elif "timeout" in lower_reason:
            error_class = "TIMEOUT"
        elif "429" in lower_reason or "rate" in lower_reason:
            error_class = "RATE_LIMIT"
        elif "401" in lower_reason or "403" in lower_reason or "api_key" in lower_reason or "auth" in lower_reason:
            error_class = "AUTH_ERROR"
        elif "pillow" in lower_reason or "unreadable" in lower_reason or "format" in lower_reason:
            error_class = "UNSUPPORTED_FORMAT"
        elif "save" in lower_reason or "write" in lower_reason or "permission" in lower_reason:
            error_class = "FILE_WRITE_ERROR"
        elif "plate_quality" in lower_reason or "semantic_quality" in lower_reason:
            error_class = "RENDER_ERROR"
        else:
            error_class = "PROVIDER_ERROR"
        metadata.update({
            "visual_model": model,
            "generation_finished_at": datetime.now(timezone.utc).isoformat(),
            "generation_status": "success" if success and artifact_exists else "failed",
            "artifact_path": output_path if artifact_exists else "",
            "artifact_exists": artifact_exists,
            "artifact_size": os.path.getsize(output_path) if artifact_exists else 0,
            "artifact_dimensions": dimensions,
            "fallback_reason": "" if success else sanitized_reason,
            "provider_error_class": error_class,
            "provider_error_message_sanitized": "" if success else sanitized_reason,
            "render_error": "" if success else sanitized_reason,
            "retry_count": retry_count,
        })
        return success and artifact_exists, sanitized_reason, metadata

    if not api_key:
        return completed(False, "no_api_key")

    prompt = _build_gemini_image_prompt(content, platform, visual_plan)
    metadata["visual_prompt_hash"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    v5_direction = _safe_json_dict(visual_plan.get("v5_direction"))
    v5_text_forward = bool((_safe_json_dict(v5_direction.get("text_overlay"))).get("enabled"))
    expected_headline, _ = _headline_lockup(content) if not v5_text_forward else ("", "")
    expected_cta = normalize_brand_text(str(content.get("selected_cta") or "Learn more")) if not v5_text_forward else ""
    repo_context = _load_visual_repo_context()
    repo_refs = repo_context.get("references", []) if isinstance(repo_context, dict) else []
    reasons_by_model: dict[str, str] = {}
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)
        model_candidates = [
            str(os.environ.get("GEMINI_IMAGE_MODEL", "")).strip(),
            "gemini-2.5-flash-image",
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
        metadata["source_product_asset"] = product_source
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
                retry_note = "" if attempt == 0 else (" Previous attempt failed automated quality checks. Preserve the requested aspect ratio and produce a physically credible scene." if v5_direction else " Previous attempt failed automated quality checks. Keep every listed text string exact, legible, and correctly spelled, and preserve the requested aspect ratio.")
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
                        reasons_by_model[model_name] = "no_image_bytes"
                        continue

                    image_module, _, _ = _load_pillow()
                    if image_module is None:
                        return False, "pillow_unavailable"

                    generated = image_module.open(io.BytesIO(raw)).convert("RGB")
                    accepted, plate_reasons = _gemini_plate_quality(generated, platform)
                    if not accepted:
                        reasons_by_model[model_name] = f"plate_quality_rejected:{','.join(plate_reasons)}"
                        continue
                    accepted, semantic_reasons = _gemini_semantic_plate_quality(client, types, raw, platform, expected_headline, expected_cta)
                    if not accepted:
                        reasons_by_model[model_name] = f"semantic_quality_rejected:{','.join(semantic_reasons)}"
                        continue
                    generated = _resize_cover(generated, spec["target"], image_module)
                    if generated.size != spec["target"]:
                        reasons_by_model[model_name] = "resize_mismatch"
                        continue
                    generated, overlay_error = _apply_v5_text_overlay(generated, v5_direction)
                    if overlay_error:
                        reasons_by_model[model_name] = overlay_error
                        continue
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    generated.save(output_path, format="PNG", optimize=True)
                    return completed(True, "ok", model=model_name, retry_count=attempt)
                except Exception as e:
                    reasons_by_model[model_name] = f"api_exception:{type(e).__name__}:{str(e)[:160]}"
                    continue
        summary = "; ".join(f"{model}={reason}" for model, reason in reasons_by_model.items()) or "no_attempts_made"
        return completed(False, summary, model=next(reversed(reasons_by_model), ""), retry_count=1)
    except Exception as e:
        return completed(False, f"setup_exception:{type(e).__name__}:{str(e)[:160]}")


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


def review_rendered_visual(path: str, platform: str) -> dict[str, Any]:
    """Inspect the saved PNG so publication is gated on a real artifact, not only its plan."""
    issues: list[str] = []
    dimensions: list[int] | None = None
    file_size = 0
    image_module, _, _ = _load_pillow()
    expected_size = _platform_visual_spec(platform)["target"]
    if not path or not os.path.isfile(path):
        issues.append("rendered_asset_unavailable")
    elif image_module is None:
        issues.append("pillow_unavailable")
    else:
        try:
            file_size = os.path.getsize(path)
            if file_size <= 0:
                issues.append("rendered_asset_empty")
            with image_module.open(path) as image:
                image.load()
                dimensions = list(image.size)
                if image.size != expected_size:
                    issues.append("rendered_dimensions_mismatch")
                if image.convert("RGB").getbbox() is None:
                    issues.append("rendered_asset_blank")
        except Exception as exc:
            issues.append(f"rendered_asset_unreadable:{type(exc).__name__}")
    verdict = "PASS" if not issues else "REGENERATE_VISUAL"
    return {
        "verdict": verdict,
        "issues": issues,
        "artifact_path": path,
        "inspected_path": path,
        "dimensions": dimensions,
        "file_size": file_size,
        "expected_dimensions": list(expected_size),
        "inspected_at": datetime.now(timezone.utc).isoformat(),
    }


def _save_product_photo_fallback(source: str, output_path: str, platform: str) -> bool:
    """Create a publishable platform artifact from an approved product source."""
    image_module, _, _ = _load_pillow()
    if image_module is None:
        return False
    raw, _ = _read_image_bytes_any(source)
    if not raw:
        return False
    try:
        with image_module.open(io.BytesIO(raw)) as source_image:
            image = source_image.convert("RGB")
            artifact = _resize_cover(image, _platform_visual_spec(platform)["target"], image_module)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            artifact.save(output_path, format="PNG", optimize=True)
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False


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
    artifact_reviews: dict[str, dict[str, Any]] = {}
    visual_generation: dict[str, dict[str, Any]] = {}
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
        rendered, reason, metadata = _generate_gemini_full_creative(content, platform, plan, file_path)
        visual_generation[platform] = metadata
        if rendered:
            render_engines[platform] = "gemini"
            product_overlay_applied[platform] = product_specific_source_present
            visuals[platform] = file_path
            artifact_reviews[platform] = review_rendered_visual(file_path, platform)
            v5_direction = _safe_json_dict(plan.get("v5_direction"))
            if v5_direction:
                try:
                    from agents import visual_qa_reviewer
                    visual_generation[platform]["v5_qa"] = visual_qa_reviewer.run(
                        DATA_DIR, image_path=file_path, platform=platform, direction=v5_direction
                    )
                except Exception as exc:
                    visual_generation[platform]["v5_qa"] = {"direction_fidelity": "UNAVAILABLE", "reason": type(exc).__name__}
        elif resolved_override and _save_product_photo_fallback(resolved_override, file_path, platform):
            render_engines[platform] = "approved_product_photo"
            product_overlay_applied[platform] = True
            fallback_reasons[platform] = reason
            visual_generation[platform] = {
                **metadata,
                "generation_status": "fallback_product_photo",
                "artifact_path": file_path,
                "artifact_exists": True,
                "fallback_used": True,
                "fallback_source": "approved_product_photo",
            }
            visuals[platform] = file_path
            artifact_reviews[platform] = review_rendered_visual(file_path, platform)
        else:
            render_engines[platform] = "failed"
            product_overlay_applied[platform] = False
            fallback_reasons[platform] = reason
            artifact_reviews[platform] = review_rendered_visual("", platform)

    visuals["template"] = template_name
    visuals["image_strategy"] = image_strategy
    unique_engines = set(render_engines.values())
    visuals["render_engine"] = next(iter(unique_engines)) if len(unique_engines) == 1 else "mixed"
    visuals["render_engines"] = render_engines
    visuals["product_overlay_applied"] = product_overlay_applied
    visuals["fallback_reasons"] = fallback_reasons
    visuals["visual_generation"] = visual_generation
    visuals["artifact_reviews"] = artifact_reviews
    visuals["gemini_available"] = str(gemini_available).lower()
    visuals["style_reference_count"] = str(len(repo_refs) if isinstance(repo_refs, list) else 0)
    visuals["db_visual_override_present"] = str(bool(str(settings.get("visual_product_image_override_url", "")).strip()) if isinstance(settings, dict) else False).lower()
    visuals["resolved_product_source_present"] = str(bool(str(resolved_override).strip())).lower()
    visuals["product_specific_source_present"] = str(product_specific_source_present).lower()
    return visuals
