"""BusinessProfile assembler + version writer.

Master Build §10, §41, §57-§58, §66.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from . import (
    audience,
    brand,
    learning,
    offerings,
    paths,
    research,
    social_mandate,
)
from .schemas import BusinessProfile, ProfileVersion, SCHEMA_VERSION, to_dict, validate_profile


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assemble() -> BusinessProfile:
    """Assemble a BusinessProfile in-memory from module outputs.

    The result reflects current source-of-truth data; owner overrides are
    applied on :func:`save_current` for the persisted form.
    """
    offering_list = offerings.load() or offerings.build_from_csv()
    audience_list = audience.build_segments()
    profile = BusinessProfile(
        profile_id="infenergy-power",
        profile_version=_version_string(),
        schema_version=SCHEMA_VERSION,
        identity=brand.build_identity(),
        why=brand.build_why(),
        worldview=brand.build_worldview(),
        job=brand.build_job(),
        positioning=brand.build_positioning(),
        promise=brand.build_promise(),
        reputation=brand.build_reputation(),
        voice=brand.build_voice(),
        visual=brand.build_visual(),
        posture=brand.build_posture(),
        social_mandate=social_mandate.build_mandate(),
        content_territories=social_mandate.build_territories(),
        audience_segments=audience_list,
        customer_moments=audience.build_moments(),
        transformations=audience.build_transformations(),
        offerings=offering_list,
        offering_graph=offerings.load_graph() or offerings.build_graph(offering_list),
        research_policy=research.load_policy(),
        knowledge_gaps=research.load_gaps() or research.default_infenergy_gaps(),
        hypotheses=research.load_hypotheses() or research.default_infenergy_hypotheses(),
        claims=[],
        current_priorities={},
        learning_state=learning.summarize_learning(),
        source_refs=[],
        field_confidences={},
        field_info_types={},
        generated_at=_now(),
    )
    return profile


def _version_string() -> str:
    return datetime.now(timezone.utc).strftime("v%Y%m%d.%H%M%S")


# --- Persistence -------------------------------------------------------


def current_path() -> str:
    return os.path.join(paths.profile_dir(), "current_profile.json")


def markdown_path() -> str:
    return os.path.join(paths.profile_dir(), "current_profile.md")


def versions_dir() -> str:
    return os.path.join(paths.profile_dir(), "versions")


def save_current(profile: BusinessProfile, *, change_reason: str = "rebuild") -> ProfileVersion:
    profile_dict = _to_serializable(profile)
    profile_dict = learning.apply_overrides(profile_dict)
    with open(current_path(), "w", encoding="utf-8") as fh:
        json.dump(profile_dict, fh, indent=2)
    with open(markdown_path(), "w", encoding="utf-8") as fh:
        fh.write(_render_markdown(profile_dict))
    # Version snapshot
    prev_version = _latest_version()
    version = ProfileVersion(
        profile_version=profile.profile_version,
        created_at=profile.generated_at,
        updated_at=profile.generated_at,
        changed_fields=[],
        change_reason=change_reason,
        source_event="assemble",
        previous_version=prev_version,
        confidence_change=0.0,
        approved_by="system",
    )
    _write_version_snapshot(profile.profile_version, profile_dict, version)
    return version


def _write_version_snapshot(version_str: str, profile_dict: dict[str, Any], version: ProfileVersion) -> None:
    d = versions_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{version_str}.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": asdict(version), "profile": profile_dict}, fh, indent=2)


def _latest_version() -> str:
    d = versions_dir()
    if not os.path.isdir(d):
        return ""
    files = sorted([f for f in os.listdir(d) if f.endswith(".json")])
    return os.path.splitext(files[-1])[0] if files else ""


def load_current() -> dict[str, Any]:
    p = current_path()
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _to_serializable(profile: BusinessProfile) -> dict[str, Any]:
    return asdict(profile)


# --- Markdown rendering (§58) ------------------------------------------


def _render_markdown(p: dict[str, Any]) -> str:
    lines: list[str] = []
    idn = p.get("identity", {})
    lines.append(f"# Business Profile — {idn.get('business_name', 'Unknown Business')}")
    lines.append("")
    lines.append(f"_generated: {p.get('generated_at', '')}_")
    lines.append(f"_profile version: {p.get('profile_version', '')}_")
    lines.append(f"_schema version: {p.get('schema_version', '')}_")
    lines.append("")
    lines.append("## Identity")
    for k in ("business_name", "business_description", "industry", "business_model", "commercial_model", "primary_category", "stage"):
        v = idn.get(k)
        if v:
            lines.append(f"- **{k}**: {v}")
    lines.append("")
    why = p.get("why", {})
    lines.append("## Why")
    for k in ("mission", "vision", "purpose", "reason_for_existence", "foundational_problem"):
        v = why.get(k)
        if v:
            lines.append(f"- **{k}**: {v}")
    lines.append("")
    pos = p.get("positioning", {})
    lines.append("## Positioning")
    for k in ("market_category", "primary_position"):
        v = pos.get(k)
        if v:
            lines.append(f"- **{k}**: {v}")
    if pos.get("differentiators"):
        lines.append("### Differentiators")
        for d in pos.get("differentiators", []):
            lines.append(f"- {d}")
    lines.append("")
    promise = p.get("promise", {})
    lines.append("## Brand Promise")
    for k in ("promise", "business_capability", "offering_capability", "customer_outcome"):
        v = promise.get(k)
        if v:
            lines.append(f"- **{k}**: {v}")
    lines.append("")
    voice = p.get("voice", {})
    lines.append("## Voice")
    if voice.get("brand_personality"):
        lines.append(f"- **personality**: {voice['brand_personality']}")
    if voice.get("preferred_phrases"):
        lines.append(f"- preferred phrases: {', '.join(voice['preferred_phrases'])}")
    if voice.get("prohibited_phrases"):
        lines.append(f"- prohibited phrases: {', '.join(voice['prohibited_phrases'])}")
    lines.append("")
    lines.append("## Social Mandate")
    sm = p.get("social_mandate", {})
    if sm.get("social_account_role"):
        lines.append(f"- **role**: {sm['social_account_role']}")
    if sm.get("social_account_promise"):
        lines.append(f"- **promise**: {sm['social_account_promise']}")
    lines.append("")
    lines.append("## Audience Segments")
    for seg in p.get("audience_segments", []):
        lines.append(f"### {seg.get('name', seg.get('segment_id'))}")
        if seg.get("definition"):
            lines.append(seg["definition"])
        if seg.get("problems"):
            lines.append(f"- problems: {'; '.join(seg['problems'])}")
        if seg.get("questions"):
            lines.append(f"- questions: {'; '.join(seg['questions'])}")
        lines.append("")
    lines.append(f"## Offerings ({len(p.get('offerings', []))})")
    for o in p.get("offerings", [])[:20]:
        line = f"- **{o.get('name')}** ({o.get('sku')}) — {o.get('category', '')}"
        if o.get("price"):
            line += f" — ${o['price']}"
        lines.append(line)
    if len(p.get("offerings", [])) > 20:
        lines.append(f"- … and {len(p['offerings']) - 20} more")
    lines.append("")
    gaps = p.get("knowledge_gaps", [])
    if gaps:
        lines.append("## Open Knowledge Gaps")
        for g in gaps:
            lines.append(f"- **[{g.get('importance')}]** ({g.get('domain')}): {g.get('question')}")
        lines.append("")
    return "\n".join(lines)


def validate() -> list[str]:
    profile = assemble()
    return validate_profile(profile)
