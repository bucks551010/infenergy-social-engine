"""CTA engine — Spec Section 28.

Chooses a CTA by awareness stage + campaign objective. Composes with the
existing funnel-stage cta_library (loaded via campaign_runtime.py) — if a
funnel-stage CTA is passed in, we return it; otherwise we synthesize from
the awareness ladder.
"""

from __future__ import annotations

from .libraries import cta_ladder


def by_awareness(stage: str) -> list[str]:
    return list(cta_ladder()["by_awareness"].get(stage, []))


def by_objective(objective: str) -> list[str]:
    return list(cta_ladder()["by_campaign_objective"].get(objective, []))


def choose(
    awareness_stage: str,
    campaign_objective: str = "",
    existing_cta: str = "",
    recent_ctas: list[str] | None = None,
) -> str:
    """Return a CTA. Prefer existing_cta if it is fresh, otherwise ladder pick."""
    recent = {c.lower() for c in (recent_ctas or []) if c}
    if existing_cta and existing_cta.lower() not in recent:
        return existing_cta

    pool = by_objective(campaign_objective) if campaign_objective else []
    if not pool:
        pool = by_awareness(awareness_stage)

    fresh = [c for c in pool if c.lower() not in recent]
    return (fresh or pool or ["Learn more"])[0]
