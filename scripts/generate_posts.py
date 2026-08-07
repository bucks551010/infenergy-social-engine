import os
import json
import random
import hashlib
import csv
import glob
import re
import uuid
from datetime import date, datetime, timezone, timedelta
from google import genai
from google.genai import types
from campaign_runtime import (
    apply_claim_guardrails,
    choose_cta_for_stage,
    cta_is_valid_for_stage,
    ensure_campaign_runtime_files,
    load_cta_library,
    load_funnel_config,
    score_generated_content,
    select_weekly_sequence,
    stable_text_hash,
    stage_for_slot,
)
from generate_hooks import select_hook
from anti_repeat import load_anti_repeat_windows
from build_utm_url import build_utm_url
from social_visuals import generate_visuals, normalize_brand_content, normalize_brand_text

FUNNEL_STAGES = {"ATTENTION", "EDUCATION", "DESIRE", "TRUST", "CONVERSION"}

SITE_URL = os.environ.get("WP_URL", "https://www.infenergypower.com")
# DATA_DIR can be overridden by Railway volume mount (set DATA_DIR=/app/data in Railway Variables)
BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DATA_DIR = os.environ.get("DATA_DIR", BASE_DATA_DIR)

DEFAULT_TOPIC_QUEUE = {
    "pillars": [
        "solar_savings",
        "battery_storage",
        "energy_independence",
        "promotions",
    ],
    "topics": {
        "solar_savings": [
            "How solar panels can reduce monthly utility costs",
            "The real ROI of residential solar in 2026",
            "How net metering can offset electricity bills",
        ],
        "battery_storage": [
            "How home batteries keep essentials running during outages",
            "Battery capacity basics: what can 1kWh actually power?",
            "When battery backup beats a traditional generator",
        ],
        "energy_independence": [
            "How to protect your home from rising energy rates",
            "Why energy resilience matters in severe weather seasons",
            "How solar plus storage reduces grid dependency",
        ],
        "promotions": [
            "Book a free energy consultation and savings estimate",
            "How to start your solar evaluation in under 15 minutes",
            "What to expect from your first energy strategy call",
        ],
    },
}

DEFAULT_CATEGORY_IMAGE_FALLBACKS = {
    "portable power": "https://infenergypower.com/wp-content/uploads/2024/11/IMG_4214.png",
    "travel power": "https://infenergypower.com/wp-content/uploads/2024/12/IMG_4806.jpg",
    "solar generators": "https://infenergypower.com/wp-content/uploads/2024/08/1.png",
    "solar panels": "https://infenergypower.com/wp-content/uploads/2025/08/AF-S400A1-1.jpg",
    "home backup": "https://infenergypower.com/wp-content/uploads/2025/06/a0fc14752770c414bd090fa2f986454-scaled.png",
    "emergency power": "https://infenergypower.com/wp-content/uploads/2022/05/1642710505878.png",
}

CONVERSION_COPY_BRIEF = """
You are the conversion copywriter for Infenergy Power.

Objective:
- Stop the scroll.
- Make the reader recognize a real situation.
- Educate before selling.
- Connect the product as a logical solution.
- Use only verified product facts.
- Build trust and reduce hesitation.
- End with one clear next action.

Writing requirements:
- Focus on one primary angle and one specific customer moment.
- Use this sequence: Attention -> Problem/Desire -> Consequence -> Education -> Product fit -> Verified proof -> Objection reduction -> CTA.
- Do not invent runtime, appliance compatibility, savings, certifications, durability, warranty, or unsupported specs.
- Avoid generic ad language and banned cliches (for example: game changer, revolutionary, unlock the power of, don't miss out).
- Keep platform-native tone:
    - Facebook: conversational, educational, community trust.
    - Instagram: short high-impact first line, visual relevance, readable line breaks.
    - LinkedIn: authority and business continuity perspective, professional credibility.

Brand:
- Use Infenergy naming and trustworthy practical tone.
""".strip()

VISUAL_DIRECTOR_BRIEF = """
You are the visual prompt director for Infenergy Power social creatives.

Goal:
- Produce visual direction that increases click-through and trust.
- Ensure image concept supports the copy angle, funnel stage, and CTA.
- Decide when to feature product photos versus concept visuals.

Rules:
- Keep visuals premium, realistic, and brand-safe.
- Prefer practical scenarios (home backup, preparedness, energy confidence) over abstract art.
- If product image quality is strong, suggest a hybrid composition that highlights the product naturally.
- Never include text baked into the image unless it is short and legible.
- Return only the requested JSON shape.
""".strip()

AGENT_CONFERENCE_BRIEF = """
You are facilitating a conference room discussion between specialized creative agents for Infenergy Power.

Participants:
- Copywriter Agent: maximizes clarity, persuasion, and conversion.
- Visual Director Agent: ensures image concept and composition amplify the message.
- Product Truth Agent: blocks unsupported claims and keeps facts verifiable.
- Platform Editor Agent: adapts execution for Facebook, Instagram, and LinkedIn behavior.

Task:
- Have the agents debate strengths, weaknesses, and risks in the current draft.
- Produce a unified plan to improve collective performance.
- Keep recommendations practical and directly applicable in this run.

Constraints:
- No invented product specs, warranties, or guarantees.
- Keep tone trustworthy and practical.
- Prefer specific improvements over generic feedback.
""".strip()

PREGEN_CONFERENCE_BRIEF = """
You are facilitating a pre-generation conference room meeting for Infenergy Power before any draft is written.

Participants:
- Copywriter Agent
- Visual Director Agent
- Product Truth Agent
- Platform Editor Agent

Objective:
- Decide the single best post direction for this run before writing starts.
- Agree on the strongest hook angle, CTA framing, and visual focus.
- Reduce duplication risk by choosing a fresh direction versus recent posts.

Constraints:
- Use only supported product facts.
- Keep recommendations practical, specific, and conversion-oriented.
- Return only JSON in the requested shape.
""".strip()


def ensure_runtime_data() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    ensure_campaign_runtime_files()

    topic_primary = os.path.join(DATA_DIR, "topic_queue.json")
    topic_fallback = os.path.join(BASE_DATA_DIR, "topic_queue.json")
    if not os.path.exists(topic_primary) and not os.path.exists(topic_fallback):
        with open(topic_primary, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_TOPIC_QUEUE, f, indent=2)

    history_primary = os.path.join(DATA_DIR, "post_history.json")
    history_fallback = os.path.join(BASE_DATA_DIR, "post_history.json")
    if not os.path.exists(history_primary) and not os.path.exists(history_fallback):
        with open(history_primary, "w", encoding="utf-8") as f:
            json.dump({"posts": []}, f, indent=2)


def _read_json_with_fallback(filename: str) -> dict:
    primary = os.path.join(DATA_DIR, filename)
    fallback = os.path.join(BASE_DATA_DIR, filename)
    for path in (primary, fallback):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    if filename == "post_history.json":
        return {"posts": []}

    if filename == "topic_queue.json":
        return DEFAULT_TOPIC_QUEUE

    raise FileNotFoundError(f"Missing required JSON file: {filename}")


def load_topic_queue() -> dict:
    return _read_json_with_fallback("topic_queue.json")


def load_history() -> dict:
    return _read_json_with_fallback("post_history.json")


