from __future__ import annotations

import json

import pytest

from consumer_life import assess_copy_fidelity, assess_product_compatibility, REQUIRED_MOMENT_FIELDS, load_consumer_foundation, select_consumer_root, validate_consumer_receipt


def test_foundation_has_broad_worlds_and_complete_concrete_moments() -> None:
    foundation = load_consumer_foundation()

    assert len(foundation["worlds"]) >= 30
    assert len(foundation["moments"]) >= 160
    assert {moment["world_id"] for moment in foundation["moments"]} == {
        world["id"] for world in foundation["worlds"]
    }
    for moment in foundation["moments"]:
        assert set(REQUIRED_MOMENT_FIELDS).issubset(moment)
        assert "education" not in " ".join(moment.get("public_categories", [])).lower()
        assert moment["useful_discovery"] != moment["curiosity_payoff"]
        assert "required_capabilities" in moment["product_fit"] or moment["product_fit"]["mode"] == "none"
    counts = {
        world["id"]: sum(moment["world_id"] == world["id"] for moment in foundation["moments"])
        for world in foundation["worlds"]
    }
    assert min(counts.values()) >= 5
    assert len({moment["useful_discovery"] for moment in foundation["moments"]}) >= 160
    assert len({moment["immediate_action"] for moment in foundation["moments"]}) >= 160


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
        preferred_moment_id="neighborhood_check_in",
    )
    content = {
        "consumer_root": root,
        "consumer_receipt": root["consumer_receipt"],
        "product_id": "SHOULD-NOT-BE-HERE",
    }

    result = validate_consumer_receipt(content)
    assert result["passed"] is False
    assert "product_forbidden_for_consumer_moment" in result["errors"]


def test_selection_avoids_recently_saturated_moment() -> None:
    baseline = select_consumer_root(current_date="2026-09-03", slot="midday")
    history = [{"consumer_moment_id": baseline["moment_id"], "quality_score": 90} for _ in range(3)]

    selected = select_consumer_root(current_date="2026-09-03", slot="midday", history=history)

    assert selected["moment_id"] != baseline["moment_id"]
    assert selected["selection_receipt"]["history_sample_size"] == 3


def test_product_compatibility_requires_verified_capabilities() -> None:
    moment = {
        "product_fit": {
            "mode": "restricted",
            "required_capabilities": ["medical_device", "quiet_operation"],
        }
    }
    ordinary_station = {"id": "station", "product_type": "power_station", "verified_facts": ["2048Wh", "2400W"]}
    supported_station = {"id": "supported", "verified_facts": ["Designed for CPAP use", "quiet low noise operation"]}

    rejected = assess_product_compatibility(moment, ordinary_station)
    accepted = assess_product_compatibility(moment, supported_station)

    assert rejected["compatible"] is False
    assert rejected["failed_requirements"] == ["medical_device", "quiet_operation"]
    assert accepted["compatible"] is True


@pytest.mark.parametrize(("product_type", "world_id"), [
    ("solar_panel", "solar_harvesting"),
    ("portable_water_filter", "water_access"),
    ("electric_bike", "electric_mobility"),
    ("expansion_battery", "modular_power_growth"),
    ("power_system_component", "modular_power_growth"),
])
def test_catalog_product_families_select_exact_compatible_world(product_type: str, world_id: str) -> None:
    root = select_consumer_root(
        current_date="2026-09-03",
        preferred_world_id=world_id,
        product_required=True,
        product={"id": product_type, "product_type": product_type},
    )

    assert root["world_id"] == world_id
    assert assess_product_compatibility(root["moment"], {"id": product_type, "product_type": product_type})["compatible"] is True


def test_copy_fidelity_requires_moment_discovery_and_action_in_public_copy() -> None:
    root = select_consumer_root(current_date="2026-09-03")
    missing = assess_copy_fidelity({"consumer_root": root, "ig_caption": "A generic product promotion."})
    faithful = assess_copy_fidelity({
        "consumer_root": root,
        "ig_caption": " ".join(str(value) for value in root["consumer_receipt"].values()),
    })

    assert missing["passed"] is False
    assert faithful["passed"] is True


def test_copy_fidelity_accepts_exact_short_location_phrase() -> None:
    root = select_consumer_root(
        current_date="2026-09-03",
        preferred_world_id="boating",
        preferred_moment_id="boating_recovery",
    )
    result = assess_copy_fidelity({
        "consumer_root": root,
        "ig_caption": " ".join(str(value) for value in root["consumer_receipt"].values()),
    })

    assert root["consumer_receipt"]["where"] == "dock"
    assert result["checks"]["where"] is True
    assert result["passed"] is True