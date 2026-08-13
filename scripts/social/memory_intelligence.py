"""Memory intelligence (Master Build §70-§73).

Two persistent stores backed by simple JSON on disk:
  * content memory — records of past posts (topic, angle, memory_anchor, hook family, tone, emotion, etc.)
  * visual memory — records of past visuals (format, subject, composition, color, signature)

These are additive to the existing ``data/post_history.json`` — we do not
duplicate its schema, we build a lightweight index over it plus a
signature-based fatigue detector.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable


def _default_data_dir() -> str:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = os.environ.get("DATA_DIR")
    if env and os.path.isdir(env):
        return env
    return os.path.join(here, "data")


# --- Content memory ---------------------------------------------------------


def content_memory_path(data_dir: str | None = None) -> str:
    d = data_dir or _default_data_dir()
    return os.path.join(d, "social", "content_memory.json")


def visual_memory_path(data_dir: str | None = None) -> str:
    d = data_dir or _default_data_dir()
    return os.path.join(d, "social", "visual_memory.json")


def post_history_path(data_dir: str | None = None) -> str:
    d = data_dir or _default_data_dir()
    return os.path.join(d, "post_history.json")


def strategy_lessons_path(data_dir: str | None = None) -> str:
    d = data_dir or _default_data_dir()
    return os.path.join(d, "social", "strategy_lessons.json")


def _load(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {"records": []}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"records": []}


def _save(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def append_content_record(
    record: dict[str, Any],
    *,
    data_dir: str | None = None,
    keep_last: int = 500,
) -> None:
    path = content_memory_path(data_dir)
    data = _load(path)
    data["records"].append(record)
    if len(data["records"]) > keep_last:
        data["records"] = data["records"][-keep_last:]
    _save(path, data)


def append_visual_record(
    record: dict[str, Any],
    *,
    data_dir: str | None = None,
    keep_last: int = 500,
) -> None:
    path = visual_memory_path(data_dir)
    data = _load(path)
    data["records"].append(record)
    if len(data["records"]) > keep_last:
        data["records"] = data["records"][-keep_last:]
    _save(path, data)


def append_strategy_lesson(lesson: dict[str, Any], *, data_dir: str | None = None, keep_last: int = 250) -> None:
    """Persist only a bounded, evidence-linked lesson for a matching future context."""
    path = strategy_lessons_path(data_dir)
    data = _load(path)
    required = {"product_id", "condition", "action", "evidence"}
    if not required <= set(lesson) or not lesson.get("evidence"):
        raise ValueError("strategy lesson requires product_id, condition, action, and evidence")
    lesson = dict(lesson)
    lesson.setdefault("lesson_id", uuid.uuid4().hex)
    lesson.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    lesson.setdefault("scope", {"product_id": lesson["product_id"], "condition": lesson["condition"]})
    lesson.setdefault("future_applicability", "Consult only when the same product and evidence condition recur.")
    lesson.setdefault("revalidation", "Reassess when verified product evidence or claim limits change.")
    data["records"].append(lesson)
    if len(data["records"]) > keep_last:
        data["records"] = data["records"][-keep_last:]
    _save(path, data)


def strategy_lessons(*, product_id: str, condition: str, data_dir: str | None = None) -> list[dict[str, Any]]:
    """Return lessons only for the same product and evidence condition."""
    records = _load(strategy_lessons_path(data_dir)).get("records", [])
    return [
        record for record in records
        if isinstance(record, dict)
        and str(record.get("product_id")) == product_id
        and str(record.get("condition")) == condition
    ]


def append_post_history_record(
    record: dict[str, Any],
    *,
    data_dir: str | None = None,
    keep_last: int = 2000,
) -> None:
    path = post_history_path(data_dir)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        data = {"posts": []}
    if not isinstance(data, dict) or not isinstance(data.get("posts"), list):
        data = {"posts": []}
    posts = data["posts"]
    post_id = str(record.get("post_id", ""))
    if post_id and any(str(existing.get("post_id", "")) == post_id for existing in posts if isinstance(existing, dict)):
        return
    posts.append(record)
    if len(posts) > keep_last:
        data["posts"] = posts[-keep_last:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(temp_path, path)


def backfill_post_history_from_content_memory(data_dir: str | None = None) -> int:
    content = _load(content_memory_path(data_dir)).get("records", [])
    before_path = post_history_path(data_dir)
    try:
        with open(before_path, "r", encoding="utf-8") as fh:
            before = len(json.load(fh).get("posts", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        before = 0
    for record in content:
        if isinstance(record, dict):
            append_post_history_record(record, data_dir=data_dir)
    try:
        with open(before_path, "r", encoding="utf-8") as fh:
            after = len(json.load(fh).get("posts", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        after = before
    return max(0, after - before)


# --- Recency projections (used by strategy/opportunity engines) -------------


def _recent_field(records: list[dict[str, Any]], field: str, limit: int) -> list[Any]:
    out: list[Any] = []
    for rec in reversed(records):
        val = rec.get(field)
        if val:
            out.append(val)
        if len(out) >= limit:
            break
    return out


def recent(data_dir: str | None = None, *, limit: int = 20) -> dict[str, list[Any]]:
    cdata = _load(content_memory_path(data_dir))
    vdata = _load(visual_memory_path(data_dir))
    return {
        "pillars": _recent_field(cdata["records"], "pillar_id", limit),
        "genres": _recent_field(cdata["records"], "genre_id", limit),
        "topics": _recent_field(cdata["records"], "topic", limit),
        "microtopics": _recent_field(cdata["records"], "microtopic", limit),
        "hooks": _recent_field(cdata["records"], "hook", limit),
        "ctas": _recent_field(cdata["records"], "cta_type", limit),
        "tones": _recent_field(cdata["records"], "tone", limit),
        "copy_grammars": _recent_field(cdata["records"], "copy_grammar", limit),
        "benefit_orders": _recent_field(cdata["records"], "benefit_order", limit),
        "emotional_framings": _recent_field(cdata["records"], "emotional_framing", limit),
        "customer_moments": _recent_field(cdata["records"], "customer_moment", limit),
        "reader_jobs": _recent_field(cdata["records"], "reader_job", limit),
        "visual_signatures": _recent_field(vdata["records"], "visual_signature", limit),
        "visual_formats": _recent_field(vdata["records"], "visual_format", limit),
        "layout_grammars": _recent_field(vdata["records"], "layout_grammar", limit),
        "product_roles": _recent_field(vdata["records"], "product_role", limit),
        "human_presence": _recent_field(vdata["records"], "human_presence", limit),
        "text_densities": _recent_field(vdata["records"], "text_density", limit),
        "product_placements": _recent_field(vdata["records"], "product_placement", limit),
        "headline_placements": _recent_field(vdata["records"], "headline_placement", limit),
        "art_direction_families": _recent_field(vdata["records"], "art_direction_family", limit),
        "visual_concepts": _recent_field(vdata["records"], "visual_concept", limit),
    }


# --- Semantic duplicate detection (§72) ------------------------------------


def approximate_topic_repeat(candidate_topic: str, recent_topics: Iterable[str]) -> bool:
    if not candidate_topic:
        return False
    low = candidate_topic.lower()
    tokens = {t for t in low.split() if len(t) > 3}
    for rt in recent_topics:
        if not rt:
            continue
        rlow = str(rt).lower()
        rtokens = {t for t in rlow.split() if len(t) > 3}
        if not rtokens:
            continue
        overlap = len(tokens & rtokens) / max(1, len(tokens | rtokens))
        if overlap >= 0.3:
            return True
    return False
