from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from social_engine.marketing_team.planner import build_weekly_plan


def main() -> None:
    output_dir = os.environ.get("MARKETING_OUTPUT_DIR", os.path.join(ROOT, "data", "marketing"))
    plan = build_weekly_plan(output_dir=output_dir)

    print("Weekly marketing plan generated.")
    print(json.dumps(plan.get("artifacts", {}), indent=2))


if __name__ == "__main__":
    main()
