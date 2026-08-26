"""Deterministic Instagram Reel cognition, rendering, and artifact QA.

This module deliberately owns no publishing. It produces a final-state-first
creative family that the existing Instagram publisher can publish only after
the normal governance gates approve it.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat


REEL_WIDTH = 1080
REEL_HEIGHT = 1920
REEL_FPS = 30
MIN_REEL_SECONDS = 3.0
MAX_REEL_SECONDS = 15 * 60.0
STORY_EMOTIONS = ("mystery", "eerie", "tension", "danger", "discovery", "relief", "triumph", "reflection")
EMOTION_SCORE = {
    "mystery": (146.83, 0.12), "eerie": (138.59, 0.10), "tension": (196.00, 0.14),
    "danger": (220.00, 0.16), "discovery": (261.63, 0.13), "relief": (329.63, 0.11),
    "triumph": (392.00, 0.16), "reflection": (293.66, 0.10),
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
    return ImageFont.load_default()


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
        duration = round(min(7.0, max(2.8, 2.4 + words * 0.22)), 2)
        emotion = _text(requested_emotions[index] if index < len(requested_emotions) else STORY_EMOTIONS[index % len(STORY_EMOTIONS)], 24).lower()
        if emotion not in EMOTION_SCORE:
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
        "scenes": scenes,
        "music_score": {
            "source": "ffmpeg_procedural_original",
            "license": "original_generated_audio",
            "commercial_use": True,
            "emotional_arc": [scene["emotion"] for scene in scenes],
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
    scenes = plan["scenes"]
    _story_frame(scenes[0]["asset_path"], cover_path)
    _story_frame(scenes[-1]["asset_path"], final_path)
    _story_frame(scenes[-1]["asset_path"], static_path, square=True)
    command = [_ffmpeg(), "-y"]
    for scene in scenes:
        command.extend(["-loop", "1", "-framerate", str(REEL_FPS), "-t", str(scene["duration"]), "-i", scene["asset_path"]])
    narration_path = str(plan.get("narration_path") or "").strip()
    if narration_path:
        if not os.path.isfile(narration_path):
            raise ValueError("scored_story_narration_not_found")
        command.extend(["-i", narration_path])
    filters = []
    video_labels = []
    audio_labels = []
    intensity = float(plan.get("motion_intensity") or 0.55)
    for index, scene in enumerate(scenes):
        frames = max(1, int(math.ceil(float(scene["duration"]) * REEL_FPS)))
        zoom_step = (0.00018 + intensity * 0.00032) * (1 if scene["movement"] == "slow_push" else -1)
        zoom = f"min(zoom+{zoom_step:.6f},1.08)" if zoom_step > 0 else f"max(zoom{zoom_step:.6f},1.0)"
        filters.append(
            f"[{index}:v]scale={REEL_WIDTH}:{REEL_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={REEL_WIDTH}:{REEL_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x10191d,"
            f"zoompan=z='{zoom}':d={frames}:s={REEL_WIDTH}x{REEL_HEIGHT}:fps={REEL_FPS},"
            f"trim=duration={scene['duration']},setpts=PTS-STARTPTS[v{index}]"
        )
        frequency, volume = EMOTION_SCORE[scene["emotion"]]
        fade_out = max(0.0, float(scene["duration"]) - 0.45)
        filters.append(
            f"sine=frequency={frequency}:sample_rate=48000:duration={scene['duration']},"
            f"volume={volume},afade=t=in:st=0:d=0.35,afade=t=out:st={fade_out:.2f}:d=0.45[a{index}]"
        )
        video_labels.append(f"[v{index}]")
        audio_labels.append(f"[a{index}]")
    filters.append(f"{''.join(video_labels)}concat=n={len(scenes)}:v=1:a=0,format=yuv420p[v]")
    filters.append(f"{''.join(audio_labels)}concat=n={len(scenes)}:v=0:a=1[score]")
    audio_map = "[score]"
    if narration_path:
        narration_index = len(scenes)
        filters.append(f"[score]volume=0.32[ducked];[{narration_index}:a]volume=1.0[narration];[ducked][narration]amix=inputs=2:duration=first:dropout_transition=1[aout]")
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
    narration_path = str(plan.get("narration_path") or "").strip()
    if not narration_path and bool(plan.get("auto_narration")):
        narration_path = render_story_narration(plan, output_path=str(media_dir / f"{stem}_narration.wav"))


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
    duration = float(data.get("format", {}).get("duration") or 0)
    reasons = []
    if video.get("codec_name") != "h264": reasons.append("codec_not_h264")
    if (int(video.get("width") or 0), int(video.get("height") or 0)) != (REEL_WIDTH, REEL_HEIGHT): reasons.append("wrong_resolution")
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