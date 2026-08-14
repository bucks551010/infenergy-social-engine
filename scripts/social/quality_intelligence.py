"""Quality intelligence (Master Build §83-§89, §104).

Provides:
  * 20-factor quality score (§83)
  * Quality gate with configurable thresholds (§84)
  * Regret / screenshot / share / save / identity tests (§85-§89)
  * Final creative director test — the 11-question gate (§104)

All deterministic. Meant to be run BEFORE any publish action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from . import claim_intelligence, copy_intelligence


QUALITY_FACTORS = (
    "reason_to_exist",
    "audience_relevance",
    "hook",
    "novelty",
    "information_value",
    "usefulness",
    "clarity",
    "credibility",
    "specificity",
    "memorability",
    "saveability",
    "shareability",
    "conversation_potential",
    "brand_alignment",
    "platform_fit",
    "visual_concept",
    "visual_execution",
    "copy_visual_alignment",
    "humanness",
    "payoff",
)


DEFAULT_THRESHOLDS = {
    # The runtime publish gate is 82. Keep the strategic diagnostic bands
    # aligned so one post cannot be called publishable and then rejected.
    "publish": 82.0,
    "revise": 75.0,
    "regenerate": 60.0,
    "high_risk_claims_blocking": True,
}

_CONCEPT_ALIASES = {
    "charge": {"charge", "charged", "charging", "recharge", "recharged", "recharging", "power", "powered"},
    "device": {"device", "devices", "laptop", "laptops", "phone", "phones", "tablet", "tablets", "equipment", "gear"},
    "away": {"away", "outlet", "outlets", "remote", "inaccessible", "travel", "far", "offgrid"},
    "reduce": {"reduce", "reduces", "reduced", "shorten", "shortens", "faster", "quick", "quickly"},
    "team": {"team", "teams", "crew", "crews", "staff", "workers"},
    "coverage": {"coverage", "cover", "covers", "range", "reach"},
    "save": {"save", "saves", "saving", "savings", "cheaper", "lower", "less"},
}


def _concept(token: str) -> str:
    return next((concept for concept, aliases in _CONCEPT_ALIASES.items() if token in aliases), token)


@dataclass
class QualityScore:
    factors: dict[str, float] = field(default_factory=dict)
    overall: float = 0.0
    band: str = ""
    reasons: list[str] = field(default_factory=list)
    semantic_evidence: dict[str, Any] = field(default_factory=dict)
    response_contract: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        evidence = [
            {"component": name, "score": value}
            for name, value in self.factors.items()
            if value < 0.6
        ]
        return {
            "factors": self.factors,
            "component_scores": self.factors,
            "overall": self.overall,
            "band": self.band,
            "reasons": self.reasons,
            "critic_findings": self.reasons,
            "critic_evidence": evidence,
            "semantic_evidence": self.semantic_evidence,
            "response_contract": self.response_contract,
        }


def _band(overall: float) -> str:
    if overall >= 95: return "extraordinary"
    if overall >= 90: return "excellent"
    if overall >= 84: return "strong"
    if overall >= DEFAULT_THRESHOLDS["publish"]: return "publishable"
    if overall >= DEFAULT_THRESHOLDS["revise"]: return "revise"
    return "regenerate"


def _semantic_novelty_evidence(body: str) -> dict[str, Any]:
    """Recognize explained relationships, never instructional vocabulary alone."""
    text = " ".join(body.lower().split())
    if re.search(r"\bdoes not always\b", text) and re.search(r"\bif\b", text) and re.search(r"\b(move|shift|leave|create|increase|reduce)\b", text):
        return {
            "type": "COUNTERINTUITIVE_RELATIONSHIP",
            "evidence": "A familiar action has a conditional, non-obvious consequence.",
            "reason": "The copy explains how an expected benefit can move work or risk elsewhere.",
            "confidence": 0.8,
        }
    if re.search(r"\b(not the same|rather than|instead of|unlike)\b", text) and re.search(r"\b(still|leave|because|so that|which means)\b", text):
        return {
            "type": "USEFUL_DISTINCTION",
            "evidence": "Two related outcomes are separated and linked to a practical consequence.",
            "reason": "The distinction changes how a reader evaluates the familiar problem.",
            "confidence": 0.75,
        }
    if (
        re.search(r"\bdetermine(?:s|d)?\b", text)
        and re.search(r"\b(whether|can|will)\b", text)
        and re.search(r"\b(after|before|then)\b", text)
        and re.search(r"\b(describe(?:s|d)?|reserve|remaining|consequence|result)\b", text)
    ):
        return {
            "type": "DECISION_DEPENDENCY",
            "evidence": "One criterion determines viability before a separate criterion describes the remaining outcome.",
            "reason": "The ordering is justified by a dependency, rather than by sequence alone.",
            "confidence": 0.8,
        }
    return {
        "type": "NONE",
        "evidence": "",
        "reason": "No explained distinction, dependency, tradeoff, or consequence was identified.",
        "confidence": 0.0,
    }


def _conversation_evidence(hook: str, body: str) -> dict[str, Any]:
    """Separate response-worthy experience prompts from questions and engagement bait."""
    text = " ".join((hook + " " + body).lower().split())
    if re.search(r"\b(comment yes|drop your answer|thoughts\??|which one are you)\b", text):
        return {
            "type": "GENERIC_ENGAGEMENT",
            "evidence": "The copy requests engagement without a substantive response context.",
            "reason": "An engagement prompt alone does not create useful conversation.",
            "confidence": 0.9,
        }
    if re.search(r"\b(can your|does your|is your|are you)\b", hook.lower()):
        return {
            "type": "SELF_DIAGNOSTIC",
            "evidence": "The question asks the reader to assess their own situation.",
            "reason": "Self-assessment can be useful without inviting varied public responses.",
            "confidence": 0.8,
        }
    if (
        re.search(r"\bwhen\b", hook.lower())
        and re.search(r"\b(which|what|how)\b", hook.lower())
        and re.search(r"\b(what makes|why|how does)\b", hook.lower())
    ):
        return {
            "type": "EXPERIENCE_TRADEOFF",
            "evidence": "The question situates a real choice and asks for the reason behind a personal priority.",
            "reason": "Different relevant experiences can produce meaningfully different answers.",
            "confidence": 0.8,
        }
    return {
        "type": "NONE",
        "evidence": "",
        "reason": "No meaningful public response opportunity was identified.",
        "confidence": 0.0,
    }


def expected_response_contract(
    *,
    reader_job: str,
    cta_class: str = "",
    content_role: str = "",
) -> dict[str, Any]:
    """Derive the intended reader response before final copy quality is scored."""
    job = str(reader_job or "").upper()
    cta = str(cta_class or "").upper()
    role = str(content_role or "").upper()
    source = "reader_job"
    if job == "START_A_CONVERSATION":
        response_type = "PUBLIC_CONVERSATION"
    elif job in {"MAKE_ME_THINK", "REFLECT"}:
        response_type = "REFLECTION"
    elif job == "GIVE_ME_A_REFERENCE":
        response_type = "SAVE_REFERENCE"
    elif job == "HELP_ME_CHOOSE":
        response_type = "COMPARE_DECISION"
    elif role in {"COMMUNITY", "COMMUNITY_CONVERSATION"}:
        response_type = "PUBLIC_CONVERSATION"
        source = "content_role"
    elif role in {"FIT_DEMONSTRATION", "DECISION_SUPPORT"}:
        response_type = "COMPARE_DECISION"
        source = "content_role"
    elif role in {"DIRECT_OFFER", "OFFER"}:
        response_type = "ACTION_CLARITY"
        source = "content_role"
    elif cta in {"COMPARE"}:
        response_type = "COMPARE_DECISION"
        source = "cta_class"
    elif cta in {"BUY", "LEARN", "EXPLORE"}:
        response_type = "ACTION_CLARITY"
        source = "cta_class"
    elif cta in {"RESPOND", "COMMENT"}:
        response_type = "PUBLIC_CONVERSATION"
        source = "cta_class"
    elif cta in {"SAVE"}:
        response_type = "SAVE_REFERENCE"
        source = "cta_class"
    elif cta == "REFLECT":
        response_type = "REFLECTION"
        source = "cta_class"
    else:
        response_type = "GENERAL_VALUE"
    return {
        "expected_response_type": response_type,
        "reader_job": job,
        "cta_class": cta,
        "content_role": role,
        "response_applicability": "CONVERSATION_REQUIRED" if response_type == "PUBLIC_CONVERSATION" else "INTENT_RESPONSE_REQUIRED",
        "response_contract_source": source,
        "response_contract_inputs": {"reader_job": job, "cta_class": cta, "content_role": role},
        "response_contract_resolution": f"{source} resolved {response_type} before copy scoring",
    }


def _response_value_evidence(
    contract: dict[str, Any],
    *,
    body: str,
    takeaway: str,
    novelty_evidence: dict[str, Any],
    conversation_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Award response value only when copy delivers the response promised upstream."""
    response_type = str(contract.get("expected_response_type") or "GENERAL_VALUE")
    text = " ".join((body + " " + takeaway).lower().split())
    if response_type == "PUBLIC_CONVERSATION":
        passed = conversation_evidence.get("type") == "EXPERIENCE_TRADEOFF"
        return {
            "type": response_type,
            "score": 0.8 if passed else 0.35,
            "evidence": conversation_evidence.get("evidence", ""),
            "reason": "The locked strategy requires a meaningful public response opportunity." if passed else "The locked community strategy lacks a meaningful public response opportunity.",
        }
    if response_type == "COMPARE_DECISION":
        passed = (
            novelty_evidence.get("type") in {"DECISION_DEPENDENCY", "USEFUL_DISTINCTION"}
            and bool(re.search(r"\b(compare|choose|match|evaluate)\b", text))
            and bool(re.search(r"\b(requirement|criterion|constraint|fit|tradeoff|consequence)\b", text))
        )
        return {
            "type": response_type,
            "score": 0.8 if passed else 0.35,
            "evidence": "The copy explains a decision relationship and gives criteria the reader can compare." if passed else "No explained comparison relationship and reusable criteria were identified.",
            "reason": "The content supports a concrete compare decision." if passed else "A compare CTA alone does not supply decision value.",
        }
    if response_type == "SAVE_REFERENCE":
        passed = bool(re.search(r"\b(first|second|third|step|checklist|criteria|before|after)\b", text)) and len(re.findall(r"[.;]", body)) >= 2
        return {
            "type": response_type,
            "score": 0.8 if passed else 0.35,
            "evidence": "The copy provides a reusable reference sequence." if passed else "No reusable reference structure was identified.",
            "reason": "The content earns a save action through later reuse." if passed else "A save CTA alone does not create reference value.",
        }
    if response_type == "REFLECTION":
        passed = novelty_evidence.get("type") in {"COUNTERINTUITIVE_RELATIONSHIP", "USEFUL_DISTINCTION"} and bool(takeaway.strip())
        return {
            "type": response_type,
            "score": 0.8 if passed else 0.35,
            "evidence": "The copy offers a consequential perspective shift." if passed else "No substantive perspective shift was identified.",
            "reason": "Private reflection is appropriate for the locked job." if passed else "Generic motivation does not earn reflection value.",
        }
    if response_type == "ACTION_CLARITY":
        passed = bool(re.search(r"\b(compare|check|choose|review|explore)\b", text)) and bool(takeaway.strip())
        return {
            "type": response_type,
            "score": 0.8 if passed else 0.35,
            "evidence": "The copy states a concrete next action tied to the offer." if passed else "No concrete, offer-relevant next action was identified.",
            "reason": "The offer earns action through clarity." if passed else "An offer CTA alone does not create action clarity.",
        }
    return {
        "type": response_type,
        "score": 0.8 if takeaway.strip() else 0.35,
        "evidence": "The copy has a usable takeaway." if takeaway.strip() else "",
        "reason": "General value requires a usable takeaway.",
    }


