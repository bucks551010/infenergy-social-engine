from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(ROOT / "scripts"))

from social.static_repository import is_static_path


def test_human_truth_static_schemas_are_owner_only_and_guarded() -> None:
    repository = ROOT / "data" / "marketing" / "human_truth"
    expected = {
        "tension_library.json": "tensions",
        "human_material_reserve.json": "materials",
        "reader_value_criteria.json": "criteria",
        "trust_behaviors.json": "behaviors",
        "brand_truth.json": "approved_brand_truth",
        "visual_identity.json": "approved_visual_identity",
    }

    for file_name, required_key in expected.items():
        path = repository / file_name
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload["schema_version"] == 1
        assert payload["owner_authored_only"] is True
        assert required_key in payload
        assert is_static_path(path)