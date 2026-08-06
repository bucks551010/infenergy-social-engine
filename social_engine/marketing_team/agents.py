from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class MarketingAgent:
    name: str
    mission: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ai_json(prompt: str) -> dict[str, Any] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model_name, contents=prompt)
        raw = (response.text or "").strip()
        if not raw:
            return None
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1]
            if raw.lower().startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return None


def research_agent(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": "market_research_agent",
        "market_position": "Preparedness-first portable and modular power brand balancing emergency reliability with clean-energy independence.",
        "top_buyer_jobs": [
            "Keep lights/devices running during outages",
            "Avoid downtime for home office or small business",
            "Portable power for travel/camping/worksites",
            "Transition toward solar-ready energy resilience",
        ],
        "proof_assets": [
            "Published wattage/capacity specs",
            "Warranty and support promises",
            "Use-case education content",
            "Category breadth across emergency and travel power",
        ],
        "timestamp_utc": _utc_now(),
    }


def audience_agent(profile: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": "audience_psychology_agent",
        "segments": [
            {
                "name": "Prepared Family Protector",
                "pain": "Fear of blackout vulnerability",
                "desired_state": "Calm control during emergencies",
                "trigger": "Storm warnings and outage memories",
            },
            {
                "name": "Practical Energy Optimizer",
                "pain": "Rising utility instability and uncertainty",
                "desired_state": "Predictable independent power",
                "trigger": "Bill shock and grid reliability concerns",
            },
            {
                "name": "Mobile Power User",
                "pain": "Power constraints while traveling or working remote",
                "desired_state": "Portable confidence anywhere",
                "trigger": "Trips, jobsites, and device-heavy days",
            },
        ],
        "core_objections": profile.get("psychographics", {}).get("objections", []),
        "timestamp_utc": _utc_now(),
    }


def voice_agent(profile: dict[str, Any]) -> dict[str, Any]:
    # Uses principle-based conversion style without imitating named living writers.
    return {
        "agent": "brand_voice_agent",
        "voice_name": "Resilient Momentum",
        "voice_rules": [
            "Lead with tension: risk of doing nothing.",
            "Translate specs into outcomes buyers feel.",
            "Use value stacking and practical next steps.",
            "Be urgent but never manipulative or exaggerated.",
            "Anchor claims in concrete facts and examples.",
        ],
        "style_markers": {
            "energy": "high",
            "cadence": "short-to-medium punchy lines",
            "authority": "advisor, not hype machine",
            "cta": "single clear action per asset",
        },
        "do_not": [
            "Do not copy or mimic specific living public figures.",
            "Do not use unverifiable guarantees.",
            "Do not overuse jargon.",
        ],
        "timestamp_utc": _utc_now(),
    }


def offer_agent(profile: dict[str, Any], audience: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": "offer_strategy_agent",
        "core_offers": [
            "Free Power Readiness Assessment",
            "Device-by-device runtime planning",
            "Emergency kit + power bundle recommendations",
            "Modular system upgrade roadmap",
        ],
        "risk_reversal": [
            "Warranty-forward framing",
            "Live support and onboarding guidance",
            "Transparent spec-based recommendation process",
        ],
        "value_stack_template": [
            "Primary product fit",
            "Runtime planning sheet",
            "Setup checklist",
            "Emergency scenario playbook",
            "Support access",
        ],
        "timestamp_utc": _utc_now(),
    }


def copy_agent(
    profile: dict[str, Any],
    audience: dict[str, Any],
    voice: dict[str, Any],
    offer: dict[str, Any],
) -> dict[str, Any]:
    fallback = {
        "agent": "copywriter_agent",
        "hero": "When the grid fails, your family should not.",
        "subhero": "Build a power plan that keeps essentials running with modular, portable backup you can trust.",
        "email_subjects": [
            "Power outage plan in 15 minutes",
            "What your backup system must handle first",
            "Stop guessing: map your runtime today",
        ],
        "social_hooks": [
            "Blackout question: what must stay on first in your home?",
            "Most people buy backup power backward. Do this first.",
            "Your emergency power plan should start with 3 devices.",
        ],
        "cta_bank": [
            "Get your free power readiness assessment",
            "See your custom runtime plan",
            "Build your outage-proof setup today",
        ],
        "ad_angles": [
            "Fear-to-control: outage anxiety to preparedness confidence",
            "Spec-to-outcome: watt-hours translated to daily peace of mind",
            "Savings-through-downtime-avoidance for home and business",
        ],
        "timestamp_utc": _utc_now(),
    }

    prompt = f"""
You are a conversion copy strategist for INF Energy Power.
Use this context:\n{json.dumps({'profile': profile, 'audience': audience, 'voice': voice, 'offer': offer})[:10000]}

Return ONLY JSON with keys:
hero, subhero, email_subjects (3), social_hooks (5), cta_bank (5), ad_angles (5).
Constraints:
- High-energy, trust-first, value-stacking voice.
- No imitation of specific living people.
- No fake claims.
"""
    ai = _ai_json(prompt)
    if ai:
        ai["agent"] = "copywriter_agent"
        ai["timestamp_utc"] = _utc_now()
        return ai
    return fallback


def creative_agent(profile: dict[str, Any], voice: dict[str, Any], copy: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": "creative_director_agent",
        "visual_system": {
            "palette": profile.get("visual_identity", {}).get("primary_colors", []),
            "typography": "bold geometric headlines + readable sans body",
            "composition": "high contrast product + scenario storytelling",
        },
        "image_prompts": [
            "Family kitchen at night during outage, home still lit by modular power station, realistic documentary style, clean blue accent lighting, confidence and calm.",
            "Portable power station on tailgate with laptop and tools at dusk, practical setup, rugged but premium, focus on reliability and portability.",
            "Split-scene before/after blackout: left dark home, right powered essentials with Infenergy setup, clear emotional relief, cinematic realism.",
        ],
        "short_video_concepts": [
            "15s: '3 things that must stay on' checklist",
            "20s: runtime myth vs reality with one product",
            "30s: outage simulation to control plan CTA",
        ],
        "timestamp_utc": _utc_now(),
    }


def channel_ops_agent(copy: dict[str, Any], creative: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": "channel_editor_agent",
        "channels": {
            "facebook": "story + practical checklist + comments question",
            "instagram": "visual-first hook + concise value bullets + CTA",
            "linkedin": "authority insight + ROI/control angle + CTA",
            "email": "one problem, one solution, one action",
        },
        "publishing_calendar": [
            "Morning: education hook",
            "Midday: proof/story",
            "Evening: urgency CTA",
        ],
        "timestamp_utc": _utc_now(),
    }


def qa_agent(bundle: dict[str, Any]) -> dict[str, Any]:
    checks = [
        "Claims tied to factual specs",
        "Single CTA per asset",
        "No hype-only language",
        "No imitation of specific living authors",
        "Message-to-segment fit",
    ]
    return {
        "agent": "conversion_qa_agent",
        "checklist": checks,
        "status": "pass",
        "timestamp_utc": _utc_now(),
    }
