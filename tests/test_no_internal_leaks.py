from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import scripts.generate_posts as generate_posts  # noqa: E402

# Internal validation/agent instruction language that must never reach public
# copy. These are verbatim (or near-verbatim) strings named as active leaks in
# the CURRENT BASELINE bug report.
FORBIDDEN_SNIPPETS = [
    "use only published",
    "proof-first",
    "the product's primary job",
    "do not buy this until",
    "stop waiting for the wrong product choice",
    "proof rule",
    "proof_rule",
    "validate fit before buying",
]

PUBLIC_COPY_KEYS = ["wp_title", "wp_content", "wp_excerpt", "fb_caption", "ig_caption", "li_text"]


class NoInternalLeaksTests(unittest.TestCase):
    def _assert_no_leaks(self, content: dict) -> None:
        for key in PUBLIC_COPY_KEYS:
            text = str(content.get(key, "") or "").lower()
            for snippet in FORBIDDEN_SNIPPETS:
                self.assertNotIn(
                    snippet,
                    text,
                    f"Forbidden internal-instruction snippet '{snippet}' leaked into '{key}': {text[:400]}",
                )

    def test_generated_post_has_no_internal_instruction_leaks(self) -> None:
        content = generate_posts.generate("morning")
        self._assert_no_leaks(content)

    def test_multiple_slots_have_no_internal_instruction_leaks(self) -> None:
        for slot in ("morning", "midday", "evening"):
            content = generate_posts.generate(slot)
            self._assert_no_leaks(content)


if __name__ == "__main__":
    unittest.main()
