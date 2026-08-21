"""Canonical, human-owned INF Energy company knowledge contract."""

from __future__ import annotations

import hashlib
import json
import os
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
    "visual_language",
    "thought_library",
    "agent_specializations",
}


def knowledge_path(data_dir: str) -> str:
    persistent_path = os.path.join(data_dir, "marketing", "infenergy_company_knowledge.json")
    if os.path.exists(persistent_path):
        return persistent_path
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "marketing", "infenergy_company_knowledge.json")
    )


def load_company_knowledge(data_dir: str) -> dict[str, Any]:
    path = knowledge_path(data_dir)
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
        "product_truth_policy": knowledge.get("product_truth_policy", {}),
    }


def agent_specialization(knowledge: dict[str, Any], agent_name: str) -> dict[str, Any]:
    specializations = knowledge.get("agent_specializations", {})
    return {
        "company_knowledge_id": knowledge.get("knowledge_id"),
        "company_knowledge_version": knowledge.get("schema_version"),
        "company_knowledge_digest": knowledge_digest(knowledge),
        "specialization": str(specializations.get(agent_name) or "Apply canonical company truth to the assigned discipline."),
        "operating_rule": "Canonical company truth is fixed; improve the expression without inventing a new mission, promise, benefit, or product fact.",
    }
