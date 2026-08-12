"""Lean, persistent marketing-decision loop; it observes and prioritizes, never posts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from . import research_router

STATES = {"NEW", "RESEARCH_NEEDED", "READY", "DEFERRED", "SELECTED", "USED", "EXPIRED", "REJECTED"}


def _path(data_dir: str) -> str:
    return os.path.join(data_dir, "social", "living_intelligence.json")


def load(data_dir: str) -> dict[str, Any]:
    try:
        with open(_path(data_dir), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"first_party": {}, "competitors": {}, "opportunities": []}


def save(data_dir: str, state: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_path(data_dir)), exist_ok=True)
    with open(_path(data_dir), "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def human_connection(*, audience: str, moment: str, situation: str, need: str, capability: str, benefit: str, outcome: str) -> dict[str, str]:
    """Express a human meaning only when supported by a real customer moment."""
    meaning = ""
    text = f"{moment} {situation} {need}".lower()
    if any(word in text for word in ("outage", "storm", "emergency", "family")):
        meaning = "preparedness and confidence"
    elif any(word in text for word in ("travel", "commute", "away")):
        meaning = "freedom and convenience"
    return {"person": audience, "situation": situation, "what_matters": need, "human_need": need,
            "offering_capability": capability, "benefit": benefit, "outcome": outcome, "human_meaning": meaning}


def non_price_edge(*, capability: str, benefit: str, evidence: list[str], communication_edge: str = "") -> dict[str, str]:
    if evidence and capability and benefit:
        return {"kind": "PRODUCT_EDGE", "reason": f"{capability} supports {benefit}", "proof": "; ".join(evidence[:2])}
    if communication_edge:
        return {"kind": "MARKETING_COMMUNICATION_EDGE", "reason": communication_edge, "proof": "communication clarity, not superiority"}
    return {"kind": "NO_DEFENSIBLE_EDGE", "reason": "No supported reason beyond price", "proof": ""}


def heartbeat(data_dir: str, *, level: str = "LIGHT_HEARTBEAT", website_url: str = "") -> dict[str, Any]:
    """Observe only decision-relevant deltas and emit opportunities; no copy or publishing."""
    state = load(data_dir)
    observations: list[dict[str, Any]] = []
    if website_url:
        prior = (state.get("first_party") or {}).get(website_url, {}).get("content_hash", "")
        current = research_router.inspect_first_party(website_url, prior)
        state.setdefault("first_party", {})[website_url] = current
        if current["changed"] or not prior:
            observations.append({"type": "first_party_change", "source": website_url, "signal": "business messaging or product change"})
    for observation in observations:
        key = sha256(json.dumps(observation, sort_keys=True).encode()).hexdigest()[:16]
        if not any(item.get("id") == key for item in state["opportunities"]):
            state["opportunities"].append({"id": key, "state": "NEW", "source": observation["type"],
                "why_now": observation["signal"], "decision": "evaluate strategic angle", "created_at": datetime.now(timezone.utc).isoformat()})
    state["last_heartbeat"] = {"level": level, "observations": len(observations), "at": datetime.now(timezone.utc).isoformat()}
    save(data_dir, state)
    return {"status": "ok", "observations": observations, "opportunities": state["opportunities"]}


def council(state: dict[str, Any], *, strategy_inputs: dict[str, Any]) -> dict[str, Any]:
    """Select a strategy from evidence; roles appear only when their evidence exists."""
    ready = [item for item in state.get("opportunities", []) if item.get("state") in {"NEW", "READY"}]
    if not ready:
        return {"decision": "do_not_generate", "reason": "no evidence-backed opportunity", "participants": ["Opportunity Strategist"]}
    opportunity = ready[0]
    participants = ["Business Intelligence Delegate", "Audience Advocate", "Human Connection Strategist", "Opportunity Strategist", "Final Reviewer"]
    if strategy_inputs.get("competitor_context"):
        participants.append("Competitor Strategist")
    return {"decision": "strategy_selected", "participants": participants, "opportunity_id": opportunity["id"],
            "approved_strategy": strategy_inputs | {"opportunity_id": opportunity["id"]}}