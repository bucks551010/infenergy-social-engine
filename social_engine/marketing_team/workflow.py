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
    experimentation_agent,
    lifecycle_email_agent,
    offer_agent,
    qa_agent,
    research_agent,
    seo_agent,
    voice_agent,
)
from .brand_intel import infer_brand_profile, save_brand_profile


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _markdown_summary(strategy: dict[str, Any]) -> str:
    profile = strategy["brand_profile"]
    research = strategy["research"]
    audience = strategy["audience"]
    voice = strategy["voice"]
    copy = strategy["copy"]
    creative = strategy["creative"]
    experiments = strategy["experiments"]
    seo = strategy["seo"]

    lines = []
    lines.append("# INF Energy Growth System Output")
    lines.append("")
    lines.append("## Brand Snapshot")
    lines.append(f"- Product count: {profile.get('product_count', 0)}")
    lines.append(f"- Top categories: {', '.join(profile.get('top_categories', [])[:6])}")
    lines.append(f"- Price tier: {profile.get('demographics', {}).get('value_tier', 'n/a')}")
    lines.append(f"- Authority: {profile.get('brand_voice', {}).get('authority_position', '')}")
    lines.append("")
    lines.append("## Positioning")
    lines.append(f"- Market position: {research.get('market_position', '')}")
    for edge in research.get("competitive_edges", [])[:3]:
        lines.append(f"- Edge: {edge}")
    lines.append("")
    lines.append("## Audience Priorities")
    for segment in audience.get("segments", [])[:3]:
        lines.append(
            f"- {segment.get('name', '')}: trigger={segment.get('trigger', '')} | offer={segment.get('best_offer', '')}"
        )
    lines.append("")
    lines.append("## Voice System")
    for rule in voice.get("voice_rules", []):
        lines.append(f"- {rule}")
    lines.append("")
    lines.append("## Hero Copy")
    lines.append(f"- Hero: {copy.get('hero', '')}")
    lines.append(f"- Subhero: {copy.get('subhero', '')}")
    lines.append("")
    lines.append("## SEO Pillars")
    for pillar in seo.get("pillar_clusters", [])[:2]:
        lines.append(f"- {pillar.get('pillar', '')}: {', '.join(pillar.get('topics', [])[:3])}")
    lines.append("")
    lines.append("## Creative Prompts")
    for prompt in creative.get("image_prompts", []):
        lines.append(f"- {prompt}")
    lines.append("")
    lines.append("## Experiments")
    for exp in experiments.get("experiments", [])[:3]:
        lines.append(f"- {exp.get('name', '')}: {exp.get('hypothesis', '')}")
    lines.append("")
    lines.append("## QA")
    lines.append(f"- Score: {strategy['qa'].get('score', 0)}")
    lines.append(f"- Status: {strategy['qa'].get('status', 'unknown')}")
    return "\n".join(lines)


def _build_execution_pack(strategy: dict[str, Any]) -> dict[str, Any]:
    copy = strategy.get("copy", {})
    channels = strategy.get("channel_ops", {}).get("channels", {})
    audience = strategy.get("audience", {}).get("segments", [])
    return {
        "hero": copy.get("hero", ""),
        "subhero": copy.get("subhero", ""),
        "top_hooks": copy.get("social_hooks", [])[:5],
        "top_ctas": copy.get("cta_bank", [])[:5],
        "channel_frameworks": channels,
        "priority_segments": [
            {
                "name": s.get("name", ""),
                "trigger": s.get("trigger", ""),
                "best_offer": s.get("best_offer", ""),
            }
            for s in audience[:3]
        ],
        "publish_rule": "One clear CTA per post, one measurable proof point per asset.",
    }


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
    seo = seo_agent(profile, copy)
    lifecycle = lifecycle_email_agent(copy, audience)

    strategy = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "brand_profile": profile,
        "research": research,
        "audience": audience,
        "voice": voice,
        "offer": offer,
        "copy": copy,
        "creative": creative,
        "channel_ops": channel_ops,
        "seo": seo,
        "lifecycle": lifecycle,
    }
    strategy["experiments"] = experimentation_agent(strategy)
    strategy["qa"] = qa_agent(strategy)
    strategy["execution_pack"] = _build_execution_pack(strategy)

    stamp = _utc_stamp()
    os.makedirs(output_dir, exist_ok=True)

    profile_path = os.path.join(output_dir, f"brand_profile_{stamp}.json")
    save_brand_profile(profile, profile_path)

    strategy_path = os.path.join(output_dir, f"marketing_strategy_{stamp}.json")
    with open(strategy_path, "w", encoding="utf-8") as f:
        json.dump(strategy, f, indent=2)

    execution_path = os.path.join(output_dir, f"execution_pack_{stamp}.json")
    with open(execution_path, "w", encoding="utf-8") as f:
        json.dump(strategy["execution_pack"], f, indent=2)

    summary_path = os.path.join(output_dir, f"marketing_summary_{stamp}.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(_markdown_summary(strategy))

    strategy["artifacts"] = {
        "brand_profile": profile_path,
        "strategy": strategy_path,
        "execution_pack": execution_path,
        "summary": summary_path,
    }
    return strategy
