from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from social.static_repository import REPOSITORY_ROOT, guard_static_write, is_static_path, write_living_json


def test_static_repository_paths_are_read_only() -> None:
    static_path = REPOSITORY_ROOT / "data" / "marketing" / "human_truth" / "tension_library.json"

    assert is_static_path(static_path)
    with pytest.raises(RuntimeError, match="static_repository_write_blocked"):
        guard_static_write(static_path)


def test_living_repository_writer_rejects_static_paths_and_allows_living_paths(tmp_path) -> None:
    static_path = REPOSITORY_ROOT / "data" / "marketing" / "human_truth" / "human_material_reserve.json"
    with pytest.raises(RuntimeError, match="static_repository_write_blocked"):
        write_living_json(static_path, {"materials": []})

    living_path = tmp_path / "living.json"
    write_living_json(living_path, {"status": "ok"})

    assert living_path.read_text(encoding="utf-8").strip() == '{\n  "status": "ok"\n}'