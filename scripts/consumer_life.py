from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import date
from typing import Any

BASE_DIR = os.path.dirname(__file__)
DEFAULT_PATH = os.path.join(BASE_DIR, "..", "data", "social", "consumer_life_foundation.json")

REQUIRED_WORLD_FIELDS = (
    "id",
    "name",
    "people",
    "places",
    "activities",
    "devices_and_jobs",
)
REQUIRED_MOMENT_FIELDS = (
    "id",
    "world_id",
    "person",
    "setting",
    "activity",
    "devices_and_jobs",
    "friction",
    "disruption",
    "failure",
    "consequence",
    "immediate_action",
    "backup_plan",
    "question",
    "false_assumption",
    "curiosity_payoff",
    "useful_discovery",
    "visual_evidence",
    "compatible_treatments",
    "product_fit",
)
FORBIDDEN_PUBLIC_CATEGORIES = {"verified_education", "technical_education", "product_education"}


def _require_text(record: dict[str, Any], field: str, label: str) -> None:
    if not str(record.get(field) or "").strip():
        raise ValueError(f"{label} requires non-empty {field}")


def _validate_foundation(data: dict[str, Any]) -> None:
    worlds = data.get("worlds")
    moments = data.get("moments")
    if not isinstance(worlds, list) or not worlds:
        raise ValueError("consumer foundation requires worlds")
    if not isinstance(moments, list) or not moments:
        raise ValueError("consumer foundation requires moments")

    world_ids: set[str] = set()
    for world in worlds:
        if not isinstance(world, dict):
            raise ValueError("each consumer world must be an object")
        for field in REQUIRED_WORLD_FIELDS:
            if field in {"people", "places", "activities", "devices_and_jobs"}:
                if not isinstance(world.get(field), list) or not world[field]:
                    raise ValueError(f"consumer world requires non-empty {field}")
            else:
                _require_text(world, field, "consumer world")
        world_id = str(world["id"])
        if world_id in world_ids:
            raise ValueError(f"duplicate consumer world id: {world_id}")
        world_ids.add(world_id)

    moment_ids: set[str] = set()
    for moment in moments:
        if not isinstance(moment, dict):
            raise ValueError("each consumer moment must be an object")
        for field in REQUIRED_MOMENT_FIELDS:
            if field in {"devices_and_jobs", "visual_evidence", "compatible_treatments"}:
                if not isinstance(moment.get(field), list) or not moment[field]:
                    raise ValueError(f"consumer moment requires non-empty {field}")
            elif field == "product_fit":
                if not isinstance(moment.get(field), dict) or not str(moment[field].get("mode") or "").strip():
                    raise ValueError("consumer moment requires product_fit.mode")
            else:
                _require_text(moment, field, "consumer moment")
        moment_id = str(moment["id"])
        if moment_id in moment_ids:
            raise ValueError(f"duplicate consumer moment id: {moment_id}")
        if str(moment["world_id"]) not in world_ids:
            raise ValueError(f"unknown world_id for consumer moment: {moment_id}")
        categories = {str(value).strip().lower() for value in moment.get("public_categories", [])}
        if categories.intersection(FORBIDDEN_PUBLIC_CATEGORIES):
            raise ValueError(f"consumer moment exposes a forbidden public category: {moment_id}")
        moment_ids.add(moment_id)


def load_consumer_foundation(path: str = DEFAULT_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("consumer foundation must be an object")
    _validate_foundation(data)
    return data


def select_consumer_root(
    *,
    current_date: str | date,
    slot: str = "midday",
    preferred_world_id: str = "",
    sequence: int = 0,
    path: str = DEFAULT_PATH,
) -> dict[str, Any]:
    data = load_consumer_foundation(path)
    worlds = {str(world["id"]): world for world in data["worlds"]}
    candidates = [
        moment for moment in data["moments"]
        if not preferred_world_id or str(moment["world_id"]) == preferred_world_id
    ]
    if not candidates:
        raise ValueError(f"no consumer moments for world: {preferred_world_id}")
    date_key = current_date.isoformat() if isinstance(current_date, date) else str(current_date)
    digest = hashlib.sha256(f"{date_key}|{slot}|{sequence}".encode("utf-8")).hexdigest()
    selected = deepcopy(candidates[int(digest[:12], 16) % len(candidates)])
    world = deepcopy(worlds[str(selected["world_id"])])
    return {
        "schema_version": str(data.get("schema_version") or "consumer-life.v1"),
        "root_id": f"{world['id']}:{selected['id']}",
        "world_id": str(world["id"]),
        "moment_id": str(selected["id"]),
        "world": world,
        "moment": selected,
        "consumer_receipt": {
            "who": selected["person"],
            "where": selected["setting"],
            "doing": selected["activity"],
            "friction": selected["friction"],
            "consequence": selected["consequence"],
            "useful_discovery": selected["useful_discovery"],
            "immediate_action": selected["immediate_action"],
            "product_fit_mode": selected["product_fit"]["mode"],
        },
    }


def validate_consumer_receipt(content: dict[str, Any]) -> dict[str, Any]:
    root = content.get("consumer_root") if isinstance(content.get("consumer_root"), dict) else {}
    receipt = content.get("consumer_receipt") if isinstance(content.get("consumer_receipt"), dict) else {}
    errors: list[str] = []
    if str(root.get("schema_version") or "") != "consumer-life.v1":
        errors.append("missing_consumer_life_schema")
    for field in ("root_id", "world_id", "moment_id"):
        if not str(root.get(field) or "").strip():
            errors.append(f"missing_consumer_{field}")
    for field in ("who", "where", "doing", "friction", "consequence", "useful_discovery", "immediate_action", "product_fit_mode"):
        if not str(receipt.get(field) or "").strip():
            errors.append(f"missing_consumer_receipt_{field}")
    if root and receipt and receipt != root.get("consumer_receipt"):
        errors.append("consumer_receipt_root_mismatch")
    moment = root.get("moment") if isinstance(root.get("moment"), dict) else {}
    product_fit = moment.get("product_fit") if isinstance(moment.get("product_fit"), dict) else {}
    if str(product_fit.get("mode") or "") == "none" and any(
        str(content.get(field) or "").strip() for field in ("product_id", "product_name", "product_sku")
    ):
        errors.append("product_forbidden_for_consumer_moment")
    return {"passed": not errors, "errors": errors, "root_id": str(root.get("root_id") or "")}
