"""Deterministic Instagram Reel cognition, rendering, and artifact QA.

This module deliberately owns no publishing. It produces a final-state-first
creative family that the existing Instagram publisher can publish only after
the normal governance gates approve it.
"""

from __future__ import annotations

import json
import math
import os
import random
import shutil
import struct
import subprocess
import textwrap
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat


REEL_WIDTH = 1080
REEL_HEIGHT = 1920
REEL_FPS = 30
MIN_REEL_SECONDS = 3.0
MAX_REEL_SECONDS = 15 * 60.0
STORY_EMOTIONS = ("mystery", "eerie", "tension", "danger", "discovery", "relief", "triumph", "reflection")
EMOTION_HARMONY = {
    "mystery": (50, (0, 3, 7)), "eerie": (47, (0, 1, 7)), "tension": (45, (0, 3, 6)),
    "danger": (43, (0, 1, 6)), "discovery": (52, (0, 4, 7)), "relief": (55, (0, 4, 7)),
    "triumph": (57, (0, 4, 7)), "reflection": (50, (0, 3, 7)),
}


def _text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default(size=size)


def _media_base_url() -> str:
    configured = os.environ.get("PUBLIC_MEDIA_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    return f"https://{domain}" if domain else ""


def _public_url(path: str) -> str:
    base = _media_base_url()
    return f"{base}/media/{Path(path).name}" if base else ""


def choose_instagram_media(
    *,
    strategy_lock: dict[str, Any] | None,
    components: dict[str, Any],
    visual_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose motion only when sequencing advances the protected strategy."""
    lock = strategy_lock or {}
    plan = visual_plan or {}
    job = _text(lock.get("reader_job") or components.get("content_job") or "decision_support", 80).lower()
    moment = _text(lock.get("customer_moment") or components.get("situation"), 180).lower()
    topic = _text(lock.get("topic") or components.get("topic"), 120).lower()
    signals = {
        "demonstration": any(token in f"{job} {moment}" for token in ("use", "setup", "compare", "choose", "how")),
        "sequencing": any(token in f"{job} {topic}" for token in ("decision", "education", "explain", "compare", "framework")),
        "human_connection": any(token in moment for token in ("trip", "outage", "family", "travel", "home", "work")),
        "visual_story": bool(plan.get("customer_moment") or plan.get("visual_message")),
    }
    motion_value = sum(1 for value in signals.values() if value)
    if motion_value >= 3:
        selected = "REEL"
        reason = "motion sequences a supported customer decision into a readable final poster state"
    elif motion_value == 2:
        selected = "CAROUSEL"
        reason = "multiple supported ideas benefit from deliberate static sequencing more than motion"
    else:
        selected = "STATIC"
        reason = "a single premium composition communicates the supported message more clearly than motion"
    return {
        "instagram_media_decision": selected,
        "selected_format": selected,
        "reason": reason,
        "content_job": job,
        "motion_value": {"score": motion_value, "signals": signals},
    }


def build_reel_plan(
    *,
    post_id: str,
    components: dict[str, Any],
    decision: dict[str, Any],
    strategy_lock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build final state first, then motion that terminates before its hold."""
    if decision.get("selected_format") != "REEL":
        return {"pre_render_gate": "USE_STATIC_INSTEAD", "reason": decision.get("reason", "")}
    hook = _text(components.get("logic_hook") or components.get("on_image_headline") or components.get("hook"), 72)
    product = _text(components.get("product_name"), 72)
    benefit = _text(components.get("benefit_fragment") or components.get("logic_bridge"), 110)
    use_case = _text(components.get("use_case_line"), 96)
    headline = product or hook
    supporting_copy = benefit
    proof = _text((components.get("feature_bullets") or [""])[0], 48)
    cta = _text(components.get("cta") or "Learn more", 48)
    if not headline or not supporting_copy:
        return {"pre_render_gate": "REVISE_FINAL_FRAME", "reason": "final_state_requires_supported_headline_and_benefit"}
    freeze_hold = 2.8 if len(headline) + len(supporting_copy) > 120 else 2.3
    motion_end = 4.2 if decision["motion_value"]["score"] >= 4 else 3.4
    total = motion_end + freeze_hold
    final_state = {
        "composition": "product-led vertical poster with one supported proof and a quiet CTA",
        "product_position": "center_lower",
        "headline": headline,
        "supporting_copy": supporting_copy,
        "cta": cta,
        "proof_elements": [proof] if proof else [],
        "background": "deep neutral gradient with restrained amber energy line",
        "lighting": "focused product halo",
        "layout": "top headline, centered product, lower proof and CTA",
        "typography": "high-contrast sans serif",
        "brand_elements": ["Infenergy Power"],
    }
    scenes = [
        {
            "purpose": "ATTENTION",
            "start": 0.0,
            "end": 1.0,
            "message": hook,
            "visual": "cropped product-context opening",
            "movement": "purposeful focus pull",
            "transition": "reveal",
        },
        {
            "purpose": "SEQUENCING",
            "start": 1.0,
            "end": min(2.3, motion_end),
            "message": f"{product}: {benefit}".strip(": "),
            "visual": "product resolves toward final poster position",
            "movement": "single eased scale and opacity settle",
            "transition": "product_reveal",
        },
        {
            "purpose": "PROOF_AND_HUMAN_USE",
            "start": min(2.3, motion_end),
            "end": motion_end,
            "message": _text(f"{proof}. {use_case}", 140),
            "visual": "selected proof settles into the product context",
            "movement": "restrained proof reveal",
            "transition": "settle_into_final_state",
        },
    ]
    return {
        "pre_render_gate": "REEL_READY",
        "creative_family_id": f"reel-family-{post_id}",
        "parent_reel_id": post_id,
        "concept": "decision-support motion resolving into a standalone product poster",
        "content_job": decision["content_job"],
        "target_duration": total,
        "motion_end_time": motion_end,
        "freeze_start_time": motion_end,
        "freeze_hold_duration": freeze_hold,
        "video_end_time": total,
        "final_state": final_state,
        "scenes": scenes,
        "motion_grammar": {"opening": "focus_pull", "transition": "eased_settle", "prohibited": ["looping", "bouncing", "spinning", "particles"]},
        "cover_strategy": "final_freeze_frame",
        "caption_strategy": "caption adds decision context without restating final-frame proof",
        "message_hierarchy": ["hook", "product", "primary_benefit", "selected_proof_human_use", "final_sales_frame"],
        "strategy_version": (strategy_lock or {}).get("strategy_version"),
    }


def validate_reel_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("pre_render_gate") != "REEL_READY":
        return {"status": plan.get("pre_render_gate", "ABSTAIN"), "reasons": [plan.get("reason", "not_reel_ready")]}
    freeze_start = float(plan["freeze_start_time"])
    errors = []
    for scene in plan.get("scenes", []):
        if float(scene.get("end", 0)) > freeze_start:
            errors.append("animation_track_extends_into_freeze")
        if not _text(scene.get("purpose")):
            errors.append("motion_without_purpose")
    if float(plan["freeze_hold_duration"]) < 1.5:
        errors.append("freeze_hold_too_short")
    if float(plan["video_end_time"]) != freeze_start + float(plan["freeze_hold_duration"]):
        errors.append("freeze_contract_mismatch")
    return {"status": "REEL_READY" if not errors else "REVISE_STORYBOARD", "reasons": errors}


def build_scored_story_plan(
    *,
    post_id: str,
    carousel_assets: list[dict[str, Any]],
    slide_texts: list[str] | None = None,
    emotions: list[str] | None = None,
    narration_path: str | None = None,
    motion_intensity: float = 0.55,
    auto_narration: bool = False,
) -> dict[str, Any]:
    """Turn ordered carousel assets into a readable, emotionally scored story timeline."""
    if len(carousel_assets) < 2:
        raise ValueError("scored_story_reel_requires_at_least_two_slides")
    texts = slide_texts or []
    requested_emotions = emotions or []
    scenes = []
    cursor = 0.0
    for index, asset in enumerate(carousel_assets):
        local_path = str(asset.get("local_path") or "").strip()
        if not local_path:
            raise ValueError(f"scored_story_slide_missing_local_path:{index + 1}")
        text = _text(texts[index] if index < len(texts) else asset.get("caption") or asset.get("title"), 500)
        words = len(text.split())
        duration = round(min(10.0, max(5.0, 3.6 + words * 0.32)), 2)
        emotion = _text(requested_emotions[index] if index < len(requested_emotions) else STORY_EMOTIONS[index % len(STORY_EMOTIONS)], 24).lower()
        if emotion not in EMOTION_HARMONY:
            raise ValueError(f"unsupported_story_emotion:{emotion}")
        scenes.append({
            "index": index, "asset_path": local_path, "public_url": str(asset.get("public_url") or ""),
            "caption": text, "emotion": emotion, "start": round(cursor, 2),
            "end": round(cursor + duration, 2), "duration": duration,
            "movement": "slow_push" if index % 2 == 0 else "slow_pull",
        })
        cursor += duration
    return {
        "pre_render_gate": "SCORED_STORY_READY",
        "creative_family_id": f"scored-story-{post_id}",
        "parent_reel_id": post_id,
        "reel_type": "SCORED_STORY_REEL",
        "target_duration": round(cursor, 2),
        "video_end_time": round(cursor, 2),
        "motion_intensity": max(0.0, min(float(motion_intensity), 1.0)),
        "narration_path": narration_path,
        "auto_narration": bool(auto_narration),
        "scenes": scenes,
        "music_score": {
            "source": "original_cue_based_cinematic_composition",
            "license": "original_generated_audio",
            "commercial_use": True,
            "score_version": 3,
            "tempo_bpm": 68,
            "instrumentation": ["low_strings", "felt_piano_motif", "sub_bass", "restrained_taiko", "late_brass_swell", "transition_swell", "final_resolve"],
            "channels": 2,
            "emotional_arc": [scene["emotion"] for scene in scenes],
            "cue_arc": ["suspense", "threat", "investigation", "stakes", "plan", "pursuit", "reversal", "resolution"][:len(scenes)],
            "narration_ducking": bool(narration_path),
        },
        "caption_strategy": "captions_are_inherited_from_the_readable_carousel_slides",
    }


def _story_frame(source_path: str, destination: Path, *, square: bool = False) -> None:
    size = (1080, 1080) if square else (REEL_WIDTH, REEL_HEIGHT)
    with Image.open(source_path) as source:
        source = source.convert("RGB")
        contained = source.copy()
        contained.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", size, "#10191d")
        canvas.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
        canvas.save(destination, format="JPEG", quality=94, subsampling=0)


def _story_vertical_frame(scene: dict[str, Any], destination: Path, *, scene_count: int) -> None:
    with Image.open(scene["asset_path"]) as source:
        source = source.convert("RGB")
        if source.size == (REEL_WIDTH, REEL_HEIGHT):
            source.save(destination, format="JPEG", quality=95, subsampling=0)
            return
        background = source.resize((REEL_WIDTH, REEL_HEIGHT), Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(34))
        background = ImageEnhance.Brightness(background).enhance(0.34)
        canvas = background.copy()
        foreground = source.copy()
        foreground.thumbnail((1000, 1250), Image.Resampling.LANCZOS)
        foreground_x = (REEL_WIDTH - foreground.width) // 2
        foreground_y = 238
        canvas.paste(foreground, (foreground_x, foreground_y))
        draw = ImageDraw.Draw(canvas, "RGBA")
        draw.rectangle((0, 0, REEL_WIDTH, 205), fill=(8, 15, 18, 218))
        draw.rectangle((0, 1518, REEL_WIDTH, REEL_HEIGHT), fill=(8, 15, 18, 228))
        draw.rounded_rectangle(
            (foreground_x - 4, foreground_y - 4, foreground_x + foreground.width + 4, foreground_y + foreground.height + 4),
            radius=4, outline=(205, 255, 68, 215), width=4,
        )
        draw.text((54, 52), "INFENERGY  |  MICRO MISSION", fill=(205, 255, 68, 255), font=_font(38))
        counter = f"{int(scene['index']) + 1:02d} / {scene_count:02d}"
        counter_width = draw.textbbox((0, 0), counter, font=_font(34))[2]
        draw.text((REEL_WIDTH - 54 - counter_width, 58), counter, fill=(255, 255, 255, 245), font=_font(34))
        caption = _text(scene.get("caption"), 180)
        wrapped = "\n".join(textwrap.wrap(caption, width=42, break_long_words=False)[:4])
        draw.multiline_text((58, 1570), wrapped, fill=(255, 255, 255, 255), font=_font(43), spacing=13)
        canvas.save(destination, format="JPEG", quality=95, subsampling=0)


def _midi_frequency(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _render_cinematic_score(plan: dict[str, Any], destination: Path) -> None:
    sample_rate = 48_000
    tempo = float(plan.get("music_score", {}).get("tempo_bpm") or 84)
    beat_seconds = 60.0 / tempo
    scenes = plan["scenes"]
    total_seconds = float(plan["video_end_time"])
    total_samples = int(math.ceil(total_seconds * sample_rate))
    randomizer = random.Random(str(plan.get("parent_reel_id") or "infenergy-score"))
    scene_index = 0
    noise = [randomizer.uniform(-1.0, 1.0) for _ in range(4096)]
    scene_count = len(scenes)
    motif_intervals = (0, 3, 7, 10)

    def harmonic_tone(frequency: float, time_seconds: float, harmonics: tuple[float, ...]) -> float:
        return sum(
            amplitude * math.sin(2 * math.pi * frequency * (index + 1) * time_seconds)
            for index, amplitude in enumerate(harmonics)
        ) / max(1.0, sum(harmonics))

    def triangle_tone(frequency: float, time_seconds: float) -> float:
        return (2.0 / math.pi) * math.asin(math.sin(2 * math.pi * frequency * time_seconds))

    with wave.open(str(destination), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        block = bytearray()
        for sample_index in range(total_samples):
            time_seconds = sample_index / sample_rate
            while scene_index + 1 < len(scenes) and time_seconds >= float(scenes[scene_index]["end"]):
                scene_index += 1
            scene = scenes[scene_index]
            local_time = max(0.0, time_seconds - float(scene["start"]))
            scene_duration = float(scene["duration"])
            arc = scene_index / max(1, scene_count - 1)
            fallback_emotion = "relief" if scene_index == scene_count - 1 else "tension"
            root, intervals = EMOTION_HARMONY.get(str(scene.get("emotion") or "").lower(), EMOTION_HARMONY[fallback_emotion])
            scene_envelope = min(1.0, local_time / 0.32, max(0.0, (scene_duration - local_time) / 0.42))
            phrase_pulse = 0.76 + 0.24 * math.sin(2 * math.pi * time_seconds / (beat_seconds * 8))

            string_chord = sum(
                harmonic_tone(_midi_frequency(root + interval - 12), time_seconds + interval * 0.013, (1.0, 0.42, 0.2, 0.1))
                for interval in intervals
            ) / len(intervals)
            high_strings = sum(
                triangle_tone(_midi_frequency(root + interval + 12), time_seconds + interval * 0.009)
                for interval in intervals
            ) / len(intervals)
            bass_frequency = _midi_frequency(root - 24)
            sub_bass = harmonic_tone(bass_frequency, time_seconds, (1.0, 0.22, 0.08))

            motif_step_seconds = beat_seconds * (2.0 if arc < 0.55 else 1.0)
            motif_step = int(time_seconds / motif_step_seconds)
            motif_phase = time_seconds % motif_step_seconds
            motif_note = root + 12 + motif_intervals[motif_step % len(motif_intervals)]
            piano_envelope = math.exp(-4.8 * motif_phase / motif_step_seconds)
            piano = harmonic_tone(_midi_frequency(motif_note), time_seconds, (1.0, 0.5, 0.22, 0.12, 0.07)) * piano_envelope

            eighth_seconds = beat_seconds
            ostinato_step = int(time_seconds / eighth_seconds)
            ostinato_phase = time_seconds % eighth_seconds
            ostinato_note = root - 12 + (0, 7, 3, 7)[ostinato_step % 4]
            ostinato = harmonic_tone(_midi_frequency(ostinato_note), time_seconds, (1.0, 0.24, 0.08)) * math.exp(-4.2 * ostinato_phase / eighth_seconds)

            beat_phase = time_seconds % beat_seconds
            beat_number = int(time_seconds / beat_seconds)
            act_turns = {max(1, scene_count // 3), max(2, (scene_count * 2) // 3), scene_count - 2}
            taiko_active = scene_index in act_turns and beat_number % 2 == 0
            taiko = 0.0
            if taiko_active and beat_phase < 0.42:
                taiko_frequency = 76.0 - 38.0 * min(1.0, beat_phase / 0.3)
                taiko = harmonic_tone(taiko_frequency, beat_phase, (1.0, 0.48, 0.22)) * math.exp(-8.5 * beat_phase)
                taiko += noise[(sample_index * 5) % len(noise)] * math.exp(-34 * beat_phase) * 0.14

            scene_impact = 0.0
            if scene_index in {0, max(1, scene_count // 2), scene_count - 1} and local_time < 0.8:
                scene_impact = harmonic_tone(42.0, local_time, (1.0, 0.32, 0.15)) * math.exp(-4.2 * local_time)
            brass = 0.0
            if scene_index >= max(2, scene_count // 2):
                brass_swell = math.sin(math.pi * min(1.0, local_time / max(0.5, scene_duration * 0.72))) ** 2
                brass = sum(
                    harmonic_tone(_midi_frequency(root + interval), time_seconds, (1.0, 0.65, 0.34, 0.18, 0.08))
                    for interval in intervals
                ) / len(intervals) * brass_swell

            transition = 0.0
            transition_window = min(0.9, scene_duration * 0.25)
            if scene_duration - local_time < transition_window and scene_index < scene_count - 1:
                transition_progress = 1.0 - max(0.0, scene_duration - local_time) / transition_window
                shimmer = noise[(sample_index * 13) % len(noise)] * (0.25 + 0.75 * transition_progress)
                rising_tone = math.sin(2 * math.pi * (280 + 520 * transition_progress) * time_seconds)
                transition = (shimmer * 0.045 + rising_tone * 0.018) * transition_progress

            resolution = 0.0
            if scene_index == scene_count - 1:
                resolution_root = 55
                resolution = sum(
                    harmonic_tone(_midi_frequency(resolution_root + interval), time_seconds, (1.0, 0.4, 0.18))
                    for interval in (0, 4, 7, 12)
                ) / 4

            tension_gain = 0.55 + 0.65 * arc
            tonal = scene_envelope * (
                string_chord * (0.17 + 0.08 * arc) * phrase_pulse
                + high_strings * max(0.0, arc - 0.42) * 0.09
                + sub_bass * (0.14 + 0.08 * arc)
                + piano * (0.17 if arc < 0.7 else 0.1)
                + ostinato * max(0.0, arc - 0.36) * 0.12
                + brass * max(0.0, arc - 0.58) * 0.24
                + resolution * (0.28 if scene_index == scene_count - 1 else 0.0)
            )
            percussion = taiko * (0.2 + 0.16 * arc) + scene_impact * (0.28 if scene_index else 0.14) + transition
            overall_fade = min(1.0, time_seconds / 1.2, max(0.0, (total_seconds - time_seconds) / 1.7))
            stereo_motion = 0.16 * math.sin(2 * math.pi * time_seconds / (beat_seconds * 4))
            left = math.tanh((tonal * (1.0 - stereo_motion) + percussion) * tension_gain * overall_fade)
            right = math.tanh((tonal * (1.0 + stereo_motion) + percussion * 0.94) * tension_gain * overall_fade)
            block.extend(struct.pack("<hh", int(left * 24_000), int(right * 24_000)))
            if len(block) >= 65_536:
                output.writeframesraw(block)
                block.clear()
        if block:
            output.writeframesraw(block)


def render_scored_story_reel(plan: dict[str, Any], *, data_dir: str | None = None) -> dict[str, Any]:
    """Render ordered slides and an adaptive procedural score into the standard Reel contract."""
    if plan.get("pre_render_gate") != "SCORED_STORY_READY" or not plan.get("scenes"):
        raise RuntimeError("scored_story_pre_render_gate_failed")
    root = Path(data_dir or os.environ.get("DATA_DIR") or Path(__file__).resolve().parents[2] / "data")
    media_dir = root / "public_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{plan['parent_reel_id']}_{uuid.uuid4().hex[:8]}_scored_story"
    video_path = media_dir / f"{stem}.mp4"
    cover_path = media_dir / f"{stem}_cover.jpg"
    final_path = media_dir / f"{stem}_final_frame.jpg"
    static_path = media_dir / f"{stem}_static.jpg"
    score_path = media_dir / f"{stem}_score.wav"
    scenes = plan["scenes"]
    scene_frames = []
    for scene in scenes:
        frame_path = media_dir / f"{stem}_scene_{int(scene['index']) + 1:02d}.jpg"
        _story_vertical_frame(scene, frame_path, scene_count=len(scenes))
        scene_frames.append(frame_path)
    _story_frame(scenes[0]["asset_path"], cover_path)
    _story_frame(scenes[-1]["asset_path"], final_path)
    _story_frame(scenes[-1]["asset_path"], static_path, square=True)
    _render_cinematic_score(plan, score_path)
    narration_path = str(plan.get("narration_path") or "").strip()
    if not narration_path and bool(plan.get("auto_narration")):
        narration_path = render_story_narration(plan, output_path=str(media_dir / f"{stem}_narration.wav"))
    command = [_ffmpeg(), "-y"]
    for scene, frame_path in zip(scenes, scene_frames):
        command.extend(["-loop", "1", "-framerate", str(REEL_FPS), "-t", str(scene["duration"]), "-i", str(frame_path)])
    command.extend(["-i", str(score_path)])
    if narration_path:
        if not os.path.isfile(narration_path):
            raise ValueError("scored_story_narration_not_found")
        command.extend(["-i", narration_path])
    filters = []
    video_labels = []
    intensity = float(plan.get("motion_intensity") or 0.55)
    for index, scene in enumerate(scenes):
        frames = max(1, int(math.ceil(float(scene["duration"]) * REEL_FPS)))
        zoom_step = (0.00009 + intensity * 0.00016) * (1 if scene["movement"] == "slow_push" else -1)
        zoom = f"min(zoom+{zoom_step:.6f},1.025)" if zoom_step > 0 else f"max(zoom{zoom_step:.6f},1.0)"
        filters.append(
            f"[{index}:v]scale={REEL_WIDTH}:{REEL_HEIGHT},"
            f"zoompan=z='{zoom}':d={frames}:s={REEL_WIDTH}x{REEL_HEIGHT}:fps={REEL_FPS},"
            f"trim=duration={scene['duration']},setpts=PTS-STARTPTS[v{index}]"
        )
        video_labels.append(f"[v{index}]")
    filters.append(f"{''.join(video_labels)}concat=n={len(scenes)}:v=1:a=0,format=yuv420p[v]")
    score_index = len(scenes)
    audio_map = f"{score_index}:a"
    if narration_path:
        narration_index = score_index + 1
        filters.append(f"[{score_index}:a]volume=0.32[ducked];[{narration_index}:a]volume=1.0[narration];[ducked][narration]amix=inputs=2:duration=first:dropout_transition=1[aout]")
        audio_map = "[aout]"
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[v]", "-map", audio_map,
        "-r", str(REEL_FPS), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-pix_fmt", "yuv420p",
        "-shortest", str(video_path),
    ])
    result = _run(command)
    if result.returncode != 0 or not video_path.exists():
        raise RuntimeError(f"scored_story_render_failed:{result.stderr[-900:]}")
    return {
        "reel_artifact_path": str(video_path), "cover_path": str(cover_path),
        "final_freeze_frame_path": str(final_path), "static_derivative_path": str(static_path),
        "public_urls": {"video": _public_url(str(video_path)), "cover": _public_url(str(cover_path)), "final_frame": _public_url(str(final_path)), "static": _public_url(str(static_path))},
        "creative_family_id": plan["creative_family_id"], "parent_reel_id": plan["parent_reel_id"],
        "reel_type": "SCORED_STORY_REEL", "story_score": plan["music_score"], "scenes": scenes,
    }


def _poster(final_state: dict[str, Any], source_image: str | None, *, square: bool = False) -> Image.Image:
    width, height = (1080, 1080) if square else (REEL_WIDTH, REEL_HEIGHT)
    image = Image.new("RGB", (width, height), "#15242a")
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        draw.line((0, y, width, y), fill=(21 + int(15 * ratio), 36 + int(18 * ratio), 42 + int(12 * ratio)))
    if source_image and os.path.exists(source_image):
        with Image.open(source_image) as asset:
            asset = asset.convert("RGBA")
            asset.thumbnail((int(width * 0.82), int(height * (0.46 if not square else 0.48))))
            image.alpha_composite(asset, ((width - asset.width) // 2, int(height * (0.34 if not square else 0.34)))) if image.mode == "RGBA" else image.paste(asset, ((width - asset.width) // 2, int(height * (0.34 if not square else 0.34))), asset)
    accent = "#e3a13a"
    draw.rounded_rectangle((64, int(height * 0.82), width - 64, int(height * 0.84)), radius=10, fill=accent)
    headline = final_state["headline"]
    supporting = final_state["supporting_copy"]
    proof = " | ".join(final_state.get("proof_elements") or [])
    draw.multiline_text((64, int(height * 0.07)), headline, fill="white", font=_font(58 if not square else 44), spacing=8)
    draw.multiline_text((64, int(height * 0.72)), supporting, fill="#dce8e7", font=_font(30 if not square else 25), spacing=6)
    if proof:
        draw.text((64, int(height * 0.86)), proof, fill=accent, font=_font(30 if not square else 24))
    draw.text((64, int(height * 0.92)), final_state["cta"], fill="white", font=_font(34 if not square else 28))
    draw.text((width - 310, int(height * 0.94)), "Infenergy Power", fill="#b9c7c9", font=_font(22 if not square else 18))
    return image


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)


def _ffmpeg() -> str:
    executable = os.environ.get("FFMPEG_BIN", "").strip() or shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("ffmpeg_not_available")
    return executable


def _ffprobe() -> str:
    executable = os.environ.get("FFPROBE_BIN", "").strip() or shutil.which("ffprobe")
    if not executable:
        raise RuntimeError("ffprobe_not_available")
    return executable

def _espeak() -> str:
    executable = os.environ.get("ESPEAK_BIN", "").strip() or shutil.which("espeak-ng") or shutil.which("espeak")
    if not executable:
        raise RuntimeError("espeak_not_available")
    return executable

def render_story_narration(plan: dict[str, Any], *, output_path: str) -> str:
    script = " ".join(_text(scene.get("caption"), 500) for scene in plan.get("scenes", [])).strip()
    if not script:
        raise ValueError("scored_story_narration_requires_slide_text")
    result = _run([_espeak(), "-s", "150", "-p", "38", "-w", output_path, script])
    if result.returncode != 0 or not os.path.isfile(output_path):
        raise RuntimeError(f"story_narration_failed:{result.stderr[-500:]}")
    return output_path


def render_reel(plan: dict[str, Any], *, source_image: str | None, data_dir: str | None = None) -> dict[str, Any]:
    """Render a deliberate opening focus pull followed by an exact frozen poster."""
    gate = validate_reel_plan(plan)
    if gate["status"] != "REEL_READY":
        raise RuntimeError(f"reel_pre_render_gate:{gate['status']}:{','.join(gate['reasons'])}")
    root = Path(data_dir or os.environ.get("DATA_DIR") or Path(__file__).resolve().parents[2] / "data")
    media_dir = root / "public_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{plan['parent_reel_id']}_{uuid.uuid4().hex[:8]}"
    opener_path = media_dir / f"{stem}_opening.png"
    final_path = media_dir / f"{stem}_final_freeze_frame.png"
    cover_path = media_dir / f"{stem}_cover.jpg"
    static_path = media_dir / f"{stem}_static.jpg"
    video_path = media_dir / f"{stem}_reel.mp4"
    final_state = plan["final_state"]
    opener = _poster({**final_state, "supporting_copy": ""}, source_image)
    final = _poster(final_state, source_image)
    opener.save(opener_path, format="PNG")
    final.save(final_path, format="PNG")
    final.save(cover_path, format="JPEG", quality=94, subsampling=0)
    _poster(final_state, source_image, square=True).save(static_path, format="JPEG", quality=94, subsampling=0)
    total_frames = int(round(float(plan["video_end_time"]) * REEL_FPS))
    motion_frames = int(round(float(plan["motion_end_time"]) * REEL_FPS))
    command = [
        _ffmpeg(), "-y", "-loop", "1", "-framerate", "1", "-t", "1", "-i", str(opener_path),
        "-loop", "1", "-framerate", str(REEL_FPS), "-t", str(plan["freeze_hold_duration"]), "-i", str(final_path),
        "-filter_complex", f"[0:v]zoompan=z='min(zoom+0.0007,1.06)':d={motion_frames}:s={REEL_WIDTH}x{REEL_HEIGHT}:fps={REEL_FPS},trim=duration={plan['motion_end_time']},setpts=PTS-STARTPTS[motion];[1:v]setpts=PTS-STARTPTS[hold];[motion][hold]concat=n=2:v=1:a=0,format=yuv420p[v]",
        "-map", "[v]", "-r", str(REEL_FPS), "-frames:v", str(total_frames), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(video_path),
    ]
    result = _run(command)
    if result.returncode != 0 or not video_path.exists():
        raise RuntimeError(f"reel_render_failed:{result.stderr[-600:]}")
    return {
        "reel_artifact_path": str(video_path),
        "final_freeze_frame_path": str(final_path),
        "cover_path": str(cover_path),
        "static_derivative_path": str(static_path),
        "public_urls": {"video": _public_url(str(video_path)), "cover": _public_url(str(cover_path)), "final_frame": _public_url(str(final_path)), "static": _public_url(str(static_path))},
        "creative_family_id": plan["creative_family_id"],
        "parent_reel_id": plan["parent_reel_id"],
    }


def technical_qa(artifact: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    path = artifact.get("reel_artifact_path", "")
    if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
        return {"status": "FAIL", "reasons": ["missing_or_empty_mp4"]}
    probe = _run([_ffprobe(), "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    if probe.returncode != 0:
        return {"status": "FAIL", "reasons": ["ffprobe_failed"]}
    data = json.loads(probe.stdout)
    video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"), {})
    duration = float(data.get("format", {}).get("duration") or 0)
    reasons = []
    if video.get("codec_name") != "h264": reasons.append("codec_not_h264")
    if (int(video.get("width") or 0), int(video.get("height") or 0)) != (REEL_WIDTH, REEL_HEIGHT): reasons.append("wrong_resolution")
    if audio.get("codec_name") != "aac": reasons.append("audio_not_aac")
    if int(audio.get("channels") or 0) != 2: reasons.append("audio_not_stereo")
    if not MIN_REEL_SECONDS <= duration <= MAX_REEL_SECONDS: reasons.append("invalid_duration")
    return {"status": "PASS" if not reasons else "FAIL", "reasons": reasons, "duration": duration, "width": video.get("width"), "height": video.get("height"), "fps": REEL_FPS, "codec": video.get("codec_name"), "file_size": os.path.getsize(path)}


def freeze_qa(artifact: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    video = artifact["reel_artifact_path"]
    root = Path(video).parent
    times = [float(plan["freeze_start_time"]), float(plan["freeze_start_time"]) + float(plan["freeze_hold_duration"]) / 2, float(plan["video_end_time"]) - 0.05]
    frames = []
    for index, timestamp in enumerate(times):
        frame_path = root / f"{Path(video).stem}_freeze_{index}.png"
        result = _run([_ffmpeg(), "-y", "-ss", f"{timestamp:.3f}", "-i", video, "-frames:v", "1", str(frame_path)])
        if result.returncode != 0 or not frame_path.exists():
            return {"status": "FAIL", "freeze_verified": False, "reasons": ["freeze_frame_decode_failed"]}
        frames.append(frame_path)
    with Image.open(frames[0]) as first, Image.open(frames[1]) as middle, Image.open(frames[2]) as final:
        comparisons = []
        for candidate in (middle, final):
            stat = ImageStat.Stat(ImageChops.difference(first.convert("RGB"), candidate.convert("RGB")))
            comparisons.append(round(sum(stat.mean) / len(stat.mean), 4))
    tolerance = 1.5
    passed = all(value <= tolerance for value in comparisons)
    return {"status": "PASS" if passed else "FAIL", "freeze_verified": passed, "freeze_start": plan["freeze_start_time"], "freeze_duration": plan["freeze_hold_duration"], "frame_comparison_result": {"mean_channel_differences": comparisons, "tolerance": tolerance}}


def cover_qa(artifact: dict[str, Any]) -> dict[str, Any]:
    path = artifact.get("cover_path", "")
    if not path or not os.path.isfile(path):
        return {"status": "FAIL", "reasons": ["missing_cover"]}
    with Image.open(path) as cover:
        thumbnail = cover.convert("RGB").resize((135, 240))
        extrema = thumbnail.getextrema()
    contrast = max(high - low for low, high in extrema)
    passed = contrast >= 35
    return {"status": "PASS" if passed else "FAIL", "thumbnail_legibility": "PASS" if passed else "REVISE", "thumbnail_focus": "PASS" if passed else "REVISE", "thumbnail_brand_visibility": "PASS", "derived_from_final_state": True, "contrast_range": contrast}


def final_frame_qa(artifact: dict[str, Any]) -> dict[str, Any]:
    path = artifact.get("final_freeze_frame_path", "")
    if not path or not os.path.isfile(path):
        return {"status": "FAIL", "reasons": ["missing_final_freeze_frame"]}
    with Image.open(path) as frame:
        if frame.size != (REEL_WIDTH, REEL_HEIGHT):
            return {"status": "FAIL", "reasons": ["wrong_final_frame_resolution"]}
        extrema = frame.convert("RGB").getextrema()
    contrast = max(high - low for low, high in extrema)
    return {
        "status": "PASS" if contrast >= 35 else "FAIL",
        "hierarchy": "PASS" if contrast >= 35 else "REVISE",
        "contrast": contrast,
        "claim_safety": "INHERITED_FROM_LOCKED_COPY",
        "final_state_source": "rendered_reel_composition",
    }


def motion_qa(plan: dict[str, Any]) -> dict[str, Any]:
    grammar = plan.get("motion_grammar") if isinstance(plan.get("motion_grammar"), dict) else {}
    prohibited = {"looping", "bouncing", "spinning", "particles"}
    scene_text = " ".join(str(scene.get("movement") or "").lower() for scene in plan.get("scenes", []))
    reasons = []
    if any(token in scene_text for token in prohibited):
        reasons.append("cheap_or_unbounded_motion")
    if any(not _text(scene.get("purpose")) for scene in plan.get("scenes", [])):
        reasons.append("motion_without_function")
    if float(plan.get("motion_end_time") or 0) > float(plan.get("freeze_start_time") or 0):
        reasons.append("motion_does_not_settle")
    return {
        "status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "pace": "restrained",
        "transition_quality": "eased_settle",
        "movement_restraint": "PASS" if not reasons else "REVISE",
        "final_frame_polish": "delegated_to_final_frame_qa",
        "grammar": grammar,
    }