def score(
    *,
    hook: str,
    body: str,
    takeaway: str,
    memory_anchor: str,
    visual_concept_description: str,
    platform: str,
    genre: dict[str, Any],
    reader_job_config: dict[str, Any],
    ledger: claim_intelligence.ClaimLedger,
    visual_prompt_humanness: float,
    caption_visual_relationship: str,
    engine: str,
    brand_voice: dict[str, Any] | None = None,
    response_contract: dict[str, Any] | None = None,
) -> QualityScore:
    factors: dict[str, float] = {}

    # reason_to_exist: proxy for "does the memory anchor exist?"
    factors["reason_to_exist"] = 0.9 if memory_anchor else 0.55

    # audience_relevance: from reader_job typical_emotion presence
    factors["audience_relevance"] = 0.8 if reader_job_config.get("typical_emotion") else 0.55

    # hook
    hs = copy_intelligence.hook_strength(hook)
    factors["hook"] = hs

    novelty_evidence = _semantic_novelty_evidence(body)
    factors["novelty"] = 0.8 if novelty_evidence["type"] != "NONE" else 0.55

    # information_value: from density + genre density
    factors["information_value"] = 0.6 * float(genre.get("avg_information_density", 0.5)) + 0.4 * copy_intelligence.density(body)

    # usefulness
    factors["usefulness"] = 0.85 if takeaway or memory_anchor else 0.55

    # clarity: density is a proxy
    factors["clarity"] = copy_intelligence.density(body)

    # credibility: from claim ledger
    total_claims = len(ledger.claims)
    if total_claims == 0:
        factors["credibility"] = 0.75
    else:
        v = len(ledger.verified)
        u = len(ledger.unverified_high_risk)
        factors["credibility"] = max(0.0, min(1.0, 0.5 + 0.5 * (v / total_claims) - 0.25 * (u / total_claims)))

    # specificity: numbers/proper nouns
    factors["specificity"] = 0.85 if any(ch.isdigit() for ch in body) else 0.5

    # memorability
    factors["memorability"] = 0.9 if memory_anchor else 0.5

    # Save/share are genre affordances; conversation requires a response opportunity.
    ctas = set(genre.get("cta_preferences", []))
    factors["saveability"] = 0.9 if "SAVE" in ctas else 0.4
    factors["shareability"] = 0.85 if "SHARE" in ctas else 0.4
    conversation_evidence = _conversation_evidence(hook, body)
    factors["conversation_potential"] = 0.8 if conversation_evidence["type"] == "EXPERIENCE_TRADEOFF" else 0.35
    contract = dict(response_contract or {})
    if not contract:
        contract = expected_response_contract(reader_job=str(reader_job_config.get("id") or ""))
    response_evidence = _response_value_evidence(
        contract,
        body=body,
        takeaway=takeaway,
        novelty_evidence=novelty_evidence,
        conversation_evidence=conversation_evidence,
    )
    factors["response_value"] = float(response_evidence["score"])

    factors["brand_alignment"] = 0.85
    if brand_voice:
        text_lower = (hook + " " + body).lower()
        prohibited = [p for p in brand_voice.get("prohibited_phrases", []) if p and str(p).lower() in text_lower]
        preferred = [p for p in brand_voice.get("preferred_phrases", []) if p and str(p).lower() in text_lower]
        adj = 0.0
        if prohibited:
            adj -= min(0.6, 0.25 * len(prohibited))
        if preferred:
            adj += min(0.15, 0.05 * len(preferred))
        factors["brand_alignment"] = max(0.0, min(1.0, factors["brand_alignment"] + adj))

    factors["platform_fit"] = 0.75

    # visual_concept + execution
    factors["visual_concept"] = 0.8 if visual_concept_description else 0.4
    factors["visual_execution"] = visual_prompt_humanness

    # copy_visual_alignment
    factors["copy_visual_alignment"] = {
        "VISUAL_SUMMARIZES_CAPTION": 0.9,
        "VISUAL_EXPLAINS_CAPTION": 0.85,
        "CAPTION_EXPLAINS_VISUAL": 0.8,
        "VISUAL_AND_CAPTION_SPLIT_INFORMATION": 0.85,
        "VISUAL_TEASES_CAPTION": 0.7,
    }.get(caption_visual_relationship, 0.6)

    # humanness (copy)
    factors["humanness"] = copy_intelligence.humanness_score(hook + " " + body)

    # payoff — from hook-payoff contract
    ok, _ = copy_intelligence.contract_ok(hook, body)
    factors["payoff"] = 0.85 if ok else 0.45

    aggregate_factors = dict(factors)
    aggregate_factors.pop("conversation_potential")
    overall = sum(aggregate_factors.values()) / len(aggregate_factors) * 100.0
    reasons: list[str] = []
    if factors["humanness"] < 0.6:
        reasons.append("humanness below bar")
    if factors["payoff"] < 0.6:
        reasons.append("hook-payoff mismatch")
    if factors["credibility"] < 0.55:
        reasons.append("unverified high-risk claims")
    if factors["information_value"] < 0.5:
        reasons.append("information density weak")
    if factors["novelty"] < 0.6:
        reasons.append("novelty_angle_weak")
    if factors["specificity"] < 0.6:
        reasons.append("specificity_weak")
    if contract.get("expected_response_type") == "PUBLIC_CONVERSATION" and factors["conversation_potential"] < 0.6:
        reasons.append("conversation_potential_weak")
    if factors["response_value"] < 0.6:
        reasons.append("intent_response_value_weak")
    if brand_voice and factors["brand_alignment"] < 0.55:
        reasons.append("brand voice violation (prohibited phrases present)")

    return QualityScore(
        factors=factors,
        overall=overall,
        band=_band(overall),
        reasons=reasons,
        semantic_evidence={"novelty": novelty_evidence, "conversation": conversation_evidence, "response": response_evidence},
        response_contract=contract,
    )


