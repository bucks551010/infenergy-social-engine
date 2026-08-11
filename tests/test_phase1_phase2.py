from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from scripts.build_campaign_plan import build_campaign_plan  # noqa: E402
from scripts.campaign_runtime import FUNNEL_STAGES, load_funnel_config  # noqa: E402
import scripts.generate_posts as generate_posts  # noqa: E402


class PhaseOneTwoTests(unittest.TestCase):
    def test_campaign_plan_schema_fields_exist(self) -> None:
        output_dir = os.path.join(ROOT, "data", "marketing")
        result = build_campaign_plan(output_dir=output_dir)
        campaign = result.get("campaign", {})
        required = {
            "campaign_id",
            "campaign_name",
            "week_start",
            "primary_objective",
            "audience_segment",
            "customer_problem",
            "educational_message",
            "featured_product_ids",
            "supporting_product_ids",
            "core_message",
            "primary_cta",
            "secondary_cta",
            "destination_url",
            "content_angles",
            "approved_claims",
            "prohibited_claims",
        }
        self.assertTrue(required.issubset(set(campaign.keys())))

    def test_funnel_config_has_required_distribution(self) -> None:
        cfg = load_funnel_config()
        distribution = cfg.get("distribution", {})
        stages = cfg.get("stages", {})
        for stage in FUNNEL_STAGES:
            self.assertIn(stage, distribution)
            self.assertIn(stage, stages)
            self.assertIn("objective", stages[stage])
            self.assertIn("approved_cta_types", stages[stage])
            self.assertIn("preferred_content_formats", stages[stage])
            self.assertIn("prohibited_cta_types", stages[stage])
            self.assertIn("preferred_hook_styles", stages[stage])
            self.assertIn("primary_success_metric", stages[stage])

    def test_generator_records_funnel_stage(self) -> None:
        content = generate_posts.generate("morning")
        self.assertIn("funnel_stage", content)
        self.assertIn(content["funnel_stage"], FUNNEL_STAGES)


if __name__ == "__main__":
    unittest.main()
