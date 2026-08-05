import os
import json
import random
import hashlib
from datetime import date
import google.generativeai as genai

SITE_URL = os.environ.get("WP_URL", "https://www.infenergypower.com")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


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

    post_type = {"morning": "educational", "midday": "proof", "evening": "cta"}.get(slot, "educational")

    prompt = f"""You are a social media content writer for INF Energy Power (infenergypower.com), a solar and home energy solutions company.
Brand voice: professional, confident, helpful, and results-focused. Never make unverifiable claims or guarantees.
Topic: {topic}
Post type today: {post_type}
  - educational: teach something genuinely valuable, no hard sell
  - proof: share a result, stat, or case study with credibility
  - cta: clear, specific call to action driving leads or consultations

Return ONLY valid JSON with these exact keys (no markdown, no code fences):
{{
  "wp_title": "SEO blog post title under 65 characters",
  "wp_content": "Full blog post as HTML paragraphs, 350-500 words, informative and engaging with subheadings",
  "wp_excerpt": "One sentence excerpt under 160 characters",
  "fb_caption": "Facebook post 100-200 words, conversational, ends with question or CTA, 3-5 hashtags",
  "ig_caption": "Instagram caption 100-150 words, strong hook as first line, 6-8 hashtags at end",
  "li_text": "LinkedIn post 150-250 words, professional and insight-driven, ends with CTA to schedule a free consultation"
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
