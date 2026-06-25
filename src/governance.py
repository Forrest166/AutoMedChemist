from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import yaml

from .chemistry import canonicalize_smiles, count_attachment_points, mol_from_smiles
from .library import ensure_list
from .scoring import load_direction_rules


SUBSTITUENT_ID_PATTERN = re.compile(r"^SUB\d{6}$")
KNOWN_CONNECTION_TYPES = {
    "single_atom_substitution",
    "carbon_attachment",
    "heteroatom_attachment",
    "aryl_attachment",
    "heteroaryl_attachment",
    "ring_attachment",
    "functional_group_replacement",
    "tail_attachment",
}
REQUIRED_FIELDS = {
    "substituent_id",
    "name",
    "smiles",
    "connection_type",
    "allowed_site_types",
    "direction_tags",
    "class",
    "source",
}


def load_site_types(path: str | Path = "data/rules/site_smarts.yaml") -> set[str]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return set((data.get("site_types") or {}).keys())


def known_direction_tags(path: str | Path = "data/rules/direction_rules.yaml") -> set[str]:
    rules = load_direction_rules(path)
    tags = set((rules.get("directions") or {}).keys())
    for direction in (rules.get("directions") or {}).values():
        tags.update(direction.get("include_tags") or [])
        for score_rule in direction.get("score_rules") or []:
            tags.update(score_rule.get("tags") or [])
    return tags


def issue(
    record: dict,
    severity: str,
    category: str,
    message: str,
    field: str | None = None,
    value: object | None = None,
) -> dict:
    return {
        "substituent_id": record.get("substituent_id"),
        "name": record.get("name"),
        "severity": severity,
        "category": category,
        "field": field or "",
        "value": "" if value is None else str(value),
        "message": message,
    }


def _check_record_shape(record: dict, site_types: set[str], direction_tags: set[str]) -> list[dict]:
    issues: list[dict] = []
    for field in REQUIRED_FIELDS:
        if not record.get(field):
            issues.append(issue(record, "error", "schema", f"Missing required field: {field}", field=field))

    substituent_id = record.get("substituent_id")
    if substituent_id and not SUBSTITUENT_ID_PATTERN.match(str(substituent_id)):
        issues.append(issue(record, "error", "schema", "substituent_id must match SUB000001 format.", "substituent_id", substituent_id))

    connection_type = record.get("connection_type")
    if connection_type and connection_type not in KNOWN_CONNECTION_TYPES:
        issues.append(issue(record, "error", "controlled_vocab", "Unknown connection_type.", "connection_type", connection_type))

    for site_type in ensure_list(record.get("allowed_site_types")):
        if site_type not in site_types:
            issues.append(issue(record, "error", "controlled_vocab", "Unknown allowed_site_type.", "allowed_site_types", site_type))

    unknown_direction_tags = [tag for tag in ensure_list(record.get("direction_tags")) if tag not in direction_tags]
    for tag in unknown_direction_tags:
        issues.append(issue(record, "warning", "controlled_vocab", "Direction tag is not defined in direction_rules.yaml.", "direction_tags", tag))

    source = record.get("source") or {}
    if not source.get("type"):
        issues.append(issue(record, "warning", "provenance", "source.type is missing.", "source.type"))
    if not (source.get("pubchem_query") or source.get("reference") or source.get("pubchem")):
        issues.append(issue(record, "warning", "provenance", "No source query, reference, or fetched metadata is attached.", "source"))
    if not source.get("version"):
        issues.append(issue(record, "warning", "provenance", "source.version is missing.", "source.version"))

    risk = record.get("risk") or {}
    if "default_enabled" in risk and not isinstance(risk.get("default_enabled"), bool):
        issues.append(issue(record, "error", "schema", "risk.default_enabled must be boolean.", "risk.default_enabled", risk.get("default_enabled")))

    priority = record.get("priority") or {}
    rank = priority.get("default_rank")
    if rank is not None:
        try:
            rank_value = float(rank)
            if rank_value < 0:
                issues.append(issue(record, "warning", "priority", "default_rank should be non-negative.", "priority.default_rank", rank))
        except Exception:
            issues.append(issue(record, "error", "schema", "priority.default_rank must be numeric.", "priority.default_rank", rank))
    return issues


