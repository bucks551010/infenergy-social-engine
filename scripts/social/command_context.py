from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _normalized(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def resolve_product_context(command: str, data_dir: str) -> dict[str, Any]:
    path = Path(data_dir) / "marketing" / "product_consumer_profiles.json"
    try:
        profiles = json.loads(path.read_text(encoding="utf-8")).get("profiles", {})
    except (OSError, ValueError, AttributeError):
        return {}
    normalized_command = _normalized(command)
    matches: list[tuple[int, dict[str, Any]]] = []
    for profile in profiles.values() if isinstance(profiles, dict) else []:
        if not isinstance(profile, dict):
            continue
        product_id = _normalized(profile.get("product_id"))
        product_name = _normalized(profile.get("product_name"))
        base_name = re.sub(r"\b(?:white|black|green|blue|red|orange|silver|gray|grey)\b.*$", "", product_name).strip()
        score = 0
        if product_id and product_id in normalized_command:
            score = 1000 + len(product_id)
        elif product_name and product_name in normalized_command:
            score = 800 + len(product_name)
        elif len(base_name) >= 5 and base_name in normalized_command:
            score = 500 + len(base_name)
        if score:
            matches.append((score, profile))
    if not matches:
        return {}
    profile = max(matches, key=lambda item: item[0])[1]
    product_id = str(profile.get("product_id") or "").strip()
    brief: dict[str, Any] = {}
    if product_id:
        brief_path = Path(data_dir) / "product_briefs" / f"{product_id}.json"
        try:
            loaded = json.loads(brief_path.read_text(encoding="utf-8"))
            brief = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            brief = {}
    command_tokens = set(normalized_command.split())
    personas = [item for item in profile.get("personas", []) if isinstance(item, dict)]

    def persona_score(persona: dict[str, Any]) -> int:
        fields = ("name", "identity", "life_context", "profession_context", "family_context", "leisure_context", "use_case")
        return len(command_tokens & set(_normalized(" ".join(str(persona.get(key) or "") for key in fields)).split()))

    persona = max(personas, key=persona_score, default={})
    return {"profile": profile, "persona": persona, "evidence": brief}


def originality_context(command: str, data_dir: str) -> list[str]:
    path = Path(data_dir) / "social" / "content_memory.json"
    try:
        records = json.loads(path.read_text(encoding="utf-8")).get("records", [])
    except (OSError, ValueError, AttributeError):
        return []
    command_tokens = set(_normalized(command).split())
    scored: list[tuple[float, dict[str, Any]]] = []
    for record in records[-50:] if isinstance(records, list) else []:
        if not isinstance(record, dict) or record.get("source") != "creative.command.produce":
            continue
        prior_tokens = set(_normalized(record.get("objective")).split())
        similarity = len(command_tokens & prior_tokens) / max(1, len(command_tokens | prior_tokens))
        scored.append((similarity, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [str(item.get("visual_signature") or item.get("objective") or "") for score, item in scored[:3] if score >= 0.35]
