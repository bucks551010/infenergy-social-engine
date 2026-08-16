from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

import run_engine  # noqa: E402
import worker  # noqa: E402


class PhaseElevenTwelveTests(unittest.TestCase):
    def test_platform_history_records_shape(self) -> None:
        content = {
            "post_id": "post_123",
            "campaign_id": "camp_123",
            "funnel_stage": "EDUCATION",
            "audience_segment": "Prepared Buyer",
            "product_id": "100",
            "topic": "Energy readiness",
            "selected_hook": "Most homes miss this",
            "selected_hook_type": "question",
            "selected_cta": "Read more",
            "quality_score": 88,
            "destination_url": "https://example.com/product",
            "platform_posts": {
                "facebook": {"cta": "Read more", "content_format": "comparison"},
                "instagram": {"cta": "Save this", "content_format": "short_caption"},
                "linkedin": {"cta": "See details", "content_format": "authority_post"},
            },
        }
        ids = {
            "wordpress": "skipped",
            "facebook": "fb_1",
            "instagram": "ig_1",
            "linkedin": "li_1",
        }
        links = {
            "facebook": "https://example.com/product?utm_source=facebook",
            "instagram": "https://example.com/product?utm_source=instagram",
            "linkedin": "https://example.com/product?utm_source=linkedin",
            "wordpress": "https://example.com/product",
        }
        rows = run_engine._build_platform_history_records(
            content=content,
            run_started="2026-01-01T00:00:00+00:00",
            effective_channels={"wordpress": False, "facebook": True, "instagram": True, "linkedin": True},
            dry_run=True,
            ids=ids,
            tracked_links=links,
            error_map={},
        )
        self.assertEqual(len(rows), 3)
        self.assertNotIn("wordpress", {row["platform"] for row in rows})
        expected = {
            "post_id",
            "platform_post_id",
            "campaign_id",
            "platform",
            "published_at",
            "funnel_stage",
            "audience_segment",
            "product_id",
            "topic",
            "hook",
            "hook_type",
            "cta",
            "content_format",
            "quality_score",
            "destination_url",
            "utm_url",
            "status",
            "error",
        }
        for row in rows:
            self.assertTrue(expected.issubset(set(row.keys())))

    def test_quality_report_aggregates(self) -> None:
        posts = [
            {
                "quality_score": 90,
                "funnel_stage": "EDUCATION",
                "status": "success",
                "platform_records": [
                    {"platform": "facebook", "error": None},
                    {"platform": "linkedin", "error": "timeout"},
                ],
                "duplicate_reasons": ["duplicate_hook_within_window"],
                "validation_errors": [],
            },
            {
                "quality_score": 70,
                "funnel_stage": "DESIRE",
                "status": "skipped_validation_or_quality",
                "platform_records": [
                    {"platform": "instagram", "error": None},
                ],
                "duplicate_reasons": [],
                "validation_errors": ["claim_mismatch"],
            },
        ]
        report = worker._quality_report(posts)
        self.assertEqual(report["sample_size"], 2)
        self.assertEqual(report["scores"]["count"], 2)
        self.assertIn("facebook", report["platform_distribution"])
        self.assertIn("EDUCATION", report["funnel_stage_distribution"])
        self.assertGreaterEqual(len(report["rejected_posts"]), 1)

    def test_parse_preview_params_sanitizes_values(self) -> None:
        params = {
            "platform": ["bad"],
            "slot": ["badslot"],
            "funnel_stage": ["not-a-stage"],
            "product_id": ["sku-1"],
        }
        parsed = worker._parse_preview_params(params)
        self.assertEqual(parsed["slot"], "morning")
        self.assertEqual(parsed["platform"], "")
        self.assertEqual(parsed["funnel_stage"], "")
        self.assertEqual(parsed["product_id"], "sku-1")

    def test_content_preview_passes_source_overrides(self) -> None:
        preview_params = {
            "platform": "facebook",
            "slot": "midday",
            "funnel_stage": "TRUST",
            "product_id": "123",
        }
        generated = {
            "funnel_stage": "TRUST",
            "product_id": "123",
            "platform_posts": {
                "facebook": {"platform": "facebook"},
                "instagram": {"platform": "instagram"},
            },
        }
        with patch.object(worker.generate_posts, "generate", return_value=generated) as mock_generate:
            content = worker._content_preview(preview_params)

        mock_generate.assert_called_once_with(
            "midday",
            funnel_stage_override="TRUST",
            product_id_override="123",
            pipeline_override="",
        )
        self.assertEqual(list(content["platform_posts"].keys()), ["facebook"])
        self.assertIn("funnel_stage_override_applied", content["preview_notes"])
        self.assertIn("requested_product_matched", content["preview_notes"])


if __name__ == "__main__":
    unittest.main()
