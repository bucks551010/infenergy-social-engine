import os
import json
import random
import hashlib
import csv
import glob
import re
import uuid
from datetime import date, datetime, timezone, timedelta
from google import genai
from google.genai import types
try:
    import inventory_db
except ImportError:  # pragma: no cover
    from scripts import inventory_db
from campaign_runtime import (
    apply_claim_guardrails,
    choose_cta_for_stage,
    cta_is_valid_for_stage,
    ensure_campaign_runtime_files,
    load_cta_library,
    load_funnel_config,
    score_generated_content,
    select_weekly_sequence,
    stable_text_hash,
    stage_for_slot,
)
from generate_hooks import select_hook
from anti_repeat import load_anti_repeat_windows
from build_utm_url import build_utm_url
from social_visuals import generate_visuals, normalize_brand_content, normalize_brand_text
from agent_control_plane import (
    SCHEMAS_VERSION,
    build_gate_record,
    build_run_context,
    evaluate_global_gates,
    validate_agent_output,
)

FUNNEL_STAGES = {"ATTENTION", "EDUCATION", "DESIRE", "TRUST", "CONVERSION"}

SITE_URL = os.environ.get("WP_URL", "https://www.infenergypower.com")
# DATA_DIR can be overridden by Railway volume mount (set DATA_DIR=/app/data in Railway Variables)
BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DATA_DIR = os.environ.get("DATA_DIR", BASE_DATA_DIR)

DEFAULT_TOPIC_QUEUE = {
    "pillars": [
        "portable_power_readiness",
        "emergency_preparedness",
        "outdoor_rv_power",
        "product_education",
        "promotions",
    ],
    "topics": {
        "portable_power_readiness": [
            "How to choose a portable power station for your daily must-run devices",
            "Battery capacity basics: what can 1kWh actually power?",
            "How to avoid buying a power station that is too small for real use",
        ],
        "emergency_preparedness": [
            "How to build a 24-hour outage plan with portable backup power",
            "The most common outage-prep mistakes and how to avoid them",
            "What to power first during outages: a practical priority list",
        ],
        "outdoor_rv_power": [
            "Portable power setups for camping and RV weekends",
            "How to match solar panel wattage to your portable generator",
            "Travel power checklist: charging phones, laptops, and essentials off-grid",
        ],
        "product_education": [
            "Portable generator vs power station: what actually matters",
            "Inverter and output basics for non-technical buyers",
            "How to compare recharge speed, output, and portability before buying",
        ],
        "promotions": [
            "Book a free portable-power readiness assessment",
            "How to get a product match in under 15 minutes",
            "What to expect from your first product-fit consultation",
        ],
    },
}

DEFAULT_STAGE_PAIN_POINTS = {
    "ATTENTION": "Most buyers realize too late that their backup plan does not match real device usage.",
    "EDUCATION": "People compare battery products by headline numbers and miss the specs that actually determine reliability.",
    "DESIRE": "Families want confidence during outages but hesitate because options look similar and confusing.",
    "TRUST": "Buyers worry about making an expensive mistake and need transparent, verifiable guidance.",
    "CONVERSION": "People postpone decisions until the next outage because the first step feels unclear.",
}

DEFAULT_STAGE_PAIN_POINT_VARIANTS = {
    "ATTENTION": [
        "Most buyers realize too late that their backup plan does not match real device usage.",
        "People often discover during the first outage that their backup setup cannot run what matters most.",
        "The expensive mistake is buying backup power before mapping real device priorities.",
    ],
    "EDUCATION": [
        "People compare battery products by headline numbers and miss the specs that actually determine reliability.",
        "Most shoppers focus on capacity labels and skip output and recharge details that decide real-world performance.",
        "A lot of buyers pick the wrong unit because they do not compare wattage, runtime, and recharge together.",
    ],
    "DESIRE": [
        "Families want confidence during outages but hesitate because options look similar and confusing.",
        "Buyers want peace of mind, but uncertainty about fit keeps them stuck in research mode.",
        "People want reliable backup power without overpaying for features they will not use.",
    ],
    "TRUST": [
        "Buyers worry about making an expensive mistake and need transparent, verifiable guidance.",
        "Trust breaks when specs are vague, so buyers need clear facts tied to real use cases.",
        "Most customers do not need hype, they need a product-fit recommendation backed by measurable details.",
    ],
    "CONVERSION": [
        "People postpone decisions until the next outage because the first step feels unclear.",
        "Many ready-to-buy customers delay because no one translates specs into a simple purchase decision.",
        "When next steps are vague, even motivated buyers wait instead of acting.",
    ],
}

POSITIONING_REPLACEMENTS = {
    "rooftop solar installation": "portable backup power setup",
    "residential solar installation": "portable backup power planning",
    "home solar installation": "portable power setup",
    "solar installation": "portable power setup",
    "rooftop solar": "portable solar panel",
    "net metering": "portable runtime planning",
    "home energy audit": "power readiness assessment",
    "solar tax credits": "equipment value and readiness planning",
}

DEFAULT_CATEGORY_IMAGE_FALLBACKS = {
    "portable power": "https://infenergypower.com/wp-content/uploads/2024/11/IMG_4214.png",
    "travel power": "https://infenergypower.com/wp-content/uploads/2024/12/IMG_4806.jpg",
    "solar generators": "https://infenergypower.com/wp-content/uploads/2024/08/1.png",
    "solar panels": "https://infenergypower.com/wp-content/uploads/2025/08/AF-S400A1-1.jpg",
    "home backup": "https://infenergypower.com/wp-content/uploads/2025/06/a0fc14752770c414bd090fa2f986454-scaled.png",
    "emergency power": "https://infenergypower.com/wp-content/uploads/2022/05/1642710505878.png",
}

CONVERSION_COPY_BRIEF = """
You are the conversion copywriter for Infenergy Power.

Objective:
- Stop the scroll.
- Make the reader recognize a real situation.
- Educate before selling.
- Connect the product as a logical solution.
- Use only verified product facts.
- Build trust and reduce hesitation.
- End with one clear next action.

Writing requirements:
- Focus on one primary angle and one specific customer moment.
- Use this sequence: Attention -> Problem/Desire -> Consequence -> Education -> Product fit -> Verified proof -> Objection reduction -> CTA.
- Do not invent runtime, appliance compatibility, savings, certifications, durability, warranty, or unsupported specs.
- Avoid generic ad language and banned cliches (for example: game changer, revolutionary, unlock the power of, don't miss out).
- Keep platform-native tone:
    - Facebook: conversational, educational, community trust.
    - Instagram: short high-impact first line, visual relevance, readable line breaks.
    - LinkedIn: authority and business continuity perspective, professional credibility.

Brand:
- Use Infenergy naming and trustworthy practical tone.
- The business is primarily portable power, emergency readiness, and outdoor/off-grid power products.
- Do not position the brand as a residential rooftop solar installer.
- Solar can be referenced only as portable/foldable solar panels paired with portable generators or power stations.
""".strip()

VISUAL_DIRECTOR_BRIEF = """
You are the visual prompt director for Infenergy Power social creatives.

Goal:
- Produce visual direction that increases click-through and trust.
- Ensure image concept supports the copy angle, funnel stage, and CTA.
- Decide when to feature product photos versus concept visuals.

Rules:
- Keep visuals premium, realistic, and brand-safe.
- Prefer practical scenarios (home backup, preparedness, energy confidence) over abstract art.
- If product image quality is strong, suggest a hybrid composition that highlights the product naturally.
- Never include text baked into the image unless it is short and legible.
- Return only the requested JSON shape.
""".strip()

AGENT_CONFERENCE_BRIEF = """
You are facilitating a conference room discussion between specialized creative agents for Infenergy Power.

Participants:
- Copywriter Agent: maximizes clarity, persuasion, and conversion.
- Visual Director Agent: ensures image concept and composition amplify the message.
- Product Truth Agent: blocks unsupported claims and keeps facts verifiable.
- Platform Editor Agent: adapts execution for Facebook, Instagram, and LinkedIn behavior.

Task:
- Have the agents debate strengths, weaknesses, and risks in the current draft.
- Produce a unified plan to improve collective performance.
- Keep recommendations practical and directly applicable in this run.

Constraints:
- No invented product specs, warranties, or guarantees.
- Keep tone trustworthy and practical.
- Prefer specific improvements over generic feedback.
""".strip()

PREGEN_CONFERENCE_BRIEF = """
You are facilitating a pre-generation conference room meeting for Infenergy Power before any draft is written.

Participants:
- Copywriter Agent
- Visual Director Agent
- Product Truth Agent
- Platform Editor Agent

Objective:
- Decide the single best post direction for this run before writing starts.
- Agree on the strongest hook angle, CTA framing, and visual focus.
- Reduce duplication risk by choosing a fresh direction versus recent posts.

Constraints:
- Use only supported product facts.
- Keep recommendations practical, specific, and conversion-oriented.
- Return only JSON in the requested shape.
""".strip()

IDEATION_DIVERGENCE_BRIEF = """
You are the Ideation Divergence Agent.

Goal:
- Produce fresh, genuinely distinct creative angles for this run.
- Avoid repeating recent hooks and topics.
- Return only JSON in the requested shape.
""".strip()

AUDIENCE_PSYCHOGRAPHICS_BRIEF = """
You are the Audience Psychographics Agent.

Goal:
- Translate the chosen angle into emotional drivers, objections, trust triggers, and CTA framing.
- Keep language practical and directly actionable for copy generation.
- Return only JSON in the requested shape.
""".strip()

NARRATIVE_ARCHITECT_BRIEF = """
You are the Narrative Architect Agent.

Goal:
- Define the narrative sequence and mandatory proof elements.
- Keep structure conversion-oriented and platform-ready.
- Return only JSON in the requested shape.
""".strip()

PLATFORM_VOICE_CALIBRATOR_BRIEF = """
You are the Platform Voice Calibrator Agent.

Goal:
- Provide platform-native voice directives for Facebook, Instagram, and LinkedIn.
- Keep each directive concise, practical, and distinct.
- Return only JSON in the requested shape.
""".strip()

HOOK_STRESS_TEST_BRIEF = """
You are the Hook Stress-Test Agent.

Goal:
- Evaluate candidate hooks for clarity, specificity, credibility, and curiosity.
- Select one best hook for this run.
- Return only JSON in the requested shape.
""".strip()

PRECISION_CLAIMS_VERIFIER_BRIEF = """
You are the Precision Claims Verifier Agent.

Goal:
- Validate claim precision and factual grounding.
- Flag unsupported, absolute, or unverifiable statements.
- Return only JSON in the requested shape.
""".strip()

COMPLIANCE_POLICY_SENTINEL_BRIEF = """
You are the Compliance and Policy Sentinel Agent.

Goal:
- Detect compliance and policy risk in social copy.
- Assign a risk level and required remediation actions.
- Return only JSON in the requested shape.
""".strip()

SEMANTIC_NOVELTY_BRIEF = """
You are the Semantic Novelty Agent.

Goal:
- Evaluate novelty versus recent posts.
- Provide rewrite guidance if the concept is too similar.
- Return only JSON in the requested shape.
""".strip()

VISUAL_STRATEGY_BRIEF = """
You are the Visual Strategy Agent.

Goal:
- Improve visual intent, composition, and per-platform emphasis.
- Keep recommendations practical for immediate generation.
- Return only JSON in the requested shape.
""".strip()

CTA_OPTIMIZATION_BRIEF = """
You are the CTA Optimization Agent.

Goal:
- Optimize CTA wording for funnel stage and audience friction.
- Provide one recommended CTA plus alternates.
- Return only JSON in the requested shape.
""".strip()


def _default_phase2_stack(
    *,
    selected_hook: str,
    selected_cta: str,
    audience_segment: str,
    topic: str,
    funnel_stage: str,
) -> dict:
    return {
        "ideation_divergence": {
            "concepts": [
                {
                    "angle": f"Practical decision framework for {topic.lower()}",
                    "hook_candidate": selected_hook,
                    "narrative_focus": "problem to practical framework to clear next step",
                    "risk_note": "avoid unsupported performance guarantees",
                }
            ],
            "winner_angle": f"Practical decision framework for {topic.lower()}",
            "winner_hook": selected_hook,
            "novelty_rationale": "Chosen for practical specificity and low repetition risk.",
        },
        "audience_psychographics": {
            "primary_segment": audience_segment,
            "emotional_driver": "confidence in making a smart and safe power decision",
            "core_objection": "fear of buying the wrong system for real-world usage",
            "trust_trigger": "specific verifiable specs tied to everyday use",
            "cta_framing": selected_cta,
        },
        "narrative_architect": {
            "narrative_sequence": ["attention", "pain", "education", "product_fit", "proof", "cta"],
            "must_include": [
                "one practical scenario",
                "at least one verifiable metric",
                "one objection handling line",
            ],
            "proof_style": "specific and verifiable without overclaiming",
            "close_style": "single direct call to action",
        },
        "platform_voice_calibrator": {
            "facebook": "conversational community educator with practical examples",
            "instagram": "short visual-first lines with concrete benefit and urgency",
            "linkedin": "professional advisory tone with clear framework and business relevance",
        },
        "hook_stress_test": {
            "candidate_hooks": [selected_hook],
            "recommended_hook": selected_hook,
            "reason": f"Best fit for {funnel_stage.lower()} stage clarity and credibility.",
        },
    }


def _run_phase2_creative_stack(
    model_candidates: list[str],
    *,
    topic: str,
    funnel_stage: str,
    stage_objective: str,
    selected_hook: str,
    selected_cta: str,
    audience_segment: str,
    product_name: str,
    product_categories: str,
    product_metrics: str,
    recent_hooks: list[str],
    recent_topics: list[str],
) -> dict:
    stack = _default_phase2_stack(
        selected_hook=selected_hook,
        selected_cta=selected_cta,
        audience_segment=audience_segment,
        topic=topic,
        funnel_stage=funnel_stage,
    )

    ideation_prompt = f"""{IDEATION_DIVERGENCE_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Stage objective: {stage_objective}
- Audience segment: {audience_segment}
- Product: {product_name or 'N/A'}
- Product categories: {product_categories or 'N/A'}
- Product measurable specs: {product_metrics or 'N/A'}
- Current hook candidate: {selected_hook}
- Recent hooks to avoid: {recent_hooks}
- Recent topics to avoid: {recent_topics}

Return ONLY valid JSON with this exact shape:
{{
  "concepts": [
    {{"angle": "string", "hook_candidate": "string", "narrative_focus": "string", "risk_note": "string"}},
    {{"angle": "string", "hook_candidate": "string", "narrative_focus": "string", "risk_note": "string"}}
  ],
  "winner_angle": "string",
  "winner_hook": "string",
  "novelty_rationale": "string"
}}"""
    ideation = _generate_json_with_gemini(ideation_prompt, model_candidates)
    if isinstance(ideation, dict):
        stack["ideation_divergence"] = ideation

    winner_angle = str(stack["ideation_divergence"].get("winner_angle", "")).strip() or topic
    winner_hook = str(stack["ideation_divergence"].get("winner_hook", "")).strip() or selected_hook

    psychographics_prompt = f"""{AUDIENCE_PSYCHOGRAPHICS_BRIEF}

Run context:
- Topic: {topic}
- Chosen angle: {winner_angle}
- Chosen hook: {winner_hook}
- Funnel stage: {funnel_stage}
- Audience segment: {audience_segment}

Return ONLY valid JSON with this exact shape:
{{
  "primary_segment": "string",
  "emotional_driver": "string",
  "core_objection": "string",
  "trust_trigger": "string",
  "cta_framing": "string"
}}"""
    psychographics = _generate_json_with_gemini(psychographics_prompt, model_candidates)
    if isinstance(psychographics, dict):
        stack["audience_psychographics"] = psychographics

    narrative_prompt = f"""{NARRATIVE_ARCHITECT_BRIEF}

Run context:
- Topic: {topic}
- Chosen angle: {winner_angle}
- Hook: {winner_hook}
- Funnel stage: {funnel_stage}
- Stage objective: {stage_objective}
- CTA direction: {selected_cta}

Return ONLY valid JSON with this exact shape:
{{
  "narrative_sequence": ["string", "string", "string"],
  "must_include": ["string", "string"],
  "proof_style": "string",
  "close_style": "string"
}}"""
    narrative = _generate_json_with_gemini(narrative_prompt, model_candidates)
    if isinstance(narrative, dict):
        stack["narrative_architect"] = narrative

    voice_prompt = f"""{PLATFORM_VOICE_CALIBRATOR_BRIEF}

Run context:
- Topic: {topic}
- Chosen angle: {winner_angle}
- Hook: {winner_hook}
- Funnel stage: {funnel_stage}

Return ONLY valid JSON with this exact shape:
{{
  "facebook": "string",
  "instagram": "string",
  "linkedin": "string"
}}"""
    voice = _generate_json_with_gemini(voice_prompt, model_candidates)
    if isinstance(voice, dict):
        stack["platform_voice_calibrator"] = voice

    hook_candidates = [winner_hook, selected_hook] + [
        str(row.get("hook_candidate", "")).strip()
        for row in stack.get("ideation_divergence", {}).get("concepts", [])
        if isinstance(row, dict)
    ]
    hook_candidates = [h for h in hook_candidates if h]
    unique_hook_candidates: list[str] = []
    seen = set()
    for hook in hook_candidates:
        k = hook.lower().strip()
        if not k or k in seen:
            continue
        seen.add(k)
        unique_hook_candidates.append(hook)

    hook_test_prompt = f"""{HOOK_STRESS_TEST_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Candidate hooks: {unique_hook_candidates[:6]}

Return ONLY valid JSON with this exact shape:
{{
  "candidate_hooks": ["string", "string"],
  "recommended_hook": "string",
  "reason": "string"
}}"""
    hook_test = _generate_json_with_gemini(hook_test_prompt, model_candidates)
    if isinstance(hook_test, dict):
        stack["hook_stress_test"] = hook_test

    return stack


