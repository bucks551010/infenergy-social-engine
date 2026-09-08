import pytest

from scripts import generate_micro_mission_story
from scripts.generate_micro_mission_story import _image_prompt, _sanitize_candidate, _validate_episode


def _episode():
    return {
        "series_label": "MICRO MISSIONS",
        "episode_title": "THE FALLING LIFT",
        "threat_caption": "The backup line snaps.",
        "threat_scene": "A stalled accessibility lift begins sliding toward a landing.",
        "action_line": "I can reroute the drop.",
        "hero_action": "Infenergy dives beneath the lift and bridges its failing brake with an adaptive energy tether.",
        "resolution_caption": "The lift settles safely.",
        "resolution_scene": "The passenger rolls onto the landing while Infenergy verifies the stable brake.",
        "mission_line": "Power should return control.",
    }


def test_episode_contract_builds_one_vertical_rescue_scene_prompt():
    episode = _validate_episode(_episode())
    prompt = _image_prompt(episode)

    assert "one finished vertical 9:16 unlettered comic-book illustration" in prompt
    assert "Illustrate this physical emergency" in prompt
    assert "At the center, illustrate this intervention" in prompt
    assert "Integrate this physical result" in prompt
    assert "multi-panel page" in prompt
    assert "not a carousel" in prompt
    assert "Do not copy any wording" in prompt
    assert all(episode[key] in prompt for key in ("threat_scene", "hero_action", "resolution_scene"))


def test_episode_contract_rejects_oversized_visible_copy():
    episode = _episode()
    episode["action_line"] = "x" * 43

    with pytest.raises(RuntimeError, match="gemini_episode_text_too_long:action_line"):
        _validate_episode(episode)


def test_candidate_sanitizer_preserves_story_dimensions(tmp_path):
    from PIL import Image

    source = tmp_path / "candidate.png"
    output = tmp_path / "clean.png"
    Image.new("RGB", (1080, 1920), "#444444").save(source)

    _sanitize_candidate(source, output)

    with Image.open(output) as image:
        assert image.size == (1080, 1920)


def test_generation_uses_micro_mission_review_profile(tmp_path, monkeypatch):
    reference = tmp_path / "canon.png"
    reference.write_bytes(b"canon")
    captured = {}
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(generate_micro_mission_story, "_author_episode", _episode)

    def generate_image(content, **kwargs):
        captured.update(content)
        from PIL import Image
        Image.new("RGB", (1080, 1920), "#888888").save(kwargs["output_path"])
        return {"render_engine": "gemini", "review": {"verdict": "PASS"}}

    monkeypatch.setattr(generate_micro_mission_story, "generate_strict_gemini_image", generate_image)
    monkeypatch.setattr(generate_micro_mission_story, "_review_final_story", lambda *_args: {"all_clear": False})

    result = generate_micro_mission_story.generate(tmp_path / "output", reference)

    assert result["provider"] == "gemini"
    assert captured["visual_quality_profile"] == "micro_mission_story"
    assert "expected_text_lines" not in captured