def save_history(history: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    target = os.path.join(DATA_DIR, "post_history.json")
    temp = target + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    os.replace(temp, target)


def _load_latest_marketing_strategy() -> dict:
    paths = []
    for base in (DATA_DIR, BASE_DATA_DIR):
        paths.extend(glob.glob(os.path.join(base, "marketing", "marketing_strategy_*.json")))
        # Backward compatibility with older artifact name.
        paths.extend(glob.glob(os.path.join(base, "marketing", "marketing_bundle_*.json")))

    if not paths:
        return {}

    latest = max(paths, key=os.path.getmtime)
    try:
        with open(latest, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_latest_structured_campaign() -> dict:
    paths = []
    for base in (DATA_DIR, BASE_DATA_DIR):
        paths.extend(glob.glob(os.path.join(base, "marketing", "campaigns", "campaign_*.json")))
    if not paths:
        return {}
    latest = max(paths, key=os.path.getmtime)
    try:
        with open(latest, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _is_usable_image_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        return False
    if any(x in u for x in ("placeholder", "no-image", "default")):
        return False
    return True


def _load_category_image_fallbacks() -> dict[str, str]:
    custom = os.environ.get("IG_CATEGORY_FALLBACKS_JSON", "").strip()
    merged = dict(DEFAULT_CATEGORY_IMAGE_FALLBACKS)
    if custom:
        try:
            parsed = json.loads(custom)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    key = str(k).strip().lower()
                    val = str(v).strip()
                    if key and _is_usable_image_url(val):
                        merged[key] = val
        except Exception:
            pass
    return merged


def _category_tokens(categories: list[str]) -> list[str]:
    tokens = []
    for c in categories:
        raw = (c or "").strip().lower()
        if not raw:
            continue
        tokens.append(raw)
        if ">" in raw:
            tokens.append(raw.split(">", 1)[0].strip())
    out = []
    seen = set()
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _fallback_images_for_categories(categories: list[str]) -> list[str]:
    mapping = _load_category_image_fallbacks()
    out = []
    seen = set()
    for token in _category_tokens(categories):
        url = mapping.get(token, "")
        if _is_usable_image_url(url) and url not in seen:
            seen.add(url)
            out.append(url)
    return out[:4]


def _score_image_url(url: str) -> int:
    score = 0
    u = url.lower()
    if "-300x300" in u or "-150x150" in u:
        score -= 3
    if "scaled" in u:
        score += 2
    if u.endswith(".jpg") or u.endswith(".jpeg"):
        score += 2
    if u.endswith(".png"):
        score += 1
    if "wp-content/uploads" in u:
        score += 1
    return score


def _pick_best_image_urls(image_urls: list[str]) -> tuple[str, list[str]]:
    usable = [u for u in image_urls if _is_usable_image_url(u)]
    if not usable:
        return "", []
    ranked = sorted(usable, key=_score_image_url, reverse=True)
    primary = ranked[0]
    candidates = []
    seen = set()
    for u in ranked:
        if u not in seen:
            seen.add(u)
            candidates.append(u)
    return primary, candidates[:4]


def _strip_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text or "", flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_metrics(text: str) -> list[str]:
    if not text:
        return []
    pattern = re.compile(
        r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?(?:Wh|mAh|W|kW|V|A|lbs|lb|in|mm|g|hours|hour|%|PD\s?\d+W|QC\s?\d+\.\d+)\b",
        flags=re.IGNORECASE,
    )
    seen = set()
    out = []
    for m in pattern.findall(text):
        k = m.lower()
        if k not in seen:
            seen.add(k)
            out.append(m)
    return out[:8]


def load_products() -> list[dict]:
    products_dir = os.path.join(BASE_DATA_DIR, "products")
    csv_paths = sorted(glob.glob(os.path.join(products_dir, "*.csv")))
    products = []

    for csv_path in csv_paths:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Published", "").strip() != "1":
                    continue

                name = (row.get("Name") or "").strip()
                if not name:
                    continue

                sku = (row.get("SKU") or "").strip()
                short_text = _strip_html(row.get("Short description") or "")
                long_text = _strip_html(row.get("Description") or "")
                merged_text = f"{short_text} {long_text}".strip()
                metrics = _extract_metrics(merged_text)
                categories = [c.strip() for c in (row.get("Categories") or "").split(",") if c.strip()]
                image_urls = [u.strip() for u in (row.get("Images") or "").split(",") if u.strip()]
                primary_image, image_candidates = _pick_best_image_urls(image_urls)

                products.append(
                    {
                        "id": (row.get("ID") or "").strip(),
                        "name": name,
                        "sku": sku,
                        "price": (row.get("Regular price") or "").strip(),
                        "sale_price": (row.get("Sale price") or "").strip(),
                        "in_stock": (row.get("In stock?") or "").strip(),
                        "stock": (row.get("Stock") or "").strip(),
                        "product_url": (row.get("External URL") or "").strip(),
                        "categories": categories[:4],
                        "metrics": metrics,
                        "fact_snippet": merged_text[:500],
                        "image_url": primary_image,
                        "image_candidates": image_candidates,
                        "category_image_candidates": _fallback_images_for_categories(categories),
                    }
                )

    return products


def _pick_product(products: list[dict], history: dict) -> dict | None:
    if not products:
        return None

    windows = load_anti_repeat_windows()
    days = int(windows.get("product_feature_days", 7))
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))

    def _post_dt(post: dict) -> datetime | None:
        raw = str(post.get("run_started_at_utc") or post.get("date") or "")
        if not raw:
            return None
        try:
            if len(raw) == 10 and "-" in raw:
                return datetime.fromisoformat(raw + "T00:00:00+00:00")
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    recent_keys = {
        f"{p.get('product_name', '')}|{p.get('product_sku', '')}".lower()
        for p in history.get("posts", [])
        if p.get("product_name") and (_post_dt(p) and _post_dt(p) >= cutoff)
    }

    random.shuffle(products)
    for product in products:
        key = f"{product.get('name', '')}|{product.get('sku', '')}".lower()
        if key not in recent_keys:
            return product

    return random.choice(products)


def _pick_product_by_id(products: list[dict], product_id: str) -> dict | None:
    requested = str(product_id or "").strip()
    if not requested:
        return None
    for product in products:
        if str(product.get("id", "")).strip() == requested:
            return product
    return None


def _normalize_funnel_stage_override(value: str) -> str:
    stage = str(value or "").strip().upper()
    return stage if stage in FUNNEL_STAGES else ""


def _pick_topic(queue: dict, history: dict) -> tuple[str, str, str]:
    windows = load_anti_repeat_windows()
    days = int(windows.get("topic_days", 21))
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))

    used_hashes = set()
    for p in history.get("posts", []):
        if not isinstance(p, dict):
            continue
        topic_hash = str(p.get("topic_hash", "")).strip()
        if not topic_hash:
            continue
        raw = str(p.get("run_started_at_utc") or p.get("date") or "")
        if not raw:
            continue
        try:
            if len(raw) == 10 and "-" in raw:
                dt = datetime.fromisoformat(raw + "T00:00:00+00:00")
            else:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt >= cutoff:
                used_hashes.add(topic_hash)
        except Exception:
            continue

    pillars = queue["pillars"][:]
    random.shuffle(pillars)
    for pillar in pillars:
        topics = queue["topics"][pillar][:]
        random.shuffle(topics)
        for topic in topics:
            h = hashlib.md5(topic.encode()).hexdigest()
            if h not in used_hashes:
                return pillar, topic, h
    # All used recently — reset and pick random
    pillar = random.choice(pillars)
    topic = random.choice(queue["topics"][pillar])
    return pillar, topic, hashlib.md5(topic.encode()).hexdigest()