def _default_phase3_safety_stack(*, selected_hook: str, selected_cta: str, recent_topics: list[str]) -> dict:
    novelty_signal = "high" if selected_hook not in recent_topics else "medium"
    novelty_score = 0.82 if novelty_signal == "high" else 0.66
    return {
        "precision_claims_verifier": {
            "passed": True,
            "issues": [],
            "required_fixes": [],
        },
        "compliance_policy_sentinel": {
            "risk_level": "low",
            "blocked_terms": [],
            "required_actions": [],
        },
        "semantic_novelty": {
            "novelty_score": novelty_score,
            "signal": novelty_signal,
            "rewrite_guidance": [] if novelty_signal == "high" else ["Use a less familiar opening scenario."],
        },
    }


def _run_phase3_safety_stack(
    model_candidates: list[str],
    *,
    topic: str,
    funnel_stage: str,
    selected_hook: str,
    selected_cta: str,
    recent_hooks: list[str],
    recent_topics: list[str],
    content_preview: str,
) -> dict:
    stack = _default_phase3_safety_stack(
        selected_hook=selected_hook,
        selected_cta=selected_cta,
        recent_topics=recent_topics,
    )

    precision_prompt = f"""{PRECISION_CLAIMS_VERIFIER_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Hook: {selected_hook}
- CTA: {selected_cta}

Draft preview:
{content_preview}

Return ONLY valid JSON with this exact shape:
{{
  "passed": true,
  "issues": ["string"],
  "required_fixes": ["string"]
}}"""
    precision = _generate_json_with_gemini(precision_prompt, model_candidates)
    if isinstance(precision, dict):
        stack["precision_claims_verifier"] = precision

    compliance_prompt = f"""{COMPLIANCE_POLICY_SENTINEL_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Hook: {selected_hook}
- CTA: {selected_cta}

Draft preview:
{content_preview}

Return ONLY valid JSON with this exact shape:
{{
  "risk_level": "low",
  "blocked_terms": ["string"],
  "required_actions": ["string"]
}}"""
    compliance = _generate_json_with_gemini(compliance_prompt, model_candidates)
    if isinstance(compliance, dict):
        stack["compliance_policy_sentinel"] = compliance

    novelty_prompt = f"""{SEMANTIC_NOVELTY_BRIEF}

Run context:
- Topic: {topic}
- Hook: {selected_hook}
- Recent hooks: {recent_hooks}
- Recent topics: {recent_topics}

Return ONLY valid JSON with this exact shape:
{{
  "novelty_score": 0.75,
  "signal": "high|medium|low",
  "rewrite_guidance": ["string"]
}}"""
    novelty = _generate_json_with_gemini(novelty_prompt, model_candidates)
    if isinstance(novelty, dict):
        stack["semantic_novelty"] = novelty

    return stack


def _default_phase4_optimization_stack(*, selected_cta: str, funnel_stage: str) -> dict:
    return {
        "visual_strategy": {
            "visual_objective": f"Reinforce {funnel_stage.lower()} intent with practical context.",
            "composition_adjustments": [
                "Show one concrete real-world use case.",
                "Keep product visibility natural and not over-styled.",
            ],
            "platform_focus": {
                "facebook": "education-first composition with readable focal hierarchy",
                "instagram": "high-contrast focal point and depth",
                "linkedin": "clean credibility composition",
            },
        },
        "cta_optimization": {
            "recommended_cta": selected_cta,
            "alternates": [
                "Get a practical system match for your setup.",
                "Compare options based on your real daily loads.",
            ],
            "friction_note": "Reduce effort language and specify the first step.",
        },
    }


def _run_phase4_optimization_stack(
    model_candidates: list[str],
    *,
    topic: str,
    funnel_stage: str,
    selected_hook: str,
    selected_cta: str,
    audience_segment: str,
) -> dict:
    stack = _default_phase4_optimization_stack(
        selected_cta=selected_cta,
        funnel_stage=funnel_stage,
    )

    visual_prompt = f"""{VISUAL_STRATEGY_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Hook: {selected_hook}
- Audience: {audience_segment}

Return ONLY valid JSON with this exact shape:
{{
  "visual_objective": "string",
  "composition_adjustments": ["string", "string"],
  "platform_focus": {{
    "facebook": "string",
    "instagram": "string",
    "linkedin": "string"
  }}
}}"""
    visual = _generate_json_with_gemini(visual_prompt, model_candidates)
    if isinstance(visual, dict):
        stack["visual_strategy"] = visual

    cta_prompt = f"""{CTA_OPTIMIZATION_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Hook: {selected_hook}
- Current CTA: {selected_cta}
- Audience: {audience_segment}

Return ONLY valid JSON with this exact shape:
{{
  "recommended_cta": "string",
  "alternates": ["string", "string"],
  "friction_note": "string"
}}"""
    cta = _generate_json_with_gemini(cta_prompt, model_candidates)
    if isinstance(cta, dict):
        stack["cta_optimization"] = cta

    return stack


def _build_phase7_conference_packets(
    *,
    run_context: dict,
    pre_generation_conference: dict,
    phase2_stack: dict,
    phase3_stack: dict,
    phase4_stack: dict,
    conference_summary: dict,
) -> dict:
    return {
        "pre_generation_packet": {
            "topic": run_context.get("topic", ""),
            "funnel_stage": run_context.get("funnel_stage", ""),
            "hook_direction": run_context.get("draft_direction", {}).get("selected_hook", ""),
            "cta_direction": run_context.get("draft_direction", {}).get("selected_cta", ""),
            "inputs": {
                "pre_generation_conference": pre_generation_conference,
                "phase2": phase2_stack,
            },
        },
        "pre_publish_packet": {
            "safety": phase3_stack,
            "optimization": phase4_stack,
            "conference_refinement": conference_summary,
        },
        "post_run_packet": {
            "expected_next_actions": [
                "record outcomes",
                "compare channel-level performance",
                "feed lessons into next prompt context",
            ],
            "trace": {
                "schema_version": SCHEMAS_VERSION,
                "phase2_keys": sorted(list((phase2_stack or {}).keys())),
                "phase3_keys": sorted(list((phase3_stack or {}).keys())),
                "phase4_keys": sorted(list((phase4_stack or {}).keys())),
            },
        },
    }


