from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from .ring_library import normalize_attachment_smiles


DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "transform_mmp_mapping.yaml"


def load_transform_mmp_mappings(path: str | Path | None = None) -> list[dict]:
    mapping_path = Path(path) if path is not None else DEFAULT_MAPPING_PATH
    if not mapping_path.exists():
        return []
    with mapping_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("mappings") or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported transform MMP mapping shape: {mapping_path}")


def _canonical_pair(row: dict) -> tuple[str, str] | None:
    try:
        return normalize_attachment_smiles(row["from_smiles"]), normalize_attachment_smiles(row["to_smiles"])
    except Exception:
        return None


def map_mmp_to_transform_rules(mmp_rows: list[dict], mapping_rules: list[dict]) -> list[dict]:
    lookup = {}
    for row in mmp_rows:
        try:
            left = normalize_attachment_smiles(row["variable_from_smiles"])
            right = normalize_attachment_smiles(row["variable_to_smiles"])
        except Exception:
            continue
        lookup[(left, right)] = row
        lookup[(right, left)] = {**row, "variable_from_smiles": row["variable_to_smiles"], "variable_to_smiles": row["variable_from_smiles"]}

    results = []
    for rule in mapping_rules:
        pair = _canonical_pair(rule)
        if pair is None:
            continue
        hit = lookup.get(pair)
        if not hit:
            continue
        digest = hashlib.sha1(f"{rule['rule_id']}:{hit['transform_id']}:{pair}".encode("utf-8")).hexdigest()[:12].upper()
        results.append(
            {
                "mapping_id": f"TMM-{digest}",
                "rule_id": rule.get("rule_id"),
                "replacement_label": rule.get("replacement_label"),
                "transform_id": hit.get("transform_id"),
                "match_type": rule.get("match_type", "exact_variable_pair"),
                "pair_count": hit.get("pair_count"),
                "mean_delta_fragment_mw": hit.get("mean_delta_fragment_mw"),
                "mean_delta_clogp": hit.get("mean_delta_clogp"),
                "mean_delta_tpsa": hit.get("mean_delta_tpsa"),
                "variable_from_smiles": hit.get("variable_from_smiles"),
                "variable_to_smiles": hit.get("variable_to_smiles"),
            }
        )
    return results


def validate_transform_mmp_mappings(rows: list[dict]) -> dict:
    issues = []
    seen = set()
    for row in rows:
        mapping_id = row.get("mapping_id")
        if not mapping_id:
            issues.append({"severity": "error", "check": "transform_mmp_mapping_id", "item_id": None, "message": "Missing mapping_id"})
        elif mapping_id in seen:
            issues.append({"severity": "error", "check": "transform_mmp_mapping_duplicate", "item_id": mapping_id, "message": "Duplicate mapping_id"})
        seen.add(mapping_id)
    return {
        "mapping_count": len(rows),
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "issues": issues,
    }

