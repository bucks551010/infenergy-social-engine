"""Generate one Gemini-authored, Gemini-rendered Infenergy Micro Mission Story."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from social import model_router
from social.gemini_budget import tracked_gemini_call
from social_visuals import generate_strict_gemini_image, review_rendered_visual


REQUIRED_TEXT_LIMITS = {
    "series_label": 24,
    "episode_title": 32,
    "threat_caption": 42,
    "action_line": 42,
    "resolution_caption": 42,
    "mission_line": 42,
}
VISIBLE_TEXT_KEYS = ("series_label", "episode_title", "threat_caption", "action_line", "mission_line")


def _validate_episode(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RuntimeError("gemini_episode_schema_invalid:not_an_object")
    missing = [key for key in REQUIRED_TEXT_LIMITS if not str(value.get(key) or "").strip()]
    missing.extend(key for key in ("threat_scene", "hero_action", "resolution_scene") if not str(value.get(key) or "").strip())
    if missing:
        raise RuntimeError(f"gemini_episode_schema_invalid:{','.join(missing)}")
    oversized = [
        key for key, limit in REQUIRED_TEXT_LIMITS.items()
        if len(str(value[key]).strip()) > limit
    ]
    if oversized:
        raise RuntimeError(f"gemini_episode_text_too_long:{','.join(oversized)}")
    return {key: str(value[key]).strip() for key in (*REQUIRED_TEXT_LIMITS, "threat_scene", "hero_action", "resolution_scene")}


def _author_episode() -> dict[str, str]:
    prompt = (
        "Invent one original episode of Infenergy: Micro Missions for a single Instagram Story graphic. "
        "Return one JSON object with exactly these string keys: series_label, episode_title, threat_caption, "
        "threat_scene, action_line, hero_action, resolution_caption, resolution_scene, mission_line. "
        "The episode must have a concrete civilian in immediate danger from a sudden power failure, a visible consequence "
        "that will happen within seconds, and one unmistakably superheroic intervention only Infenergy could perform. "
        "Infenergy must first observe a specific signal, predict the failure, adapt his intelligent energy system, then take "
        "dynamic physical action that prevents harm and restores the civilian's agency. Do not make him merely advise, pose, "
        "hold a flashlight, or point at equipment. End in a visibly changed state caused by his action. Keep the action plausible "
        "inside Infenergy's preparation-and-intelligent-energy power language; no magic lightning attacks. Make the three scenes "
        "visually different and instantly readable in order. All public text must be original, plain English, and short. "
        "series_label must be at most 24 characters; episode_title at most 32; threat_caption, action_line, "
        "resolution_caption, and mission_line at most 42 characters each. Use no hashtags, trademark symbols, specs, or markdown."
    )
    episode = model_router.generate_json(
        "topic_generation",
        prompt,
        system_instruction=(
            "You are the sole story and copy author for Infenergy: Micro Missions. Write compact visual superhero storytelling, "
            "not preparedness advertising. Preserve the hero's originality and human-centered restraint."
        ),
    )
    if episode is None:
        raise RuntimeError(f"gemini_episode_generation_failed:{model_router.last_error() or 'empty_response'}")
    return _validate_episode(episode)


def _image_prompt(episode: dict[str, str]) -> str:
    return (
        "Create one finished vertical 9:16 unlettered comic-book illustration, not a carousel, contact sheet, poster, cover, slide deck, or multi-panel page. "
        "The one continuous 1080x1920 image captures the decisive instant of a complete superhero rescue. Reserve clean negative "
        "space at y=250-390 for a title, y=430-520 for a threat caption, y=900-1000 for one speech balloon, and y=1400-1500 for a final mission line. "
        "Use premium contemporary American comic-book realism, precise anatomy, expressive faces, cinematic amber practical light, "
        "deep charcoal and clean neutral colors, crisp action, and strong visual continuity. No dominant purple or blue glow. "
        f"Illustrate this physical emergency: {episode['threat_scene']} "
        f"At the center, illustrate this intervention: {episode['hero_action']} Show dynamic movement, visible energy routing, physical protection, "
        "and the imminent consequence being stopped. The endangered civilian must be a large foreground subject occupying at least "
        "20% of the canvas, with a visible face and body, physically supported by Infenergy's energy tether or guided onto a safe ledge. "
        "Never reduce the civilian to a tiny rooftop figure, distant silhouette, or background bystander. Their rescue must be unmistakable. "
        f"Integrate this physical result into the same instant without duplicating people: {episode['resolution_scene']} "
        "Show Infenergy exactly once. Show the endangered civilian exactly once. Use the attached character reference as the authoritative source for "
        "his Black face, short black hair, trimmed beard, powerful build, black segmented armored suit, black energy-strand cape, green "
        "circuit accents, utility belt, and physically attached purple-and-green infinity-bolt chest emblem. Keep his chest and emblem "
        "clearly visible during the rescue action. Never put his emblem, logo, or a "
        "proxy symbol in the sky, clouds, smoke, light beam, wall, or background. No imitation of any existing superhero, no cape "
        "unless shown on the reference, no rooftop brooding, no generic heroic pose, no weapons, no extra limbs, no duplicated people. "
        "This is unlettered interior art. Render absolutely no visible words, letters, numbers, labels, signage, brand wordmarks, "
        "captions, dialogue balloons, title bars, footer bars, panel borders, or typography. Do not copy any wording from this instruction. The reserved "
        "negative spaces must remain visually quiet for the later placement of Gemini-authored copy. The art alone must read as a "
        "complete superhero episode at phone size."
    )


def _font(size: int, *, bold: bool):
    from PIL import ImageFont

    names = [
        os.environ.get("SOCIAL_FONT_BOLD_PATH" if bold else "SOCIAL_FONT_REGULAR_PATH", ""),
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for name in names:
        if not name:
            continue
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise RuntimeError("story_font_unavailable")


def _fit_text(draw, text: str, max_width: int, max_size: int, min_size: int, *, bold: bool):
    for size in range(max_size, min_size - 1, -2):
        font = _font(size, bold=bold)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    raise RuntimeError(f"story_text_does_not_fit:{text}")


def _compose_story_text(image_path: Path, episode: dict[str, str]) -> None:
    from PIL import Image, ImageDraw

    with Image.open(image_path) as source:
        image = source.convert("RGB")
    if image.size != (1080, 1920):
        raise RuntimeError("story_dimensions_invalid")
    draw = ImageDraw.Draw(image, "RGBA")
    amber = (247, 163, 15, 255)
    charcoal = (21, 25, 29, 255)
    warm_white = (250, 247, 239, 245)

    draw.polygon(((128, 250), (952, 250), (922, 390), (128, 390)), fill=(21, 25, 29, 242))
    label_font = _fit_text(draw, episode["series_label"], 744, 34, 22, bold=True)
    title_font = _fit_text(draw, episode["episode_title"], 744, 68, 38, bold=True)
    draw.text((164, 270), episode["series_label"], font=label_font, fill=amber)
    draw.text((164, 310), episode["episode_title"], font=title_font, fill=(255, 255, 255, 255))

    placements = (
        (episode["threat_caption"], (128, 430, 850, 516), False),
        (episode["action_line"], (128, 1120, 850, 1210), True),
        (episode["mission_line"], (128, 1400, 952, 1498), False),
    )
    for text, (left, top, right, bottom), speech in placements:
        if speech:
            draw.ellipse((left, top, right, bottom), fill=warm_white, outline=charcoal, width=5)
        else:
            draw.polygon(((left, top), (right, top), (right - 20, bottom), (left, bottom)), fill=warm_white)
            draw.rectangle((left, top, left + 12, bottom), fill=amber)
        font = _fit_text(draw, text, right - left - 64, 40 if speech else 36, 24, bold=True)
        box = draw.textbbox((0, 0), text, font=font)
        text_x = left + ((right - left) - (box[2] - box[0])) // 2
        text_y = top + ((bottom - top) - (box[3] - box[1])) // 2 - box[1]
        draw.text((text_x, text_y), text, font=font, fill=charcoal)
    image.save(image_path, format="PNG", optimize=True)


def _sanitize_candidate(source_path: Path, output_path: Path) -> None:
    from PIL import Image

    with Image.open(source_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    if width < 256 or height < 256:
        raise RuntimeError("candidate_dimensions_invalid")
    clean_height = round(height * 1780 / 1920)
    clean_width = min(width, round(clean_height * 9 / 16))
    left = (width - clean_width) // 2
    clean = image.crop((left, 0, left + clean_width, clean_height)).resize((1080, 1920), Image.Resampling.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean.save(output_path, format="PNG", optimize=True)


def _review_final_story(image_path: Path, episode: dict[str, str]) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    exact_lines = [episode[key] for key in VISIBLE_TEXT_KEYS]
    prompt = (
        "Review this finished Infenergy Micro Mission Story. Return JSON only with booleans for exactly these keys: "
        "wrong_dimensions_or_format, text_missing_or_inexact, text_illegible, story_order_unclear, threat_missing, "
        "superhero_action_missing, civilian_rescue_missing, character_inconsistent, malformed_anatomy, duplicated_people, "
        "infenergy_symbol_in_atmosphere, derivative_existing_superhero_imitation, unsafe_story_text_placement. "
        "It must be one 9:16 graphic, not a carousel or multi-panel page. One continuous scene must clearly show immediate civilian danger, "
        "Infenergy performing a decisive physical intelligent-energy rescue, and the civilian visibly reaching safety because of that action. "
        "Advising, pointing, posing, or holding a device is not superhero action. Every exact line must appear once, legibly: "
        f"{json.dumps(exact_lines, ensure_ascii=True)}. Text must remain between y=240 and y=1570. The attached character master "
        "is authoritative. Infenergy must appear exactly once and match the reference face, suit, cape, colors, and attached chest emblem. "
        "An emblem in sky, smoke, light, wall, or background fails the review."
    )
    reference_path = Path(os.environ["MICRO_MISSION_CANON_REFERENCE"])
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = model_router.route_for("image_analysis")
    with tracked_gemini_call("reasoning", model, "Micro Mission final visual review", initiating_subsystem="micro_mission_story"):
        response = client.models.generate_content(
            model=model,
            contents=[
                prompt,
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png"),
                types.Part.from_bytes(data=reference_path.read_bytes(), mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
    review = json.loads(str(response.text or "{}"))
    if not isinstance(review, dict):
        raise RuntimeError("gemini_final_story_review_invalid")
    failures = [key for key, failed in review.items() if failed is True]
    if failures:
        raise RuntimeError(f"gemini_final_story_review_failed:{','.join(failures)}")
    return review


def generate(output_dir: Path, reference_image: Path) -> dict[str, Any]:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError("GEMINI_API_KEY is required; fallback generation is forbidden")
    if not reference_image.is_file():
        raise RuntimeError(f"canon_reference_missing:{reference_image}")
    os.environ["MICRO_MISSION_CANON_REFERENCE"] = str(reference_image.resolve())
    episode = _author_episode()
    prompt = _image_prompt(episode)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    mission_id = f"micro-mission-{uuid.uuid4().hex[:12]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    draft_path = output_dir / f"{mission_id}.draft.json"
    draft_path.write_text(
        json.dumps({"mission_id": mission_id, "provider": "gemini", "episode": episode}, indent=2),
        encoding="utf-8",
    )
    image_path = output_dir / f"{mission_id}.png"
    content = {
        "post_id": mission_id,
        "topic": episode["episode_title"],
        "selected_hook": "",
        "selected_cta": "",
        "on_image_headline": "",
        "visual_quality_profile": "micro_mission_story",
        "reference_image_urls": [str(reference_image.resolve())],
    }
    receipt = generate_strict_gemini_image(
        content,
        prompt_plan={
            "gemini_image_prompt": prompt,
            "prompt_sha256": prompt_hash,
            "v5_direction": {"format": "single_story_comic", "text_source": "gemini"},
        },
        output_path=str(image_path),
        platform="iis_reel_cover",
    )
    _compose_story_text(image_path, episode)
    technical_review = review_rendered_visual(str(image_path), "iis_reel_cover")
    if technical_review.get("verdict") != "PASS":
        raise RuntimeError(f"story_artifact_qa_failed:{','.join(technical_review.get('issues') or [])}")
    final_review = _review_final_story(image_path, episode)
    result = {
        "status": "GENERATED",
        "mission_id": mission_id,
        "provider": "gemini",
        "platform": "instagram_story",
        "episode": episode,
        "image_path": str(image_path.resolve()),
        "prompt_sha256": prompt_hash,
        "receipt": receipt,
        "technical_review": technical_review,
        "gemini_final_review": final_review,
    }
    receipt_path = output_dir / f"{mission_id}.json"
    receipt_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["receipt_path"] = str(receipt_path.resolve())
    return result


def recover_candidate(candidate_path: Path, draft_path: Path, output_dir: Path, reference_image: Path) -> dict[str, Any]:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError("GEMINI_API_KEY is required for final review")
    if not candidate_path.is_file() or not draft_path.is_file() or not reference_image.is_file():
        raise RuntimeError("candidate_recovery_input_missing")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    episode = _validate_episode(draft.get("episode"))
    mission_id = str(draft.get("mission_id") or f"micro-mission-{uuid.uuid4().hex[:12]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"{mission_id}-recovered.png"
    os.environ["MICRO_MISSION_CANON_REFERENCE"] = str(reference_image.resolve())
    _sanitize_candidate(candidate_path, image_path)
    _compose_story_text(image_path, episode)
    technical_review = review_rendered_visual(str(image_path), "iis_reel_cover")
    if technical_review.get("verdict") != "PASS":
        raise RuntimeError(f"story_artifact_qa_failed:{','.join(technical_review.get('issues') or [])}")
    final_review = _review_final_story(image_path, episode)
    result = {
        "status": "GENERATED",
        "mission_id": mission_id,
        "provider": "gemini",
        "platform": "instagram_story",
        "episode": episode,
        "image_path": str(image_path.resolve()),
        "source_candidate": str(candidate_path.resolve()),
        "recovery": "bottom_edge_crop_and_story_safe_typesetting",
        "technical_review": technical_review,
        "gemini_final_review": final_review,
    }
    receipt_path = output_dir / f"{mission_id}-recovered.json"
    receipt_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["receipt_path"] = str(receipt_path.resolve())
    return result


def repair_candidate(candidate_path: Path, draft_path: Path, output_dir: Path, reference_image: Path) -> dict[str, Any]:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError("GEMINI_API_KEY is required; fallback generation is forbidden")
    if not candidate_path.is_file() or not draft_path.is_file() or not reference_image.is_file():
        raise RuntimeError("candidate_repair_input_missing")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    episode = _validate_episode(draft.get("episode"))
    mission_id = str(draft.get("mission_id") or f"micro-mission-{uuid.uuid4().hex[:12]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"{mission_id}-repaired.png"
    os.environ["MICRO_MISSION_CANON_REFERENCE"] = str(reference_image.resolve())
    prompt = (
        "Edit the attached garage rescue candidate into one clean, unlettered 9:16 comic-book illustration. Preserve the garage, "
        "failing overhead vehicle lift, dramatic scale, and intelligent energy intervention. Correct the story so the mechanic is "
        "directly beneath the descending vehicle and visibly moving into a safe clear zone because Infenergy has re-energized the "
        "lift brakes inches before impact. The mechanic must be a large foreground subject with a visible face and full body. "
        "Correct Infenergy to match the first attached canon reference exactly: same Black face, short hair, trimmed beard, build, "
        "black segmented suit, energy-strand cape, green circuit accents, belt, and attached purple-green infinity-bolt chest emblem. "
        "Show Infenergy once and the mechanic once. Keep Infenergy in decisive physical action with one hand coupling green energy "
        "into the control terminal and his body braced beneath the load. Remove every existing word, letter, number, speech balloon, "
        "caption, title bar, footer, sign, and pseudo-text. Add no new typography. Leave visually quiet areas for later copy at the "
        "upper quarter, left middle, and lower quarter. Do not place the emblem in the environment or imitate another superhero."
    )
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    content = {
        "post_id": f"{mission_id}-repair",
        "topic": episode["episode_title"],
        "selected_hook": "",
        "selected_cta": "",
        "on_image_headline": "",
        "visual_quality_profile": "micro_mission_story",
        "reference_image_urls": [str(reference_image.resolve()), str(candidate_path.resolve())],
    }
    receipt = generate_strict_gemini_image(
        content,
        prompt_plan={
            "gemini_image_prompt": prompt,
            "prompt_sha256": prompt_hash,
            "v5_direction": {"format": "single_story_comic", "text_source": "gemini"},
        },
        output_path=str(image_path),
        platform="iis_reel_cover",
    )
    _compose_story_text(image_path, episode)
    technical_review = review_rendered_visual(str(image_path), "iis_reel_cover")
    if technical_review.get("verdict") != "PASS":
        raise RuntimeError(f"story_artifact_qa_failed:{','.join(technical_review.get('issues') or [])}")
    final_review = _review_final_story(image_path, episode)
    result = {
        "status": "GENERATED",
        "mission_id": mission_id,
        "provider": "gemini",
        "platform": "instagram_story",
        "episode": episode,
        "image_path": str(image_path.resolve()),
        "source_candidate": str(candidate_path.resolve()),
        "repair_prompt_sha256": prompt_hash,
        "receipt": receipt,
        "technical_review": technical_review,
        "gemini_final_review": final_review,
    }
    receipt_path = output_dir / f"{mission_id}-repaired.json"
    receipt_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["receipt_path"] = str(receipt_path.resolve())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-image", type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.output_dir, args.reference_image)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())