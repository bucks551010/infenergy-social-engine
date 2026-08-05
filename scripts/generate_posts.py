import os
import json
import random
import hashlib
import csv
import glob
import re
from datetime import date
import google.generativeai as genai

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


def ensure_runtime_data() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

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
    with open(os.path.join(DATA_DIR, "post_history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


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

                products.append(
                    {
                        "id": (row.get("ID") or "").strip(),
                        "name": name,
                        "sku": sku,
                        "price": (row.get("Regular price") or "").strip(),
                        "sale_price": (row.get("Sale price") or "").strip(),
                        "categories": categories[:4],
                        "metrics": metrics,
                        "fact_snippet": merged_text[:500],
                        "image_url": image_urls[0] if image_urls else "",
                    }
                )

    return products


def _pick_product(products: list[dict], history: dict) -> dict | None:
    if not products:
        return None

    recent_keys = {
        f"{p.get('product_name', '')}|{p.get('product_sku', '')}".lower()
        for p in history.get("posts", [])[-40:]
        if p.get("product_name")
    }

    random.shuffle(products)
    for product in products:
        key = f"{product.get('name', '')}|{product.get('sku', '')}".lower()
        if key not in recent_keys:
            return product

    return random.choice(products)


def _pick_topic(queue: dict, history: dict) -> tuple[str, str, str]:
    used_hashes = {p["topic_hash"] for p in history["posts"][-60:]}
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


def _build_fallback_content(slot: str, topic: str, product: dict | None) -> dict:
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

    wp_title = f"{name}: What To Know Before You Buy"
    if len(wp_title) > 64:
        wp_title = f"{name[:52]}: Buyer Guide"

    wp_content = (
        f"<p>Choosing backup power is not just about watts on a label. It is about reliability, runtime, and how well a product matches your real daily use. Today we are breaking down <strong>{name}</strong> and where it fits for homeowners and small business owners.</p>"
        f"<h2>Start With Your Real Use Case</h2>"
        f"<p>Before buying any power solution, list the devices you need to run first. Most buyers overestimate occasional loads and underestimate frequent loads. The smarter move is to match your frequent loads to verified product specs. For this model, key published specs include <strong>{m1}</strong> and <strong>{m2}</strong>. These two data points are usually the best first filter when comparing options.</p>"
        f"<h2>How This Product Compares In Practical Terms</h2>"
        f"<p>When evaluating alternatives, focus on three things: usable output, charging speed, and portability. A product that looks cheaper can cost more over time if charging is slow or output is limited for the devices you use most. {name} is positioned for buyers who want consistent performance without overcomplicating setup.{price_line}</p>"
        f"<h2>Avoid The Most Common Buying Mistakes</h2>"
        f"<p>The biggest mistake is buying only on headline capacity. The second is ignoring how and where the unit will be used. A better approach is to map your top 3 devices, compare real specs, and confirm compatibility up front. This avoids returns, downtime, and frustration.</p>"
        f"<h2>Next Step</h2>"
        f"<p>If you want a tailored recommendation, book a free consultation with INF Energy Power. We can help you compare your options and select the right system for your actual usage, not generic assumptions.</p>"
    )

    fb_caption = (
        f"Most people buy backup power by guesswork and marketing hype. That is exactly why they end up with the wrong unit.\n\n"
        f"If you are comparing options like {name}, start with what actually matters: published specs and your real daily devices. This product lists {m1} and {m2}, which are the kinds of details that should drive your decision, not just brand name."
        f"{price_line}\n\n"
        f"If you want help matching the right system to your usage, we can walk you through it in a free consultation.\n\n"
        f"What device is non-negotiable for you during an outage?\n"
        f"#BackupPower #EnergyResilience #SmartBuying #InfEnergyPower #PortablePower"
    )

    ig_caption = (
        f"Stop buying backup power blind.\n"
        f"If you are considering {name}, do not pick based on marketing alone. Compare real specs to your actual daily devices.\n\n"
        f"Two key published details on this model are {m1} and {m2}. Those numbers matter more than hype because they affect runtime, compatibility, and reliability when you need power most."
        f"{price_line}\n\n"
        f"Want help choosing the right setup for your home or business? We offer a free consultation.\n"
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
        f"If you want a practical recommendation based on your exact use case, INF Energy Power offers a free consultation with a clear side-by-side comparison."
    )

    return {
        "wp_title": wp_title,
        "wp_content": wp_content,
        "wp_excerpt": f"{name}: practical buying guidance, key specs, and what to compare before you purchase.",
        "fb_caption": fb_caption,
        "ig_caption": ig_caption,
        "li_text": li_text,
    }


def generate(slot: str) -> dict:
    ensure_runtime_data()
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    preferred_model = os.environ.get("GEMINI_MODEL", "").strip()
    model_candidates = [
        preferred_model,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    model_candidates = [m for m in model_candidates if m]

    queue = load_topic_queue()
    history = load_history()
    pillar, topic, topic_hash = _pick_topic(queue, history)
    products = load_products()
    product = _pick_product(products, history)

    product_name = product.get("name", "") if product else ""
    product_sku = product.get("sku", "") if product else ""
    product_price = product.get("price", "") if product else ""
    product_sale_price = product.get("sale_price", "") if product else ""
    product_metrics = ", ".join(product.get("metrics", [])[:5]) if product else ""
    product_categories = ", ".join(product.get("categories", [])[:3]) if product else ""
    product_facts = product.get("fact_snippet", "") if product else ""

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

    prompt = f"""You are an expert content strategist and copywriter for INF Energy Power (infenergypower.com), a solar and home energy solutions company.

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

    response = None
    last_error = None
    for model_name in model_candidates:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            break
        except Exception as e:
            last_error = e
            continue

    if response is None:
        content = _build_fallback_content(slot, topic, product)
        content["topic"] = topic
        content["pillar"] = pillar
        content["topic_hash"] = topic_hash
        content["product_name"] = product_name
        content["product_sku"] = product_sku
        content["product_price"] = product_price
        content["product_sale_price"] = product_sale_price
        content["product_image_url"] = product.get("image_url", "") if product else ""
        content["date"] = str(date.today())
        content["slot"] = slot
        return content

    raw = response.text.strip()

    # Strip markdown code fences if Gemini wraps response
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.lower().startswith("json"):
            raw = raw[4:]

    content = json.loads(raw.strip())
    content["topic"] = topic
    content["pillar"] = pillar
    content["topic_hash"] = topic_hash
    content["product_name"] = product_name
    content["product_sku"] = product_sku
    content["product_price"] = product_price
    content["product_sale_price"] = product_sale_price
    content["product_image_url"] = product.get("image_url", "") if product else ""
    content["date"] = str(date.today())
    content["slot"] = slot
    return content
