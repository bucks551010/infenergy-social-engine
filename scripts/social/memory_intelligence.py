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
        "visual_signatures": _recent_field(vdata["records"], "visual_signature", limit),
        "visual_formats": _recent_field(vdata["records"], "visual_format", limit),
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
