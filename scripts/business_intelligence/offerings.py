"""Offering intelligence (Master Build §15-§18).

Turns discovered sources into normalized :class:`Offering` records, then
builds the relationship graph specified in §17. Works for products today;
the same schema accepts SERVICE/SUBSCRIPTION/... rows if a different
source adapter emits them.
"""

from __future__ import annotations

import glob
import json
import os
import re
import uuid
from collections import Counter
from dataclasses import asdict
from typing import Any, Iterable

from . import evidence, paths, sources
from .schemas import Offering, OfferingGraphEdge


_NUMERIC = re.compile(r"(-?\d+(?:[.,]\d+)?)")


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUMERIC.search(str(value).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _split_csv_field(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[|,;\n]", value)
    return [p.strip() for p in parts if p.strip()]


# --- Product-brief loader ------------------------------------------------


def _load_briefs() -> dict[str, dict[str, Any]]:
    d = paths.product_briefs_dir()
    if not os.path.isdir(d):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(glob.glob(os.path.join(d, "*.json"))):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        sku = str(data.get("sku") or data.get("product_id") or "").strip()
        if sku:
            out[sku] = data
    return out


# --- CSV → Offering ------------------------------------------------------


_STOP_FEATURE_WORDS = {"the", "and", "for", "with", "our", "your", "you", "this", "that"}


def _feature_candidates(desc: str) -> list[str]:
    """Very cheap feature extractor — pulls short noun-phrase-ish snippets
    from bullet lines and sentence heads."""
    if not desc:
        return []
    lines = [l.strip(" -•*\t") for l in re.split(r"[\n\r•]+", desc) if l.strip()]
    out: list[str] = []
    for line in lines:
        if 3 <= len(line.split()) <= 14 and not line.endswith("."):
            out.append(line)
    return out[:20]


def build_from_csv() -> list[Offering]:
    """Normalize all discovered WooCommerce CSVs into Offering records.

    Merges the per-SKU JSON briefs when they exist.
    """
    briefs = _load_briefs()
    all_offerings: dict[str, Offering] = {}

    for src in sources.CsvCatalogAdapter().discover():
        for row in sources.CsvCatalogAdapter().read(src):
            sku = (row.get("SKU") or "").strip()
            product_id = (row.get("ID") or sku or uuid.uuid4().hex[:10]).strip()
            if product_id in all_offerings:
                continue
            desc_clean = row.get("Description_clean") or row.get("Short_description_clean") or ""
            categories = _split_csv_field(row.get("Categories", ""))
            tags = _split_csv_field(row.get("Tags", ""))
            images = _split_csv_field(row.get("Images", ""))
            offering = Offering(
                offering_id=product_id,
                offering_type="PRODUCT",
                name=row.get("Name", "") or sku,
                parent_offering_id=(row.get("Parent") or "").strip(),
                sku=sku,
                brand=row.get("Brands", "") or "",
                category=categories[0] if categories else "",
                subcategory=categories[1] if len(categories) > 1 else "",
                price=_to_float(row.get("Regular price")),
                sale_price=_to_float(row.get("Sale price")),
                stock_status=(row.get("In stock?") or "").strip(),
                description_raw=row.get("Description", ""),
                description_clean=desc_clean,
                features=_feature_candidates(desc_clean),
                dimensions={
                    "length_in": _to_float(row.get("Length (in)")),
                    "width_in": _to_float(row.get("Width (in)")),
                    "height_in": _to_float(row.get("Height (in)")),
                },
                weight=_to_float(row.get("Weight (lbs)")),
                images=images,
                tags=tags,
            )

            brief = briefs.get(sku) or briefs.get(product_id)
            if brief:
                offering.use_cases = list(brief.get("best_fit_use_cases", []))
                offering.functional_benefits = list(brief.get("core_benefits", []))
                offering.customer_fit = list(brief.get("best_fit_audiences", []))
                offering.problems_addressed = [brief.get("primary_pain_point", "")] if brief.get("primary_pain_point") else []
                offering.verified_facts = list(brief.get("verified_facts", []))
                offering.forbidden_claims = list(brief.get("forbidden_claims", []))
                offering.claim_constraints = [brief.get("proof_rule", "")] if brief.get("proof_rule") else []
                offering.content_opportunities = list(brief.get("hashtag_themes", []))
            all_offerings[product_id] = offering

    return list(all_offerings.values())


# --- Catalog-level intelligence (§18) -----------------------------------


def catalog_snapshot(offerings: list[Offering]) -> dict[str, Any]:
    prices = [o.price for o in offerings if o.price]
    prices.sort()
    if prices:
        low = prices[0]
        high = prices[-1]
        median = prices[len(prices) // 2]
    else:
        low = high = median = None
    cat_counter: Counter[str] = Counter()
    for o in offerings:
        if o.category:
            cat_counter[o.category] += 1
    tag_counter: Counter[str] = Counter()
    for o in offerings:
        for t in o.tags:
            tag_counter[t] += 1
    return {
        "total_offerings": len(offerings),
        "price_range": {"low": low, "median": median, "high": high},
        "top_categories": [{"name": k, "count": v} for k, v in cat_counter.most_common(8)],
        "top_tags": [{"name": k, "count": v} for k, v in tag_counter.most_common(12)],
        "with_verified_facts": sum(1 for o in offerings if o.verified_facts),
        "with_briefs": sum(1 for o in offerings if o.use_cases or o.functional_benefits),
    }


# --- Relationship graph (§17) -----------------------------------------


def build_graph(offerings: list[Offering]) -> list[OfferingGraphEdge]:
    edges: list[OfferingGraphEdge] = []
    for o in offerings:
        if o.category:
            edges.append(OfferingGraphEdge(o.offering_id, f"category:{o.category}", "IN_CATEGORY"))
        for f in o.features:
            edges.append(OfferingGraphEdge(o.offering_id, f"feature:{f[:60]}", "HAS_FEATURE"))
        for uc in o.use_cases:
            edges.append(OfferingGraphEdge(o.offering_id, f"use_case:{uc}", "ENABLES_USE_CASE"))
        for prob in o.problems_addressed:
            if prob:
                edges.append(OfferingGraphEdge(o.offering_id, f"problem:{prob[:60]}", "ADDRESSES_PROBLEM"))
        for aud in o.customer_fit:
            edges.append(OfferingGraphEdge(o.offering_id, f"segment:{aud}", "SERVES_SEGMENT"))
        for b in o.functional_benefits:
            edges.append(OfferingGraphEdge(o.offering_id, f"benefit:{b[:60]}", "PROVIDES_BENEFIT"))
    return edges


# --- Persistence -------------------------------------------------------


def offerings_json_path() -> str:
    return os.path.join(paths.offerings_dir(), "offerings.json")


def graph_json_path() -> str:
    return os.path.join(paths.offerings_dir(), "offering_graph.json")


def snapshot_json_path() -> str:
    return os.path.join(paths.offerings_dir(), "catalog_snapshot.json")


def save(offerings: list[Offering], edges: list[OfferingGraphEdge], snapshot: dict[str, Any]) -> None:
    with open(offerings_json_path(), "w", encoding="utf-8") as fh:
        json.dump({"schema_version": "bi.v1", "offerings": [asdict(o) for o in offerings]}, fh, indent=2)
    with open(graph_json_path(), "w", encoding="utf-8") as fh:
        json.dump({"schema_version": "bi.v1", "edges": [asdict(e) for e in edges]}, fh, indent=2)
    with open(snapshot_json_path(), "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2)


def load() -> list[Offering]:
    p = offerings_json_path()
    if not os.path.isfile(p):
        return []
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [Offering(**o) for o in data.get("offerings", [])]


def load_snapshot() -> dict[str, Any]:
    p = snapshot_json_path()
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_graph() -> list[OfferingGraphEdge]:
    p = graph_json_path()
    if not os.path.isfile(p):
        return []
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [OfferingGraphEdge(**e) for e in data.get("edges", [])]


# --- Evidence emission --------------------------------------------------


def emit_evidence(offerings: list[Offering]) -> int:
    """Register every non-empty offering field as a CATALOG_FACT."""
    n = 0
    for o in offerings:
        src_id = f"offering:{o.offering_id}"
        for field_name in ("name", "sku", "price", "sale_price", "category", "subcategory", "brand", "weight", "stock_status"):
            v = getattr(o, field_name, None)
            if v in ("", None, [], {}):
                continue
            rec = evidence.make_record(
                subject=f"offering:{o.offering_id}",
                field=field_name,
                value=v,
                information_type="CATALOG_FACT",
                source_id=src_id,
                domain="product_specification",
            )
            evidence.append(rec)
            n += 1
        for vf in o.verified_facts:
            rec = evidence.make_record(
                subject=f"offering:{o.offering_id}",
                field="verified_fact",
                value=vf,
                information_type="CATALOG_FACT",
                source_id=src_id,
                domain="product_specification",
            )
            evidence.append(rec)
            n += 1
    return n
