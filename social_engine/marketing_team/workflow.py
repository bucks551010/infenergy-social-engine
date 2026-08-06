from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from .agents import (
    audience_agent,
    channel_ops_agent,
    copy_agent,
    creative_agent,
    offer_agent,
    qa_agent,
    research_agent,
    voice_agent,
)
from .brand_intel import infer_brand_profile, save_brand_profile


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _markdown_summary(bundle: dict[str, Any]) -> str:
    profile = bundle["brand_profile"]
    voice = bundle["voice"]
    copy = bundle["copy"]
    creative = bundle["creative"]

    lines = []
    lines.append("# INF Energy Marketing Team Output")
    lines.append("")
    lines.append("## Brand Snapshot")
    lines.append(f"- Product count: {profile.get('product_count', 0)}")
    lines.append(f"- Top categories: {', '.join(profile.get('top_categories', [])[:6])}")
    lines.append(f"- Authority: {profile.get('brand_voice', {}).get('authority_position', '')}")
    lines.append("")
    lines.append("## Voice System")
    for rule in voice.get("voice_rules", []):
        lines.append(f"- {rule}")
    lines.append("")
    lines.append("## Hero Copy")
    lines.append(f"- Hero: {copy.get('hero', '')}")
    lines.append(f"- Subhero: {copy.get('subhero', '')}")
    lines.append("")
    lines.append("## Creative Prompts")
    for prompt in creative.get("image_prompts", []):
        lines.append(f"- {prompt}")
    lines.append("")
    lines.append("## QA")
    lines.append(f"- Status: {bundle['qa'].get('status', 'unknown')}")
    return "\n".join(lines)


def run_marketing_team(
    site_url: str = "https://www.infenergypower.com",
    products_dir: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    products_dir = products_dir or os.path.join(root, "data", "products")
    output_dir = output_dir or os.path.join(root, "data", "marketing")

    profile = infer_brand_profile(site_url=site_url, products_dir=products_dir)
    research = research_agent(profile)
    audience = audience_agent(profile, research)
    voice = voice_agent(profile)
    offer = offer_agent(profile, audience)
    copy = copy_agent(profile, audience, voice, offer)
    creative = creative_agent(profile, voice, copy)
    channel_ops = channel_ops_agent(copy, creative)

    bundle = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "brand_profile": profile,
        "research": research,
        "audience": audience,
        "voice": voice,
        "offer": offer,
        "copy": copy,
        "creative": creative,
        "channel_ops": channel_ops,
    }
    bundle["qa"] = qa_agent(bundle)

    stamp = _utc_stamp()
    os.makedirs(output_dir, exist_ok=True)

    profile_path = os.path.join(output_dir, f"brand_profile_{stamp}.json")
    save_brand_profile(profile, profile_path)

    bundle_path = os.path.join(output_dir, f"marketing_bundle_{stamp}.json")
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)

    summary_path = os.path.join(output_dir, f"marketing_summary_{stamp}.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(_markdown_summary(bundle))

    bundle["artifacts"] = {
        "brand_profile": profile_path,
        "bundle": bundle_path,
        "summary": summary_path,
    }
    return bundle
