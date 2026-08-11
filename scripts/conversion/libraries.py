"""JSON library loader for the conversion decision-logic layer.

Libraries are loaded once and cached in-process. They live under
data/marketing/conversion/ and are hand-editable — no code change needed.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LIB_DIR_DEFAULT = os.path.join(_HERE, "data", "marketing", "conversion")


def _lib_dir() -> str:
    override = os.environ.get("CONVERSION_LIB_DIR")
    if override and os.path.isdir(override):
        return override
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        candidate = os.path.join(data_dir, "marketing", "conversion")
        if os.path.isdir(candidate):
            return candidate
    return _LIB_DIR_DEFAULT


def _load(name: str) -> dict[str, Any]:
    path = os.path.join(_lib_dir(), name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def awareness_levels() -> dict[str, Any]:
    return _load("awareness_levels.json")["levels"]


@lru_cache(maxsize=None)
def emotional_drivers() -> dict[str, Any]:
    return _load("emotional_drivers.json")


@lru_cache(maxsize=None)
def logic_laws() -> dict[str, Any]:
    return _load("logic_laws.json")["laws"]


@lru_cache(maxsize=None)
def copy_structures() -> dict[str, Any]:
    return _load("copy_structures.json")["structures"]


@lru_cache(maxsize=None)
def objection_library() -> dict[str, Any]:
    return _load("objection_library.json")


@lru_cache(maxsize=None)
def personas() -> dict[str, Any]:
    return _load("personas.json")["personas"]


@lru_cache(maxsize=None)
def transformations() -> list[dict[str, Any]]:
    return _load("transformations.json")["transformations"]


@lru_cache(maxsize=None)
def hook_categories() -> dict[str, Any]:
    return _load("hook_categories.json")


@lru_cache(maxsize=None)
def cta_ladder() -> dict[str, Any]:
    return _load("cta_ladder.json")


def reload_all() -> None:
    for fn in (
        awareness_levels, emotional_drivers, logic_laws, copy_structures,
        objection_library, personas, transformations, hook_categories, cta_ladder,
    ):
        fn.cache_clear()