def _check_chemistry(record: dict) -> list[dict]:
    issues: list[dict] = []
    smiles = record.get("smiles")
    if not smiles:
        return issues
    try:
        mol = mol_from_smiles(smiles)
        attachment_count = count_attachment_points(mol)
        if attachment_count != 1:
            issues.append(issue(record, "error", "chemistry", "Expected exactly one attachment dummy atom.", "smiles", smiles))
    except Exception as exc:
        issues.append(issue(record, "error", "chemistry", str(exc), "smiles", smiles))
    return issues


def _check_enriched_descriptors(record: dict) -> list[dict]:
    desc = record.get("calculated_descriptors")
    if not desc:
        return []
    issues: list[dict] = []
    sanity_bounds = {
        "fragment_mw": (0.0, 750.0),
        "clogp": (-10.0, 12.0),
        "tpsa": (0.0, 260.0),
        "hbd": (0, 10),
        "hba": (0, 20),
        "heavy_atom_count": (1, 80),
    }
    for key, (low, high) in sanity_bounds.items():
        value = desc.get(key)
        if value is None:
            issues.append(issue(record, "warning", "descriptor", f"Descriptor {key} is missing.", f"calculated_descriptors.{key}"))
            continue
        if value < low or value > high:
            issues.append(
                issue(
                    record,
                    "warning",
                    "descriptor",
                    f"Descriptor {key} is outside expected fragment range {low}..{high}.",
                    f"calculated_descriptors.{key}",
                    value,
                )
            )
    return issues


def _check_metadata(record: dict) -> list[dict]:
    pubchem = (record.get("source") or {}).get("pubchem") or {}
    if not pubchem:
        return [issue(record, "warning", "metadata", "No fetched PubChem/RDKit metadata payload attached.", "source.pubchem")]
    issues: list[dict] = []
    if pubchem.get("metadata_source") == "RDKit local fallback":
        issues.append(issue(record, "warning", "metadata", "PubChem fetch failed; RDKit local fallback properties were used.", "source.pubchem.metadata_source"))
    if not pubchem.get("properties"):
        issues.append(issue(record, "warning", "metadata", "Fetched metadata payload has no properties block.", "source.pubchem.properties"))
    return issues


def govern_records(
    records: Iterable[dict],
    site_rules_path: str | Path = "data/rules/site_smarts.yaml",
    direction_rules_path: str | Path = "data/rules/direction_rules.yaml",
    check_metadata: bool = True,
) -> dict:
    records = list(records)
    site_types = load_site_types(site_rules_path)
    direction_tags = known_direction_tags(direction_rules_path)
    issues: list[dict] = []
    id_counts = Counter(str(record.get("substituent_id")) for record in records if record.get("substituent_id"))
    canonical_to_ids: dict[str, list[str]] = defaultdict(list)

    for record in records:
        issues.extend(_check_record_shape(record, site_types, direction_tags))
        issues.extend(_check_chemistry(record))
        issues.extend(_check_enriched_descriptors(record))
        if check_metadata:
            issues.extend(_check_metadata(record))

        substituent_id = record.get("substituent_id")
        if substituent_id and id_counts[str(substituent_id)] > 1:
            issues.append(issue(record, "error", "dedupe", "Duplicate substituent_id.", "substituent_id", substituent_id))
        if record.get("smiles"):
            try:
                canonical_to_ids[canonicalize_smiles(record["smiles"])].append(str(substituent_id))
            except Exception:
                pass

    for canonical_smiles, ids in canonical_to_ids.items():
        unique_ids = sorted(set(ids))
        if len(unique_ids) > 1:
            for record in records:
                if str(record.get("substituent_id")) in unique_ids:
                    issues.append(issue(record, "error", "dedupe", "Duplicate canonical SMILES across records.", "smiles", canonical_smiles))

    issue_counts = Counter(item["severity"] for item in issues)
    blocked_ids = {
        str(item.get("substituent_id"))
        for item in issues
        if item.get("severity") == "error" and item.get("substituent_id")
    }
    return {
        "record_count": len(records),
        "issue_count": len(issues),
        "error_count": issue_counts.get("error", 0),
        "warning_count": issue_counts.get("warning", 0),
        "blocked_substituent_ids": sorted(blocked_ids),
        "issues": issues,
    }
