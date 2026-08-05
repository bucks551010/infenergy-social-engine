import os
import json
import random
import hashlib
from datetime import date
import google.generativeai as genai

SITE_URL = os.environ.get("WP_URL", "https://www.infenergypower.com")
# DATA_DIR can be overridden by Railway volume mount (set DATA_DIR=/app/data in Railway Variables)
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def load_topic_queue() -> dict:
    with open(os.path.join(DATA_DIR, "topic_queue.json"), "r") as f:
        return json.load(f)


def load_history() -> dict:
    with open(os.path.join(DATA_DIR, "post_history.json"), "r") as f:
        return json.load(f)


def save_history(history: dict) -> None:
    with open(os.path.join(DATA_DIR, "post_history.json"), "w") as f:
        json.dump(history, f, indent=2)


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


def generate(slot: str) -> dict:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")

    queue = load_topic_queue()
    history = load_history()
    pillar, topic, topic_hash = _pick_topic(queue, history)

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

QUALITY RULES — every piece must follow all of these:
1. Open with a hook that creates immediate curiosity or challenges a common assumption.
2. Include at least one specific number, stat, or real-world comparison that makes the content credible.
3. Deliver a genuine insight the reader cannot easily Google — a specific angle they haven't considered.
4. Write like a human expert, not a marketing team. Never use words like "revolutionize", "game-changer", or "unlock your potential."
5. Never make unverifiable guarantees. Use language like "many homeowners", "up to", "in most cases" where appropriate.
6. Every post must have a clear emotional payoff: relief, confidence, curiosity satisfied, or urgency to act.

Return ONLY valid JSON with these exact keys (no markdown, no code fences):
{{
  "wp_title": "Specific, curiosity-driven SEO title under 65 characters — not generic",
  "wp_content": "Full blog post as clean HTML with <h2> subheadings. 450-550 words. Open strong, build a logical case, end with a clear next step. Include at least 2 specific data points or examples.",
  "wp_excerpt": "One punchy sentence under 160 characters that makes someone want to click",
  "fb_caption": "150-220 words. Conversational and personal. Open with a surprising statement or question. Include one specific number or fact. End with a genuine question that invites comments. 4-5 targeted hashtags on the last line only.",
  "ig_caption": "First line must be a scroll-stopping hook under 10 words. 120-160 words total. Specific, visual, and personal. 7-9 hashtags on the final line only — mix broad and niche.",
  "li_text": "180-260 words. Professional but not corporate. Open with a counterintuitive insight or bold statement. Build a tight logical argument. Include one specific data point. End with a direct, frictionless CTA — tell them exactly what the first step looks like."
}}"""

    response = model.generate_content(prompt)
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
    content["date"] = str(date.today())
    content["slot"] = slot
    return content