def _pick_non_repeating_text(candidates: list[str], recent_hashes: set[str], fallback: str) -> str:
    cleaned = [c.strip() for c in candidates if isinstance(c, str) and c.strip()]
    random.shuffle(cleaned)
    for item in cleaned:
        if stable_text_hash(item) not in recent_hashes:
            return item
    if cleaned:
        return cleaned[0]
    return fallback


def _recent_unique_values(history: dict, key: str, limit: int = 8) -> list[str]:
    posts = history.get("posts", []) if isinstance(history, dict) else []
    out = []
    seen = set()
    for row in reversed(posts):
        if not isinstance(row, dict):
            continue
        value = str(row.get(key, "")).strip()
        if not value:
            continue
        low = value.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _one_line(text: str, limit: int = 220) -> str:
    out = re.sub(r"\s+", " ", (text or "").strip())
    if len(out) <= limit:
        return out
    return out[: limit - 3].rstrip() + "..."


def _build_post_components(
    topic: str,
    selected_hook: str,
    selected_cta: str,
    product: dict | None,
    funnel_stage: str,
) -> dict:
    product_name = (product or {}).get("name", "our energy solution")
    product_id = (product or {}).get("id", "")
    metrics = (product or {}).get("metrics", [])
    m1 = metrics[0] if len(metrics) > 0 else "verified output specs"
    m2 = metrics[1] if len(metrics) > 1 else "runtime and charging context"

    situation = f"Many households and small businesses discover their power plan is incomplete during outages or peak-rate periods."
    info = f"A better approach is to map your must-run devices and compare them against measured specs like {m1} and {m2}."
    why = "This reduces expensive guesswork, improves resilience, and helps buyers choose what actually fits real usage."
    product_connection = f"For this topic, {product_name} can be part of a practical setup when the specs match your actual daily loads."
    proof = f"Start from verified details and published product fields only."

    cta = selected_cta
    stage = funnel_stage.upper()
    if stage == "EDUCATION":
        cta = "Save this checklist and compare your current setup."
    elif stage == "DESIRE":
        cta = "See what this product is designed to support."
    elif stage == "CONVERSION":
        cta = "Build your backup-power setup."

    return {
        "product_id": product_id or None,
        "hook": selected_hook,
        "situation": situation,
        "info": info,
        "why": why,
        "product_connection": product_connection,
        "proof": proof,
        "cta": cta,
        "topic": topic,
    }


def _adapt_facebook(components: dict, funnel_stage: str) -> tuple[str, str, str]:
    question = "What would you power first if the grid went down tonight?"
    if funnel_stage.upper() == "CONVERSION":
        question = "Want a practical recommendation matched to your devices?"
    cta = components["cta"] if funnel_stage.upper() == "CONVERSION" else "Comment with your top device and we will help you map priorities."
    caption = (
        f"{_one_line(components['hook'], 120)}\n\n"
        f"{components['situation']} {components['info']}\n\n"
        f"{components['why']} {components['product_connection']}\n\n"
        f"{components['proof']}\n\n"
        f"{cta}\n"
        f"{question}\n"
        "#EnergyResilience #PreparedHome #BackupPower"
    )
    return caption, cta, "community_story"


def _adapt_instagram(components: dict, funnel_stage: str) -> tuple[str, str, str, str]:
    hook = _one_line(components["hook"], 60)
    hook_words = hook.split()
    hook_line = " ".join(hook_words[:9]) if hook_words else "Power planning, done right"
    stage = funnel_stage.upper()
    cta = components["cta"]
    if stage == "EDUCATION":
        cta = "Save this and share it with someone preparing their home."
    elif stage in ("DESIRE", "CONVERSION"):
        cta = "See product options and compare what fits your daily loads."

    caption = (
        f"{hook_line}\n"
        f"{components['situation']}\n"
        f"{components['info']}\n"
        f"Why it matters: {components['why']}\n"
        f"{components['product_connection']}\n"
        f"{components['proof']}\n"
        f"{cta}\n"
        "#PortablePower #EnergyPreparedness #SolarBackup #HomeResilience #PowerPlanning"
    )
    visual_direction = "reel" if stage in ("ATTENTION", "DESIRE") else "carousel"
    alt_text = f"{components['topic']} with practical power-planning visuals and product context."
    return caption, cta, visual_direction, alt_text


def _adapt_linkedin(components: dict, funnel_stage: str) -> tuple[str, str, str]:
    stage = funnel_stage.upper()
    cta = components["cta"]
    if stage != "CONVERSION":
        cta = "Review the framework and adapt it to your own resilience plan."
    caption = (
        f"{_one_line(components['hook'], 120)}\n\n"
        f"Context: {components['situation']}\n"
        f"Useful model: {components['info']}\n"
        f"Why this matters: {components['why']}\n"
        f"Product connection: {components['product_connection']}\n"
        f"Credibility check: {components['proof']}\n\n"
        f"Next step: {cta}\n"
        "#EnergyResilience #BusinessContinuity"
    )
    return caption, cta, "authority_post"


def _build_platform_posts(
    post_id: str,
    campaign_id: str,
    audience_segment: str,
    funnel_stage: str,
    destination_url: str,
    components: dict,
    quality_score: float,
    caption_overrides: dict | None = None,
) -> dict:
    fb_caption, fb_cta, fb_format = _adapt_facebook(components, funnel_stage)
    ig_caption, ig_cta, ig_visual, ig_alt = _adapt_instagram(components, funnel_stage)
    li_text, li_cta, li_format = _adapt_linkedin(components, funnel_stage)

    utm_fb = build_utm_url(
        destination_url,
        source="facebook",
        campaign=campaign_id or "campaign",
        content=f"{components.get('product_id') or 'general'}_{funnel_stage.lower()}",
        term=audience_segment.lower().replace(" ", "_"),
    )
    utm_ig = build_utm_url(
        destination_url,
        source="instagram",
        campaign=campaign_id or "campaign",
        content=f"{components.get('product_id') or 'general'}_{funnel_stage.lower()}",
        term=audience_segment.lower().replace(" ", "_"),
    )
    utm_li = build_utm_url(
        destination_url,
        source="linkedin",
        campaign=campaign_id or "campaign",
        content=f"{components.get('product_id') or 'general'}_{funnel_stage.lower()}",
        term=audience_segment.lower().replace(" ", "_"),
    )

    platform_posts = {
        "facebook": {
            "post_id": post_id,
            "campaign_id": campaign_id,
            "platform": "facebook",
            "funnel_stage": funnel_stage,
            "audience_segment": audience_segment,
            "product_id": components.get("product_id"),
            "hook": components["hook"],
            "caption": fb_caption,
            "cta": fb_cta,
            "destination_url": destination_url,
            "utm_url": utm_fb.get("utm_url", destination_url),
            "content_format": fb_format,
            "visual_direction": "single_image",
            "alt_text": "Facebook visual illustrating practical home energy preparedness.",
            "quality_score": float(quality_score),
            "validation_status": "ok",
            "validation_errors": [],
        },
        "instagram": {
            "post_id": post_id,
            "campaign_id": campaign_id,
            "platform": "instagram",
            "funnel_stage": funnel_stage,
            "audience_segment": audience_segment,
            "product_id": components.get("product_id"),
            "hook": components["hook"],
            "caption": ig_caption,
            "cta": ig_cta,
            "destination_url": destination_url,
            "utm_url": utm_ig.get("utm_url", destination_url),
            "content_format": "short_caption",
            "visual_direction": ig_visual,
            "alt_text": ig_alt,
            "quality_score": float(quality_score),
            "validation_status": "ok",
            "validation_errors": [],
        },
        "linkedin": {
            "post_id": post_id,
            "campaign_id": campaign_id,
            "platform": "linkedin",
            "funnel_stage": funnel_stage,
            "audience_segment": audience_segment,
            "product_id": components.get("product_id"),
            "hook": components["hook"],
            "caption": li_text,
            "cta": li_cta,
            "destination_url": destination_url,
            "utm_url": utm_li.get("utm_url", destination_url),
            "content_format": li_format,
            "visual_direction": "insight_graphic",
            "alt_text": "LinkedIn visual focused on resilience strategy and verified product details.",
            "quality_score": float(quality_score),
            "validation_status": "ok",
            "validation_errors": [],
        },
    }

    overrides = caption_overrides or {}
    for platform in ("facebook", "instagram", "linkedin"):
        platform_override = overrides.get(platform, {}) if isinstance(overrides, dict) else {}
        if not isinstance(platform_override, dict):
            continue
        override_caption = str(platform_override.get("caption", "")).strip()
        override_cta = str(platform_override.get("cta", "")).strip()
        if override_caption:
            platform_posts[platform]["caption"] = override_caption
        if override_cta:
            platform_posts[platform]["cta"] = override_cta

    return platform_posts


