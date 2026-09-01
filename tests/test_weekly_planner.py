from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from social_engine.marketing_team.planner import build_weekly_plan  # noqa: E402


class WeeklyPlannerTests(unittest.TestCase):
    def test_build_weekly_plan_emits_campaign_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            strategy_path = os.path.join(tmp, "marketing_strategy_20990101T000000Z.json")
            with open(strategy_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "generated_at_utc": "2099-01-01T00:00:00Z",
                        "brand_profile": {"top_categories": ["Portable Power"]},
                        "audience": {"segments": [{"name": "Prepared Buyer"}]},
                        "copy": {
                            "social_hooks": ["Most people miss this outage gap"],
                            "cta_bank": ["Book your free readiness review"],
                            "ad_angles": ["risk-control framing"],
                        },
                        "offer": {"core_offers": ["Device-by-device planning"]},
                        "experiments": {"experiments": [{"name": "Hook test", "hypothesis": "Specific hook improves CTR"}]},
                    },
                    f,
                    indent=2,
                )

            plan = build_weekly_plan(output_dir=tmp)
            artifacts = plan.get("artifacts", {})
            self.assertIn("weekly_plan_json", artifacts)
            self.assertIn("campaign_plan_json", artifacts)
            self.assertTrue(os.path.exists(artifacts["campaign_plan_json"]))
            installments = [row for row in plan["sequence"] if row.get("series", {}).get("id") == "infenergy_intervention"]
            self.assertEqual([(row["day"], row["slot"]) for row in installments], [("Tuesday", "midday"), ("Friday", "morning")])
            self.assertEqual(len({row["series"]["preferred_format"] for row in installments}), 2)
            self.assertTrue(all(row["series"]["product_required"] for row in installments))
            self.assertTrue(all(row["series"]["character_canon_required"] for row in installments))


if __name__ == "__main__":
    unittest.main()
