"""Retention: prune old snapshots from data/marketing/ and data/agents/.

Keeps latest N per prefix per day, latest M snapshots overall.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict

from ._base import env_int, utc_now, write_snapshot

_STAMP_RE = re.compile(r"(\d{8}T\d{6}Z)")


def _stamp_key(name: str) -> str:
    m = _STAMP_RE.search(name)
    return m.group(1) if m else ""


def _prefix(name: str) -> str:
    m = _STAMP_RE.search(name)
    if not m:
        return name
    return name[: m.start()].rstrip("_-")


def _prune(folder: str, keep_per_day: int, keep_total: int, dry_run: bool) -> dict:
    if not os.path.isdir(folder):
        return {"folder": folder, "removed": 0, "kept": 0, "skipped": "missing"}
    entries = [e for e in os.listdir(folder) if e.endswith(".json")]
    by_prefix_day: dict[tuple[str, str], list[str]] = defaultdict(list)
    for name in entries:
        stamp = _stamp_key(name)
        day = stamp[:8] if stamp else ""
        by_prefix_day[(_prefix(name), day)].append(name)

    removed: list[str] = []
    kept: list[str] = []
    for (_prefix_key, _day), names in by_prefix_day.items():
        names_sorted = sorted(names, reverse=True)
        for name in names_sorted[:keep_per_day]:
            kept.append(name)
        for name in names_sorted[keep_per_day:]:
            removed.append(name)

    all_sorted = sorted(entries, key=lambda n: _stamp_key(n), reverse=True)
    keep_overall = set(all_sorted[:keep_total])
    for name in list(removed):
        if name in keep_overall:
            removed.remove(name)
            kept.append(name)

    if not dry_run:
        for name in removed:
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass

    return {"folder": folder, "removed": len(removed), "kept": len(kept), "dry_run": dry_run}


def run(data_dir: str, dry_run: bool = False) -> dict:
    keep_per_day = env_int("RETENTION_KEEP_PER_DAY", 2)
    keep_total = env_int("RETENTION_KEEP_TOTAL", 50)
    targets = [
        os.path.join(data_dir, "marketing"),
        os.path.join(data_dir, "marketing", "campaigns"),
        os.path.join(data_dir, "agents"),
    ]
    results = [_prune(t, keep_per_day, keep_total, dry_run) for t in targets]
    for base in [os.path.join(data_dir, "agents")]:
        if os.path.isdir(base):
            for sub in os.listdir(base):
                sub_path = os.path.join(base, sub)
                if os.path.isdir(sub_path):
                    results.append(_prune(sub_path, keep_per_day, keep_total, dry_run))

    payload = {
        "agent": "retention",
        "time_utc": utc_now(),
        "keep_per_day": keep_per_day,
        "keep_total": keep_total,
        "results": results,
    }
    if not dry_run:
        write_snapshot(data_dir, "retention", payload)
    return payload
