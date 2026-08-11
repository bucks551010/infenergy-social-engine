"""Loaders for the Autonomous Social Creative Intelligence layer.

Mirrors ``scripts/conversion/libraries.py`` but points at ``data/social/``.
All JSON is hand-editable and cached in-process.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LIB_DIR_DEFAULT = os.path.join(_HERE, "data", "social")


def _lib_dir() -> str:
    override = os.environ.get("SOCIAL_LIB_DIR")
    if override and os.path.isdir(override):
        return override
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        candidate = os.path.join(data_dir, "social")
        if os.path.isdir(candidate):
            return candidate
    return _LIB_DIR_DEFAULT


def _load(name: str) -> dict[str, Any]:
    path = os.path.join(_lib_dir(), name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def pillars() -> dict[str, Any]:
    return _load("pillars.json")["pillars"]


@lru_cache(maxsize=None)
def pillar_defaults() -> dict[str, Any]:
    return _load("pillars.json").get("defaults", {})


@lru_cache(maxsize=None)
def genres() -> dict[str, Any]:
    return _load("genres.json")["genres"]


@lru_cache(maxsize=None)
def reader_jobs() -> dict[str, Any]:
    return _load("reader_jobs.json")["jobs"]


@lru_cache(maxsize=None)
def audience_segments() -> dict[str, Any]:
    return _load("audience_world.json")["segments"]


@lru_cache(maxsize=None)
def topic_graph() -> dict[str, Any]:
    return _load("topic_graph.json")["topics"]


@lru_cache(maxsize=None)
def hook_families() -> dict[str, Any]:
    return _load("hook_families.json")["families"]


@lru_cache(maxsize=None)
def hook_global_banned_openers() -> list[str]:
    return list(_load("hook_families.json").get("global_banned_openers", []))


@lru_cache(maxsize=None)
def visual_formats() -> dict[str, Any]:
    return _load("visual_formats.json")["formats"]


@lru_cache(maxsize=None)
def visual_semantic_purposes() -> list[str]:
    return list(_load("visual_formats.json").get("semantic_purposes", []))


@lru_cache(maxsize=None)
def brand_design_tokens() -> dict[str, Any]:
    return _load("brand_design_tokens.json")


@lru_cache(maxsize=None)
def platform_specs() -> dict[str, Any]:
    return _load("platform_specs.json")["platforms"]


@lru_cache(maxsize=None)
def series_registry() -> dict[str, Any]:
    return _load("series.json")["series"]


def reset_cache() -> None:
    """Testing helper: drop all cached library JSON."""
    for fn in (
        pillars, pillar_defaults, genres, reader_jobs, audience_segments,
        topic_graph, hook_families, hook_global_banned_openers,
        visual_formats, visual_semantic_purposes, brand_design_tokens,
        platform_specs, series_registry,
    ):
        fn.cache_clear()
