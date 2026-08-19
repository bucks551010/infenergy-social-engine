from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from social import visual_intelligence  # noqa: E402


CASES = (
    ("product", "HELP_ME_CHOOSE", "comparison", {"id": "PPP-200", "name": "PowerPulse Pro 200"}),
    ("product_free", "MAKE_ME_THINK", "editorial", None),
    ("human_story", "START_A_CONVERSATION", "human_story", None),
    ("educational", "TEACH_ME", "how_it_works", None),
    ("preparedness", "PREPARE_ME", "checklist", None),
)


def test_representative_visual_packages_have_thesis_routes_and_art_direction():
    for label, reader_job, genre, offering in CASES:
        strategy = {
            "audience": "preparedness_focused_household",
            "customer_moment": f"a real {label.replace('_', ' ')} moment before pressure",
            "human_need": "identify what matters before equipment enters the decision",
            "angle": f"clarity for {label.replace('_', ' ')}",
            "topic": "Preparedness",
        }
        routes = visual_intelligence.build_v5_art_directions(
            strategy=strategy,
            reader_job=reader_job,
            genre_id=genre,
            platform="instagram_feed",
            offering=offering,
        )
        assert len(routes) == 3
        winner = routes[0]
        assert winner["hero_idea"]
        assert winner["scene"]
        assert winner["subject"]
        assert winner["environment"]
        assert winner["foreground"] and winner["midground"] and winner["background"]
        assert winner["light"]["source"] and winner["light"]["quality"]
        assert winner["composition"]["camera_height"] and winner["composition"]["angle"]
        assert winner["optics"]["focal_length"] and winner["optics"]["focus_point"]
        assert winner["color"]["palette"]
        assert winner["negative_space"]
        assert winner["must_not_appear"]
        assert winner["style_anchor"] == "available-light documentary reportage"
        assert winner["score"] >= routes[-1]["score"]
        prompt = visual_intelligence.compile_v5_scene_prompt(winner)
        assert "Foreground:" in prompt and "Midground:" in prompt and "Background:" in prompt
        assert "No readable text" in prompt
        if offering:
            assert winner["reference_conditioning_required"] is True
        else:
            assert winner["product_presence"] == "absent"
