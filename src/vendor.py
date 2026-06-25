from __future__ import annotations

import csv
from pathlib import Path

from .chemistry import canonicalize_smiles


DEFAULT_VENDOR_OVERLAY_PATH = Path(__file__).resolve().parents[2] / "data" / "vendor" / "reagent_availability_overlay.csv"


def _coerce_overlay_row(row: dict) -> dict:
    coerced = dict(row)
    for key in ["lead_time_days", "min_order_mg", "route_steps"]:
        value = coerced.get(key)
        coerced[key] = int(value) if value not in {None, ""} else None
    for key in ["route_confidence"]:
        value = coerced.get(key)
        coerced[key] = float(value) if value not in {None, ""} else None
    return coerced


def load_vendor_overlay(path: str | Path | None = None) -> list[dict]:
    overlay_path = Path(path) if path is not None else DEFAULT_VENDOR_OVERLAY_PATH
    if not overlay_path.exists():
        return []
    with overlay_path.open("r", encoding="utf-8", newline="") as handle:
        return [_coerce_overlay_row(row) for row in csv.DictReader(handle)]


def overlay_lookup(rows: list[dict]) -> dict[tuple[str, str], dict]:
    lookup = {}
    for row in rows:
        record_key = str(row.get("record_key") or "").strip()
        key_type = str(row.get("key_type") or "substituent_id").strip()
        if record_key:
            lookup[(key_type, record_key)] = row
    return lookup


def match_vendor_overlay(record: dict, lookup: dict[tuple[str, str], dict]) -> dict | None:
    candidates = [
        ("substituent_id", record.get("substituent_id")),
        ("canonical_smiles", record.get("canonical_smiles")),
        ("smiles", record.get("smiles")),
    ]
    if record.get("smiles"):
        try:
            candidates.append(("canonical_smiles", canonicalize_smiles(record["smiles"])))
        except Exception:
            pass
    for key_type, key in candidates:
        if key is None:
            continue
        hit = lookup.get((key_type, str(key)))
        if hit:
            vendor = dict(hit)
            vendor.pop("record_key", None)
            vendor.pop("key_type", None)
            return vendor
    return None


def apply_vendor_overlay(records: list[dict], rows: list[dict]) -> list[dict]:
    lookup = overlay_lookup(rows)
    enriched = []
    for record in records:
        updated = dict(record)
        vendor = match_vendor_overlay(updated, lookup)
        if vendor:
            updated["vendor"] = vendor
        enriched.append(updated)
    return enriched


def score_vendor_availability(substituent: dict) -> float | None:
    vendor = substituent.get("vendor") or {}
    if not vendor:
        return None

    availability_base = {
        "in_stock": 100.0,
        "building_block": 88.0,
        "reagent_route": 76.0,
        "custom_route": 52.0,
        "unknown": 55.0,
        "unavailable": 10.0,
    }.get(str(vendor.get("availability_tier") or "unknown"), 55.0)
    price_penalty = {"low": 0.0, "medium": 7.0, "high": 16.0}.get(str(vendor.get("price_tier") or "medium"), 7.0)
    lead_time = vendor.get("lead_time_days")
    lead_penalty = min(float(lead_time or 0) * 1.2, 24.0)
    route_step_penalty = min(float(vendor.get("route_steps") or 0) * 2.5, 10.0)
    confidence_bonus = float(vendor.get("route_confidence") or 0.0) * 8.0
    bucket_bonus = {"quick_purchase": 5.0, "standard_route": 0.0, "custom_synthesis": -8.0, "blocked": -45.0}.get(
        procurement_bucket(vendor),
        -2.0,
    )
    return max(0.0, min(100.0, availability_base - price_penalty - lead_penalty - route_step_penalty + confidence_bonus + bucket_bonus))


def procurement_bucket(vendor: dict | None) -> str:
    vendor = vendor or {}
    if not vendor:
        return "unknown"
    explicit = str(vendor.get("procurement_bucket") or "").strip()
    if explicit:
        return explicit
    availability = str(vendor.get("availability_tier") or "unknown")
    lead_time = float(vendor.get("lead_time_days") or 999)
    confidence = float(vendor.get("route_confidence") or 0.0)
    if availability == "unavailable":
        return "blocked"
    if availability in {"in_stock", "building_block"} and lead_time <= 5 and confidence >= 0.75:
        return "quick_purchase"
    if availability in {"building_block", "reagent_route"} and lead_time <= 14 and confidence >= 0.55:
        return "standard_route"
    if availability == "custom_route":
        return "custom_synthesis"
    return "review"


def availability_summary(substituent: dict, site_type: str | None = None) -> dict:
    vendor = substituent.get("vendor") or {}
    bucket = procurement_bucket(vendor)
    return {
        "availability_tier": vendor.get("availability_tier"),
        "procurement_bucket": bucket,
        "price_tier": vendor.get("price_tier"),
        "lead_time_days": vendor.get("lead_time_days"),
        "route_confidence": vendor.get("route_confidence"),
        "route_steps": vendor.get("route_steps"),
        "min_order_mg": vendor.get("min_order_mg"),
        "vector_context": vendor.get("vector_context") or site_type,
        "suggested_building_block": vendor.get("suggested_building_block"),
        "reaction_family": vendor.get("reaction_family"),
        "availability_source_url": vendor.get("availability_source_url"),
        "availability_note": vendor.get("notes"),
    }
