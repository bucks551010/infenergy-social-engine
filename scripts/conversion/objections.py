"""Objection engine — Spec Section 27.

Selects the objection most likely to matter for this audience + awareness
stage + product and returns a reframe pattern + supporting proof types.
"""

from __future__ import annotations

from typing import Any

from .libraries import objection_library


def all_objections() -> list[str]:
    return list(objection_library()["objections"].keys())


def objection(name: str) -> dict[str, Any]:
    lib = objection_library()["objections"]
    return lib.get(name, lib["necessity"])


def select(
    awareness_stage: str,
    persona_top_objection: str | None = None,
    explicit: str | None = None,
) -> str:
    lib = objection_library()
    all_defined = lib["objections"]

    if explicit and explicit in all_defined:
        return explicit
    if persona_top_objection and persona_top_objection in all_defined:
        return persona_top_objection

    defaults = lib["awareness_default_objections"].get(awareness_stage, [])
    if defaults:
        return defaults[0]
    return next(iter(all_defined))


def reframe_pattern(name: str) -> str:
    return objection(name).get("reframe_pattern", "")


def supporting_proof_types(name: str) -> list[str]:
    return list(objection(name).get("supporting_proof_types", []))
