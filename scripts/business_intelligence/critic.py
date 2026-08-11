"""Profile Critic — the §63 quality check.

Answers 13 questions about the assembled profile. Returns a
``ProfileVerdict`` (pass/fail + failure list) that Bootstrap uses to
gate publishing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProfileVerdict:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)


def _check(name: str, ok: bool, why: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "why": why}


def review(profile: dict[str, Any]) -> ProfileVerdict:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    warnings: list[str] = []

    idn = profile.get("identity", {})
    why = profile.get("why", {})
    promise = profile.get("promise", {})
    pos = profile.get("positioning", {})
    reputation = profile.get("reputation", {})
    voice = profile.get("voice", {})
    social = profile.get("social_mandate", {})
    segments = profile.get("audience_segments", [])
    offering_list = profile.get("offerings", [])
    territories = profile.get("content_territories", [])

    # 1. Business identity presence
    ok = bool(idn.get("business_name") and idn.get("industry"))
    checks.append(_check("identity_present", ok, "business_name + industry required"))
    if not ok:
        failures.append("Business identity is incomplete")

    # 2. Business why present
    ok = bool(why.get("mission") or why.get("reason_for_existence"))
    checks.append(_check("why_present", ok))
    if not ok:
        failures.append("Business why is empty (need mission or reason_for_existence)")

    # 3. Positioning is defensible
    ok = bool(pos.get("primary_position") and pos.get("differentiators"))
    checks.append(_check("positioning_defensible", ok))
    if not ok:
        warnings.append("Positioning has no differentiators")

    # 4. Brand promise is concrete
    ok = bool(promise.get("promise") and promise.get("customer_outcome"))
    checks.append(_check("promise_concrete", ok))
    if not ok:
        warnings.append("Brand promise is not fully specified")

    # 5. Reputation is stated
    ok = bool(reputation.get("desired_reputation"))
    checks.append(_check("reputation_stated", ok))
    if not ok:
        warnings.append("Desired reputation is empty")

    # 6. Voice DNA present
    ok = bool(voice.get("brand_personality") and voice.get("preferred_phrases"))
    checks.append(_check("voice_dna_present", ok))
    if not ok:
        failures.append("Voice DNA is incomplete (need brand_personality + preferred_phrases)")

    # 7. Voice prohibits real risks
    ok = bool(voice.get("prohibited_phrases"))
    checks.append(_check("voice_has_prohibitions", ok))
    if not ok:
        warnings.append("No prohibited_phrases declared")

    # 8. Social mandate declared
    ok = bool(social.get("social_account_role") and social.get("social_account_promise"))
    checks.append(_check("social_mandate_declared", ok))
    if not ok:
        failures.append("Social mandate is incomplete")

    # 9. Audience segments present
    ok = len(segments) > 0
    checks.append(_check("audience_present", ok))
    if not ok:
        failures.append("No audience segments defined")

    # 10. Audience segments have depth
    if segments:
        avg_depth = sum(len(s.get("problems", [])) + len(s.get("questions", [])) for s in segments) / max(1, len(segments))
        ok = avg_depth >= 3
        checks.append(_check("audience_depth", ok, f"avg problems+questions={avg_depth:.1f}"))
        if not ok:
            warnings.append("Audience segments are thin")

    # 11. Content territories anchored to something
    if territories:
        without_authority = [t for t in territories if not t.get("authority_basis")]
        ok = len(without_authority) == 0
        checks.append(_check("territories_have_authority", ok))
        if not ok:
            warnings.append(f"{len(without_authority)} content territories lack authority_basis")

    # 12. Offerings present (business-type dependent)
    biztype = idn.get("business_type", "")
    if "product" in biztype or not biztype:
        ok = len(offering_list) > 0
        checks.append(_check("offerings_present", ok))
        if not ok:
            warnings.append("Product business has zero offerings")

    # 13. No obvious internal contradictions
    prohibited = set(voice.get("prohibited_phrases", []))
    preferred = set(voice.get("preferred_phrases", []))
    contradiction = prohibited & preferred
    ok = len(contradiction) == 0
    checks.append(_check("no_voice_contradiction", ok, f"overlap={sorted(contradiction)}"))
    if not ok:
        failures.append(f"Voice contradiction: phrases in both preferred + prohibited: {sorted(contradiction)}")

    return ProfileVerdict(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
        checks=checks,
    )
