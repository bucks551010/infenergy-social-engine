"""Visual intelligence (Master Build §24-§42, §47, §51-§54, §63).

Purpose
-------
Given the strategic content decision (pillar/genre/audience/copy), decide:
  * whether a visual is even necessary (§26)
  * what format best carries the message (§27, §28)
  * the semantic role of the visual (§25)
  * the visual message (§29) and creative concepts (§30)
  * the full art direction object (§32)
  * a provider-ready image prompt (§33)
  * text-vs-visual information allocation (§36)
  * visual hierarchy (§37)
  * fatigue tracking + visual signatures (§53, §54)

Everything is data-driven; safe to run without a network.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import libraries


# --- Visual necessity (§26) --------------------------------------------------


def visual_necessity_score(
    *,
    genre: dict[str, Any],
    reader_job_config: dict[str, Any],
    platform: str,
    body_word_count: int,
) -> float:
    """0-1: higher = visual really adds value."""
    score = 0.0
    # Genre with strong visual formats → high necessity
    v_prefs = genre.get("visual_format_preferences", [])
    if not v_prefs or v_prefs == ["no_visual"]:
        score += 0.1
    else:
        score += 0.4
    # Instagram all-but-requires an image
    if platform.startswith("instagram"):
        score += 0.4
    elif platform.startswith("facebook"):
        score += 0.25
    else:  # linkedin
        score += 0.15
    # Short body → visual carries the idea
    if body_word_count < 40:
        score += 0.1
    # Reader jobs where visuals save meaningful time
    if reader_job_config.get("typical_emotion") in {"fascination", "surprise"}:
        score += 0.1
    return min(1.0, score)


def visual_required(*, necessity: float, threshold: float = 0.5) -> bool:
    return necessity >= threshold


# --- Visual format routing (§27, §28) ---------------------------------------


def _format_scores(
    *,
    genre: dict[str, Any],
    platform: str,
    body_word_count: int,
    has_product_asset: bool,
    is_carousel_ok: bool,
) -> dict[str, float]:
    formats = libraries.visual_formats()
    scores: dict[str, float] = {}
    genre_prefs = genre.get("visual_format_preferences", [])
    for fid, cfg in formats.items():
        s = 0.0
        # Alignment with genre preferences
        if fid in genre_prefs:
            s += 0.5 - 0.05 * genre_prefs.index(fid)
        # Platform fit
        plat_stem = platform.split("_", 1)[0]
        if any(pf.startswith(plat_stem) for pf in cfg.get("platform_fit", [])):
            s += 0.25
        # Carousel gating
        if cfg.get("carousel") and not is_carousel_ok:
            s -= 0.4
        # Prefer real product asset when we actually have one AND product-related genre
        if fid == "real_product_asset" and has_product_asset and body_word_count < 120:
            s += 0.3
        # Complexity bump for text-heavy genres
        if body_word_count > 120 and cfg.get("carousel"):
            s += 0.2
        scores[fid] = s
    return scores


def route_visual_format(
    *,
    genre: dict[str, Any],
    platform: str,
    body_word_count: int,
    has_product_asset: bool = False,
    allow_carousel: bool = True,
) -> str:
    """Return the chosen visual format id (§27)."""
    scores = _format_scores(
        genre=genre,
        platform=platform,
        body_word_count=body_word_count,
        has_product_asset=has_product_asset,
        is_carousel_ok=allow_carousel,
    )
    if not scores:
        return "fact_card"
    return max(scores.items(), key=lambda kv: kv[1])[0]


# --- Semantic role (§25) ----------------------------------------------------


def visual_semantic_role(*, genre_id: str, reader_job: str) -> str:
    mapping = {
        ("myth_vs_reality", "*"): "COMPARE",
        ("checklist", "*"): "ORGANIZE",
        ("this_vs_that", "*"): "COMPARE",
        ("counterintuitive_insight", "*"): "STOP",
        ("did_you_know", "*"): "STOP",
        ("how_it_works", "*"): "EXPLAIN",
        ("why_does_this_happen", "*"): "EXPLAIN",
        ("problem_consequence_solution", "*"): "TELL_STORY",
        ("faq", "*"): "SIMPLIFY",
        ("term_explainer", "*"): "SIMPLIFY",
    }
    if (genre_id, "*") in mapping:
        return mapping[(genre_id, "*")]
    job_defaults = {
        "TEACH_ME": "EXPLAIN", "EXPLAIN_THIS": "EXPLAIN", "SHOW_ME": "SHOW",
        "PREPARE_ME": "ORGANIZE", "WARN_ME": "STOP", "HELP_ME_CHOOSE": "COMPARE",
        "MAKE_ME_CURIOUS": "CREATE_CURIOSITY", "SURPRISE_ME": "STOP",
        "MAKE_ME_THINK": "MEMORIALIZE", "SAVE_ME_TIME": "SIMPLIFY",
        "GIVE_ME_A_REFERENCE": "MAKE_SAVEABLE", "START_A_CONVERSATION": "MEMORIALIZE",
    }
    return job_defaults.get(reader_job, "EXPLAIN")


# --- Visual message (§29) ---------------------------------------------------


def visual_message(*, angle: str, memory_anchor: str, semantic_role: str) -> str:
    """Precise instruction for the visual, not a caption paraphrase."""
    anchor = memory_anchor.strip() or angle.strip()
    role_verb = {
        "STOP": "Make the viewer stop scrolling with",
        "EXPLAIN": "Explain visually",
        "SHOW": "Show a concrete instance of",
        "COMPARE": "Show a side-by-side comparison illustrating",
        "DEMONSTRATE": "Demonstrate",
        "ORGANIZE": "Present as an organized reference:",
        "EMOTIONALIZE": "Convey emotionally",
        "SIMPLIFY": "Simplify visually",
        "PROVE": "Provide visual evidence of",
        "CONTEXTUALIZE": "Set the scene for",
        "MEMORIALIZE": "Create a memorable single-line visual for",
        "CREATE_CURIOSITY": "Open a visual curiosity gap around",
        "MAKE_SAVEABLE": "Design a saveable reference for",
        "TELL_STORY": "Tell a short visual story of",
        "SUPPORT_BRAND": "Reinforce the brand's identity around",
    }.get(semantic_role, "Communicate")
    return f"{role_verb} {anchor}".strip()


# --- Creative concept generation (§30) --------------------------------------


@dataclass
class CreativeConcept:
    label: str
    description: str
    scores: dict[str, float] = field(default_factory=dict)
    total: float = 0.0


def _score_concept(
    *,
    label: str,
    description: str,
    semantic_role: str,
    genre_id: str,
    brand_tokens: dict[str, Any],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    scores["clarity"] = 0.85 if len(description.split()) <= 24 else 0.55
    scores["originality"] = 0.6 if genre_id in {"educational", "how_it_works"} else 0.75
    scores["relevance"] = 0.85
    scores["scroll_stop"] = 0.8 if semantic_role in {"STOP", "CREATE_CURIOSITY", "COMPARE"} else 0.55
    scores["information_value"] = 0.8 if semantic_role in {"EXPLAIN", "ORGANIZE", "SIMPLIFY"} else 0.5
    scores["brand_fit"] = 0.9 if all(w not in description.lower() for w in brand_tokens.get("must_avoid_in_generated_imagery", [])) else 0.3
    scores["generation_feasibility"] = 0.85
    return scores


def generate_concepts(
    *,
    angle: str,
    memory_anchor: str,
    semantic_role: str,
    genre_id: str,
    concept_stems: list[str] | None = None,
) -> list[CreativeConcept]:
    """Return several ranked creative concepts.

    ``concept_stems`` allow the caller to inject LLM-generated ideas; the
    scorer picks the strongest. Without stems, we synthesize three
    reasonable defaults from the strategy.
    """
    brand = libraries.brand_design_tokens()
    stems = concept_stems or [
        f"A single striking visual centered on {memory_anchor or angle}",
        f"A split-composition comparing the wrong assumption vs the true mechanism of {angle}",
        f"A clean numbered layout organizing the key facts about {angle}",
    ]
    labels = ("hero-focused", "comparison-split", "organized-reference")
    out: list[CreativeConcept] = []
    for i, description in enumerate(stems):
        label = labels[i] if i < len(labels) else f"concept-{i+1}"
        scores = _score_concept(
            label=label,
            description=description,
            semantic_role=semantic_role,
            genre_id=genre_id,
            brand_tokens=brand,
        )
        total = sum(scores.values()) / max(1, len(scores))
        out.append(CreativeConcept(label=label, description=description, scores=scores, total=total))
    out.sort(key=lambda c: c.total, reverse=True)
    return out


# --- Art direction object (§32) ---------------------------------------------


@dataclass
class ArtDirection:
    visual_purpose: str
    visual_message: str
    visual_format: str
    creative_concept: str
    primary_subject: str
    secondary_subjects: list[str]
    action: str
    environment: str
    composition: str
    focal_point: str
    depth: str
    camera_angle: str
    lens_feel: str
    lighting: str
    time_of_day: str
    color_direction: str
    texture: str
    mood: str
    style: str
    realism_level: str
    brand_connection: str
    text_safe_area: str
    must_include: list[str]
    must_avoid: list[str]
    platform_constraints: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "visual_purpose": self.visual_purpose,
            "visual_message": self.visual_message,
            "visual_format": self.visual_format,
            "creative_concept": self.creative_concept,
            "primary_subject": self.primary_subject,
            "secondary_subjects": self.secondary_subjects,
            "action": self.action,
            "environment": self.environment,
            "composition": self.composition,
            "focal_point": self.focal_point,
            "depth": self.depth,
            "camera_angle": self.camera_angle,
            "lens_feel": self.lens_feel,
            "lighting": self.lighting,
            "time_of_day": self.time_of_day,
            "color_direction": self.color_direction,
            "texture": self.texture,
            "mood": self.mood,
            "style": self.style,
            "realism_level": self.realism_level,
            "brand_connection": self.brand_connection,
            "text_safe_area": self.text_safe_area,
            "must_include": self.must_include,
            "must_avoid": self.must_avoid,
            "platform_constraints": self.platform_constraints,
        }


def build_art_direction(
    *,
    visual_purpose: str,
    visual_msg: str,
    visual_format: str,
    concept: CreativeConcept,
    primary_subject: str,
    platform: str,
    is_real_product: bool = False,
) -> ArtDirection:
    brand = libraries.brand_design_tokens()
    photo = brand.get("photography_style", {})
    plat = libraries.platform_specs().get(platform, {})
    must_avoid = list(brand.get("must_avoid_in_generated_imagery", []))
    if is_real_product:
        must_avoid = must_avoid + [
            "AI recreation of product ports, buttons, screens, or brand marks",
            "invented certification labels",
        ]
    return ArtDirection(
        visual_purpose=visual_purpose,
        visual_message=visual_msg,
        visual_format=visual_format,
        creative_concept=concept.description,
        primary_subject=primary_subject,
        secondary_subjects=[],
        action="",
        environment="neutral, honest, non-cliche",
        composition="clear focal point, generous negative space",
        focal_point=primary_subject,
        depth="moderate — subject-first",
        camera_angle="eye-level or slight three-quarter",
        lens_feel=photo.get("lens_feel", "natural, moderate depth of field"),
        lighting=photo.get("lighting_default", "even natural daylight"),
        time_of_day="ambiguous — soft daylight",
        color_direction=", ".join(brand.get("brand_colors", {}).values()) or "brand palette",
        texture="clean, subtle grain acceptable",
        mood=", ".join(brand.get("brand_mood", {}).get("primary_words", [])) or "clear-headed",
        style=", ".join(photo.get("mood_words", [])) or "honest editorial",
        realism_level="photorealistic" if visual_format in {"ai_photorealistic_scene", "ai_editorial_photo", "real_product_asset"} else "illustrative",
        brand_connection="subtle wordmark placement; no fake product recreation",
        text_safe_area=f"padding {plat.get('safe_area_padding_px', 96)}px; logo zone {plat.get('logo_zone_px', 160)}px",
        must_include=["clear focal point"],
        must_avoid=must_avoid,
        platform_constraints=[f"{platform} aspect: {plat.get('aspect_ratios', [])}"],
    )


# --- Image prompt compiler (§33) --------------------------------------------


def compile_image_prompt(
    ad: ArtDirection,
    *,
    extra_negatives: Iterable[str] = (),
) -> tuple[str, str]:
    """Return (positive_prompt, negative_prompt)."""
    parts = [
        f"[{ad.visual_purpose}] {ad.visual_message}",
        f"Format: {ad.visual_format}. Concept: {ad.creative_concept}.",
        f"Subject: {ad.primary_subject}.",
        f"Environment: {ad.environment}. Composition: {ad.composition}. Focal point: {ad.focal_point}.",
        f"Camera: {ad.camera_angle}, {ad.lens_feel}. Lighting: {ad.lighting}. Time: {ad.time_of_day}.",
        f"Color direction: {ad.color_direction}. Texture: {ad.texture}. Mood: {ad.mood}. Style: {ad.style}. Realism: {ad.realism_level}.",
        f"Brand connection: {ad.brand_connection}. Text safe area: {ad.text_safe_area}.",
    ]
    if ad.must_include:
        parts.append("Must include: " + "; ".join(ad.must_include) + ".")
    positive = " ".join(parts)
    negatives = list(ad.must_avoid or [])
    negatives.extend(x for x in extra_negatives if x)
    negative = "; ".join(negatives) if negatives else ""
    return positive, negative


# --- Text-to-visual allocation (§36) ---------------------------------------


@dataclass
class TextVisualAllocation:
    on_image: list[str]
    in_caption: list[str]
    relationship: str  # one of §57 modes


def allocate_text_visual(
    *,
    beats: list[str],
    beat_content: dict[str, str],
    genre: dict[str, Any],
) -> TextVisualAllocation:
    """Decide which beats go on the graphic vs the caption."""
    density = float(genre.get("avg_information_density", 0.5))
    on_image: list[str] = []
    in_caption: list[str] = []
    for beat in beats:
        content = beat_content.get(beat, "").strip()
        if not content:
            continue
        # High-density genres: put the anchor + a short list on image, rest in caption
        if density >= 0.75 and beat in {"hook", "takeaway", "problem", "myth", "reality", "answer", "surprising_answer"}:
            on_image.append(content)
        elif density < 0.6 and beat == "hook":
            on_image.append(content)
        else:
            in_caption.append(content)

    if not on_image and beat_content.get("hook"):
        on_image.append(beat_content["hook"])
    relationship = "VISUAL_AND_CAPTION_SPLIT_INFORMATION"
    if len(on_image) >= 2 and len(in_caption) <= 1:
        relationship = "VISUAL_SUMMARIZES_CAPTION"
    if not in_caption:
        relationship = "VISUAL_EXPLAINS_CAPTION"
    return TextVisualAllocation(on_image=on_image, in_caption=in_caption, relationship=relationship)


# --- Visual hierarchy (§37) -----------------------------------------------


@dataclass
class VisualHierarchy:
    primary: str
    secondary: str
    tertiary: str


def hierarchy_for(*, hook: str, memory_anchor: str, brand_wordmark: str) -> VisualHierarchy:
    return VisualHierarchy(primary=hook.strip(), secondary=memory_anchor.strip(), tertiary=brand_wordmark)


# --- Complexity budget (§42) ----------------------------------------------


def needs_carousel(*, on_image_lines: list[str], max_lines: int) -> bool:
    return len(on_image_lines) > max_lines


# --- Visual signature + fatigue (§53, §54) --------------------------------


def visual_signature(
    *,
    visual_format: str,
    layout_family: str,
    focal_position: str,
    color_family: str,
    headline_position: str,
) -> str:
    """Deterministic signature string used for duplicate/fatigue detection."""
    raw = "|".join([visual_format, layout_family, focal_position, color_family, headline_position])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def recent_signature_overlap(candidate: str, recent: Iterable[str]) -> float:
    recent_list = list(recent)
    if not recent_list:
        return 0.0
    hits = sum(1 for s in recent_list if s == candidate)
    return hits / len(recent_list)


# --- Humanness filter for visuals (§63) -----------------------------------


_VISUAL_AI_TELLS = (
    r"neon holographic ui",
    r"cyberpunk",
    r"impossible hands",
    r"floating ui elements",
    r"random circuitry",
    r"fake certification",
    r"generic smiling business person",
)


def visual_prompt_humanness(positive_prompt: str) -> float:
    low = positive_prompt.lower()
    penalty = 0.0
    for pat in _VISUAL_AI_TELLS:
        if re.search(pat, low):
            penalty += 0.25
    return max(0.0, 1.0 - penalty)


# --- Truth checks (§50) ---------------------------------------------------


_UNTRUTHFUL_CLAIMS = (
    r"waterproof",
    r"impossible",
    r"unbreakable",
    r"lifetime warranty",
    r"instant charge",
    r"solar in the dark",
    r"unlimited runtime",
    r"medical grade",
    r"military grade",
    r"FDA approved",
)


def visual_truth_violations(positive_prompt: str) -> list[str]:
    low = positive_prompt.lower()
    return [c for c in _UNTRUTHFUL_CLAIMS if re.search(c, low)]


_VISUAL_CONCEPT_RULES = (
    (("replace", "instead", "fewer", "consolidat", "one device"), ["SUBTRACTION", "CONSOLIDATION"]),
    (("before", "after", "transform"), ["BEFORE_AFTER", "TRANSFORMATION"]),
    (("outage", "interrupt", "stops", "drops"), ["INTERRUPTION", "CONTINUITY"]),
    (("compare", "choice", "choose", "versus", " vs "), ["CONTRAST", "CHOICE"]),
    (("why", "cause", "because", "mechanism"), ["CAUSE_EFFECT", "REVEAL"]),
    (("deadline", "one percent", "time", "urgent"), ["TIME_PRESSURE", "PRIORITIZATION"]),
)

_SCENE_GRAPH = {
    "airport": ["crowded gate", "occupied outlets", "carry-on bag", "boarding movement", "phones and laptops"],
    "hotel room": ["unfamiliar outlet placement", "bedside table", "packing", "multiple devices", "night routine"],
    "outage": ["changed practical lighting", "stopped appliances", "quiet rooms", "device prioritization", "altered routine"],
    "remote work": ["active laptop", "router", "meeting headset", "deadline pressure", "multiple dependent devices"],
    "workshop": ["active task", "used tools", "credible work surface", "safety clearance", "practical storage"],
    "campsite": ["used equipment", "changing daylight", "weather exposure", "limited infrastructure", "packing decisions"],
}


def _select_visual_concepts(text: str) -> list[str]:
    lower = text.lower()
    for signals, concepts in _VISUAL_CONCEPT_RULES:
        if any(signal in lower for signal in signals):
            return concepts
    return ["HUMAN_REACTION", "OBJECT_CHOREOGRAPHY"]


def _scene_relationships(environment: str) -> list[str]:
    lower = environment.lower()
    for scene, relationships in _SCENE_GRAPH.items():
        if scene in lower:
            return list(relationships)
    return ["one credible foreground object", "an active human task", "environmental evidence of use"]


def _semantic_terms(value: str) -> set[str]:
    ignored = {"about", "after", "before", "could", "every", "from", "have", "into", "should", "that", "their", "there", "these", "this", "through", "what", "when", "where", "which", "while", "with", "would"}
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 4 and token not in ignored}


def build_visual_communication_plan(
    *,
    strategy: dict[str, Any],
    art_direction: dict[str, Any],
    final_copy: str,
    platform: str,
    offering: dict[str, Any] | None = None,
    recent: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Build the communication and production decision before prompt compilation.

    This extends the existing visual pipeline rather than introducing another
    agent. The returned packet is provider-neutral and travels with the
    CreativeRequest so Studio can enforce the same decisions.
    """
    recent = recent or {}
    dominant_idea = str(strategy.get("angle") or strategy.get("human_need") or art_direction.get("visual_message") or "").strip()
    action = str(art_direction.get("action") or art_direction.get("creative_concept") or "").strip()
    environment = str(art_direction.get("environment") or strategy.get("customer_moment") or "a specific real-world environment").strip()
    emotional_mode = str(strategy.get("emotional_mode") or strategy.get("emotional_driver") or art_direction.get("mood") or "HUMAN").upper().replace(" ", "_")
    product_name = str((offering or {}).get("name") or art_direction.get("product_name") or "").strip()
    product_role = str(strategy.get("product_role") or "").strip()
    proof = [str(item) for item in (strategy.get("proof") or (offering or {}).get("verified_facts") or []) if str(item).strip()]
    product_earned = bool(product_name and product_role and proof)
    characters = strategy.get("characters") or []
    if isinstance(characters, str):
        characters = [item.strip() for item in characters.split(",") if item.strip()]
    canonical = bool(characters)
    concepts = _select_visual_concepts(f"{dominant_idea} {action} {final_copy}")
    grammar = [concept for concept in concepts if concept in {"CONTRAST", "SUBTRACTION", "INTERRUPTION", "CONTINUITY", "TRANSFORMATION", "REVEAL", "OBJECT_CHOREOGRAPHY"}]
    grammar = grammar or ["DEPTH", "FRAMING"]
    one_second_message = str(strategy.get("one_second_message") or dominant_idea or action).strip()[:180]
    image_job = str(strategy.get("image_job") or (f"Show {action}" if action else f"Make {one_second_message} understandable without words")).strip()
    headline_job = str(strategy.get("headline_job") or "Reframe the tension without describing the picture").strip()
    caption_job = str(strategy.get("caption_job") or "Explain the mechanism, evidence, and human consequence the image cannot show alone").strip()
    cta_job = str(strategy.get("cta_job") or "Offer the next proportionate action for this awareness stage").strip()
    presence = str(art_direction.get("product_presence") or "").lower()
    visibility = 0
    if product_earned:
        visibility = {"incidental": 1, "supporting": 2, "prominent": 3, "hero": 4, "demonstration": 5}.get(presence, 2)
    visual_hero = "CHARACTER" if canonical else "PRODUCT" if visibility >= 3 else "PROBLEM" if "INTERRUPTION" in concepts else "TRANSFORMATION" if "TRANSFORMATION" in concepts else "PERSON"
    before = str(strategy.get("before_frame") or strategy.get("customer_moment") or f"The normal routine is still intact in {environment}").strip()
    after = str(strategy.get("after_frame") or strategy.get("human_outcome") or strategy.get("human_value") or "The consequence of the decision becomes visible").strip()
    visual_format = str(art_direction.get("visual_format") or "editorial_photo").lower()
    text_mode = "NONE" if any(token in visual_format for token in ("cinematic", "photo")) else "INFORMATIONAL" if any(token in visual_format for token in ("diagram", "fact", "carousel")) else "HEADLINE"
    layout_archetype = "SEQUENTIAL_STORY" if "carousel" in visual_format else "BEFORE_AFTER" if "BEFORE_AFTER" in concepts else "PRODUCT_DEMONSTRATION" if visibility >= 4 else "HUMAN_STORY" if visual_hero == "PERSON" else "EDITORIAL_PHOTO"
    simpler_medium = "CAROUSEL_OR_DIAGRAM" if len(final_copy.split()) > 160 or "CAUSE_EFFECT" in concepts else "EXISTING_PRODUCT_PHOTOGRAPHY" if visibility >= 4 else "GENERATED_EDITORIAL_SCENE"
    production_strategy = "REFERENCE_GUIDED" if canonical else "PRODUCT_INSERTION" if visibility >= 3 else "GRAPHIC_DESIGN_FIRST" if text_mode == "INFORMATIONAL" else "SINGLE_PASS"
    risk = "HIGH" if canonical or visibility >= 4 or len(proof) >= 4 else "MEDIUM" if product_earned or text_mode == "INFORMATIONAL" else "LOW"
    candidate_count = {"LOW": 2, "MEDIUM": 3, "HIGH": 4}[risk]
    strategy_terms = _semantic_terms(f"{dominant_idea} {one_second_message}")
    copy_terms = _semantic_terms(final_copy)
    visual_terms = _semantic_terms(f"{image_job} {action} {' '.join(concepts)}")
    copy_overlap = len(strategy_terms & copy_terms) / max(1, len(strategy_terms))
    visual_overlap = len(strategy_terms & visual_terms) / max(1, len(strategy_terms))
    alignment = "COMPLEMENTARY" if copy_overlap >= 0.25 and visual_overlap >= 0.25 else "PROGRESSIVE" if visual_overlap >= 0.25 else "DISCONNECTED"
    return {
        "version": "visual_creative_brain_v1",
        "communication_jobs": {"image": image_job, "headline": headline_job, "caption": caption_job, "cta": cta_job},
        "one_second_message": one_second_message,
        "visual_concept": concepts,
        "visual_grammar": grammar,
        "visual_hero": visual_hero,
        "environment": {"name": environment, "relationships": _scene_relationships(environment), "recently_used": environment.lower() in {str(item).lower() for item in recent.get("environments", [])}},
        "human_behavior": action,
        "emotional_mode": emotional_mode,
        "wardrobe_direction": str(strategy.get("wardrobe_direction") or "contemporary, activity-appropriate, unbranded, believable for the environment"),
        "narrative": {"before": before, "current": action, "after": after},
        "composition": {"primary_focal_point": art_direction.get("focal_point", visual_hero), "negative_space": art_direction.get("text_safe_area", "platform-safe upper third"), "depth": art_direction.get("depth", "foreground, active middle ground, contextual background"), "eye_path": f"{visual_hero.lower()} -> action -> consequence", "crop_safety": "protect focal action and any verified product at all target ratios"},
        "camera": {"shot_size": str(strategy.get("shot_size") or "medium-wide"), "angle": art_direction.get("camera_angle", "eye-level"), "lens_feel": art_direction.get("lens_feel", "neutral editorial"), "movement": str(strategy.get("camera_movement") or "locked")},
        "lighting": art_direction.get("lighting", "naturalistic practical light motivated by the environment"),
        "color_character": art_direction.get("color_direction", "natural skin tones, restrained saturation, selective brand accents"),
        "product": {"name": product_name or None, "visibility_level": visibility, "role": product_role or None, "interaction": str(strategy.get("product_interaction") or ("physically credible use with verified orientation and connections" if visibility else "none")), "visual_lock_required": visibility >= 2},
        "text_mode": text_mode,
        "layout_archetype": layout_archetype,
        "reference_package": {
            "smallest_useful_bundle": True,
            "character_required": canonical,
            "product_required": visibility >= 2,
            "environment_reference_required": False,
            "product_asset_urls": [str(url) for url in ((offering or {}).get("images") or [])[:3] if str(url).startswith("https://")],
        },
        "production": {"strategy": production_strategy, "simpler_medium_test": simpler_medium, "candidate_count": candidate_count, "max_major_revisions": 2, "fallback_ladder": ["EDIT_OR_INPAINT", "SIMPLER_SCENE", "EXISTING_APPROVED_ASSET", "TYPOGRAPHY_OR_DIAGRAM"]},
        "quality_governance": {"risk": risk, "semantic_alignment": alignment, "copy_strategy_overlap": round(copy_overlap, 3), "visual_strategy_overlap": round(visual_overlap, 3), "blocking": alignment == "DISCONNECTED", "decision": "CHANGE_VISUAL_CONCEPT" if alignment == "DISCONNECTED" else "AUTO_APPROVE"},
        "platform_recomposition": {"platform": platform.split("_", 1)[0], "rule": "RECOMPOSE_IF_CROP_BREAKS_HIERARCHY", "mobile_scroll_test_required": text_mode != "NONE"},
    }


