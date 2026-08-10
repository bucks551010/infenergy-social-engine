from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

from campaign_runtime import (  # noqa: E402
    allowed_stages_for_slot,
    apply_claim_guardrails,
    build_utm_link,
    eligible_channels_for_slot,
    load_channel_schedule,
    should_channel_run,
    score_generated_content,
    stage_for_slot,
    was_recent_channel_success,
    weekly_schedule_coverage,
)
from datetime import datetime, timezone


class CampaignRuntimeTests(unittest.TestCase):
    def test_claim_guardrails_soften_risky_phrases(self) -> None:
        text = "We guarantee 100% savings with instant results and zero risk."
        cleaned, replaced = apply_claim_guardrails(text)
        self.assertNotIn("guarantee", cleaned.lower())
        self.assertNotIn("zero risk", cleaned.lower())
        self.assertGreaterEqual(len(replaced), 1)

    def test_utm_link_builder_preserves_path(self) -> None:
        url = "https://example.com/blog/post"
        out = build_utm_link(url, "facebook", "social", "campaign_a", "morning")
        self.assertIn("utm_source=facebook", out)
        self.assertIn("utm_medium=social", out)
        self.assertIn("utm_campaign=campaign_a", out)

    def test_should_channel_run_with_env_override(self) -> None:
        schedule = {"linkedin": {"slots": ["morning"], "days": [0, 1, 2, 3, 4]}}
        allowed, reason = should_channel_run(
            "linkedin",
            "evening",
            schedule,
            env={"ENABLE_LINKEDIN_SLOTS": "morning,midday"},
        )
        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("env_override"))

    def test_content_scoring_returns_grade(self) -> None:
        content = {
            "wp_content": "<p>Battery backup can save 20% and avoid 3 outages yearly.</p>" * 30,
            "fb_caption": "Many homes see 15% lower bills. Book a call today. #Energy #Solar #Backup #Power #Home",
            "ig_caption": "Hook line\nDetails with 25% and 3 numbers. Book now. #Energy #Solar #Backup #Power #Home #Battery #Prep",
            "li_text": "A practical framework with 2 measurable specs. Schedule an assessment.",
        }
        scored = score_generated_content(content)
        self.assertIn("grade", scored.checks)
        self.assertIsInstance(scored.score, int)

    def test_recent_success_window_detection(self) -> None:
        history = {
            "posts": [
                {
                    "slot": "morning",
                    "run_started_at_utc": "2099-01-01T00:00:00+00:00",
                    "fb_id": "12345",
                }
            ]
        }
        self.assertTrue(was_recent_channel_success(history, "fb", "morning", within_hours=999999))

    def test_stage_for_slot_only_selects_a_channel_compatible_stage(self) -> None:
        # A schedule where the given day/slot only supports TRUST-stage channels.
        schedule = {
            "monday": {
                "midday": [
                    {"platform": "linkedin", "allowed_funnel_stages": ["TRUST"], "enabled": True},
                ]
            }
        }
        # History with a heavy EDUCATION deficit would normally win on pure global
        # distribution deficit, but the slot only supports TRUST.
        history = {
            "posts": [{"funnel_stage": "TRUST"}] * 50 + [{"funnel_stage": "EDUCATION"}] * 1
        }
        monday_noon = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)  # a Monday
        self.assertEqual(monday_noon.strftime("%A").lower(), "monday")

        stage = stage_for_slot("midday", history=history, schedule=schedule, now_utc=monday_noon)
        self.assertEqual(stage, "TRUST")

        eligibility = eligible_channels_for_slot(
            slot="midday",
            funnel_stage=stage,
            schedule=schedule,
            now_utc=monday_noon,
        )
        self.assertTrue(eligibility["linkedin"][0], eligibility["linkedin"])

    def test_allowed_stages_for_slot_falls_back_to_all_stages_when_unconstrained(self) -> None:
        schedule = {"monday": {"midday": []}}
        allowed = allowed_stages_for_slot("midday", schedule=schedule, now_utc=datetime(2024, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(set(allowed), {"ATTENTION", "EDUCATION", "DESIRE", "TRUST", "CONVERSION"})

    def test_schedule_preview_and_execution_share_stage_for_slot(self) -> None:
        # Both worker._schedule_preview and generate_posts.generate() must resolve
        # the funnel stage for a given slot through the same stage_for_slot function
        # using the same schedule, so preview and live generation never disagree.
        schedule = load_channel_schedule()
        now = datetime(2024, 1, 3, 9, 0, tzinfo=timezone.utc)  # a Wednesday
        stage_a = stage_for_slot("morning", history={"posts": []}, schedule=schedule, now_utc=now)
        stage_b = stage_for_slot("morning", history={"posts": []}, schedule=schedule, now_utc=now)
        self.assertEqual(stage_a, stage_b)

    def test_default_weekly_schedule_gives_every_platform_real_opportunities(self) -> None:
        coverage = weekly_schedule_coverage(load_channel_schedule())
        self.assertFalse(coverage["legacy_schedule"])
        self.assertEqual(coverage["platforms_with_zero_opportunities"], [])
        for platform in ("facebook", "instagram", "linkedin"):
            self.assertGreaterEqual(coverage["platform_counts"][platform], 3, coverage)


if __name__ == "__main__":
    unittest.main()
