from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from social_engine.marketing_team.planner import build_weekly_plan
from scripts.build_campaign_plan import build_campaign_plan


def _sync_runtime_configs(plan: dict) -> None:
    data_dir = os.environ.get("DATA_DIR", os.path.join(ROOT, "data"))
    marketing_dir = os.path.join(data_dir, "marketing")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(marketing_dir, exist_ok=True)
    campaign = plan.get("campaign_plan", {}) if isinstance(plan, dict) else {}
    if not isinstance(campaign, dict):
        return

    funnel = campaign.get("funnel")
    if isinstance(funnel, dict):
        with open(os.path.join(marketing_dir, "funnel_config.json"), "w", encoding="utf-8") as f:
            json.dump(funnel, f, indent=2)

        # Keep legacy location for backward compatibility with older runtime readers.
        with open(os.path.join(data_dir, "funnel_config.json"), "w", encoding="utf-8") as f:
            json.dump(funnel, f, indent=2)

    channel_schedule = campaign.get("channel_schedule")
    if isinstance(channel_schedule, dict):
        with open(os.path.join(marketing_dir, "channel_schedule.json"), "w", encoding="utf-8") as f:
            json.dump(channel_schedule, f, indent=2)

        # Keep legacy location for backward compatibility with older runtime readers.
        with open(os.path.join(data_dir, "channel_schedule.json"), "w", encoding="utf-8") as f:
            json.dump(channel_schedule, f, indent=2)


def main() -> None:
    output_dir = os.environ.get("MARKETING_OUTPUT_DIR", os.path.join(ROOT, "data", "marketing"))
    plan = build_weekly_plan(output_dir=output_dir)
    campaign_result = build_campaign_plan(output_dir=output_dir)
    _sync_runtime_configs(plan)

    print("Weekly marketing plan generated.")
    payload = dict(plan.get("artifacts", {}))
    payload["structured_campaign_json"] = campaign_result.get("artifact")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
