from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from scripts.generate_hooks import select_hook  # noqa: E402
from scripts.campaign_runtime import (  # noqa: E402
    cta_is_valid_for_stage,
    load_cta_library,
    choose_cta_for_stage,
)
import scripts.generate_posts as generate_posts  # noqa: E402


class PhaseFiveSixTests(unittest.TestCase):
    def test_hook_engine_returns_category_and_score(self) -> None:
        result = select_hook(
            topic="How to protect your home from rising utility rates",
            product_name="Aferiy 3840",
            audience_segment="Prepared Homeowner",
            recent_hook_hashes=set(),
            preferred_hooks=["Power up your life"],
        )
        self.assertIn("hook", result)
        self.assertIn("hook_type", result)
        self.assertIn("component_scores", result)
        self.assertNotEqual(result["hook"].strip().lower(), "power up your life")

    def test_cta_library_load_and_select(self) -> None:
        lib = load_cta_library()
        cta = choose_cta_for_stage("EDUCATION", "", lib, set())
        self.assertTrue(cta)
        ok, reason = cta_is_valid_for_stage("EDUCATION", cta, "https://www.infenergypower.com")
        self.assertTrue(ok, msg=reason)

    def test_generator_includes_hook_type_and_valid_cta(self) -> None:
        content = generate_posts.generate("midday")
        self.assertIn("selected_hook_type", content)
        self.assertIn("selected_cta", content)
        ok, reason = cta_is_valid_for_stage(
            content.get("funnel_stage", "EDUCATION"),
            content.get("selected_cta", ""),
            content.get("destination_url", ""),
        )
        self.assertTrue(ok, msg=reason)


if __name__ == "__main__":
    unittest.main()
