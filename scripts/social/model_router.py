"""Gemini model routing + prompt versioning + API cost tracking.

Master Build §93-§96. Environment-configurable so we do not scatter
model names throughout the codebase.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_MODEL_ROUTES: dict[str, str] = {
    "classification": "gemini-2.5-flash",
    "topic_generation": "gemini-2.5-flash",
    "strategy": "gemini-2.5-pro",
    "visual_direction": "gemini-2.5-pro",
    "copy_editing": "gemini-2.5-flash",
    "image_analysis": "gemini-2.5-flash",
    "fact_reasoning": "gemini-2.5-pro",
    "final_review": "gemini-2.5-pro",
}


def route_for(task: str) -> str:
    """Return the model name for a task; env var GEMINI_ROUTE_<TASK> overrides."""
    env = os.environ.get(f"GEMINI_ROUTE_{task.upper()}")
    if env:
        return env.strip()
    return DEFAULT_MODEL_ROUTES.get(task, "gemini-2.5-flash")


# --- Prompt versioning (§96) -----------------------------------------------


PROMPT_REGISTRY: dict[str, dict[str, Any]] = {}


def register_prompt(
    *,
    prompt_id: str,
    version: str,
    purpose: str,
    template: str,
    notes: str = "",
) -> None:
    PROMPT_REGISTRY[prompt_id] = {
        "prompt_id": prompt_id,
        "version": version,
        "purpose": purpose,
        "template": template,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "notes": notes,
    }


def get_prompt(prompt_id: str) -> dict[str, Any] | None:
    return PROMPT_REGISTRY.get(prompt_id)


# --- API cost intelligence (§94) -------------------------------------------


@dataclass
class ApiCallRecord:
    model: str
    task: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    failed: bool = False
    retry_of: str | None = None
    estimated_cost_usd: float = 0.0
    started_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "task": self.task,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "failed": self.failed,
            "retry_of": self.retry_of,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "started_at": self.started_at,
        }


class ApiCostTracker:
    def __init__(self) -> None:
        self.records: list[ApiCallRecord] = []

    def record(self, r: ApiCallRecord) -> None:
        self.records.append(r)

    def totals(self) -> dict[str, Any]:
        return {
            "calls": len(self.records),
            "failed": sum(1 for r in self.records if r.failed),
            "input_tokens": sum(r.input_tokens for r in self.records),
            "output_tokens": sum(r.output_tokens for r in self.records),
            "estimated_cost_usd": round(sum(r.estimated_cost_usd for r in self.records), 6),
        }

    def dump(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"records": [r.as_dict() for r in self.records], "totals": self.totals()}, fh, indent=2)