def _build_fallback_content(slot: str, topic: str, product: dict | None, marketing_strategy: dict | None) -> dict:
    marketing_strategy = marketing_strategy or {}
    marketing_copy = marketing_strategy.get("copy", {})
    name = (product or {}).get("name", "INF Energy Power solution")
    sku = (product or {}).get("sku", "")
    price = (product or {}).get("price", "")
    sale_price = (product or {}).get("sale_price", "")
    metrics = (product or {}).get("metrics", [])
    m1 = metrics[0] if len(metrics) > 0 else "high-capacity output"
    m2 = metrics[1] if len(metrics) > 1 else "fast charging performance"

    price_line = ""
    if sale_price:
        price_line = f" Current sale price is ${sale_price}."
    elif price:
        price_line = f" Current listed price is ${price}."

    hero = (marketing_copy.get("hero") or "").strip()
    cta_bank = marketing_copy.get("cta_bank") or []
    cta = cta_bank[0] if cta_bank else "Book your free power readiness assessment"

    wp_title = f"{name}: What To Know Before You Buy"
    if len(wp_title) > 64:
        wp_title = f"{name[:52]}: Buyer Guide"
    if hero and len(hero) <= 62:
        wp_title = hero

    wp_content = (
        f"<p>Choosing backup power is not just about watts on a label. It is about reliability, runtime, and how well a product matches your real daily use. Today we are breaking down <strong>{name}</strong> and where it fits for homeowners and small business owners.</p>"
        f"<h2>Start With Your Real Use Case</h2>"
        f"<p>Before buying any power solution, list the devices you need to run first. Most buyers overestimate occasional loads and underestimate frequent loads. The smarter move is to match your frequent loads to verified product specs. For this model, key published specs include <strong>{m1}</strong> and <strong>{m2}</strong>. These two data points are usually the best first filter when comparing options.</p>"
        f"<h2>How This Product Compares In Practical Terms</h2>"
        f"<p>When evaluating alternatives, focus on three things: usable output, charging speed, and portability. A product that looks cheaper can cost more over time if charging is slow or output is limited for the devices you use most. {name} is positioned for buyers who want consistent performance without overcomplicating setup.{price_line}</p>"
        f"<h2>Avoid The Most Common Buying Mistakes</h2>"
        f"<p>The biggest mistake is buying only on headline capacity. The second is ignoring how and where the unit will be used. A better approach is to map your top 3 devices, compare real specs, and confirm compatibility up front. This avoids returns, downtime, and frustration.</p>"
        f"<h2>Next Step</h2>"
        f"<p>If you want a tailored recommendation, {cta.lower()}. We can help you compare your options and select the right system for your actual usage, not generic assumptions.</p>"
    )

    fb_caption = (
        f"Most people buy backup power by guesswork and marketing hype. That is exactly why they end up with the wrong unit.\n\n"
        f"If you are comparing options like {name}, start with what actually matters: published specs and your real daily devices. This product lists {m1} and {m2}, which are the kinds of details that should drive your decision, not just brand name."
        f"{price_line}\n\n"
        f"If you want help matching the right system to your usage, {cta.lower()}.\n\n"
        f"What device is non-negotiable for you during an outage?\n"
        f"#BackupPower #EnergyResilience #SmartBuying #InfEnergyPower #PortablePower"
    )

    ig_caption = (
        f"Stop buying backup power blind.\n"
        f"If you are considering {name}, do not pick based on marketing alone. Compare real specs to your actual daily devices.\n\n"
        f"Two key published details on this model are {m1} and {m2}. Those numbers matter more than hype because they affect runtime, compatibility, and reliability when you need power most."
        f"{price_line}\n\n"
        f"Want help choosing the right setup for your home or business? {cta}.\n"
        f"#PortablePower #EnergyBackup #PowerOutagePrep #SolarReady #EmergencyPower #SmartHomeEnergy #InfEnergyPower #BatteryBackup"
    )

    li_text = (
        f"Most backup power purchases fail for one reason: buyers optimize for headline numbers instead of real-world usage.\n\n"
        f"When evaluating products like {name}{' (' + sku + ')' if sku else ''}, the better framework is simple:\n"
        f"1) Map your top 3 critical loads\n"
        f"2) Validate published output and charging specs\n"
        f"3) Compare portability and recharge practicality\n\n"
        f"For this model, two important published specs are {m1} and {m2}. These are the details that determine whether a unit helps in a real outage or just looks good on a product page."
        f"{price_line}\n\n"
        f"If you want a practical recommendation based on your exact use case, {cta.lower()} with a clear side-by-side comparison."
    )

    return {
        "wp_title": wp_title,
        "wp_content": wp_content,
        "wp_excerpt": f"{name}: practical buying guidance, key specs, and what to compare before you purchase.",
        "fb_caption": fb_caption,
        "ig_caption": ig_caption,
        "li_text": li_text,
    }


def _generate_json_with_gemini(prompt: str, model_candidates: list[str]) -> dict | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)

    for model_name in model_candidates:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            raw = (response.text or "").strip()
            if not raw:
                continue
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            continue

    return None