# --- Simple diagnostic tests (§85-§89) --------------------------------------


def regret_test(*, memory_anchor: str, body: str) -> bool:
    """§85: True = would NOT regret giving this attention."""
    return bool(memory_anchor or copy_intelligence.has_so_what(body))


def screenshot_test(*, memory_anchor: str, visual_format: str) -> bool:
    """§86: True = worth screenshotting out of feed."""
    saveable = visual_format in {"checklist", "fact_card", "comparison_graphic", "myth_reality_graphic", "carousel"}
    return bool(memory_anchor) and saveable


def share_test(*, hook: str, memory_anchor: str) -> bool:
    """§87: True = something someone would send to a friend."""
    if not (hook and memory_anchor):
        return False
    if copy_intelligence.humanness_score(hook) < 0.6:
        return False
    return True


def save_test(*, cta_type: str, is_reference_content: bool) -> bool:
    """§88: SAVE CTA only when the content is actually reference-worthy."""
    if cta_type == "SAVE":
        return is_reference_content
    return True  # No SAVE CTA claimed → nothing to check


def identity_test(*, pillar_engine_fits: list[str], engine: str) -> bool:
    """§89: content should reinforce, not weaken, brand identity."""
    return engine in pillar_engine_fits


# --- Final Creative Director test (§104) ------------------------------------


