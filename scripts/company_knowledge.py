"""Canonical, human-owned INF Energy company knowledge contract."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any


REQUIRED_SECTIONS = {
    "brand",
    "origin_and_conviction",
    "values",
    "consumer_benefits",
    "audiences",
    "product_truth_policy",
    "content_pillars",
    "voice",
    "editorial_playbook",
    "visual_language",
    "thought_library",
    "agent_specializations",
}


def packaged_knowledge_path() -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "marketing", "infenergy_company_knowledge.json")
    )


def knowledge_path(data_dir: str) -> str:
    persistent_path = os.path.join(data_dir, "marketing", "infenergy_company_knowledge.json")
    if os.path.exists(persistent_path):
        return persistent_path
    return packaged_knowledge_path()


def _load_company_knowledge_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        knowledge = json.load(handle)
    if not isinstance(knowledge, dict):
        raise ValueError("company knowledge must be a JSON object")
    missing = sorted(REQUIRED_SECTIONS - set(knowledge))
    if missing:
        raise ValueError(f"company knowledge missing sections: {', '.join(missing)}")
    thoughts = knowledge.get("thought_library")
    if not isinstance(thoughts, list) or len(thoughts) < 30:
        raise ValueError("company knowledge must contain at least 30 social thoughts")
    identifiers = [str(item.get("id") or "") for item in thoughts if isinstance(item, dict)]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("company thought identifiers must be unique")
    return knowledge


def load_company_knowledge(data_dir: str) -> dict[str, Any]:
    return _load_company_knowledge_file(knowledge_path(data_dir))


def refresh_persistent_company_knowledge(data_dir: str) -> dict[str, Any]:
    source_path = packaged_knowledge_path()
    source = _load_company_knowledge_file(source_path)
    persistent_path = os.path.abspath(os.path.join(data_dir, "marketing", "infenergy_company_knowledge.json"))
    if os.path.samefile(source_path, persistent_path) if os.path.exists(persistent_path) else source_path == persistent_path:
        return {"status": "PACKAGED_PATH_ACTIVE", "path": persistent_path, "backup_path": None}

    os.makedirs(os.path.dirname(persistent_path), exist_ok=True)
    backup_path = None
    if os.path.exists(persistent_path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = f"{persistent_path}.backup.{stamp}"
        shutil.copy2(persistent_path, backup_path)

    descriptor, temporary_path = tempfile.mkstemp(prefix=".company-knowledge-", suffix=".json", dir=os.path.dirname(persistent_path))
    os.close(descriptor)
    try:
        shutil.copy2(source_path, temporary_path)
        _load_company_knowledge_file(temporary_path)
        os.replace(temporary_path, persistent_path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return {
        "status": "REFRESHED_FROM_PACKAGED",
        "path": persistent_path,
        "backup_path": backup_path,
        "knowledge_digest": knowledge_digest(source),
    }


def knowledge_digest(knowledge: dict[str, Any]) -> str:
    payload = json.dumps(knowledge, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_generation_context(knowledge: dict[str, Any]) -> dict[str, Any]:
    brand = knowledge.get("brand", {})
    benefits = knowledge.get("consumer_benefits", {})
    voice = knowledge.get("voice", {})
    return {
        "knowledge_id": knowledge.get("knowledge_id"),
        "schema_version": knowledge.get("schema_version"),
        "digest": knowledge_digest(knowledge),
        "mission": brand.get("mission"),
        "vision": brand.get("vision"),
        "core_purpose": brand.get("core_purpose"),
        "central_human_truth": brand.get("central_human_truth"),
        "brand_promise": brand.get("brand_promise"),
        "community_identity": brand.get("community_identity"),
        "functional_benefits": list(benefits.get("functional", [])),
        "emotional_benefits": list(benefits.get("emotional", [])),
        "lifestyle_transformations": list(benefits.get("lifestyle_transformations", [])),
        "voice": {
            "name": voice.get("name"),
            "traits": list(voice.get("traits", [])),
            "rules": list(voice.get("rules", [])),
            "avoid": list(voice.get("avoid", [])),
        },
        "editorial_playbook": knowledge.get("editorial_playbook", {}),
        "product_truth_policy": knowledge.get("product_truth_policy", {}),
    }


def agent_specialization(knowledge: dict[str, Any], agent_name: str) -> dict[str, Any]:
    specializations = knowledge.get("agent_specializations", {})
    return {
        "company_knowledge_id": knowledge.get("knowledge_id"),
        "company_knowledge_version": knowledge.get("schema_version"),
        "company_knowledge_digest": knowledge_digest(knowledge),
        "specialization": str(specializations.get(agent_name) or "Apply canonical company truth to the assigned discipline."),
        "editorial_playbook": knowledge.get("editorial_playbook", {}),
        "operating_rule": "Canonical company truth is fixed; improve the expression without inventing a new mission, promise, benefit, or product fact.",
    }
