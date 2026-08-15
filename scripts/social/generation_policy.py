"""Generation-cost policy and run-scoped provenance for creative providers.

Deterministic creative is always available. External providers are optional
capacity and must ask this module before a network request is made.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


FREE_AI_ONLY = "FREE_AI_ONLY"
ZERO_PAID_AI = "ZERO_PAID_AI"
FREE_AI_ALLOWED = "FREE_AI_ALLOWED"
PAID_AI_ALLOWED = "PAID_AI_ALLOWED"
AUTO = "AUTO"
_MODES = {FREE_AI_ONLY, ZERO_PAID_AI, FREE_AI_ALLOWED, PAID_AI_ALLOWED, AUTO}
_UNAVAILABLE: dict[str, str] = {}
_LEDGER: dict[str, Any] = {}


def mode() -> str:
    configured = str(os.environ.get("GENERATION_COST_MODE", AUTO)).strip().upper()
    return configured if configured in _MODES else AUTO


def start_run() -> None:
    """Reset run-scoped provider state; callers persist ``snapshot`` with content."""
    _UNAVAILABLE.clear()
    _LEDGER.clear()
    _LEDGER.update({
        "generation_cost_mode": mode(),
        "copy_generation_mode": "deterministic",
        "copy_provider": "deterministic_composer",
        "visual_generation_mode": "deterministic",
        "visual_provider": "deterministic_brand_renderer",
        "video_generation_mode": "deterministic",
        "video_provider": "ffmpeg",
        "paid_text_calls": 0,
        "paid_image_calls": 0,
        "paid_video_calls": 0,
        "fallback_used": False,
        "fallback_reason": "",
        "estimated_provider_cost": 0.0,
        "provider_unavailable": {},
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    })


def paid_authorized(provider: str, capability: str) -> tuple[bool, str]:
    """Return permission before any paid-provider client or request is created."""
    if provider in _UNAVAILABLE:
        return False, f"provider_unavailable:{_UNAVAILABLE[provider]}"
    current = mode()
    if current in {FREE_AI_ONLY, ZERO_PAID_AI, FREE_AI_ALLOWED}:
        return False, f"cost_mode_{current.lower()}"
    if current == AUTO:
        return False, "auto_prefers_owned_deterministic"
    if str(os.environ.get("PAID_GENERATION_AUTHORIZED", "false")).strip().lower() not in {"1", "true", "yes", "on"}:
        return False, "paid_generation_not_authorized"
    return True, "authorized"


def record_paid_call(capability: str, provider: str = "gemini", estimated_cost: float = 0.0) -> None:
    if not _LEDGER:
        start_run()
    key = {"text": "paid_text_calls", "image": "paid_image_calls", "video": "paid_video_calls"}.get(capability, "paid_text_calls")
    _LEDGER[key] += 1
    _LEDGER["estimated_provider_cost"] = round(float(_LEDGER["estimated_provider_cost"]) + float(estimated_cost), 6)
    _LEDGER[f"{capability}_provider"] = provider


def mark_provider_unavailable(provider: str, reason: str) -> None:
    sanitized = " ".join(str(reason or "provider_failure").split())[:180]
    _UNAVAILABLE[provider] = sanitized
    if not _LEDGER:
        start_run()
    _LEDGER["provider_unavailable"] = dict(_UNAVAILABLE)
    _LEDGER["fallback_used"] = True
    _LEDGER["fallback_reason"] = sanitized


def record_deterministic(capability: str, provider: str, fallback_reason: str = "") -> None:
    if not _LEDGER:
        start_run()
    _LEDGER[f"{capability}_generation_mode"] = "deterministic"
    _LEDGER[f"{capability}_provider"] = provider
    if fallback_reason:
        _LEDGER["fallback_used"] = True
        _LEDGER["fallback_reason"] = fallback_reason


def snapshot() -> dict[str, Any]:
    if not _LEDGER:
        start_run()
    return {**_LEDGER, "provider_unavailable": dict(_UNAVAILABLE)}