@dataclass
class CreativeDirectorVerdict:
    passed: bool
    answered: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)


def creative_director_test(
    *,
    strategy_reason: str,
    audience_reason: str,
    value_delivered: str,
    novelty_angle: str,
    memory_anchor: str,
    copy_earns_attention: bool,
    visual_communicates: bool,
    copy_visual_alignment: bool,
    brand_feels_like_us: bool,
    material_claims_accurate: bool,
    worth_reader_time: bool,
) -> CreativeDirectorVerdict:
    answered = {
        "STRATEGY": strategy_reason,
        "AUDIENCE": audience_reason,
        "VALUE": value_delivered,
        "NOVELTY": novelty_angle,
        "MEMORY": memory_anchor,
        "COPY": "yes" if copy_earns_attention else "no",
        "VISUAL": "yes" if visual_communicates else "no",
        "ALIGNMENT": "yes" if copy_visual_alignment else "no",
        "BRAND": "yes" if brand_feels_like_us else "no",
        "TRUTH": "yes" if material_claims_accurate else "no",
        "EXPERIENCE": "yes" if worth_reader_time else "no",
    }
    failures: list[str] = []
    for k, v in answered.items():
        if not v or (v.lower() == "no"):
            failures.append(k)
    return CreativeDirectorVerdict(passed=(not failures), answered=answered, failures=failures)