# --- V5 tension-first visual direction -------------------------------------


_HUMAN_TRUTH_DIR = Path(__file__).resolve().parents[2] / "data" / "marketing" / "human_truth"


def _human_truth_payload(name: str) -> dict[str, Any]:
    try:
        payload = json.loads((_HUMAN_TRUTH_DIR / name).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _v5_archetype(*, reader_job: str, genre_id: str, strategy: dict[str, Any]) -> str:
    job = str(reader_job or "").upper()
    genre = str(genre_id or "").lower()
    if job in {"MAKE_ME_THINK", "START_A_CONVERSATION"}:
        return "engagement"
    if job in {"GIVE_ME_A_REFERENCE", "SAVE_ME_TIME", "EXPLAIN_THIS"} or any(token in genre for token in ("checklist", "faq", "myth", "reference")):
        return "text_forward"
    if job in {"TEACH_ME", "SHOW_ME", "HELP_ME_CHOOSE", "PREPARE_ME"}:
        return "educational"
    if strategy.get("customer_moment") or strategy.get("human_need"):
        return "human_moment"
    return "brand_position"


def _product_presence(*, archetype: str, offering: dict[str, Any] | None) -> str:
    if archetype in {"engagement", "text_forward", "human_moment", "brand_position"}:
        return "absent"
    if archetype == "educational":
        return "incidental" if offering else "absent"
    return "hero" if offering else "absent"


def _matching_tension(strategy: dict[str, Any], audience: str) -> dict[str, Any]:
    tensions = _human_truth_payload("tension_library.json").get("tensions", [])
    if not isinstance(tensions, list):
        return {}
    text = " ".join(str(strategy.get(key) or "") for key in ("customer_moment", "human_need", "angle", "topic")).lower()
    for tension in tensions:
        if isinstance(tension, dict) and str(tension.get("who_feels_it") or "") == audience:
            return tension
    return next((item for item in tensions if isinstance(item, dict) and any(token in text for token in str(item.get("tension") or "").lower().split())), {})


def build_v5_art_directions(
    *,
    strategy: dict[str, Any],
    reader_job: str,
    genre_id: str,
    platform: str,
    offering: dict[str, Any] | None = None,
    overlay_text: str = "",
    recent_scenes: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Create three distinct, scored directions before choosing one render."""
    identity = _human_truth_payload("visual_identity.json").get("approved_visual_identity", {})
    archetype = _v5_archetype(reader_job=reader_job, genre_id=genre_id, strategy=strategy)
    presence = _product_presence(archetype=archetype, offering=offering)
    audience = str(strategy.get("audience") or "")
    tension = _matching_tension(strategy, audience)
    environments = identity.get("environment_library", []) if isinstance(identity, dict) else []
    lights = identity.get("light_library", []) if isinstance(identity, dict) else []
    compositions = identity.get("composition_library", []) if isinstance(identity, dict) else []
    if not environments or not lights or not compositions:
        return []
    directions: list[dict[str, Any]] = []
    recent_scene_set = {str(scene).strip().lower() for scene in recent_scenes if str(scene).strip()}
    for index in range(3):
        environment = environments[index % len(environments)]
        light = lights[index % len(lights)]
        composition = compositions[index % len(compositions)]
        text_forward = archetype == "text_forward"
        scene = str(tension.get("visual_register") or strategy.get("customer_moment") or strategy.get("angle") or "a real moment of practical preparation")
        scene_key = scene.lower()
        novelty = 0.0 if scene_key in recent_scene_set else 1.0
        score = 90.0 - index * 2.0 + novelty * 8.0
        if text_forward and composition.get("negative_space"):
            score += 4.0
        if presence == "absent":
            score += 3.0
        directions.append({
            "version": "human_truth_v5",
            "archetype": archetype,
            "product_presence": presence,
            "tension_id": tension.get("id", ""),
            "scene": scene,
            "hero_idea": str(strategy.get("human_need") or strategy.get("angle") or scene),
            "subject": str(tension.get("who_feels_it") or audience or "a person in a real preparation moment"),
            "environment": environment,
            "foreground": "one ordinary, used object that makes the moment specific",
            "midground": "the person or practical task in progress",
            "background": environment.get("place", "a real regional environment"),
            "light": light,
            "composition": composition,
            "optics": {"focal_length": "35mm", "aperture": "f/4", "focus_point": "the practical action", "motion": "subtle handheld imperfection", "capture_style": "handheld documentary"},
            "color": {"palette": identity.get("palette", []), "temperature_bias": light.get("temperature", "neutral"), "contrast_curve": light.get("contrast", "balanced"), "saturation": "restrained"},
            "texture": ", ".join(environment.get("details", [])[:3]),
            "emotional_register": "capable, calm, and seen",
            "negative_space": composition.get("negative_space", "upper third for breathing room"),
            "aspect_ratio": "1:1" if platform.startswith("instagram") else "4:5",
            "text_overlay": {"enabled": text_forward, "text": overlay_text, "placement": composition.get("negative_space", "upper third"), "safe_margin_ratio": identity.get("typography", {}).get("safe_margin_ratio", 0.08)},
            "must_not_appear": list(identity.get("never_appears", [])),
            "style_anchor": "available-light documentary reportage",
            "reference_conditioning_required": presence in {"incidental", "hero"},
            "score_components": {
                "scene_truth": 1.0 if tension else 0.6,
                "specificity": 1.0 if environment.get("details") else 0.5,
                "brand_fit": 1.0,
                "visual_novelty": novelty,
                "claim_safety": 1.0,
            },
            "score": score,
        })
    return sorted(directions, key=lambda item: float(item["score"]), reverse=True)


def compile_v5_scene_prompt(direction: dict[str, Any]) -> str:
    """Compile one clean photographic background plate; typography is composited later."""
    light = direction.get("light", {}) if isinstance(direction.get("light"), dict) else {}
    composition = direction.get("composition", {}) if isinstance(direction.get("composition"), dict) else {}
    optics = direction.get("optics", {}) if isinstance(direction.get("optics"), dict) else {}
    color = direction.get("color", {}) if isinstance(direction.get("color"), dict) else {}
    parts = [
        f"Photograph {direction.get('subject', 'a real person')} in {direction.get('scene', 'a practical real-world moment')}",
        f"Set in {direction.get('environment', {}).get('place', 'a specific regional environment') if isinstance(direction.get('environment'), dict) else direction.get('environment', '')}",
        f"Foreground: {direction.get('foreground', '')}. Midground: {direction.get('midground', '')}. Background: {direction.get('background', '')}",
        f"Light is {light.get('source', 'available light')} from {light.get('direction', 'the side')}, {light.get('quality', 'natural')}, {light.get('temperature', 'neutral')}, motivated by {light.get('motivation', 'the scene')}",
        f"Composition is {composition.get('framing', 'medium')} at {composition.get('camera_height', 'eye level')}, {composition.get('angle', 'three-quarter')}, with {composition.get('negative_space', direction.get('negative_space', 'clear negative space'))}",
        f"Capture at {optics.get('focal_length', '35mm')} {optics.get('aperture', 'f/4')}, focus on {optics.get('focus_point', 'the action')}, {optics.get('capture_style', 'documentary')}",
        f"Texture: {direction.get('texture', '')}. Color: {', '.join(color.get('palette', []))}; {color.get('temperature_bias', '')}; {color.get('contrast_curve', '')}",
        f"Style: {direction.get('style_anchor', 'available-light documentary reportage')}. No readable text, signs, screens, logos, badges, watermarks, or rendered typography.",
        "Do not show: " + "; ".join(str(item) for item in direction.get("must_not_appear", []) if str(item).strip()) + ".",
    ]
    return ". ".join(part.strip(". ") for part in parts if part).strip()[:3200]