def _conversion_caption_gate(platform_posts: dict, talking_point: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    pain = str((talking_point or {}).get("pain_point", "")).strip().lower()
    first_step = str((talking_point or {}).get("first_step", "")).strip().lower()
    for platform_name in ("facebook", "instagram", "linkedin"):
        row = platform_posts.get(platform_name, {}) if isinstance(platform_posts, dict) else {}
        caption = str(row.get("caption", "") if isinstance(row, dict) else "")
        if not caption.strip():
            reasons.append(f"{platform_name}:missing_caption")
            continue
        low = caption.lower()
        if pain and pain not in low:
            reasons.append(f"{platform_name}:missing_pain_point")
        if first_step and first_step not in low:
            reasons.append(f"{platform_name}:missing_next_step")
        if not _contains_numeric_evidence(caption):
            reasons.append(f"{platform_name}:missing_numeric_evidence")
        for bad in POSITIONING_REPLACEMENTS.keys():
            if bad in low:
                reasons.append(f"{platform_name}:off_brand_phrase:{bad}")
    return len(reasons) == 0, reasons


def ensure_runtime_data() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    ensure_campaign_runtime_files()

    topic_primary = os.path.join(DATA_DIR, "topic_queue.json")
    topic_fallback = os.path.join(BASE_DATA_DIR, "topic_queue.json")
    if not os.path.exists(topic_primary) and not os.path.exists(topic_fallback):
        with open(topic_primary, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_TOPIC_QUEUE, f, indent=2)

    history_primary = os.path.join(DATA_DIR, "post_history.json")
    history_fallback = os.path.join(BASE_DATA_DIR, "post_history.json")
    if not os.path.exists(history_primary) and not os.path.exists(history_fallback):
        with open(history_primary, "w", encoding="utf-8") as f:
            json.dump({"posts": []}, f, indent=2)

    try:
        sync_inventory_database(force=False)
    except Exception as e:
        print(f"[WARN] inventory database sync skipped: {e}")


def _read_json_with_fallback(filename: str) -> dict:
    primary = os.path.join(DATA_DIR, filename)
    fallback = os.path.join(BASE_DATA_DIR, filename)
    for path in (primary, fallback):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    if filename == "post_history.json":
        return {"posts": []}

    if filename == "topic_queue.json":
        return DEFAULT_TOPIC_QUEUE

    raise FileNotFoundError(f"Missing required JSON file: {filename}")


def load_topic_queue() -> dict:
    return _read_json_with_fallback("topic_queue.json")


def load_history() -> dict:
    return _read_json_with_fallback("post_history.json")


def save_history(history: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    target = os.path.join(DATA_DIR, "post_history.json")
    temp = target + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    os.replace(temp, target)


def _load_latest_marketing_strategy() -> dict:
    paths = []
    for base in (DATA_DIR, BASE_DATA_DIR):
        paths.extend(glob.glob(os.path.join(base, "marketing", "marketing_strategy_*.json")))
        # Backward compatibility with older artifact name.
        paths.extend(glob.glob(os.path.join(base, "marketing", "marketing_bundle_*.json")))

    if not paths:
        return {}

    latest = max(paths, key=os.path.getmtime)
    try:
        with open(latest, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_latest_structured_campaign() -> dict:
    paths = []
    for base in (DATA_DIR, BASE_DATA_DIR):
        paths.extend(glob.glob(os.path.join(base, "marketing", "campaigns", "campaign_*.json")))
    if not paths:
        return {}
    latest = max(paths, key=os.path.getmtime)
    try:
        with open(latest, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_founder_brand_manifesto() -> dict:
    for base in (DATA_DIR, BASE_DATA_DIR):
        path = os.path.join(base, "marketing", "founder_brand_manifesto.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, dict):
                    return payload
        except Exception:
            continue
    return {}


def _dedupe_str_list(values: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _build_brand_profile_seed(marketing_strategy: dict, manifesto: dict) -> dict:
    strategy = marketing_strategy if isinstance(marketing_strategy, dict) else {}
    man = manifesto if isinstance(manifesto, dict) else {}

    strategy_brand_profile = strategy.get("brand_profile", {}) if isinstance(strategy.get("brand_profile", {}), dict) else {}
    strategy_founder = strategy_brand_profile.get("founder_manifesto", {}) if isinstance(strategy_brand_profile.get("founder_manifesto", {}), dict) else {}
    strategy_voice = strategy.get("voice", {}) if isinstance(strategy.get("voice", {}), dict) else {}

    man_personality = man.get("brand_personality", {}) if isinstance(man.get("brand_personality", {}), dict) else {}
    man_approved = man.get("approved_sales_verbiage", {}) if isinstance(man.get("approved_sales_verbiage", {}), dict) else {}
    man_guardrails = man.get("guardrails", {}) if isinstance(man.get("guardrails", {}), dict) else {}
    man_business = man.get("business_profile", {}) if isinstance(man.get("business_profile", {}), dict) else {}

    audience_segments = man.get("audience_segments", [])
    if not isinstance(audience_segments, list):
        audience_segments = []

    words_to_avoid = strategy_voice.get("words_to_avoid", [])
    if not isinstance(words_to_avoid, list):
        words_to_avoid = []

    words_to_use = strategy_voice.get("words_to_use", [])
    if not isinstance(words_to_use, list):
        words_to_use = []

    seed = {
        "brand_name": man.get("brand_name") or strategy.get("brand", {}).get("brand_name") or "Infenergy Power",
        "tagline": strategy_founder.get("tagline") or man_approved.get("hero_line") or "",
        "mission": strategy_founder.get("mission") or man.get("mission") or "",
        "positioning": man_business.get("positioning") or "portable power preparedness brand",
        "audience_summary": " | ".join([str(x) for x in audience_segments[:5]]),
        "personality_name": man_personality.get("voice_name") or "Calm Strength",
        "personality_traits": _dedupe_str_list(man_personality.get("traits", [])),
        "tone_rules": _dedupe_str_list(man_personality.get("tone_rules", [])),
        "voice_rules": _dedupe_str_list(strategy_voice.get("voice_rules", [])),
        "approved_phrases": _dedupe_str_list(man_approved.get("core_phrases", [])),
        "cta_style": _dedupe_str_list(man_approved.get("cta_style", [])),
        "trust_close": man_approved.get("trust_close", "") or "",
        "words_to_use": _dedupe_str_list(words_to_use),
        "words_to_avoid": _dedupe_str_list(words_to_avoid),
        "forbidden_phrases": _dedupe_str_list(man_guardrails.get("disallowed_claim_patterns", [])),
        "core_values": _dedupe_str_list(man.get("core_values", [])),
        "additional_notes": str(man_guardrails.get("allowed_solar_context", "")).strip(),
    }
    return seed


def sync_inventory_database(force: bool = False) -> dict:
    inventory_db.init_inventory_db(DATA_DIR)
    before_count = inventory_db.products_count(DATA_DIR)
    products_seeded = 0
    brand_seeded = False
    ideology_seeded = False

    should_seed_products = force or before_count == 0
    if should_seed_products:
        csv_products = _load_products_from_csv()
        if csv_products:
            products_seeded = inventory_db.upsert_products(DATA_DIR, csv_products, source="wc_csv")

    if force or not inventory_db.has_brand_profile(DATA_DIR):
        strategy = _load_latest_marketing_strategy()
        manifesto = _load_founder_brand_manifesto()
        seed = _build_brand_profile_seed(strategy, manifesto)
        if seed:
            brand_seeded = inventory_db.upsert_brand_profile(DATA_DIR, seed)

    if force or not inventory_db.has_selling_ideology(DATA_DIR):
        ideology_seeded = inventory_db.upsert_selling_ideology(DATA_DIR, conference_selling_ideology_payload())

    after_count = inventory_db.products_count(DATA_DIR)
    return {
        "db_path": inventory_db.get_db_path(DATA_DIR),
        "products_before": before_count,
        "products_seeded": products_seeded,
        "products_after": after_count,
        "brand_seeded": brand_seeded,
        "ideology_seeded": ideology_seeded,
        "brand_profile_present": inventory_db.has_brand_profile(DATA_DIR),
        "selling_ideology_present": inventory_db.has_selling_ideology(DATA_DIR),
    }


def load_brand_profile() -> dict:
    sync_inventory_database(force=False)
    profile = inventory_db.fetch_brand_profile(DATA_DIR)
    if profile:
        return profile

    strategy = _load_latest_marketing_strategy()
    manifesto = _load_founder_brand_manifesto()
    return _build_brand_profile_seed(strategy, manifesto)


def conference_brand_profile_payload() -> dict:
    """Canonical conference output for positioning and brand voice."""
    return {
        "brand_name": "Infenergy Power",
        "tagline": "From chaos to control.",
        "mission": "Help families and everyday people stay powered, prepared, safe, and connected when normal systems fail.",
        "positioning": "Preparedness-first portable power and resilience brand for families, travelers, outdoor users, seniors, and small operators.",
        "audience_summary": (
            "Working families in storm-prone regions | RV and outdoor users | Emergency-minded households "
            "| Seniors and caregivers | Small operators who need uptime continuity"
        ),
        "personality_name": "Calm Strength",
        "personality_traits": [
            "Protective",
            "Mission-driven",
            "Practical",
            "Empathetic",
            "Confident",
            "Coach-like",
        ],
        "tone_rules": [
            "Lead with a real-life risk or customer moment.",
            "Translate technical specs into plain-language outcomes.",
            "Be urgent without fear-mongering.",
            "Sound human and committed, never generic.",
            "Close with one clear, low-friction next step.",
        ],
        "voice_rules": [
            "Lead with empathy and urgency rooted in real family preparedness moments.",
            "Translate specs into immediate and long-term outcomes people can feel.",
            "Use value stacking, practical guidance, and one clear next step.",
            "Sound committed and human: protective, coach-like, and trustworthy.",
            "Anchor every claim in concrete facts and examples.",
        ],
        "approved_phrases": [
            "Preparedness over panic",
            "Power is protection",
            "From chaos to control",
            "Practical power for real life",
            "Built for outages, travel, and everyday resilience",
            "Spec-backed recommendations you can trust",
        ],
        "cta_style": [
            "Get your readiness plan",
            "Map your must-run devices",
            "Book your product-fit consultation",
            "Build your outage-ready setup",
        ],
        "trust_close": "We do not just sell products. We help people stay calm, connected, and prepared when it matters most.",
        "words_to_use": [
            "preparedness",
            "protection",
            "resilience",
            "continuity",
            "practical",
            "spec-backed",
            "confidence",
            "control",
        ],
        "words_to_avoid": [
            "revolutionary",
            "game-changing",
            "once-in-a-lifetime",
            "guaranteed",
            "instant savings",
        ],
        "forbidden_phrases": [
            "Unverifiable guarantees",
            "Fear-only manipulation",
            "Rooftop installation positioning",
            "Tax-credit-first sales framing",
        ],
        "core_values": [
            "Protection",
            "Preparedness",
            "Reliability",
            "Integrity",
            "Service",
            "Commitment",
            "Practical guidance",
        ],
        "additional_notes": "Primary lifestyle positioning: home resilience, mobile autonomy, and family safety continuity.",
    }


def apply_conference_brand_profile() -> dict:
    sync_inventory_database(force=False)
    payload = conference_brand_profile_payload()
    ok = inventory_db.upsert_brand_profile(DATA_DIR, payload)
    profile = inventory_db.fetch_brand_profile(DATA_DIR)
    return {
        "ok": bool(ok),
        "brand_profile": profile,
    }


def conference_selling_ideology_payload() -> dict:
    return {
        "schema_version": "v1",
        "framework_mode": "mixed_with_campaign_overlay",
        "primary_conversion": "direct_checkout",
        "tone_blend": "calm_protective_plus_assertive_urgent",
        "value_lens": "benefit_first",
        "message_filter": "no_nonconverting_copy",
        "cta_mode": "checkout_first",
        "campaign_behavior": "overlay_not_replace",
        "proof_rule": "scenario_plus_spec_evidence",
        "disqualify_alternative": "patchwork_guesswork",
        "core_promise": "reliable_peace_of_mind",
        "audience_priority": [
            "working_families_outage_prone",
            "rv_and_outdoor_autonomy",
            "small_operator_and_caregiver_continuity",
        ],
        "psychographics": [
            "risk_aware_planners",
            "reliability_over_hype_buyers",
            "control_seekers_wanting_clarity",
            "value_protectors_avoiding_wrong_fit",
        ],
        "lifestyle_positioning": [
            "home_resilience",
            "mobile_autonomy",
            "family_safety_continuity",
            "preparedness_routine",
        ],
        "pillar_messages": [
            "preparedness_over_panic",
            "specs_to_outcomes",
            "right_size_before_upsell",
            "everyday_value_plus_emergency_value",
            "single_checkout_next_step",
        ],
        "objection_handling": [
            "too_expensive_vs_cost_of_outage",
            "too_complex_use_readiness_checklist",
            "fit_uncertainty_use_scenario_proof",
            "delay_risk_reframe_with_action_cost",
        ],
        "cta_ladder": [
            "attention_save_checklist",
            "education_map_top_3_devices",
            "desire_get_fit_recommendation",
            "trust_review_spec_backed_options",
            "conversion_checkout_now",
        ],
        "banned_phrases": [
            "generic_non_directional_copy",
            "hype_without_proof",
            "vague_cta_without_path",
            "fear_mongering",
            "unverifiable_guarantees",
        ],
    }


def load_selling_ideology() -> dict:
    sync_inventory_database(force=False)
    ideology = inventory_db.fetch_selling_ideology(DATA_DIR)
    if ideology:
        return ideology
    return conference_selling_ideology_payload()


def apply_conference_selling_ideology() -> dict:
    sync_inventory_database(force=False)
    payload = conference_selling_ideology_payload()
    ok = inventory_db.upsert_selling_ideology(DATA_DIR, payload)
    ideology = inventory_db.fetch_selling_ideology(DATA_DIR)
    return {
        "ok": bool(ok),
        "selling_ideology": ideology,
    }


def _is_usable_image_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        return False
    if any(x in u for x in ("placeholder", "no-image", "default")):
        return False
    return True


def _load_category_image_fallbacks() -> dict[str, str]:
    custom = os.environ.get("IG_CATEGORY_FALLBACKS_JSON", "").strip()
    merged = dict(DEFAULT_CATEGORY_IMAGE_FALLBACKS)
    if custom:
        try:
            parsed = json.loads(custom)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    key = str(k).strip().lower()
                    val = str(v).strip()
                    if key and _is_usable_image_url(val):
                        merged[key] = val
        except Exception:
            pass
    return merged


def _category_tokens(categories: list[str]) -> list[str]:
    tokens = []
    for c in categories:
        raw = (c or "").strip().lower()
        if not raw:
            continue
        tokens.append(raw)
        if ">" in raw:
            tokens.append(raw.split(">", 1)[0].strip())
    out = []
    seen = set()
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _fallback_images_for_categories(categories: list[str]) -> list[str]:
    mapping = _load_category_image_fallbacks()
    out = []
    seen = set()
    for token in _category_tokens(categories):
        url = mapping.get(token, "")
        if _is_usable_image_url(url) and url not in seen:
            seen.add(url)
            out.append(url)
    return out[:4]


def _score_image_url(url: str) -> int:
    score = 0
    u = url.lower()
    if "-300x300" in u or "-150x150" in u:
        score -= 3
    if "scaled" in u:
        score += 2
    if u.endswith(".jpg") or u.endswith(".jpeg"):
        score += 2
    if u.endswith(".png"):
        score += 1
    if "wp-content/uploads" in u:
        score += 1
    return score


def _pick_best_image_urls(image_urls: list[str]) -> tuple[str, list[str]]:
    usable = [u for u in image_urls if _is_usable_image_url(u)]
    if not usable:
        return "", []
    ranked = sorted(usable, key=_score_image_url, reverse=True)
    primary = ranked[0]
    candidates = []
    seen = set()
    for u in ranked:
        if u not in seen:
            seen.add(u)
            candidates.append(u)
    return primary, candidates[:4]


def _strip_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text or "", flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_metrics(text: str) -> list[str]:
    if not text:
        return []
    pattern = re.compile(
        r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?(?:Wh|mAh|W|kW|V|A|lbs|lb|in|mm|g|hours|hour|%|PD\s?\d+W|QC\s?\d+\.\d+)\b",
        flags=re.IGNORECASE,
    )
    seen = set()
    out = []
    for m in pattern.findall(text):
        k = m.lower()
        if k not in seen:
            seen.add(k)
            out.append(m)
    return out[:8]


def _load_products_from_csv() -> list[dict]:
    products_dir = os.path.join(BASE_DATA_DIR, "products")
    csv_paths = sorted(glob.glob(os.path.join(products_dir, "*.csv")))
    products = []

    for csv_path in csv_paths:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Published", "").strip() != "1":
                    continue

                name = (row.get("Name") or "").strip()
                if not name:
                    continue

                sku = (row.get("SKU") or "").strip()
                short_text = _strip_html(row.get("Short description") or "")
                long_text = _strip_html(row.get("Description") or "")
                merged_text = f"{short_text} {long_text}".strip()
                metrics = _extract_metrics(merged_text)
                categories = [c.strip() for c in (row.get("Categories") or "").split(",") if c.strip()]
                image_urls = [u.strip() for u in (row.get("Images") or "").split(",") if u.strip()]
                primary_image, image_candidates = _pick_best_image_urls(image_urls)
                raw_id = str(row.get("ID") or "").strip()
                stable_fallback_id = str(sku or hashlib.md5(name.lower().encode("utf-8")).hexdigest()[:12]).strip()

                products.append(
                    {
                        "id": raw_id or stable_fallback_id,
                        "name": name,
                        "sku": sku,
                        "price": (row.get("Regular price") or "").strip(),
                        "sale_price": (row.get("Sale price") or "").strip(),
                        "in_stock": (row.get("In stock?") or "").strip(),
                        "stock": (row.get("Stock") or "").strip(),
                        "product_url": (row.get("External URL") or "").strip(),
                        "categories": categories[:4],
                        "metrics": metrics,
                        "fact_snippet": merged_text[:500],
                        "image_url": primary_image,
                        "image_candidates": image_candidates,
                        "category_image_candidates": _fallback_images_for_categories(categories),
                    }
                )

    return products


def load_products() -> list[dict]:
    sync_inventory_database(force=False)
    from_db = inventory_db.fetch_products(DATA_DIR)
    if from_db:
        return from_db

    fallback = _load_products_from_csv()
    if fallback:
        inventory_db.upsert_products(DATA_DIR, fallback, source="wc_csv")
    return fallback


def _pick_product(products: list[dict], history: dict) -> dict | None:
    if not products:
        return None

    windows = load_anti_repeat_windows()
    days = int(windows.get("product_feature_days", 7))
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))

    def _post_dt(post: dict) -> datetime | None:
        raw = str(post.get("run_started_at_utc") or post.get("date") or "")
        if not raw:
            return None
        try:
            if len(raw) == 10 and "-" in raw:
                return datetime.fromisoformat(raw + "T00:00:00+00:00")
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    recent_keys = {
        f"{p.get('product_name', '')}|{p.get('product_sku', '')}".lower()
        for p in history.get("posts", [])
        if p.get("product_name") and (_post_dt(p) and _post_dt(p) >= cutoff)
    }

    random.shuffle(products)
    for product in products:
        key = f"{product.get('name', '')}|{product.get('sku', '')}".lower()
        if key not in recent_keys:
            return product

    return random.choice(products)


def _pick_product_by_id(products: list[dict], product_id: str) -> dict | None:
    requested = str(product_id or "").strip()
    if not requested:
        return None
    requested_low = requested.lower()
    for product in products:
        product_id_value = str(product.get("id", "")).strip()
        product_sku_value = str(product.get("sku", "")).strip()
        if product_id_value == requested:
            return product
        if product_id_value.lower() == requested_low:
            return product
        if product_sku_value and product_sku_value.lower() == requested_low:
            return product
    return None


def _normalize_funnel_stage_override(value: str) -> str:
    stage = str(value or "").strip().upper()
    return stage if stage in FUNNEL_STAGES else ""


def _preferred_pillars_for_stage(funnel_stage: str) -> list[str]:
    stage = str(funnel_stage or "").strip().upper()
    if stage == "CONVERSION":
        return ["promotions", "product_education", "portable_power_readiness"]
    if stage == "TRUST":
        return ["use_case_breakdowns", "product_education", "emergency_preparedness"]
    if stage == "DESIRE":
        return ["use_case_breakdowns", "outdoor_rv_power", "portable_power_readiness"]
    if stage == "EDUCATION":
        return ["product_education", "portable_power_readiness", "myth_busting_power"]
    return ["emergency_preparedness", "portable_power_readiness", "outdoor_rv_power"]


def _pick_topic(queue: dict, history: dict, preferred_pillars: list[str] | None = None) -> tuple[str, str, str]:
    windows = load_anti_repeat_windows()
    days = int(windows.get("topic_days", 21))
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))

    used_hashes = set()
    for p in history.get("posts", []):
        if not isinstance(p, dict):
            continue
        topic_hash = str(p.get("topic_hash", "")).strip()
        if not topic_hash:
            continue
        raw = str(p.get("run_started_at_utc") or p.get("date") or "")
        if not raw:
            continue
        try:
            if len(raw) == 10 and "-" in raw:
                dt = datetime.fromisoformat(raw + "T00:00:00+00:00")
            else:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt >= cutoff:
                used_hashes.add(topic_hash)
        except Exception:
            continue

    queue_pillars = [str(p).strip() for p in queue.get("pillars", []) if str(p).strip()]
    preferred = [p for p in (preferred_pillars or []) if p in queue_pillars]
    remaining = [p for p in queue_pillars if p not in preferred]
    random.shuffle(preferred)
    random.shuffle(remaining)
    pillars = preferred + remaining
    if not pillars:
        raise ValueError("topic queue has no valid pillars")
    for pillar in pillars:
        topics = queue["topics"][pillar][:]
        random.shuffle(topics)
        for topic in topics:
            h = hashlib.md5(topic.encode()).hexdigest()
            if h not in used_hashes:
                return pillar, topic, h
    # All used recently — reset and pick random
    pillar = random.choice(pillars)
    topic = random.choice(queue["topics"][pillar])
    return pillar, topic, hashlib.md5(topic.encode()).hexdigest()


def _pick_non_repeating_text(candidates: list[str], recent_hashes: set[str], fallback: str) -> str:
    cleaned = [c.strip() for c in candidates if isinstance(c, str) and c.strip()]
    random.shuffle(cleaned)
    for item in cleaned:
        if stable_text_hash(item) not in recent_hashes:
            return item
    if cleaned:
        return cleaned[0]
    return fallback


def _recent_unique_values(history: dict, key: str, limit: int = 8) -> list[str]:
    posts = history.get("posts", []) if isinstance(history, dict) else []
    out = []
    seen = set()
    for row in reversed(posts):
        if not isinstance(row, dict):
            continue
        value = str(row.get(key, "")).strip()
        if not value:
            continue
        low = value.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _one_line(text: str, limit: int = 220) -> str:
    out = re.sub(r"\s+", " ", (text or "").strip())
    if len(out) <= limit:
        return out
    return out[: limit - 3].rstrip() + "..."


def _enforce_pain_point_opening(text: str, pain_point: str, lead_chars: int = 220) -> str:
    body = str(text or "").strip()
    pain = str(pain_point or "").strip()
    if not pain:
        return body
    if not body:
        return pain
    lead = body[:lead_chars].lower()
    if pain.lower() in lead:
        return body
    return f"{pain}\n\n{body}"


def _sanitize_positioning_terms(text: str) -> str:
    body = str(text or "")
    if not body:
        return body
    for source, replacement in POSITIONING_REPLACEMENTS.items():
        pattern = re.compile(re.escape(source), flags=re.IGNORECASE)
        body = pattern.sub(replacement, body)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in body.splitlines()]
    body = "\n".join(lines)
    body = body.replace(" .", ".")
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def _contains_numeric_evidence(text: str) -> bool:
    t = str(text or "")
    if not t:
        return False
    if re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", t):
        return True
    if re.search(r"\b(top\s*\d+|\d+\s*(hours?|minutes?|wh|w|kw|mah|%)|24-hour|same-day)\b", t, flags=re.IGNORECASE):
        return True
    return False


def _enforce_conversion_caption(text: str, talking_point: dict, platform: str = "") -> str:
    body = str(text or "").strip()
    pain_point = str((talking_point or {}).get("pain_point", "")).strip()
    proof_anchor = str((talking_point or {}).get("proof_anchor", "")).strip()
    first_step = str((talking_point or {}).get("first_step", "")).strip()
    platform_name = str(platform or "").strip().lower()

    body = _sanitize_positioning_terms(body)
    body = _enforce_pain_point_opening(body, pain_point)

    low = body.lower()
    if proof_anchor and proof_anchor.lower() not in low:
        body = f"{body}\n\n{proof_anchor}"

    if not _contains_numeric_evidence(body):
        body = f"{body}\n\nStart with your top 3 must-run devices and expected hours of use."

    if first_step and first_step.lower() not in body.lower():
        if platform_name == "facebook":
            body = f"{body}\n\nNext step: {first_step}\nWhat device is non-negotiable for you in an outage?"
        elif platform_name == "instagram":
            body = f"{body}\n\nNext step: {first_step}"
        elif platform_name == "linkedin":
            body = f"{body}\n\nOperational next step: {first_step}"
        else:
            body = f"{body}\n\nNext step: {first_step}"

    return body.strip()


def _pick_pain_point_variant(topic: str, funnel_stage: str, product: dict | None) -> str:
    stage = str(funnel_stage or "").strip().upper()
    variants = DEFAULT_STAGE_PAIN_POINT_VARIANTS.get(stage, [])
    if not variants:
        return DEFAULT_STAGE_PAIN_POINTS.get(stage, "Most people choose backup power without mapping real usage first.")
    seed = f"{stage}|{topic}|{str((product or {}).get('name', ''))}"
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(variants)
    return variants[idx]


def _build_talking_point(topic: str, funnel_stage: str, product: dict | None) -> dict:
    stage = str(funnel_stage or "").strip().upper()
    pain_point = _pick_pain_point_variant(topic, stage, product)

    product_name = str((product or {}).get("name", "")).strip() or "this solution"
    metrics = (product or {}).get("metrics", []) if isinstance(product, dict) else []
    m1 = metrics[0] if len(metrics) > 0 else "published output specs"
    m2 = metrics[1] if len(metrics) > 1 else "runtime and charging details"

    proof_anchor = f"Use {m1} and {m2} to validate fit before buying."
    angle = f"{topic} through a real-world decision framework, not hype."

    first_step = "Comment with your top 3 must-run devices for a practical match today."
    if stage == "EDUCATION":
        first_step = "Save this checklist and compare your current setup tonight."
    elif stage == "DESIRE":
        first_step = f"Compare {product_name} against your top 3 daily loads in one quick review."
    elif stage == "TRUST":
        first_step = "Review your device list and verify specs before committing."
    elif stage == "CONVERSION":
        first_step = "Book your free readiness assessment and get a tailored recommendation in under 15 minutes."

    return {
        "pain_point": pain_point,
        "proof_anchor": proof_anchor,
        "angle": angle,
        "first_step": first_step,
    }


def _build_business_profile(products: list[dict]) -> dict:
    category_counts: dict[str, int] = {}
    keyword_counts: dict[str, int] = {
        "portable power": 0,
        "power station": 0,
        "portable generator": 0,
        "solar panel": 0,
        "battery": 0,
        "emergency": 0,
        "camping": 0,
        "rv": 0,
    }

    for product in products:
        if not isinstance(product, dict):
            continue
        categories = product.get("categories", [])
        if isinstance(categories, list):
            for raw in categories:
                c = str(raw).strip().lower()
                if not c:
                    continue
                category_counts[c] = category_counts.get(c, 0) + 1

        text = " ".join(
            [
                str(product.get("name", "")),
                str(product.get("fact_snippet", "")),
                " ".join([str(x) for x in product.get("categories", []) if isinstance(product.get("categories", []), list)]),
            ]
        ).lower()
        if "portable" in text and "power" in text:
            keyword_counts["portable power"] += 1
        if "power station" in text:
            keyword_counts["power station"] += 1
        if "portable generator" in text:
            keyword_counts["portable generator"] += 1
        if "solar panel" in text:
            keyword_counts["solar panel"] += 1
        if "battery" in text:
            keyword_counts["battery"] += 1
        if "emergency" in text or "outage" in text:
            keyword_counts["emergency"] += 1
        if "camping" in text:
            keyword_counts["camping"] += 1
        if "rv" in text:
            keyword_counts["rv"] += 1

    top_categories = sorted(category_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
    offers = [name for name, _ in top_categories]
    return {
        "focus_statement": "portable power, emergency readiness, outdoor and RV use cases",
        "top_categories": top_categories,
        "keyword_signals": keyword_counts,
        "offers": offers,
    }


def _build_post_components(
    topic: str,
    selected_hook: str,
    selected_cta: str,
    product: dict | None,
    funnel_stage: str,
) -> dict:
    product_name = (product or {}).get("name", "our energy solution")
    product_id = (product or {}).get("id", "")
    metrics = (product or {}).get("metrics", [])
    m1 = metrics[0] if len(metrics) > 0 else "verified output specs"
    m2 = metrics[1] if len(metrics) > 1 else "runtime and charging context"

    situation = "Many households and small businesses discover during outages, travel, or events that their backup plan does not match real power needs."
    info = f"A better approach is to map your must-run devices and compare them against measured specs like {m1} and {m2}."
    why = "This reduces expensive guesswork, improves resilience, and helps buyers choose what actually fits real usage."
    product_connection = f"For this topic, {product_name} can be part of a practical setup when the specs match your actual daily loads."
    proof = f"Start from verified details and published product fields only."

    cta = selected_cta
    stage = funnel_stage.upper()
    if stage == "EDUCATION":
        cta = "Save this checklist and compare your current setup."
    elif stage == "DESIRE":
        cta = "See what this product is designed to support."
    elif stage == "CONVERSION":
        cta = "Build your backup-power setup."

    return {
        "product_id": product_id or None,
        "hook": selected_hook,
        "situation": situation,
        "info": info,
        "why": why,
        "product_connection": product_connection,
        "proof": proof,
        "cta": cta,
        "topic": topic,
    }


def _adapt_facebook(components: dict, funnel_stage: str) -> tuple[str, str, str]:
    question = "What would you power first if the grid went down tonight?"
    if funnel_stage.upper() == "CONVERSION":
        question = "Want a practical recommendation matched to your devices?"
    cta = components["cta"] if funnel_stage.upper() == "CONVERSION" else "Comment with your top device and we will help you map priorities."
    caption = (
        f"{_one_line(components['hook'], 120)}\n\n"
        f"{components['situation']} {components['info']}\n\n"
        f"{components['why']} {components['product_connection']}\n\n"
        f"{components['proof']}\n\n"
        f"{cta}\n"
        f"{question}\n"
        "#EnergyResilience #PreparedHome #BackupPower"
    )
    return caption, cta, "community_story"


def _adapt_instagram(components: dict, funnel_stage: str) -> tuple[str, str, str, str]:
    hook = _one_line(components["hook"], 60)
    hook_words = hook.split()
    hook_line = " ".join(hook_words[:9]) if hook_words else "Power planning, done right"
    stage = funnel_stage.upper()
    cta = components["cta"]
    if stage == "EDUCATION":
        cta = "Save this and share it with someone preparing their home."
    elif stage in ("DESIRE", "CONVERSION"):
        cta = "See product options and compare what fits your daily loads."

    caption = (
        f"{hook_line}\n"
        f"{components['situation']}\n"
        f"{components['info']}\n"
        f"Why it matters: {components['why']}\n"
        f"{components['product_connection']}\n"
        f"{components['proof']}\n"
        f"{cta}\n"
        "#PortablePower #EnergyPreparedness #SolarBackup #HomeResilience #PowerPlanning"
    )
    visual_direction = "reel" if stage in ("ATTENTION", "DESIRE") else "carousel"
    alt_text = f"{components['topic']} with practical power-planning visuals and product context."
    return caption, cta, visual_direction, alt_text


def _adapt_linkedin(components: dict, funnel_stage: str) -> tuple[str, str, str]:
    stage = funnel_stage.upper()
    cta = components["cta"]
    if stage != "CONVERSION":
        cta = "Review the framework and adapt it to your own resilience plan."
    caption = (
        f"{_one_line(components['hook'], 120)}\n\n"
        f"Context: {components['situation']}\n"
        f"Useful model: {components['info']}\n"
        f"Why this matters: {components['why']}\n"
        f"Product connection: {components['product_connection']}\n"
        f"Credibility check: {components['proof']}\n\n"
        f"Next step: {cta}\n"
        "#EnergyResilience #BusinessContinuity"
    )
    return caption, cta, "authority_post"


def _build_platform_posts(
    post_id: str,
    campaign_id: str,
    audience_segment: str,
    funnel_stage: str,
    destination_url: str,
    components: dict,
    quality_score: float,
    caption_overrides: dict | None = None,
) -> dict:
    fb_caption, fb_cta, fb_format = _adapt_facebook(components, funnel_stage)
    ig_caption, ig_cta, ig_visual, ig_alt = _adapt_instagram(components, funnel_stage)
    li_text, li_cta, li_format = _adapt_linkedin(components, funnel_stage)

    utm_fb = build_utm_url(
        destination_url,
        source="facebook",
        campaign=campaign_id or "campaign",
        content=f"{components.get('product_id') or 'general'}_{funnel_stage.lower()}",
        term=audience_segment.lower().replace(" ", "_"),
    )
    utm_ig = build_utm_url(
        destination_url,
        source="instagram",
        campaign=campaign_id or "campaign",
        content=f"{components.get('product_id') or 'general'}_{funnel_stage.lower()}",
        term=audience_segment.lower().replace(" ", "_"),
    )
    utm_li = build_utm_url(
        destination_url,
        source="linkedin",
        campaign=campaign_id or "campaign",
        content=f"{components.get('product_id') or 'general'}_{funnel_stage.lower()}",
        term=audience_segment.lower().replace(" ", "_"),
    )

    platform_posts = {
        "facebook": {
            "post_id": post_id,
            "campaign_id": campaign_id,
            "platform": "facebook",
            "funnel_stage": funnel_stage,
            "audience_segment": audience_segment,
            "product_id": components.get("product_id"),
            "hook": components["hook"],
            "caption": fb_caption,
            "cta": fb_cta,
            "destination_url": destination_url,
            "utm_url": utm_fb.get("utm_url", destination_url),
            "content_format": fb_format,
            "visual_direction": "single_image",
            "alt_text": "Facebook visual illustrating practical home energy preparedness.",
            "quality_score": float(quality_score),
            "validation_status": "ok",
            "validation_errors": [],
        },
        "instagram": {
            "post_id": post_id,
            "campaign_id": campaign_id,
            "platform": "instagram",
            "funnel_stage": funnel_stage,
            "audience_segment": audience_segment,
            "product_id": components.get("product_id"),
            "hook": components["hook"],
            "caption": ig_caption,
            "cta": ig_cta,
            "destination_url": destination_url,
            "utm_url": utm_ig.get("utm_url", destination_url),
            "content_format": "short_caption",
            "visual_direction": ig_visual,
            "alt_text": ig_alt,
            "quality_score": float(quality_score),
            "validation_status": "ok",
            "validation_errors": [],
        },
        "linkedin": {
            "post_id": post_id,
            "campaign_id": campaign_id,
            "platform": "linkedin",
            "funnel_stage": funnel_stage,
            "audience_segment": audience_segment,
            "product_id": components.get("product_id"),
            "hook": components["hook"],
            "caption": li_text,
            "cta": li_cta,
            "destination_url": destination_url,
            "utm_url": utm_li.get("utm_url", destination_url),
            "content_format": li_format,
            "visual_direction": "insight_graphic",
            "alt_text": "LinkedIn visual focused on resilience strategy and verified product details.",
            "quality_score": float(quality_score),
            "validation_status": "ok",
            "validation_errors": [],
        },
    }

    overrides = caption_overrides or {}
    for platform in ("facebook", "instagram", "linkedin"):
        platform_override = overrides.get(platform, {}) if isinstance(overrides, dict) else {}
        if not isinstance(platform_override, dict):
            continue
        override_caption = str(platform_override.get("caption", "")).strip()
        override_cta = str(platform_override.get("cta", "")).strip()
        if override_caption:
            platform_posts[platform]["caption"] = override_caption
        if override_cta:
            platform_posts[platform]["cta"] = override_cta

    return platform_posts


def _build_fallback_content(
    slot: str,
    topic: str,
    product: dict | None,
    marketing_strategy: dict | None,
    talking_point: dict | None = None,
) -> dict:
    marketing_strategy = marketing_strategy or {}
    talking_point = talking_point or {}
    marketing_copy = marketing_strategy.get("copy", {})
    name = (product or {}).get("name", "INF Energy Power solution")
    sku = (product or {}).get("sku", "")
    price = (product or {}).get("price", "")
    sale_price = (product or {}).get("sale_price", "")
    metrics = (product or {}).get("metrics", [])
    m1 = metrics[0] if len(metrics) > 0 else "high-capacity output"
    m2 = metrics[1] if len(metrics) > 1 else "fast charging performance"

    price_line = ""
    if sale_price:
        price_line = f" Current sale price is ${sale_price}."
    elif price:
        price_line = f" Current listed price is ${price}."

    hero = (marketing_copy.get("hero") or "").strip()
    cta_bank = marketing_copy.get("cta_bank") or []
    cta = cta_bank[0] if cta_bank else "Book your free power readiness assessment"
    pain_point = str(talking_point.get("pain_point") or "Most people buy backup power without validating real usage first.").strip()
    proof_anchor = str(talking_point.get("proof_anchor") or f"Use {m1} and {m2} to validate fit before buying.").strip()
    first_step = str(talking_point.get("first_step") or cta).strip()
    angle = str(talking_point.get("angle") or f"{topic} through practical decision-making.").strip()

    wp_title = f"{name}: What To Know Before You Buy"
    if len(wp_title) > 64:
        wp_title = f"{name[:52]}: Buyer Guide"
    if hero and len(hero) <= 62:
        wp_title = hero

    wp_content = (
        f"<p>{pain_point} Choosing backup power is not just about watts on a label. It is about reliability, runtime, and how well a product matches your real daily use. Today we are breaking down <strong>{name}</strong> through this lens: {angle}</p>"
        f"<h2>Start With Your Real Use Case</h2>"
        f"<p>Before buying any power solution, list the devices you need to run first. Most buyers overestimate occasional loads and underestimate frequent loads. The smarter move is to match your frequent loads to verified product specs. For this model, key published specs include <strong>{m1}</strong> and <strong>{m2}</strong>. These two data points are usually the best first filter when comparing options.</p>"
        f"<h2>How This Product Compares In Practical Terms</h2>"
        f"<p>When evaluating alternatives, focus on three things: usable output, charging speed, and portability. A product that looks cheaper can cost more over time if charging is slow or output is limited for the devices you use most. {name} is positioned for buyers who want consistent performance without overcomplicating setup.{price_line}</p>"
        f"<h2>Avoid The Most Common Buying Mistakes</h2>"
        f"<p>The biggest mistake is buying only on headline capacity. The second is ignoring how and where the unit will be used. A better approach is to map your top 3 devices, compare real specs, and confirm compatibility up front. {proof_anchor} This avoids returns, downtime, and frustration.</p>"
        f"<h2>Next Step</h2>"
        f"<p>If you want a tailored recommendation, {first_step.lower()} We can help you compare your options and select the right system for your actual usage, not generic assumptions.</p>"
    )

    fb_caption = (
        f"{pain_point}\n\n"
        f"If you are comparing options like {name}, start with what actually matters: published specs and your real daily devices. This product lists {m1} and {m2}, which are the kinds of details that should drive your decision, not just brand name."
        f"{price_line}\n\n"
        f"{proof_anchor}\n\n"
        f"If you want help matching the right system to your usage, {first_step.lower()}\n\n"
        f"What device is non-negotiable for you during an outage?\n"
        f"#BackupPower #EnergyResilience #SmartBuying #InfEnergyPower #PortablePower"
    )

    ig_caption = (
        f"{_one_line(pain_point, 70)}\n"
        f"If you are considering {name}, do not pick based on marketing alone. Compare real specs to your actual daily devices.\n\n"
        f"Two key published details on this model are {m1} and {m2}. Those numbers matter more than hype because they affect runtime, compatibility, and reliability when you need power most."
        f"{price_line}\n\n"
        f"{proof_anchor}\n"
        f"Want help choosing the right setup for your home or business? {first_step}.\n"
        f"#PortablePower #EnergyBackup #PowerOutagePrep #SolarReady #EmergencyPower #SmartHomeEnergy #InfEnergyPower #BatteryBackup"
    )

    li_text = (
        f"{pain_point}\n\n"
        f"When evaluating products like {name}{' (' + sku + ')' if sku else ''}, the better framework is simple:\n"
        f"1) Map your top 3 critical loads\n"
        f"2) Validate published output and charging specs\n"
        f"3) Compare portability and recharge practicality\n\n"
        f"For this model, two important published specs are {m1} and {m2}. These are the details that determine whether a unit helps in a real outage or just looks good on a product page."
        f"{price_line}\n\n"
        f"{proof_anchor}\n\n"
        f"If you want a practical recommendation based on your exact use case, {first_step.lower()}"
    )

    return {
        "wp_title": wp_title,
        "wp_content": wp_content,
        "wp_excerpt": f"{name}: practical buying guidance, key specs, and what to compare before you purchase.",
        "fb_caption": fb_caption,
        "ig_caption": ig_caption,
        "li_text": li_text,
    }


def _generate_json_with_gemini(prompt: str, model_candidates: list[str]) -> dict | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)

    for model_name in model_candidates:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            raw = (response.text or "").strip()
            if not raw:
                continue
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception:
            continue

    return None


def _build_default_visual_plan(topic: str, funnel_stage: str, selected_hook: str, selected_cta: str, product: dict | None) -> dict:
    has_product_image = bool((product or {}).get("image_url"))
    strategy = "hybrid" if has_product_image else "gemini_generated"
    return {
        "style_intent": "Premium cinematic realism for practical energy resilience",
        "mood": "trustworthy, confident, modern",
        "image_strategy": strategy,
        "composition": "left-side negative space for headline, right-side hero visual",
        "use_product_photo": has_product_image,
        "text_on_image": "minimal",
        "gemini_image_prompt": (
            f"Create a premium social visual for topic '{topic}' with hook '{selected_hook}'. "
            f"Convey {funnel_stage.lower()} stage intent and support CTA: {selected_cta}. "
            "Show credible, modern home or small-business backup power atmosphere with cinematic lighting."
        ),
        "platform_overrides": {
            "facebook": {"composition": "balanced, educational, product-visible", "visual_direction": "single_image"},
            "instagram": {"composition": "bold focal point, strong depth, mobile-first", "visual_direction": "reel_cover_style"},
            "linkedin": {"composition": "clean professional credibility layout", "visual_direction": "insight_graphic"},
        },
    }


def _build_visual_plan_with_gemini(
    model_candidates: list[str],
    *,
    topic: str,
    funnel_stage: str,
    stage_objective: str,
    selected_hook: str,
    selected_cta: str,
    product_name: str,
    product_categories: str,
    product_metrics: str,
    has_product_image: bool,
) -> dict | None:
    prompt = f"""{VISUAL_DIRECTOR_BRIEF}

Campaign input:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Stage objective: {stage_objective}
- Hook: {selected_hook}
- CTA: {selected_cta}
- Product name: {product_name or 'N/A'}
- Product categories: {product_categories or 'N/A'}
- Product measurable specs: {product_metrics or 'N/A'}
- Product image available: {has_product_image}

Return only valid JSON with this exact shape:
{{
  "style_intent": "string",
  "mood": "string",
  "image_strategy": "gemini_generated|product_photo_featured|hybrid",
  "composition": "string",
  "use_product_photo": true,
  "text_on_image": "none|minimal",
  "gemini_image_prompt": "Detailed visual generation prompt for an image model",
  "platform_overrides": {{
    "facebook": {{"composition": "string", "visual_direction": "string"}},
    "instagram": {{"composition": "string", "visual_direction": "string"}},
    "linkedin": {{"composition": "string", "visual_direction": "string"}}
  }}
}}"""
    return _generate_json_with_gemini(prompt, model_candidates)


def _run_agent_conference(
    model_candidates: list[str],
    *,
    topic: str,
    funnel_stage: str,
    selected_hook: str,
    selected_cta: str,
    content: dict,
    visual_plan: dict,
    product_name: str,
    product_metrics: str,
) -> dict:
    prompt = f"""{AGENT_CONFERENCE_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Hook: {selected_hook}
- CTA: {selected_cta}
- Product: {product_name or 'N/A'}
- Product measurable specs: {product_metrics or 'N/A'}

Draft copy:
- wp_title: {str(content.get('wp_title', ''))[:200]}
- wp_excerpt: {str(content.get('wp_excerpt', ''))[:220]}
- fb_caption: {str(content.get('fb_caption', ''))[:700]}
- ig_caption: {str(content.get('ig_caption', ''))[:700]}
- li_text: {str(content.get('li_text', ''))[:700]}

Current visual plan:
{json.dumps(visual_plan, ensure_ascii=True)}

Return ONLY valid JSON with this exact shape:
{{
  "copywriter_feedback": ["string", "string"],
  "visual_director_feedback": ["string", "string"],
  "product_truth_feedback": ["string", "string"],
  "platform_editor_feedback": ["string", "string"],
  "collective_actions": ["string", "string", "string"],
  "refined": {{
    "hook": "optional refined hook",
    "cta": "optional refined CTA",
    "gemini_image_prompt": "optional refined visual prompt",
    "image_strategy": "gemini_generated|product_photo_featured|hybrid|",
    "fb_caption": "optional refined Facebook caption",
    "ig_caption": "optional refined Instagram caption",
    "li_text": "optional refined LinkedIn caption"
  }}
}}"""
    result = _generate_json_with_gemini(prompt, model_candidates)
    return result if isinstance(result, dict) else {}


def _apply_conference_refinements(content: dict, visual_plan: dict, conference: dict) -> tuple[dict, dict]:
    refined = conference.get("refined", {}) if isinstance(conference, dict) else {}
    if not isinstance(refined, dict):
        return content, visual_plan

    hook = str(refined.get("hook", "")).strip()
    cta = str(refined.get("cta", "")).strip()
    fb = str(refined.get("fb_caption", "")).strip()
    ig = str(refined.get("ig_caption", "")).strip()
    li = str(refined.get("li_text", "")).strip()
    image_prompt = str(refined.get("gemini_image_prompt", "")).strip()
    image_strategy = str(refined.get("image_strategy", "")).strip().lower()

    if hook:
        content["selected_hook"] = hook
    if cta:
        content["selected_cta"] = cta
    if fb:
        content["fb_caption"] = fb
    if ig:
        content["ig_caption"] = ig
    if li:
        content["li_text"] = li

    if image_prompt:
        visual_plan["gemini_image_prompt"] = image_prompt
    if image_strategy in {"gemini_generated", "product_photo_featured", "hybrid"}:
        visual_plan["image_strategy"] = image_strategy

    return content, visual_plan


def _run_pre_generation_conference(
        model_candidates: list[str],
        *,
        topic: str,
        funnel_stage: str,
        stage_objective: str,
        selected_hook: str,
        selected_cta: str,
        product_name: str,
        product_categories: str,
        product_metrics: str,
        recent_hooks: list[str],
        recent_topics: list[str],
        recent_ctas: list[str],
) -> dict:
        prompt = f"""{PREGEN_CONFERENCE_BRIEF}

Run context:
- Topic: {topic}
- Funnel stage: {funnel_stage}
- Stage objective: {stage_objective}
- Current hook candidate: {selected_hook}
- Current CTA candidate: {selected_cta}
- Product: {product_name or 'N/A'}
- Product categories: {product_categories or 'N/A'}
- Product measurable specs: {product_metrics or 'N/A'}
- Recent hooks: {recent_hooks}
- Recent topics: {recent_topics}
- Recent CTAs: {recent_ctas}

Return ONLY valid JSON with this exact shape:
{{
    "recommended_hook": "string",
    "recommended_cta": "string",
    "primary_angle": "string",
    "visual_focus": "string",
    "platform_notes": {{
        "facebook": "string",
        "instagram": "string",
        "linkedin": "string"
    }},
    "collective_actions": ["string", "string", "string"],
    "risk_checks": ["string", "string"]
}}"""
        result = _generate_json_with_gemini(prompt, model_candidates)
        return result if isinstance(result, dict) else {}


def _default_pre_generation_conference(selected_hook: str, selected_cta: str) -> dict:
    return {
        "recommended_hook": selected_hook,
        "recommended_cta": selected_cta,
        "primary_angle": "practical education plus clear next step",
        "visual_focus": "real-world preparedness scenario",
        "platform_notes": {
            "facebook": "educational and conversational",
            "instagram": "visual-first concise delivery",
            "linkedin": "framework-driven professional tone",
        },
        "collective_actions": [
            "prioritize clarity over hype",
            "use verifiable product facts only",
            "end with one direct CTA",
        ],
        "risk_checks": [
            "no unsupported claims",
            "no repeated hook framing from recent runs",
        ],
    }


def _apply_control_plane_metadata(content: dict, run_context: dict, gate_records: list[dict]) -> dict:
    global_gate = evaluate_global_gates(gate_records)
    content["agent_control_plane"] = {
        "schema_version": SCHEMAS_VERSION,
        "run_context": run_context,
        "gates": gate_records,
        "global_gate": global_gate,
    }
    blocked = not bool(global_gate.get("passed", False))
    content["orchestration_blocked"] = blocked
    if blocked:
        for gate in global_gate.get("blocking_failures", []):
            gate_id = str(gate.get("gate_id", "unknown_gate"))
            reasons = gate.get("reasons", [])
            if isinstance(reasons, list):
                for reason in reasons:
                    content.setdefault("validation_errors", []).append(f"{gate_id}:{reason}")
            content.setdefault("quality_warnings", []).append(f"orchestration_gate_failed:{gate_id}")
    return content


def generate(slot: str, *, funnel_stage_override: str = "", product_id_override: str = "") -> dict:
    ensure_runtime_data()
    preferred_model = os.environ.get("GEMINI_MODEL", "").strip()
    model_candidates = [
        preferred_model,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    model_candidates = [m for m in model_candidates if m]
    preferred_visual_director_model = os.environ.get("GEMINI_VISUAL_DIRECTOR_MODEL", "").strip()
    visual_director_candidates = [
        preferred_visual_director_model,
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ]
    visual_director_candidates = [m for m in visual_director_candidates if m]

    queue = load_topic_queue()
    history = load_history()
    funnel_config = load_funnel_config()
    cta_library = load_cta_library()
    preview_stage = _normalize_funnel_stage_override(funnel_stage_override) or stage_for_slot(
        slot,
        history=history,
        funnel_config=funnel_config,
    )
    preferred_pillars = _preferred_pillars_for_stage(preview_stage)
    pillar, topic, topic_hash = _pick_topic(queue, history, preferred_pillars=preferred_pillars)
    products = load_products()
    business_profile = _build_business_profile(products)
    product = _pick_product_by_id(products, product_id_override) or _pick_product(products, history)
    marketing_strategy = _load_latest_marketing_strategy()
    brand_profile = load_brand_profile()
    selling_ideology = load_selling_ideology()
    structured_campaign = _load_latest_structured_campaign()
    weekly_sequence = select_weekly_sequence(slot, now_utc=datetime.now(timezone.utc))
    funnel_stage = _normalize_funnel_stage_override(funnel_stage_override) or stage_for_slot(
        slot,
        history=history,
        funnel_config=funnel_config,
    )
    stage_meta = funnel_config.get("stages", {}).get(funnel_stage, {}) if isinstance(funnel_config, dict) else {}

    hook_window = int(os.environ.get("ANTI_REPEAT_HOOK_WINDOW", "30"))
    cta_window = int(os.environ.get("ANTI_REPEAT_CTA_WINDOW", "30"))
    recent_hook_hashes = {
        str(p.get("hook_hash", ""))
        for p in history.get("posts", [])[-hook_window:]
        if isinstance(p, dict)
    }
    recent_cta_hashes = {
        str(p.get("cta_hash", ""))
        for p in history.get("posts", [])[-cta_window:]
        if isinstance(p, dict)
    }

    product_name = product.get("name", "") if product else ""
    product_id = product.get("id", "") if product else ""
    product_sku = product.get("sku", "") if product else ""
    product_price = product.get("price", "") if product else ""
    product_sale_price = product.get("sale_price", "") if product else ""
    product_metrics = ", ".join(product.get("metrics", [])[:5]) if product else ""
    product_categories = ", ".join(product.get("categories", [])[:3]) if product else ""
    product_facts = product.get("fact_snippet", "") if product else ""
    product_in_stock = product.get("in_stock", "") if product else ""
    product_stock = product.get("stock", "") if product else ""
    product_url = product.get("product_url", "") if product else ""
    talking_point = _build_talking_point(topic=topic, funnel_stage=funnel_stage, product=product)

    marketing_context = ""
    selected_hook = (weekly_sequence.get("hook") or "").strip()
    selected_cta = (weekly_sequence.get("primary_cta") or "").strip()
    audience_segment = (weekly_sequence.get("segment") or structured_campaign.get("audience_segment") or "Prepared Buyer").strip()
    campaign_id = str(structured_campaign.get("campaign_id", "")).strip()
    destination_url = str(structured_campaign.get("destination_url", SITE_URL)).strip() or SITE_URL

    brand_name = str(brand_profile.get("brand_name") or "Infenergy Power").strip() or "Infenergy Power"
    brand_positioning = str(brand_profile.get("positioning") or "portable power preparedness brand").strip()
    brand_mission = str(brand_profile.get("mission") or "").strip()
    brand_personality_name = str(brand_profile.get("personality_name") or "Calm Strength").strip() or "Calm Strength"
    brand_personality_traits = _dedupe_str_list(brand_profile.get("personality_traits", []))
    brand_tone_rules = _dedupe_str_list(brand_profile.get("tone_rules", []))
    brand_voice_rules_db = _dedupe_str_list(brand_profile.get("voice_rules", []))
    brand_approved_phrases = _dedupe_str_list(brand_profile.get("approved_phrases", []))
    brand_words_to_use = _dedupe_str_list(brand_profile.get("words_to_use", []))
    brand_words_to_avoid = _dedupe_str_list(brand_profile.get("words_to_avoid", []))
    brand_forbidden_phrases = _dedupe_str_list(brand_profile.get("forbidden_phrases", []))
    brand_core_values = _dedupe_str_list(brand_profile.get("core_values", []))
    brand_trust_close = str(brand_profile.get("trust_close") or "").strip()
    brand_audience_summary = str(brand_profile.get("audience_summary") or "").strip()

    ideology_framework_mode = str(selling_ideology.get("framework_mode") or "mixed_with_campaign_overlay").strip()
    ideology_primary_conversion = str(selling_ideology.get("primary_conversion") or "direct_checkout").strip()
    ideology_tone_blend = str(selling_ideology.get("tone_blend") or "calm_protective_plus_assertive_urgent").strip()
    ideology_value_lens = str(selling_ideology.get("value_lens") or "benefit_first").strip()
    ideology_message_filter = str(selling_ideology.get("message_filter") or "no_nonconverting_copy").strip()
    ideology_cta_mode = str(selling_ideology.get("cta_mode") or "checkout_first").strip()
    ideology_proof_rule = str(selling_ideology.get("proof_rule") or "scenario_plus_spec_evidence").strip()
    ideology_core_promise = str(selling_ideology.get("core_promise") or "reliable_peace_of_mind").strip()
    ideology_banned_phrases = _dedupe_str_list(selling_ideology.get("banned_phrases", []))
    ideology_pillars = _dedupe_str_list(selling_ideology.get("pillar_messages", []))

    preferred_hooks = []
    if selected_hook:
        preferred_hooks.append(selected_hook)

    if marketing_strategy:
        founder_manifesto = marketing_strategy.get("brand_profile", {}).get("founder_manifesto", {})
        if not isinstance(founder_manifesto, dict):
            founder_manifesto = {}
        approved_sales = founder_manifesto.get("approved_sales_verbiage", {}) if isinstance(founder_manifesto.get("approved_sales_verbiage", {}), dict) else {}
        value_narrative = marketing_strategy.get("copy", {}).get("value_narrative", {})
        if not isinstance(value_narrative, dict):
            value_narrative = {}
        voice_rules = marketing_strategy.get("voice", {}).get("voice_rules", [])
        segments = marketing_strategy.get("audience", {}).get("segments", [])
        core_offers = marketing_strategy.get("offer", {}).get("core_offers", [])
        social_hooks = marketing_strategy.get("copy", {}).get("social_hooks", [])
        cta_bank = marketing_strategy.get("copy", {}).get("cta_bank", [])
        preferred_hooks.extend([h for h in social_hooks if isinstance(h, str)])
        combined_voice_rules = _dedupe_str_list((voice_rules if isinstance(voice_rules, list) else []) + brand_tone_rules + brand_voice_rules_db)
        combined_approved_phrases = _dedupe_str_list(brand_approved_phrases + (approved_sales.get("core_phrases", []) if isinstance(approved_sales.get("core_phrases", []), list) else []))
        selected_cta = choose_cta_for_stage(
            stage=funnel_stage,
            preferred=selected_cta or (cta_bank[0] if cta_bank else ""),
            cta_library=cta_library,
            recent_cta_hashes=recent_cta_hashes,
        )

        marketing_context = (
            "MARKETING TEAM DIRECTIVES:\n"
            f"- Brand name: {brand_name}\n"
            f"- Voice rules: {combined_voice_rules[:7]}\n"
            f"- Priority audience segments: {segments[:3]}\n"
            f"- Audience summary: {brand_audience_summary}\n"
            f"- Core offers: {core_offers[:4]}\n"
            f"- Proven hook styles: {social_hooks[:3]}\n"
            f"- Preferred CTAs: {cta_bank[:3]}\n"
            f"- Founder mission: {brand_mission or founder_manifesto.get('mission', '')}\n"
            f"- Brand values: {brand_core_values or founder_manifesto.get('core_values', [])}\n"
            f"- Brand personality: {brand_personality_name} | {brand_personality_traits}\n"
            f"- Approved sales language: {combined_approved_phrases[:8]}\n"
            f"- Words to emphasize: {brand_words_to_use[:10]}\n"
            f"- Words/phrases to avoid: {brand_words_to_avoid[:10]}\n"
            f"- Value narrative: {value_narrative}\n"
            f"- This slot hook direction: {selected_hook}\n"
            f"- This slot CTA direction: {selected_cta}\n"
            f"- Funnel stage: {funnel_stage}\n"
            f"- Funnel objective: {stage_meta.get('objective', '')}\n"
            "Use this as strategy guidance while still tailoring to the specific topic and product.\n"
        )
    else:
        preferred_hooks.extend([f"Most people misunderstand {topic.lower()}", "The hidden cost most buyers miss"])
        selected_cta = choose_cta_for_stage(
            stage=funnel_stage,
            preferred=selected_cta,
            cta_library=cta_library,
            recent_cta_hashes=recent_cta_hashes,
        )

    hook_choice = select_hook(
        topic=topic,
        product_name=product_name or "INF Energy Power solution",
        audience_segment=audience_segment,
        recent_hook_hashes=recent_hook_hashes,
        preferred_hooks=preferred_hooks,
    )
    selected_hook = str(hook_choice.get("hook", selected_hook)).strip() or selected_hook
    hook_type = str(hook_choice.get("hook_type", "question")).strip() or "question"

    slot_guidance = {
        "morning": (
            "MORNING — EDUCATION. Open with a surprising or counterintuitive fact. "
            "Teach one genuinely useful concept the reader can act on today. "
            "Use real numbers, comparisons, or analogies. No fluff. End with a thought-provoking question."
        ),
        "midday": (
            "MIDDAY — PROOF. Lead with a specific, believable result. "
            "Include at least one concrete number (dollar amount, percentage, timeframe). "
            "Tell a mini-story: situation → problem → solution → outcome. "
            "Make the reader feel 'that could be me.' End with a credibility statement."
        ),
        "evening": (
            "EVENING — CTA. Create genuine urgency around a real reason to act now "
            "(limited slots, seasonal incentives, rising utility rates). "
            "Be direct and specific about the next step. Tell them exactly what happens when they reach out. "
            "One clear CTA only. No vague 'learn more.'"
        ),
    }.get(slot, "educational")

    recent_hooks = _recent_unique_values(history, "selected_hook", limit=8)
    recent_products = _recent_unique_values(history, "product_name", limit=6)
    recent_ctas = _recent_unique_values(history, "selected_cta", limit=8)
    recent_topics = _recent_unique_values(history, "topic", limit=8)
    run_context = build_run_context(
        slot=slot,
        topic=topic,
        funnel_stage=funnel_stage,
        stage_objective=str(stage_meta.get("objective", "")),
        audience_segment=audience_segment,
        campaign_id=campaign_id,
        destination_url=destination_url,
        product_id=product_id,
        product_name=product_name,
        selected_hook=selected_hook,
        selected_cta=selected_cta,
        recent_hooks=recent_hooks,
        recent_topics=recent_topics,
        recent_ctas=recent_ctas,
    )
    gate_records: list[dict] = []
    conference_model = os.environ.get("GEMINI_CONFERENCE_MODEL", "").strip()

    phase2_enabled = os.environ.get("ENABLE_PHASE2_CREATIVE_STACK", "true").strip().lower() not in {"0", "false", "no"}
    phase2_stack = _default_phase2_stack(
        selected_hook=selected_hook,
        selected_cta=selected_cta,
        audience_segment=audience_segment,
        topic=topic,
        funnel_stage=funnel_stage,
    )
    if phase2_enabled:
        phase2_candidates = [preferred_model, conference_model if "conference_model" in locals() else "", "gemini-2.5-pro", "gemini-2.5-flash"]
        phase2_candidates = [m for m in phase2_candidates if m]
        phase2_raw = _run_phase2_creative_stack(
            phase2_candidates,
            topic=topic,
            funnel_stage=funnel_stage,
            stage_objective=str(stage_meta.get("objective", "")),
            selected_hook=selected_hook,
            selected_cta=selected_cta,
            audience_segment=audience_segment,
            product_name=product_name,
            product_categories=product_categories,
            product_metrics=product_metrics,
            recent_hooks=recent_hooks,
            recent_topics=recent_topics,
        )
        validated_ideation, ideation_errors = validate_agent_output("ideation_divergence", phase2_raw.get("ideation_divergence", {}))
        validated_psycho, psycho_errors = validate_agent_output("audience_psychographics", phase2_raw.get("audience_psychographics", {}))
        validated_narrative, narrative_errors = validate_agent_output("narrative_architect", phase2_raw.get("narrative_architect", {}))
        validated_voice, voice_errors = validate_agent_output("platform_voice_calibrator", phase2_raw.get("platform_voice_calibrator", {}))
        validated_hook_test, hook_test_errors = validate_agent_output("hook_stress_test", phase2_raw.get("hook_stress_test", {}))

        gate_records.append(build_gate_record(gate_id="phase2_ideation_divergence_schema", passed=len(ideation_errors) == 0, severity="error", reasons=ideation_errors, details={"enabled": True}))
        gate_records.append(build_gate_record(gate_id="phase2_audience_psychographics_schema", passed=len(psycho_errors) == 0, severity="error", reasons=psycho_errors, details={"enabled": True}))
        gate_records.append(build_gate_record(gate_id="phase2_narrative_architect_schema", passed=len(narrative_errors) == 0, severity="error", reasons=narrative_errors, details={"enabled": True}))
        gate_records.append(build_gate_record(gate_id="phase2_platform_voice_calibrator_schema", passed=len(voice_errors) == 0, severity="error", reasons=voice_errors, details={"enabled": True}))
        gate_records.append(build_gate_record(gate_id="phase2_hook_stress_test_schema", passed=len(hook_test_errors) == 0, severity="error", reasons=hook_test_errors, details={"enabled": True}))

        if not ideation_errors:
            phase2_stack["ideation_divergence"] = validated_ideation
        if not psycho_errors:
            phase2_stack["audience_psychographics"] = validated_psycho
        if not narrative_errors:
            phase2_stack["narrative_architect"] = validated_narrative
        if not voice_errors:
            phase2_stack["platform_voice_calibrator"] = validated_voice
        if not hook_test_errors:
            phase2_stack["hook_stress_test"] = validated_hook_test
    else:
        gate_records.append(build_gate_record(gate_id="phase2_ideation_divergence_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))
        gate_records.append(build_gate_record(gate_id="phase2_audience_psychographics_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))
        gate_records.append(build_gate_record(gate_id="phase2_narrative_architect_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))
        gate_records.append(build_gate_record(gate_id="phase2_platform_voice_calibrator_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))
        gate_records.append(build_gate_record(gate_id="phase2_hook_stress_test_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))

    selected_hook = str(phase2_stack.get("hook_stress_test", {}).get("recommended_hook", "")).strip() or selected_hook
    selected_cta = str(phase2_stack.get("audience_psychographics", {}).get("cta_framing", "")).strip() or selected_cta
    audience_segment = str(phase2_stack.get("audience_psychographics", {}).get("primary_segment", "")).strip() or audience_segment
    run_context["draft_direction"]["selected_hook"] = selected_hook
    run_context["draft_direction"]["selected_cta"] = selected_cta
    run_context["audience_segment"] = audience_segment

    conference_candidates = [conference_model, preferred_visual_director_model, preferred_model, "gemini-2.5-pro", "gemini-2.5-flash"]
    conference_candidates = [m for m in conference_candidates if m]

    phase3_enabled = os.environ.get("ENABLE_PHASE3_SAFETY_STACK", "true").strip().lower() not in {"0", "false", "no"}
    phase3_stack = _default_phase3_safety_stack(
        selected_hook=selected_hook,
        selected_cta=selected_cta,
        recent_topics=recent_topics,
    )
    if phase3_enabled:
        phase3_candidates = [preferred_model, conference_model, "gemini-2.5-pro", "gemini-2.5-flash"]
        phase3_candidates = [m for m in phase3_candidates if m]
        preview_for_safety = (
            f"Topic: {topic}\n"
            f"Hook: {selected_hook}\n"
            f"CTA: {selected_cta}\n"
            f"Funnel stage: {funnel_stage}\n"
            f"Objective: {stage_meta.get('objective', '')}\n"
        )
        phase3_raw = _run_phase3_safety_stack(
            phase3_candidates,
            topic=topic,
            funnel_stage=funnel_stage,
            selected_hook=selected_hook,
            selected_cta=selected_cta,
            recent_hooks=recent_hooks,
            recent_topics=recent_topics,
            content_preview=preview_for_safety,
        )
        precision, precision_errors = validate_agent_output("precision_claims_verifier", phase3_raw.get("precision_claims_verifier", {}))
        compliance, compliance_errors = validate_agent_output("compliance_policy_sentinel", phase3_raw.get("compliance_policy_sentinel", {}))
        novelty, novelty_errors = validate_agent_output("semantic_novelty", phase3_raw.get("semantic_novelty", {}))

        gate_records.append(build_gate_record(gate_id="phase3_precision_claims_schema", passed=len(precision_errors) == 0, severity="error", reasons=precision_errors, details={"enabled": True}))
        gate_records.append(build_gate_record(gate_id="phase3_compliance_sentinel_schema", passed=len(compliance_errors) == 0, severity="error", reasons=compliance_errors, details={"enabled": True}))
        gate_records.append(build_gate_record(gate_id="phase3_semantic_novelty_schema", passed=len(novelty_errors) == 0, severity="error", reasons=novelty_errors, details={"enabled": True}))

        if not precision_errors:
            phase3_stack["precision_claims_verifier"] = precision
        if not compliance_errors:
            phase3_stack["compliance_policy_sentinel"] = compliance
        if not novelty_errors:
            phase3_stack["semantic_novelty"] = novelty

        if not bool(phase3_stack.get("precision_claims_verifier", {}).get("passed", True)):
            gate_records.append(
                build_gate_record(
                    gate_id="phase3_precision_claims_pass",
                    passed=False,
                    severity="error",
                    reasons=list(phase3_stack.get("precision_claims_verifier", {}).get("issues", [])) or ["precision_claims_failed"],
                    details={},
                )
            )

        risk_level = str(phase3_stack.get("compliance_policy_sentinel", {}).get("risk_level", "low")).strip().lower()
        if risk_level == "high":
            gate_records.append(
                build_gate_record(
                    gate_id="phase3_compliance_risk",
                    passed=False,
                    severity="error",
                    reasons=list(phase3_stack.get("compliance_policy_sentinel", {}).get("required_actions", [])) or ["high_compliance_risk"],
                    details={"risk_level": risk_level},
                )
            )

        novelty_min = float(os.environ.get("NOVELTY_MIN_SCORE", "0.62"))
        novelty_score = float(phase3_stack.get("semantic_novelty", {}).get("novelty_score", 1.0) or 1.0)
        if novelty_score < novelty_min:
            gate_records.append(
                build_gate_record(
                    gate_id="phase3_semantic_novelty_min",
                    passed=False,
                    severity="error",
                    reasons=list(phase3_stack.get("semantic_novelty", {}).get("rewrite_guidance", [])) or ["low_semantic_novelty"],
                    details={"novelty_score": novelty_score, "min": novelty_min},
                )
            )
    else:
        gate_records.append(build_gate_record(gate_id="phase3_precision_claims_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))
        gate_records.append(build_gate_record(gate_id="phase3_compliance_sentinel_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))
        gate_records.append(build_gate_record(gate_id="phase3_semantic_novelty_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))

    phase4_enabled = os.environ.get("ENABLE_PHASE4_OPTIMIZATION_STACK", "true").strip().lower() not in {"0", "false", "no"}
    phase4_stack = _default_phase4_optimization_stack(
        selected_cta=selected_cta,
        funnel_stage=funnel_stage,
    )
    if phase4_enabled:
        phase4_candidates = [preferred_model, conference_model, preferred_visual_director_model, "gemini-2.5-pro", "gemini-2.5-flash"]
        phase4_candidates = [m for m in phase4_candidates if m]
        phase4_raw = _run_phase4_optimization_stack(
            phase4_candidates,
            topic=topic,
            funnel_stage=funnel_stage,
            selected_hook=selected_hook,
            selected_cta=selected_cta,
            audience_segment=audience_segment,
        )
        visual_opt, visual_opt_errors = validate_agent_output("visual_strategy", phase4_raw.get("visual_strategy", {}))
        cta_opt, cta_opt_errors = validate_agent_output("cta_optimization", phase4_raw.get("cta_optimization", {}))
        gate_records.append(build_gate_record(gate_id="phase4_visual_strategy_schema", passed=len(visual_opt_errors) == 0, severity="error", reasons=visual_opt_errors, details={"enabled": True}))
        gate_records.append(build_gate_record(gate_id="phase4_cta_optimization_schema", passed=len(cta_opt_errors) == 0, severity="error", reasons=cta_opt_errors, details={"enabled": True}))
        if not visual_opt_errors:
            phase4_stack["visual_strategy"] = visual_opt
        if not cta_opt_errors:
            phase4_stack["cta_optimization"] = cta_opt
    else:
        gate_records.append(build_gate_record(gate_id="phase4_visual_strategy_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))
        gate_records.append(build_gate_record(gate_id="phase4_cta_optimization_schema", passed=True, severity="warning", reasons=[], details={"enabled": False}))

    selected_cta = str(phase4_stack.get("cta_optimization", {}).get("recommended_cta", "")).strip() or selected_cta
    run_context["draft_direction"]["selected_cta"] = selected_cta

    pregen_enabled = os.environ.get("ENABLE_PREGEN_CONFERENCE", "true").strip().lower() not in {"0", "false", "no"}
    pre_generation_conference = {}
    if pregen_enabled:
        pre_generation_conference_raw = _run_pre_generation_conference(
            conference_candidates,
            topic=topic,
            funnel_stage=funnel_stage,
            stage_objective=str(stage_meta.get("objective", "")),
            selected_hook=selected_hook,
            selected_cta=selected_cta,
            product_name=product_name,
            product_categories=product_categories,
            product_metrics=product_metrics,
            recent_hooks=recent_hooks,
            recent_topics=recent_topics,
            recent_ctas=recent_ctas,
        )
        pre_generation_conference, pregen_errors = validate_agent_output("pre_generation_conference", pre_generation_conference_raw)
        if pregen_errors:
            pre_generation_conference = _default_pre_generation_conference(selected_hook, selected_cta)
            gate_records.append(
                build_gate_record(
                    gate_id="pre_generation_conference_schema",
                    passed=True,
                    severity="warning",
                    reasons=[],
                    details={"enabled": True, "fallback_applied": True, "source_errors": pregen_errors},
                )
            )
        else:
            gate_records.append(
                build_gate_record(
                    gate_id="pre_generation_conference_schema",
                    passed=True,
                    severity="error",
                    reasons=[],
                    details={"enabled": True, "fallback_applied": False},
                )
            )
        selected_hook = str(pre_generation_conference.get("recommended_hook", "")).strip() or selected_hook
        selected_cta = str(pre_generation_conference.get("recommended_cta", "")).strip() or selected_cta
    else:
        gate_records.append(
            build_gate_record(
                gate_id="pre_generation_conference_schema",
                passed=True,
                severity="warning",
                reasons=[],
                details={"enabled": False},
            )
        )

    pregen_context = ""
    if isinstance(pre_generation_conference, dict) and pre_generation_conference:
        pregen_context = (
            "PRE-GENERATION TEAM MEETING SUMMARY:\n"
            f"- Primary angle: {str(pre_generation_conference.get('primary_angle', ''))}\n"
            f"- Visual focus: {str(pre_generation_conference.get('visual_focus', ''))}\n"
            f"- Collective actions: {pre_generation_conference.get('collective_actions', [])}\n"
            f"- Risk checks: {pre_generation_conference.get('risk_checks', [])}\n"
            f"- Platform notes: {pre_generation_conference.get('platform_notes', {})}\n"
        )

    phase2_context = (
        "PHASE 2 CREATIVE INTELLIGENCE OUTPUTS:\n"
        f"- Ideation winner angle: {phase2_stack.get('ideation_divergence', {}).get('winner_angle', '')}\n"
        f"- Ideation novelty rationale: {phase2_stack.get('ideation_divergence', {}).get('novelty_rationale', '')}\n"
        f"- Psychographics emotional driver: {phase2_stack.get('audience_psychographics', {}).get('emotional_driver', '')}\n"
        f"- Psychographics core objection: {phase2_stack.get('audience_psychographics', {}).get('core_objection', '')}\n"
        f"- Psychographics trust trigger: {phase2_stack.get('audience_psychographics', {}).get('trust_trigger', '')}\n"
        f"- Narrative sequence: {phase2_stack.get('narrative_architect', {}).get('narrative_sequence', [])}\n"
        f"- Narrative must include: {phase2_stack.get('narrative_architect', {}).get('must_include', [])}\n"
        f"- Platform voice notes: {phase2_stack.get('platform_voice_calibrator', {})}\n"
        f"- Hook stress-test reason: {phase2_stack.get('hook_stress_test', {}).get('reason', '')}\n"
    )
    phase3_context = (
        "PHASE 3 PRECISION AND SAFETY OUTPUTS:\n"
        f"- Precision passed: {phase3_stack.get('precision_claims_verifier', {}).get('passed', True)}\n"
        f"- Precision issues: {phase3_stack.get('precision_claims_verifier', {}).get('issues', [])}\n"
        f"- Compliance risk: {phase3_stack.get('compliance_policy_sentinel', {}).get('risk_level', 'low')}\n"
        f"- Compliance actions: {phase3_stack.get('compliance_policy_sentinel', {}).get('required_actions', [])}\n"
        f"- Novelty score: {phase3_stack.get('semantic_novelty', {}).get('novelty_score', 1.0)}\n"
        f"- Novelty guidance: {phase3_stack.get('semantic_novelty', {}).get('rewrite_guidance', [])}\n"
    )
    phase4_context = (
        "PHASE 4 VISUAL AND CTA OPTIMIZATION OUTPUTS:\n"
        f"- Visual objective: {phase4_stack.get('visual_strategy', {}).get('visual_objective', '')}\n"
        f"- Visual composition adjustments: {phase4_stack.get('visual_strategy', {}).get('composition_adjustments', [])}\n"
        f"- Visual platform focus: {phase4_stack.get('visual_strategy', {}).get('platform_focus', {})}\n"
        f"- CTA recommendation: {phase4_stack.get('cta_optimization', {}).get('recommended_cta', selected_cta)}\n"
        f"- CTA alternates: {phase4_stack.get('cta_optimization', {}).get('alternates', [])}\n"
        f"- CTA friction note: {phase4_stack.get('cta_optimization', {}).get('friction_note', '')}\n"
    )

    ideology_context = (
        "SELLING IDEOLOGY DIRECTIVES:\n"
        f"- Framework mode: {ideology_framework_mode}\n"
        f"- Primary conversion: {ideology_primary_conversion}\n"
        f"- Tone blend: {ideology_tone_blend}\n"
        f"- Value lens: {ideology_value_lens}\n"
        f"- Message filter: {ideology_message_filter}\n"
        f"- CTA mode: {ideology_cta_mode}\n"
        f"- Proof rule: {ideology_proof_rule}\n"
        f"- Core promise: {ideology_core_promise}\n"
        f"- Pillars: {ideology_pillars}\n"
        f"- Banned phrases and patterns: {ideology_banned_phrases}\n"
    )

    visual_plan = _build_visual_plan_with_gemini(
        visual_director_candidates,
        topic=topic,
        funnel_stage=funnel_stage,
        stage_objective=str(stage_meta.get("objective", "")),
        selected_hook=selected_hook,
        selected_cta=selected_cta,
        product_name=product_name,
        product_categories=product_categories,
        product_metrics=product_metrics,
        has_product_image=bool((product or {}).get("image_url")),
    )
    if not isinstance(visual_plan, dict):
        visual_plan = {}
    visual_plan, visual_errors = validate_agent_output("visual_director", visual_plan)
    if visual_errors:
        visual_plan = _build_default_visual_plan(topic, funnel_stage, selected_hook, selected_cta, product)
        gate_records.append(
            build_gate_record(
                gate_id="visual_director_schema",
                passed=True,
                severity="warning",
                reasons=[],
                details={"agent": "visual_director", "fallback_applied": True, "source_errors": visual_errors},
            )
        )
    else:
        gate_records.append(
            build_gate_record(
                gate_id="visual_director_schema",
                passed=True,
                severity="error",
                reasons=[],
                details={"agent": "visual_director", "fallback_applied": False},
            )
        )
    visual_adjustments = phase4_stack.get("visual_strategy", {}).get("composition_adjustments", [])
    if isinstance(visual_adjustments, list) and visual_adjustments:
        visual_plan["phase4_composition_adjustments"] = [str(x) for x in visual_adjustments if str(x).strip()]

    prompt = f"""You are an expert content strategist and copywriter for {brand_name} ({SITE_URL}), a {brand_positioning}.

{CONVERSION_COPY_BRIEF}

BRAND VOICE: {brand_personality_name}. Traits: {brand_personality_traits or ['Direct', 'credible', 'genuinely helpful']}.
VOICE RULES: {brand_tone_rules or brand_voice_rules_db or ['Speak like a trusted expert neighbor, not a salesperson.']}
APPROVED VERBIAGE: {brand_approved_phrases[:10]}
TRUST CLOSER: {brand_trust_close or 'Use practical, non-hype language grounded in verified facts.'}
WORDS TO USE: {brand_words_to_use[:12]}
WORDS TO AVOID: {brand_words_to_avoid[:12]}
FORBIDDEN CLAIM PATTERNS: {brand_forbidden_phrases[:10]}
BRAND MISSION: {brand_mission}
BRAND VALUES: {brand_core_values}
AUDIENCE: {brand_audience_summary or 'Homeowners, families, travelers, and small businesses building practical power readiness.'}
TOPIC: {topic}
CONTENT DIRECTIVE: {slot_guidance}

PRODUCT CONTEXT (ground your content in these details when relevant):
- Product name: {product_name or 'N/A'}
- SKU: {product_sku or 'N/A'}
- Regular price: {product_price or 'N/A'}
- Sale price: {product_sale_price or 'N/A'}
- Categories: {product_categories or 'N/A'}
- Key measurable specs: {product_metrics or 'N/A'}
- Product facts excerpt: {product_facts or 'N/A'}

{marketing_context}

{pregen_context}

{phase2_context}

{phase3_context}

{phase4_context}

{ideology_context}

CAMPAIGN EXECUTION CONTEXT:
- Selected hook for this post: {selected_hook}
- Selected CTA for this post: {selected_cta}
- Funnel stage: {funnel_stage}
- Funnel objective: {stage_meta.get('objective', '')}
- Weekly plan row: {json.dumps(weekly_sequence) if weekly_sequence else 'none'}
- Recent hooks (avoid repetition): {recent_hooks}
- Recent products (avoid overusing): {recent_products}
- Recent CTAs (avoid repetition): {recent_ctas}
- Recent topics (avoid repetition): {recent_topics}

BUSINESS PROFILE (derived from published catalog):
- Focus: {business_profile.get('focus_statement', '')}
- Top categories: {business_profile.get('top_categories', [])}
- Keyword signals: {business_profile.get('keyword_signals', {})}
- Core offers: {business_profile.get('offers', [])}

POSITIONING GUARDRAILS:
- Do not frame this brand as a rooftop residential solar installation service.
- Only reference solar in the context of portable/foldable solar panels paired with portable power products.
- Forbidden phrasing examples: rooftop install, net metering savings, utility bill offset via home solar install, state solar tax-credit pitch.

QUALITY RULES — every piece must follow all of these:
1. Open with a hook that creates immediate curiosity or challenges a common assumption.
2. Name one concrete customer pain point in the first two lines.
3. Add one proof anchor based on verifiable specs or measurable details.
4. Include at least one specific number, stat, or real-world comparison that makes the content credible.
5. Deliver a genuine insight the reader cannot easily Google — a specific angle they haven't considered.
6. Write like a human expert, not a marketing team. Never use words like "revolutionize", "game-changer", or "unlock your potential."
7. Never make unverifiable guarantees. Use language like "many homeowners", "up to", "in most cases" where appropriate.
8. Every post must have a clear emotional payoff: relief, confidence, curiosity satisfied, or urgency to act.
9. If product context is available, use at least two concrete product facts or measurable specs naturally in the copy.
10. Do not invent model names, specs, prices, or warranties not present in the provided product context.
11. End with one frictionless next action that can be done today.

TALKING-POINT BRIEF FOR THIS RUN:
- Pain point: {talking_point.get('pain_point', '')}
- Proof anchor: {talking_point.get('proof_anchor', '')}
- Angle: {talking_point.get('angle', '')}
- First-step CTA: {talking_point.get('first_step', '')}

Return ONLY valid JSON with these exact keys (no markdown, no code fences):
{{
  "wp_title": "Specific, curiosity-driven SEO title under 65 characters — not generic",
  "wp_content": "Full blog post as clean HTML with <h2> subheadings. 450-550 words. Open strong, build a logical case, end with a clear next step. Include at least 2 specific data points or examples.",
  "wp_excerpt": "One punchy sentence under 160 characters that makes someone want to click",
  "fb_caption": "150-220 words. Conversational and personal. Open with a surprising statement or question. Include one specific number or fact. End with a genuine question that invites comments. 4-5 targeted hashtags on the last line only.",
  "ig_caption": "First line must be a scroll-stopping hook under 10 words. 120-160 words total. Specific, visual, and personal. 7-9 hashtags on the final line only — mix broad and niche.",
  "li_text": "180-260 words. Professional but not corporate. Open with a counterintuitive insight or bold statement. Build a tight logical argument. Include one specific data point. End with a direct, frictionless CTA — tell them exactly what the first step looks like."
}}"""

    content = _generate_json_with_gemini(prompt, model_candidates)

    if content is None:
        content = _build_fallback_content(slot, topic, product, marketing_strategy, talking_point=talking_point)
        content["topic"] = topic
        content["pillar"] = pillar
        content["topic_hash"] = topic_hash
        content["product_name"] = product_name
        content["product_id"] = product_id
        content["product_sku"] = product_sku
        content["product_price"] = product_price
        content["product_sale_price"] = product_sale_price
        content["product_metrics"] = product.get("metrics", []) if product else []
        content["product_facts"] = product_facts
        content["product_in_stock"] = product_in_stock
        content["product_stock"] = product_stock
        content["product_url"] = product_url
        content["product_image_url"] = product.get("image_url", "") if product else ""
        content["product_image_candidates"] = product.get("image_candidates", []) if product else []
        content["category_image_candidates"] = product.get("category_image_candidates", []) if product else []
        content["marketing_strategy_used"] = bool(marketing_strategy)
        content["marketing_bundle_used"] = bool(marketing_strategy)
        content["business_profile"] = business_profile
        content["selected_hook"] = selected_hook
        content["selected_cta"] = selected_cta
        content["selected_hook_type"] = hook_type
        content["hook_scores"] = hook_choice.get("component_scores", {})
        content["funnel_stage"] = funnel_stage
        content["funnel_stage_objective"] = stage_meta.get("objective", "")
        content["audience_segment"] = audience_segment
        content["campaign_id"] = campaign_id
        content["destination_url"] = destination_url
        content["weekly_plan_used"] = bool(weekly_sequence)
        content["hook_hash"] = stable_text_hash(selected_hook)
        content["cta_hash"] = stable_text_hash(selected_cta)

        cta_ok, cta_reason = cta_is_valid_for_stage(funnel_stage, selected_cta, destination_url)
        if not cta_ok:
            fallback_cta = choose_cta_for_stage(
                stage=funnel_stage,
                preferred="",
                cta_library=cta_library,
                recent_cta_hashes=recent_cta_hashes,
            )
            content["selected_cta"] = fallback_cta
            selected_cta = fallback_cta
            content["cta_hash"] = stable_text_hash(fallback_cta)
            content.setdefault("quality_warnings", []).append(f"cta_adjusted:{cta_reason}")
        content["date"] = str(date.today())
        content["slot"] = slot
        for key in ("fb_caption", "ig_caption", "li_text"):
            platform_name = "facebook" if key == "fb_caption" else "instagram" if key == "ig_caption" else "linkedin"
            content[key] = _enforce_conversion_caption(
                str(content.get(key, "")),
                talking_point,
                platform=platform_name,
            )
        for key in ("wp_content", "fb_caption", "ig_caption", "li_text"):
            cleaned, replaced = apply_claim_guardrails(str(content.get(key, "")))
            content[key] = cleaned
            if replaced:
                content.setdefault("claim_guardrail_replacements", []).extend(replaced)
        quality = score_generated_content(content)
        content["quality_score"] = quality.score
        content["quality_checks"] = quality.checks
        content["quality_warnings"] = quality.warnings

        post_id = uuid.uuid4().hex[:12]
        selected_hook = str(content.get("selected_hook", selected_hook))
        selected_cta = str(content.get("selected_cta", selected_cta))
        components = _build_post_components(topic, selected_hook, selected_cta, product, funnel_stage)
        platform_posts = _build_platform_posts(
            post_id=post_id,
            campaign_id=campaign_id,
            audience_segment=audience_segment,
            funnel_stage=funnel_stage,
            destination_url=destination_url,
            components=components,
            quality_score=float(content.get("quality_score", 0)),
        )
        for platform_name in ("facebook", "instagram", "linkedin"):
            post_payload = platform_posts.get(platform_name, {})
            if isinstance(post_payload, dict):
                post_payload["caption"] = _enforce_conversion_caption(
                    str(post_payload.get("caption", "")),
                    talking_point,
                    platform=platform_name,
                )
        platform_posts = normalize_brand_content(platform_posts)
        content = normalize_brand_content(content)
        content["post_id"] = post_id
        content["platform_posts"] = platform_posts
        content["scenario"] = components.get("situation", "")
        content["educational_lesson"] = components.get("info", "")
        content["fb_caption"] = platform_posts["facebook"]["caption"]
        content["ig_caption"] = platform_posts["instagram"]["caption"]
        content["li_text"] = platform_posts["linkedin"]["caption"]
        content["selected_cta"] = components["cta"]
        content["generated_visuals"] = generate_visuals(content, visual_plan=visual_plan)
        content["visual_plan"] = visual_plan
        content["pre_generation_conference"] = pre_generation_conference
        content["phase2_creative_stack"] = phase2_stack
        content["phase3_safety_stack"] = phase3_stack
        content["phase4_optimization_stack"] = phase4_stack
        phase7_packets = _build_phase7_conference_packets(
            run_context=run_context,
            pre_generation_conference=pre_generation_conference,
            phase2_stack=phase2_stack,
            phase3_stack=phase3_stack,
            phase4_stack=phase4_stack,
            conference_summary={},
        )
        phase7_packets_validated, phase7_errors = validate_agent_output("phase7_conference_packets", phase7_packets)
        gate_records.append(
            build_gate_record(
                gate_id="phase7_conference_packets_schema",
                passed=len(phase7_errors) == 0,
                severity="error",
                reasons=phase7_errors,
                details={"enabled": True},
            )
        )
        content["phase7_conference_packets"] = phase7_packets_validated if not phase7_errors else phase7_packets
        conv_passed, conv_reasons = _conversion_caption_gate(platform_posts, talking_point)
        gate_records.append(
            build_gate_record(
                gate_id="conversion_caption_enforcement",
                passed=conv_passed,
                severity="error",
                reasons=conv_reasons,
                details={"source": "fallback_builder"},
            )
        )
        content["creative_agents"] = {
            "copywriter": preferred_model or "gemini-2.5-flash",
            "visual_director": (preferred_visual_director_model or "gemini-2.5-pro"),
            "ideation_divergence": (preferred_model or "gemini-2.5-flash"),
            "audience_psychographics": (preferred_model or "gemini-2.5-flash"),
            "narrative_architect": (preferred_model or "gemini-2.5-flash"),
            "platform_voice_calibrator": (preferred_model or "gemini-2.5-flash"),
            "hook_stress_test": (preferred_model or "gemini-2.5-flash"),
            "precision_claims_verifier": (preferred_model or "gemini-2.5-flash"),
            "compliance_policy_sentinel": (preferred_model or "gemini-2.5-flash"),
            "semantic_novelty": (preferred_model or "gemini-2.5-flash"),
            "visual_strategy": (preferred_model or "gemini-2.5-flash"),
            "cta_optimization": (preferred_model or "gemini-2.5-flash"),
            "pre_generation_conference": (conference_model or preferred_visual_director_model or "gemini-2.5-pro"),
            "image_model": os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        }
        gate_records.append(
            build_gate_record(
                gate_id="copywriter_payload_minimum",
                passed=True,
                severity="error",
                reasons=[],
                details={"source": "fallback_builder"},
            )
        )
        quality = score_generated_content(content)
        content["quality_score"] = quality.score
        content["quality_checks"] = quality.checks
        content["quality_warnings"] = quality.warnings
        for p in content["platform_posts"].values():
            p["quality_score"] = float(quality.score)
        content = _apply_control_plane_metadata(content, run_context, gate_records)
        return content

    content["topic"] = topic
    content["pillar"] = pillar
    content["topic_hash"] = topic_hash
    content["product_name"] = product_name
    content["product_id"] = product_id
    content["product_sku"] = product_sku
    content["product_price"] = product_price
    content["product_sale_price"] = product_sale_price
    content["product_metrics"] = product.get("metrics", []) if product else []
    content["product_facts"] = product_facts
    content["product_in_stock"] = product_in_stock
    content["product_stock"] = product_stock
    content["product_url"] = product_url
    content["product_image_url"] = product.get("image_url", "") if product else ""
    content["product_image_candidates"] = product.get("image_candidates", []) if product else []
    content["category_image_candidates"] = product.get("category_image_candidates", []) if product else []
    content["marketing_strategy_used"] = bool(marketing_strategy)
    content["marketing_bundle_used"] = bool(marketing_strategy)
    content["business_profile"] = business_profile
    content["selected_hook"] = selected_hook
    content["selected_cta"] = selected_cta
    content["selected_hook_type"] = hook_type
    content["hook_scores"] = hook_choice.get("component_scores", {})
    content["funnel_stage"] = funnel_stage
    content["funnel_stage_objective"] = stage_meta.get("objective", "")
    content["audience_segment"] = audience_segment
    content["campaign_id"] = campaign_id
    content["destination_url"] = destination_url
    content["weekly_plan_used"] = bool(weekly_sequence)
    content["hook_hash"] = stable_text_hash(selected_hook)
    content["cta_hash"] = stable_text_hash(selected_cta)

    cta_ok, cta_reason = cta_is_valid_for_stage(funnel_stage, selected_cta, destination_url)
    if not cta_ok:
        fallback_cta = choose_cta_for_stage(
            stage=funnel_stage,
            preferred="",
            cta_library=cta_library,
            recent_cta_hashes=recent_cta_hashes,
        )
        content["selected_cta"] = fallback_cta
        selected_cta = fallback_cta
        content["cta_hash"] = stable_text_hash(fallback_cta)
        content.setdefault("quality_warnings", []).append(f"cta_adjusted:{cta_reason}")
    content["date"] = str(date.today())
    content["slot"] = slot
    for key in ("fb_caption", "ig_caption", "li_text"):
        platform_name = "facebook" if key == "fb_caption" else "instagram" if key == "ig_caption" else "linkedin"
        content[key] = _enforce_conversion_caption(
            str(content.get(key, "")),
            talking_point,
            platform=platform_name,
        )
    for key in ("wp_content", "fb_caption", "ig_caption", "li_text"):
        cleaned, replaced = apply_claim_guardrails(str(content.get(key, "")))
        content[key] = cleaned
        if replaced:
            content.setdefault("claim_guardrail_replacements", []).extend(replaced)
    quality = score_generated_content(content)
    content["quality_score"] = quality.score
    content["quality_checks"] = quality.checks
    content["quality_warnings"] = quality.warnings

    conference_enabled = os.environ.get("ENABLE_AGENT_CONFERENCE", "true").strip().lower() not in {"0", "false", "no"}
    conference_summary = {}
    if conference_enabled:
        conference_summary_raw = _run_agent_conference(
            conference_candidates,
            topic=topic,
            funnel_stage=funnel_stage,
            selected_hook=str(content.get("selected_hook", selected_hook)),
            selected_cta=str(content.get("selected_cta", selected_cta)),
            content=content,
            visual_plan=visual_plan,
            product_name=product_name,
            product_metrics=product_metrics,
        )
        conference_summary, conference_errors = validate_agent_output("agent_conference", conference_summary_raw)
        if conference_errors:
            conference_summary = {}
            gate_records.append(
                build_gate_record(
                    gate_id="agent_conference_schema",
                    passed=True,
                    severity="warning",
                    reasons=[],
                    details={"enabled": True, "fallback_applied": True, "source_errors": conference_errors},
                )
            )
        else:
            gate_records.append(
                build_gate_record(
                    gate_id="agent_conference_schema",
                    passed=True,
                    severity="error",
                    reasons=[],
                    details={"enabled": True, "fallback_applied": False},
                )
            )
        content, visual_plan = _apply_conference_refinements(content, visual_plan, conference_summary)
        for key in ("fb_caption", "ig_caption", "li_text"):
            platform_name = "facebook" if key == "fb_caption" else "instagram" if key == "ig_caption" else "linkedin"
            content[key] = _enforce_conversion_caption(
                str(content.get(key, "")),
                talking_point,
                platform=platform_name,
            )
        # Re-apply guardrails after conference-driven refinements.
        for key in ("wp_content", "fb_caption", "ig_caption", "li_text"):
            cleaned, replaced = apply_claim_guardrails(str(content.get(key, "")))
            content[key] = cleaned
            if replaced:
                content.setdefault("claim_guardrail_replacements", []).extend(replaced)
    else:
        gate_records.append(
            build_gate_record(
                gate_id="agent_conference_schema",
                passed=True,
                severity="warning",
                reasons=[],
                details={"enabled": False},
            )
        )

    phase7_packets = _build_phase7_conference_packets(
        run_context=run_context,
        pre_generation_conference=pre_generation_conference,
        phase2_stack=phase2_stack,
        phase3_stack=phase3_stack,
        phase4_stack=phase4_stack,
        conference_summary=conference_summary,
    )
    phase7_packets_validated, phase7_errors = validate_agent_output("phase7_conference_packets", phase7_packets)
    gate_records.append(
        build_gate_record(
            gate_id="phase7_conference_packets_schema",
            passed=len(phase7_errors) == 0,
            severity="error",
            reasons=phase7_errors,
            details={"enabled": True},
        )
    )

    post_id = uuid.uuid4().hex[:12]
    selected_hook = str(content.get("selected_hook", selected_hook))
    selected_cta = str(content.get("selected_cta", selected_cta))
    components = _build_post_components(topic, selected_hook, selected_cta, product, funnel_stage)
    platform_posts = _build_platform_posts(
        post_id=post_id,
        campaign_id=campaign_id,
        audience_segment=audience_segment,
        funnel_stage=funnel_stage,
        destination_url=destination_url,
        components=components,
        quality_score=float(content.get("quality_score", 0)),
        caption_overrides={
            "facebook": {"caption": str(content.get("fb_caption", "")), "cta": str(content.get("selected_cta", ""))},
            "instagram": {"caption": str(content.get("ig_caption", "")), "cta": str(content.get("selected_cta", ""))},
            "linkedin": {"caption": str(content.get("li_text", "")), "cta": str(content.get("selected_cta", ""))},
        },
    )
    for platform_name in ("facebook", "instagram", "linkedin"):
        post_payload = platform_posts.get(platform_name, {})
        if isinstance(post_payload, dict):
            post_payload["caption"] = _enforce_conversion_caption(
                str(post_payload.get("caption", "")),
                talking_point,
                platform=platform_name,
            )
    platform_posts = normalize_brand_content(platform_posts)
    content = normalize_brand_content(content)
    content["post_id"] = post_id
    content["platform_posts"] = platform_posts
    content["scenario"] = components.get("situation", "")
    content["educational_lesson"] = components.get("info", "")
    # Preserve publisher compatibility with existing flat keys.
    content["fb_caption"] = platform_posts["facebook"]["caption"]
    content["ig_caption"] = platform_posts["instagram"]["caption"]
    content["li_text"] = platform_posts["linkedin"]["caption"]
    content["selected_cta"] = components["cta"]
    content["generated_visuals"] = generate_visuals(content, visual_plan=visual_plan)
    content["visual_plan"] = visual_plan
    content["pre_generation_conference"] = pre_generation_conference
    content["phase2_creative_stack"] = phase2_stack
    content["phase3_safety_stack"] = phase3_stack
    content["phase4_optimization_stack"] = phase4_stack
    content["phase7_conference_packets"] = phase7_packets_validated if not phase7_errors else phase7_packets
    content["agent_conference"] = conference_summary
    conv_passed, conv_reasons = _conversion_caption_gate(platform_posts, talking_point)
    gate_records.append(
        build_gate_record(
            gate_id="conversion_caption_enforcement",
            passed=conv_passed,
            severity="error",
            reasons=conv_reasons,
            details={"source": "model_or_hybrid"},
        )
    )
    content["creative_agents"] = {
        "copywriter": preferred_model or "gemini-2.5-flash",
        "visual_director": (preferred_visual_director_model or "gemini-2.5-pro"),
        "ideation_divergence": (preferred_model or "gemini-2.5-flash"),
        "audience_psychographics": (preferred_model or "gemini-2.5-flash"),
        "narrative_architect": (preferred_model or "gemini-2.5-flash"),
        "platform_voice_calibrator": (preferred_model or "gemini-2.5-flash"),
        "hook_stress_test": (preferred_model or "gemini-2.5-flash"),
        "precision_claims_verifier": (preferred_model or "gemini-2.5-flash"),
        "compliance_policy_sentinel": (preferred_model or "gemini-2.5-flash"),
        "semantic_novelty": (preferred_model or "gemini-2.5-flash"),
        "visual_strategy": (preferred_model or "gemini-2.5-flash"),
        "cta_optimization": (preferred_model or "gemini-2.5-flash"),
        "pre_generation_conference": (conference_model or preferred_visual_director_model or "gemini-2.5-pro"),
        "conference": (conference_model or preferred_visual_director_model or "gemini-2.5-pro"),
        "image_model": os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
    }
    gate_records.append(
        build_gate_record(
            gate_id="copywriter_payload_minimum",
            passed=all(bool(str(content.get(k, "")).strip()) for k in ("wp_title", "wp_content", "fb_caption", "ig_caption", "li_text")),
            severity="error",
            reasons=[] if all(bool(str(content.get(k, "")).strip()) for k in ("wp_title", "wp_content", "fb_caption", "ig_caption", "li_text")) else ["missing_required_copy_field"],
            details={"fields": ["wp_title", "wp_content", "fb_caption", "ig_caption", "li_text"]},
        )
    )
    quality = score_generated_content(content)
    content["quality_score"] = quality.score
    content["quality_checks"] = quality.checks
    content["quality_warnings"] = quality.warnings
    for p in content["platform_posts"].values():
        p["quality_score"] = float(quality.score)
    content = _apply_control_plane_metadata(content, run_context, gate_records)
    return content
