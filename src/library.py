from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import yaml
from rdkit import Chem

from .chemistry import calculate_substituent_descriptors, canonicalize_smiles, count_attachment_points, mol_from_smiles
from .review import default_review_block, default_version_history


LIST_FIELDS = {"class", "allowed_site_types", "direction_tags"}


def ensure_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        if ";" in value:
            return [part.strip() for part in value.split(";") if part.strip()]
        if "," in value:
            return [part.strip() for part in value.split(",") if part.strip()]
        return [value] if value else []
    return [value]


def load_yaml_records(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        records = list(data.get("substituents", []))
        return [record_with_defaults(record) for record in records]
    if isinstance(data, list):
        return [record_with_defaults(record) for record in data]
    raise ValueError(f"Unsupported YAML library shape: {path}")


def record_with_defaults(record: dict) -> dict:
    normalized = dict(record)
    normalized.setdefault("review", default_review_block(normalized))
    normalized.setdefault("version_history", default_version_history(normalized))
    return normalized


def load_csv_records(path: str | Path) -> list[dict]:
    records: list[dict] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            for field in LIST_FIELDS:
                row[field] = ensure_list(row.get(field))
            records.append(row)
    return records


def load_records(paths: Iterable[str | Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        path = Path(path)
        if path.suffix.lower() in {".yaml", ".yml"}:
            records.extend(load_yaml_records(path))
        elif path.suffix.lower() == ".csv":
            records.extend(load_csv_records(path))
        else:
            raise ValueError(f"Unsupported library file type: {path}")
    return records


def validate_substituent_record(record: dict) -> list[str]:
    errors: list[str] = []
    required = [
        "substituent_id",
        "name",
        "smiles",
        "connection_type",
        "allowed_site_types",
        "direction_tags",
    ]
    for field in required:
        if not record.get(field):
            errors.append(f"Missing required field: {field}")

    smiles = record.get("smiles")
    if smiles:
        try:
            mol = mol_from_smiles(smiles)
            attachment_count = count_attachment_points(mol)
            if attachment_count != 1:
                errors.append(f"Expected exactly one attachment point, found {attachment_count}")
            else:
                dummy = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0][0]
                if dummy.GetDegree() != 1:
                    errors.append("Attachment point must have exactly one neighbor")
        except Exception as exc:
            errors.append(str(exc))

    if not ensure_list(record.get("allowed_site_types")):
        errors.append("allowed_site_types cannot be empty")
    if not ensure_list(record.get("direction_tags")):
        errors.append("direction_tags cannot be empty")
    return errors


def enrich_substituent_record(record: dict, pubchem_metadata: dict | None = None) -> dict:
    enriched = dict(record)
    for field in LIST_FIELDS:
        enriched[field] = ensure_list(enriched.get(field))

    smiles = enriched["smiles"]
    enriched["canonical_smiles"] = canonicalize_smiles(smiles)
    descriptors = calculate_substituent_descriptors(smiles)
    enriched["attachment_count"] = descriptors.pop("attachment_count")
    enriched["calculated_descriptors"] = descriptors

    enriched.setdefault("risk", {})
    enriched["risk"].setdefault("risk_tags", [])
    enriched["risk"].setdefault("default_enabled", True)
    enriched.setdefault("priority", {})
    enriched["priority"].setdefault("mvp", True)
    enriched["priority"].setdefault("common_medchem", False)
    enriched["priority"].setdefault("default_rank", 999)
    enriched.setdefault("source", {})
    enriched["source"].setdefault("type", "curated_seed")
    enriched["source"].setdefault("version", "0.1")
    enriched["review"] = default_review_block(enriched)
    enriched["version_history"] = default_version_history(enriched)

    if pubchem_metadata:
        enriched["source"]["pubchem"] = pubchem_metadata
    return enriched


def validate_library(records: list[dict]) -> tuple[list[dict], list[dict]]:
    valid: list[dict] = []
    errors: list[dict] = []
    seen_smiles: dict[str, str] = {}

    for record in records:
        record_errors = validate_substituent_record(record)
        if record_errors:
            errors.append(
                {
                    "substituent_id": record.get("substituent_id"),
                    "name": record.get("name"),
                    "errors": record_errors,
                }
            )
            continue

        canonical = canonicalize_smiles(record["smiles"])
        if canonical in seen_smiles:
            errors.append(
                {
                    "substituent_id": record.get("substituent_id"),
                    "name": record.get("name"),
                    "errors": [f"Duplicate canonical SMILES with {seen_smiles[canonical]}: {canonical}"],
                }
            )
            continue
        seen_smiles[canonical] = record["substituent_id"]
        valid.append(record)

    return valid, errors


def save_yaml(records: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump({"substituents": records}, handle, sort_keys=False, allow_unicode=False)


def flatten_record_for_csv(record: dict) -> dict:
    desc = record.get("calculated_descriptors", {})
    risk = record.get("risk", {})
    priority = record.get("priority", {})
    source = record.get("source", {})
    return {
        "substituent_id": record.get("substituent_id"),
        "name": record.get("name"),
        "short_name": record.get("short_name"),
        "smiles": record.get("smiles"),
        "canonical_smiles": record.get("canonical_smiles"),
        "connection_type": record.get("connection_type"),
        "allowed_site_types": ";".join(ensure_list(record.get("allowed_site_types"))),
        "direction_tags": ";".join(ensure_list(record.get("direction_tags"))),
        "class": ";".join(ensure_list(record.get("class"))),
        "fragment_mw": desc.get("fragment_mw"),
        "clogp": desc.get("clogp"),
        "tpsa": desc.get("tpsa"),
        "hbd": desc.get("hbd"),
        "hba": desc.get("hba"),
        "heavy_atom_count": desc.get("heavy_atom_count"),
        "ring_count": desc.get("ring_count"),
        "aromatic_ring_count": desc.get("aromatic_ring_count"),
        "formal_charge": desc.get("formal_charge"),
        "risk_tags": ";".join(ensure_list(risk.get("risk_tags"))),
        "default_enabled": risk.get("default_enabled", True),
        "mvp": priority.get("mvp", True),
        "common_medchem": priority.get("common_medchem", False),
        "default_rank": priority.get("default_rank", 999),
        "source_type": source.get("type"),
        "source_reference": source.get("pubchem", {}).get("query") or source.get("reference"),
        "version": source.get("version"),
        "review_status": record.get("review", {}).get("status"),
        "use_cases": ";".join(ensure_list(record.get("review", {}).get("use_cases"))),
        "avoid_contexts": ";".join(ensure_list(record.get("review", {}).get("avoid_contexts"))),
        "reviewed_by": record.get("review", {}).get("reviewed_by"),
        "reviewed_at": record.get("review", {}).get("reviewed_at"),
    }


def save_csv(records: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [flatten_record_for_csv(record) for record in records]
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class SubstituentIndex:
    def __init__(self, records: list[dict]):
        self.records = records

    def query(
        self,
        direction_tags: Iterable[str] | None = None,
        site_type: str | None = None,
        compatible_connection_types: Iterable[str] | None = None,
        max_fragment_mw: float | None = None,
        include_risky: bool = False,
        include_advanced: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        wanted_tags = set(direction_tags or [])
        compatible = set(compatible_connection_types or [])
        results: list[dict] = []

        for record in self.records:
            risk = record.get("risk", {})
            priority = record.get("priority", {})
            if not include_risky and not risk.get("default_enabled", True):
                continue
            if not include_advanced and priority.get("advanced_only", False):
                continue
            if site_type and site_type not in ensure_list(record.get("allowed_site_types")):
                continue
            if compatible and record.get("connection_type") not in compatible:
                continue
            tags = set(ensure_list(record.get("direction_tags")))
            tags.update(ensure_list(record.get("class")))
            tags.update(ensure_list(record.get("risk", {}).get("risk_tags")))
            if wanted_tags and not tags.intersection(wanted_tags):
                continue
            if max_fragment_mw is not None:
                mw = record.get("calculated_descriptors", {}).get("fragment_mw")
                if mw is not None and float(mw) > max_fragment_mw:
                    continue
            results.append(record)

        results.sort(key=lambda item: item.get("priority", {}).get("default_rank", 999))
        return results[:limit] if limit is not None else results