def _build_default_visual_plan(topic: str, funnel_stage: str, selected_hook: str, selected_cta: str, product: dict | None) -> dict:
    has_product_image = bool((product or {}).get("image_url"))
    strategy = "hybrid" if has_product_image else "gemini_generated"
    return {
        "style_intent": "Premium cinematic realism for practical energy resilience",
        "mood": "trustworthy, confident, modern",
        "image_strategy": strategy,
        "composition": "left-side negative space for headline, right-side hero visual",
        "use_product_photo": has_product_image,
        "text_on_image": "minimal",
        "gemini_image_prompt": (
            f"Create a premium social visual for topic '{topic}' with hook '{selected_hook}'. "
            f"Convey {funnel_stage.lower()} stage intent and support CTA: {selected_cta}. "
            "Show credible, modern home or small-business backup power atmosphere with cinematic lighting."
        ),
        "platform_overrides": {
            "facebook": {"composition": "balanced, educational, product-visible", "visual_direction": "single_image"},
            "instagram": {"composition": "bold focal point, strong depth, mobile-first", "visual_direction": "reel_cover_style"},
            "linkedin": {"composition": "clean professional credibility layout", "visual_direction": "insight_graphic"},
        },
    }


def _build_visual_plan_with_gemini(
    model_candidates: list[str],
    *,
    topic: str,
    funnel_stage: str,
    stage_objective: str,
    selected_hook: str,
    selected_cta: str,
    product_name: str,
    product_categories: str,
    product_metrics: str,
    has_product_image: bool,
) -> dict | None:
    prompt = f"""{VISUAL_DIRECTOR_BRIEF}

Campaign input:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Stage objective: {stage_objective}
- Hook: {selected_hook}
- CTA: {selected_cta}
- Product name: {product_name or 'N/A'}
- Product categories: {product_categories or 'N/A'}
- Product measurable specs: {product_metrics or 'N/A'}
- Product image available: {has_product_image}

Return only valid JSON with this exact shape:
{{
  "style_intent": "string",
  "mood": "string",
  "image_strategy": "gemini_generated|product_photo_featured|hybrid",
  "composition": "string",
  "use_product_photo": true,
  "text_on_image": "none|minimal",
  "gemini_image_prompt": "Detailed visual generation prompt for an image model",
  "platform_overrides": {{
    "facebook": {{"composition": "string", "visual_direction": "string"}},
    "instagram": {{"composition": "string", "visual_direction": "string"}},
    "linkedin": {{"composition": "string", "visual_direction": "string"}}
  }}
}}"""
    return _generate_json_with_gemini(prompt, model_candidates)


def _run_agent_conference(
    model_candidates: list[str],
    *,
    topic: str,
    funnel_stage: str,
    selected_hook: str,
    selected_cta: str,
    content: dict,
    visual_plan: dict,
    product_name: str,
    product_metrics: str,
) -> dict:
    prompt = f"""{AGENT_CONFERENCE_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Hook: {selected_hook}
- CTA: {selected_cta}
- Product: {product_name or 'N/A'}
- Product measurable specs: {product_metrics or 'N/A'}

Draft copy:
- wp_title: {str(content.get('wp_title', ''))[:200]}
- wp_excerpt: {str(content.get('wp_excerpt', ''))[:220]}
- fb_caption: {str(content.get('fb_caption', ''))[:700]}
- ig_caption: {str(content.get('ig_caption', ''))[:700]}
- li_text: {str(content.get('li_text', ''))[:700]}

Current visual plan:
{json.dumps(visual_plan, ensure_ascii=True)}

Return ONLY valid JSON with this exact shape:
{{
  "copywriter_feedback": ["string", "string"],
  "visual_director_feedback": ["string", "string"],
  "product_truth_feedback": ["string", "string"],
  "platform_editor_feedback": ["string", "string"],
  "collective_actions": ["string", "string", "string"],
  "refined": {{
    "hook": "optional refined hook",
    "cta": "optional refined CTA",
    "gemini_image_prompt": "optional refined visual prompt",
    "image_strategy": "gemini_generated|product_photo_featured|hybrid|",
    "fb_caption": "optional refined Facebook caption",
    "ig_caption": "optional refined Instagram caption",
    "li_text": "optional refined LinkedIn caption"
  }}
}}"""
    result = _generate_json_with_gemini(prompt, model_candidates)
    return result if isinstance(result, dict) else {}


def _apply_conference_refinements(content: dict, visual_plan: dict, conference: dict) -> tuple[dict, dict]:
    refined = conference.get("refined", {}) if isinstance(conference, dict) else {}
    if not isinstance(refined, dict):
        return content, visual_plan

    hook = str(refined.get("hook", "")).strip()
    cta = str(refined.get("cta", "")).strip()
    fb = str(refined.get("fb_caption", "")).strip()
    ig = str(refined.get("ig_caption", "")).strip()
    li = str(refined.get("li_text", "")).strip()
    image_prompt = str(refined.get("gemini_image_prompt", "")).strip()
    image_strategy = str(refined.get("image_strategy", "")).strip().lower()

    if hook:
        content["selected_hook"] = hook
    if cta:
        content["selected_cta"] = cta
    if fb:
        content["fb_caption"] = fb
    if ig:
        content["ig_caption"] = ig
    if li:
        content["li_text"] = li

    if image_prompt:
        visual_plan["gemini_image_prompt"] = image_prompt
    if image_strategy in {"gemini_generated", "product_photo_featured", "hybrid"}:
        visual_plan["image_strategy"] = image_strategy

    return content, visual_plan


def _run_pre_generation_conference(
        model_candidates: list[str],
        *,
        topic: str,
        funnel_stage: str,
        stage_objective: str,
        selected_hook: str,
        selected_cta: str,
        product_name: str,
        product_categories: str,
        product_metrics: str,
        recent_hooks: list[str],
        recent_topics: list[str],
        recent_ctas: list[str],
) -> dict:
        prompt = f"""{PREGEN_CONFERENCE_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Stage objective: {stage_objective}
- Current hook candidate: {selected_hook}
- Current CTA candidate: {selected_cta}
- Product: {product_name or 'N/A'}
- Product categories: {product_categories or 'N/A'}
- Product measurable specs: {product_metrics or 'N/A'}
- Recent hooks: {recent_hooks}
- Recent topics: {recent_topics}
- Recent CTAs: {recent_ctas}

Return ONLY valid JSON with this exact shape:
{{
    "recommended_hook": "string",
    "recommended_cta": "string",
    "primary_angle": "string",
    "visual_focus": "string",
    "platform_notes": {{
        "facebook": "string",
        "instagram": "string",
        "linkedin": "string"
    }},
    "collective_actions": ["string", "string", "string"],
    "risk_checks": ["string", "string"]
}}"""
        result = _generate_json_with_gemini(prompt, model_candidates)
        return result if isinstance(result, dict) else {}


