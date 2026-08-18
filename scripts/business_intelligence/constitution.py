"""Canonical Human Connection Constitution read model and scoped compiler."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import paths


def _human_truth_dir() -> Path:
    return Path(paths.marketing_dir()) / "human_truth"


def constitution_path() -> Path:
    return _human_truth_dir() / "constitution.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _checksum(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def load_constitution() -> dict[str, Any]:
    return _load_json(constitution_path())


def validate_constitution_integrity() -> dict[str, Any]:
    constitution = load_constitution()
    errors: list[str] = []
    if constitution.get("schema_version") != "constitution.v1":
        errors.append("invalid_schema_version")
    for key in ("constitution_id", "operating_principles", "core_mandates", "preemptive_creation_logic", "moment_worlds", "trust_boundaries", "voice", "references"):
        if not constitution.get(key):
            errors.append(f"missing:{key}")
    repo_root = Path(paths._repo_root())
    for reference in constitution.get("references", []):
        if not (repo_root / str(reference)).is_file():
            errors.append(f"missing_reference:{reference}")
    return {
        "valid": not errors,
        "errors": errors,
        "constitution_id": constitution.get("constitution_id", ""),
        "constitution_checksum": _checksum(constitution_path()),
        "manifesto_checksum": _checksum(Path(paths.founder_manifesto_path())),
    }


def _pick_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    if not item_id:
        return {}
    return next((item for item in items if item.get("id") == item_id), {})


def resolve_moment_id(*values: str) -> str:
    """Map a live customer-moment description to a canonical moment world."""
    text = " ".join(str(value or "").lower() for value in values)
    constitution = load_constitution()
    known = set(constitution.get("buying_moments", []))
    for value in values:
        if str(value or "") in known:
            return str(value)
    rules = (
        ("device_compatibility_question", ("compatib", "watt-hour", "watt hour", "port", "charging standard")),
        ("weather_forecast_changes", ("weather", "forecast", "radar", "storm")),
        ("outage_or_power_interruption", ("outage", "blackout", "power interruption", "grid fails", "lights go out")),
        ("limited_outlet_access_for_work_or_school", ("outlet", "laptop", "work", "school", "mobile")),
        ("trip_or_camping_plan", ("trip", "travel", "camping", "next leg")),
        ("possible_overbuying_or_underbuying", ("overbuy", "underbuy", "right fit", "too much", "too little")),
    )
    for moment_id, hints in rules:
        if any(hint in text for hint in hints):
            return moment_id
    if re.search(r"\bwh\b", text):
        return "device_compatibility_question"
    return ""


def compile_constitutional_context(*, segment_id: str = "", moment_id: str = "", job: str = "") -> dict[str, Any]:
    """Return only the high-authority Constitution material for one decision."""
    constitution = load_constitution()
    if not constitution:
        return {}
    integrity = validate_constitution_integrity()
    voice = constitution.get("voice", {})
    moment = moment_id if moment_id in constitution.get("buying_moments", []) else ""
    content_job = job if job in constitution.get("content_jobs", []) else ""
    return {
        "constitution_id": constitution.get("constitution_id", ""),
        "constitution_checksum": integrity["constitution_checksum"],
        "manifesto_checksum": integrity["manifesto_checksum"],
        "source_authority": "OWNER_CONSTITUTIONAL_TRUTH",
        "core_mandates": constitution.get("core_mandates", []),
        "founder_origin": constitution.get("founder_origin", {}),
        "worldview": constitution.get("worldview", {}),
        "preemptive_creation_logic": constitution.get("preemptive_creation_logic", {}),
        "human_value_ladder": constitution.get("human_value_ladder", {}),
        "audience_world": _pick_by_id(constitution.get("audience_worlds", []), segment_id),
        "buying_moment": moment,
        "moment_world": _pick_by_id(constitution.get("moment_worlds", []), moment),
        "content_job": content_job,
        "operating_principles": constitution.get("operating_principles", []),
        "trust_boundaries": constitution.get("trust_boundaries", {}),
        "voice_guidance": {
            "name": voice.get("name", ""),
            "behaviors": voice.get("behaviors", []),
            "semantic_world": voice.get("semantic_world", []),
            "anti_language": voice.get("anti_language", []),
        },
        "scene_library": constitution.get("scene_library", []),
        "approved_historical_language": [
            phrase for phrase in constitution.get("historical_language", [])
            if phrase.get("public_approval") is True
        ],
        "reputation_destination": constitution.get("reputation_destination", ""),
        "integrity_valid": integrity["valid"],
    }