def copy_critic(*, copy: dict[str, Any], strategy: dict[str, Any], platform: str) -> dict[str, Any]:
    """Review the final assembled copy without rewriting it blindly."""
    hook = str(copy.get("hook") or "")
    body = str(copy.get("body_text") or "")
    cta = str(copy.get("cta") or "")
    issues: list[str] = []
    if copy_intelligence.humanness_score(hook + " " + body) < 0.6:
        issues.append("generic_or_ai_like_language")
    if not hook or not body:
        issues.append("missing_opening_or_payoff")
    benefit_check = benefit_coverage(str(strategy.get("benefit") or ""), hook + " " + body)
    if strategy.get("benefit") and not benefit_check["result"]:
        issues.append("primary_benefit_not_explicit")
    if not cta:
        issues.append("missing_cta")
    if platform.startswith("linkedin") and not any(term in (hook + " " + body).lower() for term in ("decision", "planning", "operational", "business", "continuity")):
        issues.append("linkedin_professional_value_weak")
    return {"verdict": "PASS" if not issues else "REVISE", "issues": issues, "hook": hook, "platform": platform, "benefit_semantic_check": benefit_check}


def benefit_coverage(expected_benefit: str, observed_copy: str) -> dict[str, Any]:
    """Small deterministic semantic check for the supported benefit concept."""
    expected = expected_benefit.lower()
    observed = observed_copy.lower()
    tokens = {_concept(token) for token in re.findall(r"[a-z]+", expected) if len(token) > 3}
    direct = bool(expected and expected in observed)
    observed_tokens = {_concept(token) for token in re.findall(r"[a-z]+", observed)}
    overlap = len(tokens & observed_tokens) / max(1, len(tokens))
    result = direct or overlap >= 0.5
    check_type = "exact" if direct else "supported_paraphrase" if result else "insufficient_benefit_expression"
    evidence = sorted(tokens & observed_tokens)
    return {
        "semantic_check_type": check_type,
        "expected_concept": expected_benefit,
        "observed_expression": observed_copy,
        "evidence": evidence,
        "result": result,
        "confidence": 0.95 if direct else 0.85 if result else 0.9,
    }


def visual_critic(*, visual: dict[str, Any], provider_result: dict[str, Any], platform: str) -> dict[str, Any]:
    """Review the rendered plan and state when pixel inspection is unavailable."""
    layout = visual.get("layout_grammar") or {}
    priority = visual.get("information_priority") or {}
    issues: list[str] = []
    required = ("primary_focal_point", "product_placement", "headline_position", "text_density", "cta_position")
    if any(not layout.get(key) for key in required):
        issues.append("incomplete_layout_execution_plan")
    if not priority.get("MUST_SHOW"):
        issues.append("missing_visual_information_priority")
    kind = str(provider_result.get("kind") or "")
    pixel_status = "PIXEL_REVIEW_PENDING" if kind == "template_recipe" else "PIXEL_RENDER_AVAILABLE" if provider_result.get("asset_path") else "NO_RENDERED_ASSET"
    if pixel_status == "NO_RENDERED_ASSET":
        issues.append("rendered_asset_unavailable")
    return {"verdict": "PASS" if not issues else "REVISE", "issues": issues, "platform": platform, "pixel_status": pixel_status, "reviewed_layout": {key: layout.get(key) for key in required}}
