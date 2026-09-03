from __future__ import annotations

import json

import pytest

from consumer_life import REQUIRED_MOMENT_FIELDS, load_consumer_foundation, select_consumer_root, validate_consumer_receipt


def test_foundation_has_broad_worlds_and_complete_concrete_moments() -> None:
    foundation = load_consumer_foundation()

    assert len(foundation["worlds"]) >= 12
    assert len(foundation["moments"]) >= 12
    assert {moment["world_id"] for moment in foundation["moments"]} == {
        world["id"] for world in foundation["worlds"]
    }
    for moment in foundation["moments"]:
        assert set(REQUIRED_MOMENT_FIELDS).issubset(moment)
        assert "education" not in " ".join(moment.get("public_categories", [])).lower()
        assert moment["useful_discovery"] != moment["curiosity_payoff"]


def test_selection_is_deterministic_and_returns_a_consumer_receipt() -> None:
    first = select_consumer_root(current_date="2026-09-03", slot="midday", sequence=1)
    second = select_consumer_root(current_date="2026-09-03", slot="midday", sequence=1)

    assert first == second
    assert first["root_id"] == f"{first['world_id']}:{first['moment_id']}"
    assert all(str(value).strip() for value in first["consumer_receipt"].values())


def test_loader_rejects_incomplete_moment(tmp_path) -> None:
    foundation = load_consumer_foundation()
    del foundation["moments"][0]["useful_discovery"]
    invalid_path = tmp_path / "consumer-life.json"
    invalid_path.write_text(json.dumps(foundation), encoding="utf-8")

    with pytest.raises(ValueError, match="useful_discovery"):
        load_consumer_foundation(str(invalid_path))


def test_consumer_receipt_qa_rejects_dropped_fields() -> None:
    root = select_consumer_root(current_date="2026-09-03")
    content = {"consumer_root": root, "consumer_receipt": dict(root["consumer_receipt"])}
    assert validate_consumer_receipt(content)["passed"] is True

    del content["consumer_receipt"]["useful_discovery"]
    result = validate_consumer_receipt(content)
    assert result["passed"] is False
    assert "missing_consumer_receipt_useful_discovery" in result["errors"]


def test_consumer_receipt_qa_enforces_explicit_no_product_moments() -> None:
    root = select_consumer_root(
        current_date="2026-09-03",
        preferred_world_id="community_support",
    )
    content = {
        "consumer_root": root,
        "consumer_receipt": root["consumer_receipt"],
        "product_id": "SHOULD-NOT-BE-HERE",
    }

    result = validate_consumer_receipt(content)
    assert result["passed"] is False
    assert "product_forbidden_for_consumer_moment" in result["errors"]