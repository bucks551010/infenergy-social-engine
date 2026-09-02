from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


CONTENT_FORMATS: dict[str, dict[str, Any]] = {
    "infenergy_micro_mission": {
        "display_name": "Infenergy Micro Mission",
        "aliases": ["micro mission", "infenergy mission", "swipeable comic", "comic carousel"],
        "creative_route": "MICRO_MISSION",
        "delivery": "carousel",
        "kind": "carousel",
        "aspect_ratio": "4:5",
        "default_card_count": 8,
        "card_count_range": [6, 10],
        "autonomous_seed_count": [5, 10],
        "canon": {
            "version": "micro-mission-1.0",
            "cover_required": True,
            "finale_required": True,
            "story_first": True,
            "still_images_only": True,
            "product_optional": True,
            "recent_story_review_required": True,
            "permanent_canon_invention_forbidden": True,
        },
    },
    "infenergy_storypage": {
        "display_name": "Infenergy StoryPage",
        "aliases": [
            "storypage", "story page", "one-page infenergy story", "one-picture infenergy comic",
            "story-size infenergy comic", "vertical infenergy story comic", "comic-story post",
        ],
        "creative_route": "STORYPAGE",
        "delivery": "single_image",
        "kind": "storypage",
        "aspect_ratio": "9:16",
        "canvas": {"width": 1080, "height": 1920},
        "default_panel_count": 4,
        "panel_count_range": [3, 6],
        "autonomous_seed_count": [8, 15],
        "canon": {
            "version": "storypage-1.0",
            "one_image_only": True,
            "hero_panel_required": True,
            "brand_ending_required": True,
            "top_to_bottom_reading": True,
            "mobile_safe_zones_required": True,
            "product_optional": True,
            "recent_story_review_required": True,
            "permanent_canon_invention_forbidden": True,
        },
    },
    "superhero_text_integration": {
        "display_name": "Superhero Text Integration",
        "aliases": ["superhero with the text integration", "superhero with text", "infenergy quote in the scene", "physical typography"],
        "creative_route": "CINEMATIC_STORY",
        "delivery": "single_image",
        "kind": "typography",
        "aspect_ratio": "4:5",
    },
    "today_news": {
        "display_name": "Today News",
        "aliases": ["today's news", "today news", "current news", "current event"],
        "creative_route": "DOCUMENTARY",
        "delivery": "single_image",
        "kind": "cinematic",
        "aspect_ratio": "4:5",
        "source_required": True,
    },
    "cinematic_brand_poster": {"display_name": "Cinematic Brand Poster", "aliases": ["cinematic poster"], "creative_route": "CINEMATIC_STORY", "delivery": "single_image", "kind": "cinematic", "aspect_ratio": "4:5"},
    "educational_story_carousel": {"display_name": "Educational Story Carousel", "aliases": ["educational carousel"], "creative_route": "CAROUSEL", "delivery": "carousel", "kind": "carousel", "aspect_ratio": "4:5"},
    "product_proof_story": {"display_name": "Product Proof Story", "aliases": ["fit check", "product lifestyle proof"], "creative_route": "PRODUCT_STUDIO", "delivery": "single_image", "kind": "product", "aspect_ratio": "4:5"},
    "culture_current": {"display_name": "Culture Current", "aliases": ["culture current", "cultural observation"], "creative_route": "DOCUMENTARY", "delivery": "single_image", "kind": "cinematic", "aspect_ratio": "4:5"},
    "try_this_irl": {"display_name": "Try This IRL", "aliases": ["try this irl", "60-second drill", "challenge carousel"], "creative_route": "CAROUSEL", "delivery": "carousel", "kind": "carousel", "aspect_ratio": "4:5"},
    "energy_identity_statement": {"display_name": "Energy Is an Identity", "aliases": ["energy identity", "brand statement"], "creative_route": "INFENERGY_CHARACTER", "delivery": "single_image", "kind": "cinematic", "aspect_ratio": "4:5"},
}


def content_format_catalog() -> list[dict[str, Any]]:
    return [{"identifier": identifier, **deepcopy(value)} for identifier, value in CONTENT_FORMATS.items()]


def resolve_content_format(message: str) -> dict[str, Any] | None:
    text = str(message or "")
    normalized = re.sub(r"[_-]+", " ", text).lower()
    for identifier, definition in CONTENT_FORMATS.items():
        names = [identifier.replace("_", " "), definition["display_name"], *definition.get("aliases", [])]
        if any(re.search(rf"\b{re.escape(name.lower())}\b", normalized) for name in names):
            return {"identifier": identifier, **deepcopy(definition)}
    return None


def dialogue_quality_contract() -> dict[str, Any]:
    return {
        "locked_before_visual_production": True,
        "deterministic_compositing_required": True,
        "bubble_word_target": [2, 12],
        "paragraph_bubbles_forbidden": True,
        "image_exposition_forbidden": True,
        "subtext_required_when_appropriate": True,
        "silence_allowed": True,
        "infenergy_voice": ["intelligent", "observant", "confident", "concise", "human", "culturally natural"],
        "forbidden_voice": ["corporate copy", "AI assistant", "textbook", "infomercial", "generic superhero imitation"],
        "qa_questions": [
            "Would a good actor enjoy saying this?", "Does every line reveal character or advance the story?",
            "Is the dialogue concise and readable on a phone?", "Is there rhythm, subtext, or a memorable line?",
        ],
    }