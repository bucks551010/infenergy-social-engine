"""Copy-structure engine — Spec Section 10.

The Conversion Logic law sits ABOVE these; structures are execution styles.
Picks a structure compatible with the selected law and awareness stage.
"""

from __future__ import annotations

from .libraries import copy_structures


def all_structures() -> list[str]:
    return list(copy_structures().keys())


def structure(name: str) -> dict:
    lib = copy_structures()
    return lib.get(name, lib["PAS"])


def select(
    awareness_stage: str,
    law_name: str,
    recent_structures: list[str] | None = None,
    explicit: str | None = None,
    preferred: list[str] | None = None,
) -> str:
    if explicit and explicit in copy_structures():
        return explicit

    recent = set(recent_structures or [])

    # Preferred = intersection of awareness fit and law fit
    preferred_pool = []
    for name, cfg in copy_structures().items():
        law_fit = law_name in cfg.get("best_for_laws", [])
        awareness_fit = awareness_stage in cfg.get("best_for_awareness", [])
        if law_fit and awareness_fit:
            preferred_pool.append(name)

    if not preferred_pool:
        preferred_pool = [
            name for name, cfg in copy_structures().items()
            if awareness_stage in cfg.get("best_for_awareness", [])
        ] or list(copy_structures().keys())

    fresh = [name for name in preferred_pool if name not in recent]

    if preferred:
        pref_fresh = [name for name in preferred if name in fresh]
        if pref_fresh:
            return pref_fresh[0]
        pref_any = [name for name in preferred if name in preferred_pool]
        if pref_any:
            return pref_any[0]

    return (fresh or preferred_pool)[0]


def beats(name: str) -> list[str]:
    return list(structure(name).get("beats", []))
