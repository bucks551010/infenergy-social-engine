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
import re
from dataclasses import dataclass, field
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


def compile_image_prompt(ad: ArtDirection) -> tuple[str, str]:
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
    negative = "; ".join(ad.must_avoid) if ad.must_avoid else ""
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
