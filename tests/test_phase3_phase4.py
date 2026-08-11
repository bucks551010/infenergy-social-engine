from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from scripts.campaign_runtime import eligible_channels_for_slot  # noqa: E402
import scripts.generate_posts as generate_posts  # noqa: E402


class PhaseThreeFourTests(unittest.TestCase):
    def test_new_schedule_schema_eligibility(self) -> None:
        schedule = {
            "monday": {
                "midday": [
                    {"platform": "facebook", "stage": "EDUCATION", "enabled": True},
                    {"platform": "linkedin", "stage": "EDUCATION", "enabled": True},
                ]
            }
        }
        now = datetime(2026, 8, 3, 17, 0, tzinfo=timezone.utc)  # Monday
        eligible = eligible_channels_for_slot("midday", "EDUCATION", schedule, now_utc=now)
        self.assertTrue(eligible["facebook"][0])
        self.assertTrue(eligible["linkedin"][0])
        self.assertFalse(eligible["instagram"][0])

    def test_manual_platform_override(self) -> None:
        schedule = {}
        now = datetime(2026, 8, 3, 17, 0, tzinfo=timezone.utc)
        eligible = eligible_channels_for_slot(
            "midday",
            "DESIRE",
            schedule,
            now_utc=now,
            manual_platforms=["instagram"],
        )
        self.assertTrue(eligible["instagram"][0])
        self.assertFalse(eligible["facebook"][0])

    def test_generate_includes_platform_posts_schema(self) -> None:
        content = generate_posts.generate("midday")
        self.assertIn("platform_posts", content)
        for platform in ("facebook", "instagram", "linkedin"):
            self.assertIn(platform, content["platform_posts"])
            post = content["platform_posts"][platform]
            for key in (
                "post_id",
                "campaign_id",
                "platform",
                "funnel_stage",
                "audience_segment",
                "hook",
                "caption",
                "cta",
                "content_format",
                "visual_direction",
                "alt_text",
                "quality_score",
                "validation_status",
                "validation_errors",
            ):
                self.assertIn(key, post)


if __name__ == "__main__":
    unittest.main()
