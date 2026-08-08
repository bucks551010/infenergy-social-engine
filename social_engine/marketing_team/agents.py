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


def _ensure_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list) and value:
        return [str(v).strip() for v in value if str(v).strip()]
    return fallback


def _manifesto(profile: dict[str, Any]) -> dict[str, Any]:
    raw = profile.get("founder_manifesto", {})
    return raw if isinstance(raw, dict) else {}


def _ai_json(prompt: str) -> dict[str, Any] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
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
    manifesto = _manifesto(profile)
    business_profile = manifesto.get("business_profile", {}) if isinstance(manifesto.get("business_profile", {}), dict) else {}
    mission = str(manifesto.get("mission", "")).strip()
    top_categories = profile.get("top_categories", [])[:5]
    top_metrics = profile.get("top_metrics", [])[:8]
    value_tier = profile.get("demographics", {}).get("value_tier", "mid_to_premium")

    market_position = str(business_profile.get("positioning", "")).strip() or (
        "Preparedness-first portable power brand helping families and mobile users stay ready "
        "during outages, travel, and uncertain grid moments."
    )
    return {
        "agent": "market_research_agent",
        "market_position": market_position,
        "mission": mission,
        "category_dominance": top_categories,
        "spec_anchors": top_metrics,
        "value_tier": value_tier,
        "top_buyer_jobs": [
            "Keep lights, phones, and critical devices running during outages",
            "Protect family comfort and communication when the grid fails",
            "Avoid downtime for home office, travel, RV, and small business",
            "Build confidence with practical readiness planning instead of guesswork",
        ],
        "competitive_edges": [
            "Mission-led preparedness positioning with practical customer education",
            "Broad portfolio from everyday chargers to modular high-capacity systems",
            "Spec-led recommendations focused on real usage and family safety",
        ],
        "positioning_risks": [
            "Feature-heavy messaging can feel technical to first-time buyers",
            "Premium SKUs require stronger value justification and proof",
            "Crowded portable power market needs stronger trust and transformation stories",
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
    manifesto = _manifesto(profile)
    benefit_map = manifesto.get("customer_benefit_framework", {}) if isinstance(manifesto.get("customer_benefit_framework", {}), dict) else {}
    objections = profile.get("psychographics", {}).get("objections", [])
    return {
        "agent": "audience_psychology_agent",
        "segments": [
            {
                "name": "Prepared Family Protector",
                "pain": "Fear of blackout vulnerability",
                "desired_state": "Calm control and family safety during emergencies",
                "trigger": "Storm warnings and outage memories",
                "best_offer": "Free Power Readiness Assessment",
                "proof_needed": "Real outage runtime examples",
            },
            {
                "name": "Practical Energy Optimizer",
                "pain": "Rising utility instability and uncertainty",
                "desired_state": "Predictable independent power",
                "trigger": "Bill shock and grid reliability concerns",
                "best_offer": "Device-by-device runtime planning",
                "proof_needed": "Cost-of-downtime framing with spec-backed fit",
            },
            {
                "name": "Mobile Power User",
                "pain": "Power constraints while traveling or working remote",
                "desired_state": "Portable confidence anywhere",
                "trigger": "Trips, jobsites, and device-heavy days",
                "best_offer": "Portable + solar kit recommendations",
                "proof_needed": "Portability and recharge scenario demos",
            },
        ],
        "core_objections": objections,
        "benefit_map": benefit_map,
        "objection_reframes": {
            "Is this enough power for my needs?": "Map critical loads first, then match specs to those loads.",
            "Will it actually work in a real outage?": "Show outage simulations and runtime case snapshots.",
            "Is it worth the cost?": "Compare one-time investment to repeated downtime losses.",
            "Will setup be difficult?": "Provide setup checklist and onboarding support message.",
        },
        "message_priorities": [
            "Clarity before capacity",
            "Outcome before feature",
            "Safety and control before savings claims",
        ],
        "timestamp_utc": _utc_now(),
    }


def voice_agent(profile: dict[str, Any]) -> dict[str, Any]:
    manifesto = _manifesto(profile)
    personality = manifesto.get("brand_personality", {}) if isinstance(manifesto.get("brand_personality", {}), dict) else {}
    values = _ensure_list(manifesto.get("core_values", []), ["integrity", "commitment", "service"])
    claims = profile.get("site_claim_snippets", [])[:5]
    return {
        "agent": "brand_voice_agent",
        "voice_name": str(personality.get("voice_name", "Resilient Momentum")).strip() or "Resilient Momentum",
        "voice_rules": [
            "Lead with empathy and urgency rooted in real family preparedness moments.",
            "Translate specs into immediate and long-term outcomes people can feel.",
            "Use value stacking, practical guidance, and one clear next step.",
            "Sound committed and human: protective, coach-like, and trustworthy.",
            "Anchor every claim in concrete facts and examples.",
        ],
        "voice_ladders": {
            "hook": "counterintuitive truth or outage risk moment",
            "proof": "specific specs, scenarios, or quantified comparisons",
            "resolution": "clear recommendation with one frictionless CTA",
        },
        "style_markers": {
            "energy": "high",
            "cadence": "short-to-medium punchy lines",
            "authority": "advisor, not hype machine",
            "cta": "single clear action per asset",
        },
        "allowed_power_words": [
            "ready",
            "resilient",
            "protected",
            "practical",
            "reliable",
            "clear",
            "control",
            "confidence",
            "prepared",
            "secure",
            "lifeline",
        ],
        "do_not": [
            "Do not copy or mimic specific living public figures.",
            "Do not use unverifiable guarantees.",
            "Do not overuse jargon.",
        ],
        "grounding_claims": claims,
        "brand_values": values,
        "timestamp_utc": _utc_now(),
    }


def offer_agent(profile: dict[str, Any], audience: dict[str, Any]) -> dict[str, Any]:
    manifesto = _manifesto(profile)
    value_stack = _ensure_list(
        manifesto.get("value_stack", []),
        [
            "Preparedness confidence",
            "Protection during outages",
            "Portable freedom and control",
            "Clear product-fit guidance",
        ],
    )
    categories = profile.get("top_categories", [])[:4]
    return {
        "agent": "offer_strategy_agent",
        "core_offers": [
            "Free Power Readiness Assessment",
            "Device-by-device runtime planning",
            "Emergency kit + right-sized power recommendations",
            "Modular system upgrade roadmap",
        ],
        "entry_points": [
            "Checklist lead magnet",
            "Runtime calculator walkthrough",
            "Storm season readiness consult",
        ],
        "package_architecture": {
            "starter_path": "Portable essentials setup",
            "expanded_path": "Home continuity setup",
            "resilience_path": "Modular solar-resilience stack",
            "anchor_categories": categories,
        },
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
        "customer_value_stack": value_stack,
        "timestamp_utc": _utc_now(),
    }


def copy_agent(
    profile: dict[str, Any],
    audience: dict[str, Any],
    voice: dict[str, Any],
    offer: dict[str, Any],
) -> dict[str, Any]:
    manifesto = _manifesto(profile)
    story = manifesto.get("origin_story", {}) if isinstance(manifesto.get("origin_story", {}), dict) else {}
    sales_verbiage = manifesto.get("approved_sales_verbiage", {}) if isinstance(manifesto.get("approved_sales_verbiage", {}), dict) else {}
    hero_line = str(sales_verbiage.get("hero_line", "")).strip() or "When the grid fails, your family should not."
    trust_close = str(sales_verbiage.get("trust_close", "")).strip() or "When the lights go out, choose a plan that keeps people calm, connected, and prepared."
    fallback = {
        "agent": "copywriter_agent",
        "hero": hero_line,
        "subhero": "Build a preparedness-first power plan that protects your family now and gives long-term resilience you can trust.",
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
            "Map your must-run devices and build your outage-ready setup",
            "Build your outage-proof setup today",
        ],
        "ad_angles": [
            "Fear-to-control: outage anxiety to preparedness confidence",
            "Spec-to-outcome: watt-hours translated to daily peace of mind",
            "Savings-through-downtime-avoidance for home and business",
        ],
        "objection_handlers": [
            "We size power around your real load map, not generic estimates.",
            "Every recommendation is grounded in published specs and use-case fit.",
            "Setup starts simple with a clear onboarding checklist.",
        ],
        "landing_blocks": {
            "problem": str(story.get("problem", "Outages expose homes and businesses that rely on assumptions.")).strip(),
            "solution": "A clear, spec-led preparedness plan keeps essentials powered with less guesswork.",
            "proof": "Use measurable runtime and output specs matched to your critical loads and family priorities.",
            "cta": "Get your free power readiness assessment",
        },
        "value_narrative": {
            "immediate_value": "Clarity and confidence on what to power first and what to buy now.",
            "short_term_value": "Better outage readiness, less panic, and fewer wrong purchases.",
            "long_term_value": "A scalable resilience lifestyle with lower downtime risk.",
            "family_impact": "Safety, connection, and comfort when emergencies hit.",
            "lifestyle_shift": "From reactive panic to proactive preparedness.",
            "trust_close": trust_close,
        },
        "timestamp_utc": _utc_now(),
    }

    prompt = f"""
You are a conversion copy strategist for INF Energy Power.
Use this context:\n{json.dumps({'profile': profile, 'audience': audience, 'voice': voice, 'offer': offer})[:10000]}

Return ONLY JSON with keys:
hero, subhero, email_subjects (3), social_hooks (5), cta_bank (5), ad_angles (5), objection_handlers (3), landing_blocks, value_narrative.
Constraints:
- High-energy, trust-first, value-stacking voice.
- No imitation of specific living people.
- No fake claims.
- Emphasize immediate value, short-term gains, long-term transformation, and family impact.
"""
    ai = _ai_json(prompt)
    if ai:
        ai["agent"] = "copywriter_agent"
        ai["timestamp_utc"] = _utc_now()
        return ai
    return fallback


def creative_agent(profile: dict[str, Any], voice: dict[str, Any], copy: dict[str, Any]) -> dict[str, Any]:
    palette = profile.get("visual_identity", {}).get("primary_colors", ["#2563eb", "#1e3a8a", "#f8fafc"])
    return {
        "agent": "creative_director_agent",
        "visual_system": {
            "palette": palette,
            "typography": "bold geometric headlines + readable sans body",
            "composition": "high contrast product + scenario storytelling",
            "iconography": "simple line icons, energy flow arrows, runtime badges",
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
        "ad_creative_recipes": [
            "Hook frame -> problem setup -> measurable spec proof -> single CTA",
            "Before/after outage scenario -> modular setup reveal -> confidence CTA",
            "Device stack visual -> runtime estimate card -> consultation CTA",
        ],
        "timestamp_utc": _utc_now(),
    }


def channel_ops_agent(copy: dict[str, Any], creative: dict[str, Any]) -> dict[str, Any]:
    hooks = _ensure_list(copy.get("social_hooks"), ["What device cannot go down in your home?"])
    ctas = _ensure_list(copy.get("cta_bank"), ["Get your free power readiness assessment"])
    return {
        "agent": "channel_editor_agent",
        "channels": {
            "facebook": {
                "framework": "story + practical checklist + comments question",
                "asset_mix": ["carousel", "single-image proof", "customer Q&A post"],
            },
            "instagram": {
                "framework": "visual-first hook + concise value bullets + CTA",
                "asset_mix": ["reel", "story sequence", "spec explainer carousel"],
            },
            "linkedin": {
                "framework": "authority insight + ROI/control angle + CTA",
                "asset_mix": ["thought-leadership post", "case style post", "myth-busting post"],
            },
            "email": {
                "framework": "one problem, one solution, one action",
                "asset_mix": ["education email", "proof email", "offer email"],
            },
        },
        "message_matrix": {
            "hooks": hooks[:5],
            "ctas": ctas[:5],
            "repurposing": [
                "LinkedIn long-form -> Facebook story thread",
                "Instagram reel script -> email opener",
                "FAQ comment -> myth-busting post",
            ],
        },
        "publishing_calendar": [
            "Morning: education hook",
            "Midday: proof/story",
            "Evening: urgency CTA",
        ],
        "timestamp_utc": _utc_now(),
    }


def seo_agent(profile: dict[str, Any], copy: dict[str, Any]) -> dict[str, Any]:
    categories = profile.get("top_categories", [])[:6]
    hooks = _ensure_list(copy.get("social_hooks"), ["Outage readiness checklist"])
    return {
        "agent": "seo_content_agent",
        "pillar_clusters": [
            {
                "pillar": "Outage Preparedness",
                "topics": [
                    "critical load planning",
                    "home outage checklists",
                    "portable vs whole-home backup",
                ],
            },
            {
                "pillar": "Portable Power Lifestyle",
                "topics": [
                    "portable generator vs power station",
                    "everyday carry and travel power",
                    "family preparedness routines",
                ],
            },
        ],
        "priority_keywords": categories,
        "meta_framework": {
            "title": "Problem + measurable outcome + trust signal",
            "description": "One concrete pain, one practical solution, one CTA",
        },
        "internal_link_targets": hooks[:4],
        "timestamp_utc": _utc_now(),
    }


def lifecycle_email_agent(copy: dict[str, Any], audience: dict[str, Any]) -> dict[str, Any]:
    segments = audience.get("segments", [])
    subject_pool = _ensure_list(copy.get("email_subjects"), ["Power outage plan in 15 minutes"])
    ctas = _ensure_list(copy.get("cta_bank"), ["Get your free power readiness assessment"])
    return {
        "agent": "lifecycle_email_agent",
        "flows": {
            "new_lead": [
                "Email 1: pain agitation + checklist",
                "Email 2: product fit education",
                "Email 3: consultation CTA",
            ],
            "nurture": [
                "myth busting",
                "runtime education",
                "seasonal urgency",
            ],
            "reactivation": [
                "what changed in your power risk profile",
                "new product and bundle updates",
                "limited consult slots CTA",
            ],
        },
        "subject_pool": subject_pool[:5],
        "segment_personalization": [s.get("name", "Prepared Buyer") for s in segments][:4],
        "primary_cta": ctas[0],
        "timestamp_utc": _utc_now(),
    }


def experimentation_agent(bundle: dict[str, Any]) -> dict[str, Any]:
    hooks = _ensure_list(bundle.get("copy", {}).get("social_hooks"), ["What must stay on first?"])
    ctas = _ensure_list(bundle.get("copy", {}).get("cta_bank"), ["Get your free power readiness assessment"])
    return {
        "agent": "growth_experimentation_agent",
        "north_star": "consultation bookings from qualified preparedness buyers",
        "experiments": [
            {
                "name": "Hook framing test",
                "hypothesis": "Question-led hooks increase comments and CTR over statement-led hooks.",
                "variants": hooks[:3],
                "success_metric": "CTR + qualified comments",
            },
            {
                "name": "CTA specificity test",
                "hypothesis": "Specific next-step CTAs outperform generic contact CTAs.",
                "variants": ctas[:3],
                "success_metric": "landing conversion rate",
            },
            {
                "name": "Proof format test",
                "hypothesis": "Spec card visuals increase trust and saves over plain text posts.",
                "variants": ["spec card", "story-only", "before/after grid"],
                "success_metric": "save rate + profile visits",
            },
        ],
        "cadence": "Review weekly, prune bottom quartile, scale winners for 2 weeks.",
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
    copy = bundle.get("copy", {})
    hero = str(copy.get("hero", "")).strip()
    cta_bank = copy.get("cta_bank", []) if isinstance(copy.get("cta_bank"), list) else []
    hooks = copy.get("social_hooks", []) if isinstance(copy.get("social_hooks"), list) else []

    score = 0
    if hero:
        score += 20
    if len(cta_bank) >= 3:
        score += 20
    if len(hooks) >= 3:
        score += 20
    if bundle.get("brand_profile", {}).get("product_count", 0) > 0:
        score += 20
    if bundle.get("creative", {}).get("image_prompts"):
        score += 20

    status = "pass" if score >= 80 else "needs-improvement"
    return {
        "agent": "conversion_qa_agent",
        "checklist": checks,
        "score": score,
        "status": status,
        "next_fixes": [] if status == "pass" else [
            "Expand CTA bank to at least 3 options",
            "Increase hook variety and objection handling",
            "Strengthen proof blocks with explicit metrics",
        ],
        "timestamp_utc": _utc_now(),
    }
