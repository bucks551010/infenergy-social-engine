"""Source ingestion adapters (Master Build §4, §5).

Each adapter implements the ``BusinessSourceAdapter`` protocol. Adapters
are additive — the current Infenergy installation only uses the ones
that map onto existing repo data, but the architecture accepts any new
adapter without redesigning the ingestion pipeline.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import re
import sqlite3
import uuid
from dataclasses import asdict
from typing import Any, Iterable, Iterator, Protocol

from . import paths
from .information_types import INFORMATION_TYPES
from .schemas import Source


HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def _clean_html(text: str) -> str:
    if not text:
        return ""
    text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8211;", "-")
    return WHITESPACE_RE.sub(" ", text).strip()


def _sha1_file(path: str) -> str:
    h = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# --- Adapter protocol -----------------------------------------------------


class BusinessSourceAdapter(Protocol):
    source_type: str

    def discover(self) -> list[Source]: ...
    def read(self, source: Source) -> Iterator[dict[str, Any]]: ...
    def identify_source_type(self, path: str) -> str: ...


# --- CSV catalog (WooCommerce export) -----------------------------------


class CsvCatalogAdapter:
    source_type = "csv_catalog"

    def __init__(self, csv_dir: str | None = None) -> None:
        self.csv_dir = csv_dir or paths.products_csv_dir()

    def identify_source_type(self, path: str) -> str:
        return self.source_type

    def discover(self) -> list[Source]:
        if not os.path.isdir(self.csv_dir):
            return []
        out: list[Source] = []
        for p in sorted(glob.glob(os.path.join(self.csv_dir, "*.csv"))):
            out.append(
                Source(
                    source_id=f"csv:{os.path.basename(p)}",
                    source_type=self.source_type,
                    location=p,
                    display_name=os.path.basename(p),
                    format="csv",
                    discovered_at=_now_iso(),
                    checksum=_sha1_file(p),
                    size_bytes=os.path.getsize(p),
                )
            )
        return out

    def read(self, source: Source) -> Iterator[dict[str, Any]]:
        with open(source.location, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                # Normalize + strip HTML from description fields on the way out
                row = {k: (v or "").strip() for k, v in row.items()}
                if "Description" in row:
                    row["Description_clean"] = _clean_html(row["Description"])
                if "Short description" in row:
                    row["Short_description_clean"] = _clean_html(row["Short description"])
                yield row


# --- JSON structured config ---------------------------------------------


class StructuredConfigAdapter:
    """Any JSON/YAML the system is told to inspect."""

    source_type = "structured_config"

    def __init__(self, files: list[str]) -> None:
        self.files = list(files)

    def identify_source_type(self, path: str) -> str:
        return self.source_type

    def discover(self) -> list[Source]:
        out: list[Source] = []
        for p in self.files:
            if not os.path.isfile(p):
                continue
            out.append(
                Source(
                    source_id=f"json:{os.path.basename(p)}",
                    source_type=self.source_type,
                    location=p,
                    display_name=os.path.basename(p),
                    format="json" if p.endswith(".json") else "yaml",
                    discovered_at=_now_iso(),
                    checksum=_sha1_file(p),
                    size_bytes=os.path.getsize(p),
                )
            )
        return out

    def read(self, source: Source) -> Iterator[dict[str, Any]]:
        try:
            with open(source.location, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
        elif isinstance(data, dict):
            yield data


# --- Markdown / plain-text document -------------------------------------


class DocumentAdapter:
    source_type = "document"

    def __init__(self, files: list[str]) -> None:
        self.files = list(files)

    def identify_source_type(self, path: str) -> str:
        return self.source_type

    def discover(self) -> list[Source]:
        out: list[Source] = []
        for p in self.files:
            if not os.path.isfile(p):
                continue
            out.append(
                Source(
                    source_id=f"doc:{os.path.basename(p)}",
                    source_type=self.source_type,
                    location=p,
                    display_name=os.path.basename(p),
                    format=os.path.splitext(p)[1].lstrip(".").lower() or "txt",
                    discovered_at=_now_iso(),
                    checksum=_sha1_file(p),
                    size_bytes=os.path.getsize(p),
                )
            )
        return out

    def read(self, source: Source) -> Iterator[dict[str, Any]]:
        try:
            with open(source.location, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return
        headings = re.findall(r"^(#{1,6})\s+(.+)$", text, flags=re.MULTILINE)
        yield {
            "path": source.location,
            "text": text,
            "headings": [h[1].strip() for h in headings],
        }


# --- Inventory SQLite adapter -------------------------------------------


class InventoryDbAdapter:
    source_type = "inventory_db"

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or paths.inventory_db_path()

    def identify_source_type(self, path: str) -> str:
        return self.source_type

    def discover(self) -> list[Source]:
        if not os.path.isfile(self.db_path):
            return []
        return [
            Source(
                source_id=f"sqlite:{os.path.basename(self.db_path)}",
                source_type=self.source_type,
                location=self.db_path,
                display_name=os.path.basename(self.db_path),
                format="sqlite",
                discovered_at=_now_iso(),
                checksum=_sha1_file(self.db_path),
                size_bytes=os.path.getsize(self.db_path),
            )
        ]

    def read(self, source: Source) -> Iterator[dict[str, Any]]:
        try:
            conn = sqlite3.connect(f"file:{source.location}?mode=ro", uri=True)
        except sqlite3.Error:
            return
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM products")
            for row in cur.fetchall():
                yield {"table": "products", **{k: row[k] for k in row.keys()}}
        except sqlite3.Error:
            pass
        try:
            cur = conn.execute("SELECT * FROM brand_profile LIMIT 1")
            for row in cur.fetchall():
                yield {"table": "brand_profile", **{k: row[k] for k in row.keys()}}
        except sqlite3.Error:
            pass
        conn.close()


# --- Founder manifesto adapter (special case of structured_config) ------


class ManifestoAdapter(StructuredConfigAdapter):
    source_type = "manifesto"

    def __init__(self, path: str | None = None) -> None:
        super().__init__([path or paths.founder_manifesto_path()])


# --- Product brief directory --------------------------------------------


class ProductBriefsAdapter:
    source_type = "product_briefs"

    def __init__(self, briefs_dir: str | None = None) -> None:
        self.dir = briefs_dir or paths.product_briefs_dir()

    def identify_source_type(self, path: str) -> str:
        return self.source_type

    def discover(self) -> list[Source]:
        if not os.path.isdir(self.dir):
            return []
        out: list[Source] = []
        for p in sorted(glob.glob(os.path.join(self.dir, "*.json"))):
            out.append(
                Source(
                    source_id=f"brief:{os.path.basename(p)}",
                    source_type=self.source_type,
                    location=p,
                    display_name=os.path.basename(p),
                    format="json",
                    discovered_at=_now_iso(),
                    checksum=_sha1_file(p),
                    size_bytes=os.path.getsize(p),
                )
            )
        return out

    def read(self, source: Source) -> Iterator[dict[str, Any]]:
        try:
            with open(source.location, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            yield data


# --- Performance data (post history) ------------------------------------


class PerformanceDataAdapter:
    source_type = "performance"

    def __init__(self, path: str | None = None) -> None:
        self.path = path or paths.post_history_path()

    def identify_source_type(self, path: str) -> str:
        return self.source_type

    def discover(self) -> list[Source]:
        if not os.path.isfile(self.path):
            return []
        return [
            Source(
                source_id=f"perf:{os.path.basename(self.path)}",
                source_type=self.source_type,
                location=self.path,
                display_name=os.path.basename(self.path),
                format="json",
                discovered_at=_now_iso(),
                checksum=_sha1_file(self.path),
                size_bytes=os.path.getsize(self.path),
            )
        ]

    def read(self, source: Source) -> Iterator[dict[str, Any]]:
        try:
            with open(source.location, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        history = data.get("history", data) if isinstance(data, dict) else data
        if isinstance(history, list):
            for entry in history:
                if isinstance(entry, dict):
                    yield entry


# --- Source registry ----------------------------------------------------


def registry_path() -> str:
    return os.path.join(paths.sources_dir(), "source_registry.json")


def save_registry(sources: Iterable[Source]) -> None:
    payload = {
        "schema_version": "bi.v1",
        "generated_at": _now_iso(),
        "sources": [asdict(s) for s in sources],
    }
    with open(registry_path(), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def load_registry() -> list[Source]:
    p = registry_path()
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return [Source(**s) for s in data.get("sources", [])]


# --- Discovery orchestrator ---------------------------------------------


def discover_all() -> list[Source]:
    """Discover all Infenergy-known sources on the filesystem."""
    marketing = paths.marketing_dir()
    manifesto = paths.founder_manifesto_path()
    brand_profiles = sorted(glob.glob(os.path.join(marketing, "brand_profile_*.json")))
    marketing_strategies = sorted(glob.glob(os.path.join(marketing, "marketing_strategy_*.json")))
    weekly_plans = sorted(glob.glob(os.path.join(marketing, "weekly_plan_*.json")))
    execution_packs = sorted(glob.glob(os.path.join(marketing, "execution_pack_*.json")))
    other_configs = [
        os.path.join(marketing, "channel_schedule.json"),
        os.path.join(marketing, "funnel_config.json"),
        os.path.join(marketing, "cta_library.json"),
        os.path.join(marketing, "anti_repeat_config.json"),
    ]

    adapters: list[BusinessSourceAdapter] = [
        CsvCatalogAdapter(),
        ManifestoAdapter(manifesto),
        StructuredConfigAdapter(brand_profiles + marketing_strategies + weekly_plans + execution_packs + other_configs),
        ProductBriefsAdapter(),
        InventoryDbAdapter(),
        PerformanceDataAdapter(),
    ]
    all_sources: list[Source] = []
    for a in adapters:
        all_sources.extend(a.discover())
    save_registry(all_sources)
    return all_sources
