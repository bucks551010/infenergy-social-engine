"""Derive product-selection eligibility directly from product brief evidence."""

from __future__ import annotations

import json
import os
from glob import glob
from typing import Any


def _brief_index(data_dir: str) -> dict[str, dict[str, Any]]:
    briefs: dict[str, dict[str, Any]] = {}
    for path in glob(os.path.join(data_dir, "product_briefs", "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        product_id = str(payload.get("product_id") or "").strip() if isinstance(payload, dict) else ""
        if product_id:
            briefs[product_id] = payload
    return briefs


def _identifier(product: dict[str, Any]) -> str:
    return str(product.get("id") or product.get("product_id") or product.get("offering_id") or product.get("sku") or "").strip()


def filter_evidence_eligible_products(products: list[dict[str, Any]], data_dir: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Exclude only catalog entries whose matching brief lacks verified facts."""
    briefs = _brief_index(data_dir)
    eligible: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        product_id = _identifier(product)
        brief = briefs.get(product_id)
        facts = brief.get("verified_facts", []) if isinstance(brief, dict) else []
        has_facts = isinstance(facts, list) and any(str(fact).strip() for fact in facts)
        if has_facts:
            eligible.append(product)
            continue
        exclusions.append(
            {
                "product_id": product_id,
                "name": str(product.get("name") or ""),
                "reason": "zero_verified_facts" if brief is not None else "missing_product_brief",
            }
        )
    return eligible, {
        "selection_layer": "inventory_catalog_and_bi_offering",
        "eligible_pool_size": len(eligible),
        "excluded_pool_size": len(exclusions),
        "exclusions": exclusions,
    }