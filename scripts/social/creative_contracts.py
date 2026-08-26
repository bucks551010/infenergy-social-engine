"""Shared Social Engine -> Entertainment Studio production contracts."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any


CANONICAL_ROUTES = {"INFENERGY_CHARACTER", "MICRO_MISSION", "LUX_LED", "CINEMATIC_STORY"}


def _platform(value: str) -> str:
    stem = str(value or "instagram").split("_", 1)[0].lower()
    return stem if stem in {"facebook", "instagram", "linkedin"} else "instagram"


def _earned_product(strategy: dict[str, Any], art: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
    role = str(strategy.get("product_role") or "").strip()
    proof = [str(item) for item in (strategy.get("proof") or []) if str(item).strip()]
    product = str(strategy.get("offering") or art.get("product_name") or "").strip()
    return (product, role, proof) if product and role and proof else (None, None, [])


def _content_worlds(strategy: dict[str, Any], art: dict[str, Any], *, product_earned: bool) -> list[str]:
    mode = str(strategy.get("creative_mode") or strategy.get("content_world") or "").upper()
    topic = " ".join(str(strategy.get(key, "")) for key in ("topic", "angle", "reader_job")).lower()
    worlds: list[str] = []
    if mode in {"MICRO_MISSION", "ENTERTAINMENT"}:
        worlds.append("ENTERTAINMENT")
    if any(term in topic for term in ("science", "battery", "electricity", "how ", "why ")):
        worlds.append("SCIENCE_DISCOVERY")
    if product_earned:
        worlds.append("COMMERCE")
    if str(strategy.get("reader_job", "")).upper() == "START_A_CONVERSATION":
        worlds.append("COMMUNITY_PARTICIPATION")
    return worlds or ["HUMAN_LIFE"]


def _characters(strategy: dict[str, Any], art: dict[str, Any]) -> list[str]:
    declared = strategy.get("characters") or []
    if isinstance(declared, str):
        declared = [item.strip() for item in declared.split(",") if item.strip()]
    text = " ".join(str(value) for value in (
        strategy.get("creative_mode", ""), strategy.get("angle", ""), strategy.get("visual_objective", ""),
        art.get("primary_subject", ""), art.get("creative_concept", ""), art.get("action", ""),
    ))
    characters = list(declared) if isinstance(declared, list) else []
    if re.search(r"\b(eleven|infenergy superhero|infenergy character)\b", text, re.I) and "Eleven" not in characters:
        characters.append("Eleven")
    if re.search(r"\blux\b", text, re.I) and "LUX" not in characters:
        characters.append("LUX")
    return characters


def _route(strategy: dict[str, Any], characters: list[str], worlds: list[str]) -> str:
    requested = str(strategy.get("creative_mode") or strategy.get("creative_route") or "").upper().replace(" ", "_")
    aliases = {"CHARACTER": "INFENERGY_CHARACTER", "ELEVEN": "INFENERGY_CHARACTER", "MICROMISSION": "MICRO_MISSION", "LUX": "LUX_LED"}
    requested = aliases.get(requested, requested)
    if requested in CANONICAL_ROUTES and characters:
        return requested
    if any(character.upper() == "LUX" for character in characters) and not any(character.lower() == "eleven" for character in characters):
        return "LUX_LED"
    if characters:
        return "MICRO_MISSION" if "ENTERTAINMENT" in worlds and "mission" in requested.lower() else "CINEMATIC_STORY"
    if "COMMERCE" in worlds:
        return "PRODUCT_STUDIO"
    if "SCIENCE_DISCOVERY" in worlds:
        return "SCIENCE_VISUAL"
    return "REAL_WORLD_LIFESTYLE"


@dataclass
class CreativeRequest:
    request_id: str
    content_id: str
    objective: str
    content_worlds: list[str]
    platform: str
    format: str
    requested_route: str
    human_truth: str
    human_tension: str
    dominant_idea: str
    audience_reaction: str
    emotional_mode: str
    characters: list[str]
    canon_required: bool
    story: dict[str, str]
    visual_standard: str
    visual_hero: str
    what_happens: str
    must_include: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    reference_asset_ids: list[str] = field(default_factory=list)
    continuity_requirements: list[str] = field(default_factory=list)
    product: str | None = None
    product_role: str | None = None
    verified_proof: list[str] = field(default_factory=list)
    product_truth_version: str | None = None

    def as_studio_payload(self) -> dict[str, Any]:
        payload = {
            "requestId": self.request_id, "contentId": self.content_id, "objective": self.objective,
            "contentWorlds": self.content_worlds, "platform": self.platform, "format": self.format,
            "requestedRoute": self.requested_route, "humanTruth": self.human_truth,
            "humanTension": self.human_tension, "dominantIdea": self.dominant_idea,
            "audienceReaction": self.audience_reaction, "emotionalMode": self.emotional_mode,
            "characters": self.characters, "canonRequired": self.canon_required, "story": self.story,
            "visualStandard": self.visual_standard, "visualHero": self.visual_hero,
            "whatHappens": self.what_happens, "mustInclude": self.must_include, "mustAvoid": self.must_avoid,
            "referenceAssetIds": self.reference_asset_ids, "continuityRequirements": self.continuity_requirements,
        }
        if self.product:
            payload["product"] = self.product
        if self.product_role:
            payload["productRole"] = self.product_role
        if self.verified_proof:
            payload["verifiedProof"] = self.verified_proof
        if self.product_truth_version:
            payload["productTruthVersion"] = self.product_truth_version
        return payload


def build_creative_request(
    *, post_id: str, platform: str, strategy: dict[str, Any], art_direction: dict[str, Any],
    human_truth: dict[str, Any], audience_reaction: str, format_name: str,
) -> CreativeRequest:
    product, product_role, proof = _earned_product(strategy, art_direction)
    worlds = _content_worlds(strategy, art_direction, product_earned=bool(product))
    characters = _characters(strategy, art_direction)
    route = _route(strategy, characters, worlds)
    human_moment = str(strategy.get("customer_moment") or art_direction.get("environment") or "a recognizable human moment").strip()
    action = str(art_direction.get("action") or "").strip()
    if not action:
        action = str(art_direction.get("creative_concept") or strategy.get("visual_objective") or strategy.get("angle") or "").strip()
    if not action:
        raise ValueError("CreativeRequest requires an explicit WHAT_HAPPENS action")
    payoff = str(strategy.get("human_outcome") or strategy.get("human_value") or audience_reaction or "the human consequence becomes visible").strip()
    emotional = str(strategy.get("emotional_mode") or strategy.get("emotional_driver") or "HUMAN").upper().replace(" ", "_")
    allowed_emotions = {"FUNNY", "CINEMATIC", "CURIOUS", "WARM", "SERIOUS", "NERDY", "SURPRISING", "QUIET", "EPIC", "FUTURISTIC", "USEFUL", "TENSE", "ABSURD", "HOPEFUL", "DOCUMENTARY", "PREMIUM", "HUMAN", "PLAYFUL", "REFLECTIVE"}
    if emotional not in allowed_emotions:
        emotional = "CINEMATIC" if characters else "HUMAN"
    visual_hero = "CHARACTER" if characters else "PRODUCT" if art_direction.get("product_name") else "SCIENCE_PHENOMENON" if "SCIENCE_DISCOVERY" in worlds else "PERSON"
    return CreativeRequest(
        request_id=str(uuid.uuid4()), content_id=post_id,
        objective=str(strategy.get("visual_objective") or art_direction.get("visual_purpose") or "communicate one worthwhile idea"),
        content_worlds=worlds, platform=_platform(platform), format=format_name or "image", requested_route=route,
        human_truth=str(human_truth.get("human_truth") or strategy.get("human_need") or strategy.get("customer_moment") or "energy enables ordinary life"),
        human_tension=str(strategy.get("human_tension") or strategy.get("human_need") or "CONTINUITY"),
        dominant_idea=str(strategy.get("angle") or art_direction.get("visual_message") or action), audience_reaction=audience_reaction or "This matters to me",
        emotional_mode=emotional, characters=characters, canon_required=route in CANONICAL_ROUTES,
        story={"setup": human_moment, "trigger": str(strategy.get("human_need") or strategy.get("hook_promise") or "energy becomes consequential"), "action": action, "payoff": payoff},
        product=product,
        product_role=product_role,
        verified_proof=proof,
        product_truth_version=str(strategy.get("product_truth_version") or "") or None,
        visual_standard="; ".join(str(art_direction.get(key, "")) for key in ("composition", "camera_angle", "lens_feel", "lighting", "style") if art_direction.get(key)),
        visual_hero=visual_hero, what_happens=action,
        must_include=list(art_direction.get("must_include") or []), must_avoid=list(art_direction.get("must_avoid") or []),
        continuity_requirements=["locked character identity", "costume continuity", "behavioral canon", "story continuity"] if route in CANONICAL_ROUTES else [],
    )