def generate(slot: str, *, funnel_stage_override: str = "", product_id_override: str = "") -> dict:
    ensure_runtime_data()
    preferred_model = os.environ.get("GEMINI_MODEL", "").strip()
    model_candidates = [
        preferred_model,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    model_candidates = [m for m in model_candidates if m]
    preferred_visual_director_model = os.environ.get("GEMINI_VISUAL_DIRECTOR_MODEL", "").strip()
    visual_director_candidates = [
        preferred_visual_director_model,
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ]
    visual_director_candidates = [m for m in visual_director_candidates if m]

    queue = load_topic_queue()
    history = load_history()
    funnel_config = load_funnel_config()
    cta_library = load_cta_library()
    pillar, topic, topic_hash = _pick_topic(queue, history)
    products = load_products()
    product = _pick_product_by_id(products, product_id_override) or _pick_product(products, history)
    marketing_strategy = _load_latest_marketing_strategy()
    structured_campaign = _load_latest_structured_campaign()
    weekly_sequence = select_weekly_sequence(slot, now_utc=datetime.now(timezone.utc))
    funnel_stage = _normalize_funnel_stage_override(funnel_stage_override) or stage_for_slot(
        slot,
        history=history,
        funnel_config=funnel_config,
    )
    stage_meta = funnel_config.get("stages", {}).get(funnel_stage, {}) if isinstance(funnel_config, dict) else {}

    hook_window = int(os.environ.get("ANTI_REPEAT_HOOK_WINDOW", "30"))
    cta_window = int(os.environ.get("ANTI_REPEAT_CTA_WINDOW", "30"))
    recent_hook_hashes = {
        str(p.get("hook_hash", ""))
        for p in history.get("posts", [])[-hook_window:]
        if isinstance(p, dict)
    }
    recent_cta_hashes = {
        str(p.get("cta_hash", ""))
        for p in history.get("posts", [])[-cta_window:]
        if isinstance(p, dict)
    }

    product_name = product.get("name", "") if product else ""
    product_id = product.get("id", "") if product else ""
    product_sku = product.get("sku", "") if product else ""
    product_price = product.get("price", "") if product else ""
    product_sale_price = product.get("sale_price", "") if product else ""
    product_metrics = ", ".join(product.get("metrics", [])[:5]) if product else ""
    product_categories = ", ".join(product.get("categories", [])[:3]) if product else ""
    product_facts = product.get("fact_snippet", "") if product else ""
    product_in_stock = product.get("in_stock", "") if product else ""
    product_stock = product.get("stock", "") if product else ""
    product_url = product.get("product_url", "") if product else ""

    marketing_context = ""
    selected_hook = (weekly_sequence.get("hook") or "").strip()
    selected_cta = (weekly_sequence.get("primary_cta") or "").strip()
    audience_segment = (weekly_sequence.get("segment") or structured_campaign.get("audience_segment") or "Prepared Buyer").strip()
    campaign_id = str(structured_campaign.get("campaign_id", "")).strip()
    destination_url = str(structured_campaign.get("destination_url", SITE_URL)).strip() or SITE_URL

    preferred_hooks = []
    if selected_hook:
        preferred_hooks.append(selected_hook)

    if marketing_strategy:
        voice_rules = marketing_strategy.get("voice", {}).get("voice_rules", [])
        segments = marketing_strategy.get("audience", {}).get("segments", [])
        core_offers = marketing_strategy.get("offer", {}).get("core_offers", [])
        social_hooks = marketing_strategy.get("copy", {}).get("social_hooks", [])
        cta_bank = marketing_strategy.get("copy", {}).get("cta_bank", [])
        preferred_hooks.extend([h for h in social_hooks if isinstance(h, str)])
        selected_cta = choose_cta_for_stage(
            stage=funnel_stage,
            preferred=selected_cta or (cta_bank[0] if cta_bank else ""),
            cta_library=cta_library,
            recent_cta_hashes=recent_cta_hashes,
        )

        marketing_context = (
            "MARKETING TEAM DIRECTIVES:\n"
            f"- Voice rules: {voice_rules[:5]}\n"
            f"- Priority audience segments: {segments[:3]}\n"
            f"- Core offers: {core_offers[:4]}\n"
            f"- Proven hook styles: {social_hooks[:3]}\n"
            f"- Preferred CTAs: {cta_bank[:3]}\n"
            f"- This slot hook direction: {selected_hook}\n"
            f"- This slot CTA direction: {selected_cta}\n"
            f"- Funnel stage: {funnel_stage}\n"
            f"- Funnel objective: {stage_meta.get('objective', '')}\n"
            "Use this as strategy guidance while still tailoring to the specific topic and product.\n"
        )
    else:
        preferred_hooks.extend([f"Most people misunderstand {topic.lower()}", "The hidden cost most buyers miss"])
        selected_cta = choose_cta_for_stage(
            stage=funnel_stage,
            preferred=selected_cta,
            cta_library=cta_library,
            recent_cta_hashes=recent_cta_hashes,
        )

    hook_choice = select_hook(
        topic=topic,
        product_name=product_name or "INF Energy Power solution",
        audience_segment=audience_segment,
        recent_hook_hashes=recent_hook_hashes,
        preferred_hooks=preferred_hooks,
    )
    selected_hook = str(hook_choice.get("hook", selected_hook)).strip() or selected_hook
    hook_type = str(hook_choice.get("hook_type", "question")).strip() or "question"

    slot_guidance = {
        "morning": (
            "MORNING — EDUCATION. Open with a surprising or counterintuitive fact. "
            "Teach one genuinely useful concept the reader can act on today. "
            "Use real numbers, comparisons, or analogies. No fluff. End with a thought-provoking question."
        ),
        "midday": (
            "MIDDAY — PROOF. Lead with a specific, believable result. "
            "Include at least one concrete number (dollar amount, percentage, timeframe). "
            "Tell a mini-story: situation → problem → solution → outcome. "
            "Make the reader feel 'that could be me.' End with a credibility statement."
        ),
        "evening": (
            "EVENING — CTA. Create genuine urgency around a real reason to act now "
            "(limited slots, seasonal incentives, rising utility rates). "
            "Be direct and specific about the next step. Tell them exactly what happens when they reach out. "
            "One clear CTA only. No vague 'learn more.'"
        ),
    }.get(slot, "educational")

    recent_hooks = _recent_unique_values(history, "selected_hook", limit=8)
    recent_products = _recent_unique_values(history, "product_name", limit=6)
    recent_ctas = _recent_unique_values(history, "selected_cta", limit=8)
    recent_topics = _recent_unique_values(history, "topic", limit=8)

    conference_model = os.environ.get("GEMINI_CONFERENCE_MODEL", "").strip()
    conference_candidates = [conference_model, preferred_visual_director_model, preferred_model, "gemini-2.5-pro", "gemini-2.5-flash"]
    conference_candidates = [m for m in conference_candidates if m]
    pregen_enabled = os.environ.get("ENABLE_PREGEN_CONFERENCE", "true").strip().lower() not in {"0", "false", "no"}
    pre_generation_conference = {}
    if pregen_enabled:
        pre_generation_conference = _run_pre_generation_conference(
            conference_candidates,
            topic=topic,
            funnel_stage=funnel_stage,
            stage_objective=str(stage_meta.get("objective", "")),
            selected_hook=selected_hook,
            selected_cta=selected_cta,
            product_name=product_name,
            product_categories=product_categories,
            product_metrics=product_metrics,
            recent_hooks=recent_hooks,
            recent_topics=recent_topics,
            recent_ctas=recent_ctas,
        )
        selected_hook = str(pre_generation_conference.get("recommended_hook", "")).strip() or selected_hook
        selected_cta = str(pre_generation_conference.get("recommended_cta", "")).strip() or selected_cta

    pregen_context = ""
    if isinstance(pre_generation_conference, dict) and pre_generation_conference:
        pregen_context = (
            "PRE-GENERATION TEAM MEETING SUMMARY:\n"
            f"- Primary angle: {str(pre_generation_conference.get('primary_angle', ''))}\n"
            f"- Visual focus: {str(pre_generation_conference.get('visual_focus', ''))}\n"
            f"- Collective actions: {pre_generation_conference.get('collective_actions', [])}\n"
            f"- Risk checks: {pre_generation_conference.get('risk_checks', [])}\n"
            f"- Platform notes: {pre_generation_conference.get('platform_notes', {})}\n"
        )

    visual_plan = _build_visual_plan_with_gemini(
        visual_director_candidates,
        topic=topic,
        funnel_stage=funnel_stage,
        stage_objective=str(stage_meta.get("objective", "")),
        selected_hook=selected_hook,
        selected_cta=selected_cta,
        product_name=product_name,
        product_categories=product_categories,
        product_metrics=product_metrics,
        has_product_image=bool((product or {}).get("image_url")),
    )
    if not isinstance(visual_plan, dict):
        visual_plan = _build_default_visual_plan(topic, funnel_stage, selected_hook, selected_cta, product)

    prompt = f"""You are an expert content strategist and copywriter for Infenergy Power (infenergypower.com), a solar and home energy solutions company.

{CONVERSION_COPY_BRIEF}

BRAND VOICE: Direct, credible, genuinely helpful. Speak like a trusted expert neighbor, not a salesperson.
AUDIENCE: Homeowners and small business owners frustrated by rising energy bills, curious about solar but not yet convinced.
TOPIC: {topic}
CONTENT DIRECTIVE: {slot_guidance}

PRODUCT CONTEXT (ground your content in these details when relevant):
- Product name: {product_name or 'N/A'}
- SKU: {product_sku or 'N/A'}
- Regular price: {product_price or 'N/A'}
- Sale price: {product_sale_price or 'N/A'}
- Categories: {product_categories or 'N/A'}
- Key measurable specs: {product_metrics or 'N/A'}
- Product facts excerpt: {product_facts or 'N/A'}

{marketing_context}

{pregen_context}

CAMPAIGN EXECUTION CONTEXT:
- Selected hook for this post: {selected_hook}
- Selected CTA for this post: {selected_cta}
- Funnel stage: {funnel_stage}
- Funnel objective: {stage_meta.get('objective', '')}
- Weekly plan row: {json.dumps(weekly_sequence) if weekly_sequence else 'none'}
- Recent hooks (avoid repetition): {recent_hooks}
- Recent products (avoid overusing): {recent_products}
- Recent CTAs (avoid repetition): {recent_ctas}
- Recent topics (avoid repetition): {recent_topics}

QUALITY RULES — every piece must follow all of these:
1. Open with a hook that creates immediate curiosity or challenges a common assumption.
2. Include at least one specific number, stat, or real-world comparison that makes the content credible.
3. Deliver a genuine insight the reader cannot easily Google — a specific angle they haven't considered.
4. Write like a human expert, not a marketing team. Never use words like "revolutionize", "game-changer", or "unlock your potential."
5. Never make unverifiable guarantees. Use language like "many homeowners", "up to", "in most cases" where appropriate.
6. Every post must have a clear emotional payoff: relief, confidence, curiosity satisfied, or urgency to act.
7. If product context is available, use at least two concrete product facts or measurable specs naturally in the copy.
8. Do not invent model names, specs, prices, or warranties not present in the provided product context.

Return ONLY valid JSON with these exact keys (no markdown, no code fences):
{{
  "wp_title": "Specific, curiosity-driven SEO title under 65 characters — not generic",
  "wp_content": "Full blog post as clean HTML with <h2> subheadings. 450-550 words. Open strong, build a logical case, end with a clear next step. Include at least 2 specific data points or examples.",
  "wp_excerpt": "One punchy sentence under 160 characters that makes someone want to click",
  "fb_caption": "150-220 words. Conversational and personal. Open with a surprising statement or question. Include one specific number or fact. End with a genuine question that invites comments. 4-5 targeted hashtags on the last line only.",
  "ig_caption": "First line must be a scroll-stopping hook under 10 words. 120-160 words total. Specific, visual, and personal. 7-9 hashtags on the final line only — mix broad and niche.",
  "li_text": "180-260 words. Professional but not corporate. Open with a counterintuitive insight or bold statement. Build a tight logical argument. Include one specific data point. End with a direct, frictionless CTA — tell them exactly what the first step looks like."
}}"""

    content = _generate_json_with_gemini(prompt, model_candidates)

    if content is None:
        content = _build_fallback_content(slot, topic, product, marketing_strategy)
        content["topic"] = topic
        content["pillar"] = pillar
        content["topic_hash"] = topic_hash
        content["product_name"] = product_name
        content["product_id"] = product_id
        content["product_sku"] = product_sku
        content["product_price"] = product_price
        content["product_sale_price"] = product_sale_price
        content["product_metrics"] = product.get("metrics", []) if product else []
        content["product_facts"] = product_facts
        content["product_in_stock"] = product_in_stock
        content["product_stock"] = product_stock
        content["product_url"] = product_url
        content["product_image_url"] = product.get("image_url", "") if product else ""
        content["product_image_candidates"] = product.get("image_candidates", []) if product else []
        content["category_image_candidates"] = product.get("category_image_candidates", []) if product else []
        content["marketing_strategy_used"] = bool(marketing_strategy)
        content["marketing_bundle_used"] = bool(marketing_strategy)
        content["selected_hook"] = selected_hook
        content["selected_cta"] = selected_cta
        content["selected_hook_type"] = hook_type
        content["hook_scores"] = hook_choice.get("component_scores", {})
        content["funnel_stage"] = funnel_stage
        content["funnel_stage_objective"] = stage_meta.get("objective", "")
        content["audience_segment"] = audience_segment
        content["campaign_id"] = campaign_id
        content["destination_url"] = destination_url
        content["weekly_plan_used"] = bool(weekly_sequence)
        content["hook_hash"] = stable_text_hash(selected_hook)
        content["cta_hash"] = stable_text_hash(selected_cta)

        cta_ok, cta_reason = cta_is_valid_for_stage(funnel_stage, selected_cta, destination_url)
        if not cta_ok:
            fallback_cta = choose_cta_for_stage(
                stage=funnel_stage,
                preferred="",
                cta_library=cta_library,
                recent_cta_hashes=recent_cta_hashes,
            )
            content["selected_cta"] = fallback_cta
            selected_cta = fallback_cta
            content["cta_hash"] = stable_text_hash(fallback_cta)
            content.setdefault("quality_warnings", []).append(f"cta_adjusted:{cta_reason}")
        content["date"] = str(date.today())
        content["slot"] = slot
        for key in ("wp_content", "fb_caption", "ig_caption", "li_text"):
            cleaned, replaced = apply_claim_guardrails(str(content.get(key, "")))
            content[key] = cleaned
            if replaced:
                content.setdefault("claim_guardrail_replacements", []).extend(replaced)
        quality = score_generated_content(content)
        content["quality_score"] = quality.score
        content["quality_checks"] = quality.checks
        content["quality_warnings"] = quality.warnings

        post_id = uuid.uuid4().hex[:12]
        selected_hook = str(content.get("selected_hook", selected_hook))
        selected_cta = str(content.get("selected_cta", selected_cta))
        components = _build_post_components(topic, selected_hook, selected_cta, product, funnel_stage)
        platform_posts = _build_platform_posts(
            post_id=post_id,
            campaign_id=campaign_id,
            audience_segment=audience_segment,
            funnel_stage=funnel_stage,
            destination_url=destination_url,
            components=components,
            quality_score=float(content.get("quality_score", 0)),
        )
        platform_posts = normalize_brand_content(platform_posts)
        content = normalize_brand_content(content)
        content["post_id"] = post_id
        content["platform_posts"] = platform_posts
        content["scenario"] = components.get("situation", "")
        content["educational_lesson"] = components.get("info", "")
        content["fb_caption"] = platform_posts["facebook"]["caption"]
        content["ig_caption"] = platform_posts["instagram"]["caption"]
        content["li_text"] = platform_posts["linkedin"]["caption"]
        content["selected_cta"] = components["cta"]
        content["generated_visuals"] = generate_visuals(content, visual_plan=visual_plan)
        content["visual_plan"] = visual_plan
        content["pre_generation_conference"] = pre_generation_conference
        content["creative_agents"] = {
            "copywriter": preferred_model or "gemini-2.5-flash",
            "visual_director": (preferred_visual_director_model or "gemini-2.5-pro"),
            "pre_generation_conference": (conference_model or preferred_visual_director_model or "gemini-2.5-pro"),
            "image_model": os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        }
        quality = score_generated_content(content)
        content["quality_score"] = quality.score
        content["quality_checks"] = quality.checks
        content["quality_warnings"] = quality.warnings
        for p in content["platform_posts"].values():
            p["quality_score"] = float(quality.score)
        return content

    content["topic"] = topic
    content["pillar"] = pillar
    content["topic_hash"] = topic_hash
    content["product_name"] = product_name
    content["product_id"] = product_id
    content["product_sku"] = product_sku
    content["product_price"] = product_price
    content["product_sale_price"] = product_sale_price
    content["product_metrics"] = product.get("metrics", []) if product else []
    content["product_facts"] = product_facts
    content["product_in_stock"] = product_in_stock
    content["product_stock"] = product_stock
    content["product_url"] = product_url
    content["product_image_url"] = product.get("image_url", "") if product else ""
    content["product_image_candidates"] = product.get("image_candidates", []) if product else []
    content["category_image_candidates"] = product.get("category_image_candidates", []) if product else []
    content["marketing_strategy_used"] = bool(marketing_strategy)
    content["marketing_bundle_used"] = bool(marketing_strategy)
    content["selected_hook"] = selected_hook
    content["selected_cta"] = selected_cta
    content["selected_hook_type"] = hook_type
    content["hook_scores"] = hook_choice.get("component_scores", {})
    content["funnel_stage"] = funnel_stage
    content["funnel_stage_objective"] = stage_meta.get("objective", "")
    content["audience_segment"] = audience_segment
    content["campaign_id"] = campaign_id
    content["destination_url"] = destination_url
    content["weekly_plan_used"] = bool(weekly_sequence)
    content["hook_hash"] = stable_text_hash(selected_hook)
    content["cta_hash"] = stable_text_hash(selected_cta)

    cta_ok, cta_reason = cta_is_valid_for_stage(funnel_stage, selected_cta, destination_url)
    if not cta_ok:
        fallback_cta = choose_cta_for_stage(
            stage=funnel_stage,
            preferred="",
            cta_library=cta_library,
            recent_cta_hashes=recent_cta_hashes,
        )
        content["selected_cta"] = fallback_cta
        selected_cta = fallback_cta
        content["cta_hash"] = stable_text_hash(fallback_cta)
        content.setdefault("quality_warnings", []).append(f"cta_adjusted:{cta_reason}")
    content["date"] = str(date.today())
    content["slot"] = slot
    for key in ("wp_content", "fb_caption", "ig_caption", "li_text"):
        cleaned, replaced = apply_claim_guardrails(str(content.get(key, "")))
        content[key] = cleaned
        if replaced:
            content.setdefault("claim_guardrail_replacements", []).extend(replaced)
    quality = score_generated_content(content)
    content["quality_score"] = quality.score
    content["quality_checks"] = quality.checks
    content["quality_warnings"] = quality.warnings

    conference_enabled = os.environ.get("ENABLE_AGENT_CONFERENCE", "true").strip().lower() not in {"0", "false", "no"}
    conference_summary = {}
    if conference_enabled:
        conference_summary = _run_agent_conference(
            conference_candidates,
            topic=topic,
            funnel_stage=funnel_stage,
            selected_hook=str(content.get("selected_hook", selected_hook)),
            selected_cta=str(content.get("selected_cta", selected_cta)),
            content=content,
            visual_plan=visual_plan,
            product_name=product_name,
            product_metrics=product_metrics,
        )
        content, visual_plan = _apply_conference_refinements(content, visual_plan, conference_summary)
        # Re-apply guardrails after conference-driven refinements.
        for key in ("wp_content", "fb_caption", "ig_caption", "li_text"):
            cleaned, replaced = apply_claim_guardrails(str(content.get(key, "")))
            content[key] = cleaned
            if replaced:
                content.setdefault("claim_guardrail_replacements", []).extend(replaced)

    post_id = uuid.uuid4().hex[:12]
    selected_hook = str(content.get("selected_hook", selected_hook))
    selected_cta = str(content.get("selected_cta", selected_cta))
    components = _build_post_components(topic, selected_hook, selected_cta, product, funnel_stage)
    platform_posts = _build_platform_posts(
        post_id=post_id,
        campaign_id=campaign_id,
        audience_segment=audience_segment,
        funnel_stage=funnel_stage,
        destination_url=destination_url,
        components=components,
        quality_score=float(content.get("quality_score", 0)),
        caption_overrides={
            "facebook": {"caption": str(content.get("fb_caption", "")), "cta": str(content.get("selected_cta", ""))},
            "instagram": {"caption": str(content.get("ig_caption", "")), "cta": str(content.get("selected_cta", ""))},
            "linkedin": {"caption": str(content.get("li_text", "")), "cta": str(content.get("selected_cta", ""))},
        },
    )
    platform_posts = normalize_brand_content(platform_posts)
    content = normalize_brand_content(content)
    content["post_id"] = post_id
    content["platform_posts"] = platform_posts
    content["scenario"] = components.get("situation", "")
    content["educational_lesson"] = components.get("info", "")
    # Preserve publisher compatibility with existing flat keys.
    content["fb_caption"] = platform_posts["facebook"]["caption"]
    content["ig_caption"] = platform_posts["instagram"]["caption"]
    content["li_text"] = platform_posts["linkedin"]["caption"]
    content["selected_cta"] = components["cta"]
    content["generated_visuals"] = generate_visuals(content, visual_plan=visual_plan)
    content["visual_plan"] = visual_plan
    content["pre_generation_conference"] = pre_generation_conference
    content["agent_conference"] = conference_summary
    content["creative_agents"] = {
        "copywriter": preferred_model or "gemini-2.5-flash",
        "visual_director": (preferred_visual_director_model or "gemini-2.5-pro"),
        "pre_generation_conference": (conference_model or preferred_visual_director_model or "gemini-2.5-pro"),
        "conference": (conference_model or preferred_visual_director_model or "gemini-2.5-pro"),
        "image_model": os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
    }
    quality = score_generated_content(content)
    content["quality_score"] = quality.score
    content["quality_checks"] = quality.checks
    content["quality_warnings"] = quality.warnings
    for p in content["platform_posts"].values():
        p["quality_score"] = float(quality.score)
    return content
