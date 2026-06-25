from __future__ import annotations

import json
from collections import defaultdict

from rdkit import Chem

from .ring_library import normalize_attachment_smiles


def _int_or_zero(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _sorted_join(values: list[str]) -> str:
    return ";".join(sorted(dict.fromkeys(value for value in values if value)))


def canonicalize_rgroup_endpoint(smiles: str | None) -> str:
    """Canonicalize an R-group endpoint while preserving one normalized attachment atom."""
    text = str(smiles or "").strip()
    if not text:
        return ""
    try:
        return normalize_attachment_smiles(text)
    except Exception:
        mol = Chem.MolFromSmiles(text)
        if mol is None:
            return text
        dummy_index = 1
        for atom in mol.GetAtoms():
            atom.SetIsotope(0)
            if atom.GetAtomicNum() == 0:
                atom.SetAtomMapNum(dummy_index)
                dummy_index += 1
            else:
                atom.SetAtomMapNum(0)
        try:
            return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        except Exception:
            return text


def normalize_rgroup_replacement(row: dict) -> dict:
    source = canonicalize_rgroup_endpoint(row.get("source_canonical_smiles") or row.get("source_smiles"))
    target = canonicalize_rgroup_endpoint(row.get("target_canonical_smiles") or row.get("target_smiles"))
    out = dict(row)
    out["normalized_source_smiles"] = source
    out["normalized_target_smiles"] = target
    out["normalized_pair_key"] = f"{source}>>{target}" if source or target else ""
    out.setdefault("source_record_count", 1)
    out.setdefault("aggregate_edge_weight", _int_or_zero(row.get("edge_weight")))
    out.setdefault("source_replacement_ids", str(row.get("replacement_id") or ""))
    return out


def deduplicate_rgroup_replacements(rows: list[dict]) -> list[dict]:
    """Collapse directional endpoint-equivalent R-group edges and keep provenance."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        normalized = normalize_rgroup_replacement(row)
        key = normalized.get("normalized_pair_key") or str(row.get("replacement_id") or "")
        if key:
            groups[key].append(normalized)

    deduped: list[dict] = []
    for key, group in groups.items():
        representative = max(
            group,
            key=lambda item: (_int_or_zero(item.get("edge_weight")), str(item.get("replacement_id") or "")),
        )
        ids = [str(item.get("replacement_id") or "") for item in group if item.get("replacement_id")]
        layers = [str(item.get("layer") or "") for item in group if item.get("layer")]
        names = [str(item.get("source_name") or "") for item in group if item.get("source_name")]
        references = [str(item.get("source_reference") or "") for item in group if item.get("source_reference")]
        confidence_tiers = [str(item.get("source_confidence_tier") or "") for item in group if item.get("source_confidence_tier")]
        confidence_scores = [
            float(item.get("source_confidence_score"))
            for item in group
            if item.get("source_confidence_score") not in {None, ""}
        ]
        aggregate_weight = sum(_int_or_zero(item.get("edge_weight")) for item in group)
        merged = {
            **representative,
            "replacement_id": representative.get("replacement_id"),
            "normalized_pair_key": key,
            "normalized_source_smiles": representative.get("normalized_source_smiles"),
            "normalized_target_smiles": representative.get("normalized_target_smiles"),
            "representative_replacement_id": representative.get("replacement_id"),
            "source_record_count": len(group),
            "aggregate_edge_weight": aggregate_weight,
            "max_edge_weight": max(_int_or_zero(item.get("edge_weight")) for item in group),
            "source_replacement_ids": _sorted_join(ids),
            "layers": _sorted_join(layers),
            "source_names": _sorted_join(names),
            "source_references": _sorted_join(references),
            "source_confidence_tiers": _sorted_join(confidence_tiers),
            "max_source_confidence_score": round(max(confidence_scores), 4) if confidence_scores else None,
            "provenance_examples": [
                {
                    "replacement_id": item.get("replacement_id"),
                    "edge_weight": item.get("edge_weight"),
                    "layer": item.get("layer"),
                    "source_name": item.get("source_name"),
                    "source_reference": item.get("source_reference"),
                    "source_confidence_tier": item.get("source_confidence_tier"),
                }
                for item in group[:10]
            ],
        }
        deduped.append(merged)
    deduped.sort(key=lambda item: (-_int_or_zero(item.get("aggregate_edge_weight")), str(item.get("normalized_pair_key") or "")))
    return deduped


def build_rgroup_normalization_report(rows: list[dict], *, max_duplicate_examples: int = 25) -> dict:
    normalized_rows = [normalize_rgroup_replacement(row) for row in rows]
    deduped = deduplicate_rgroup_replacements(rows)
    duplicate_groups = [row for row in deduped if int(row.get("source_record_count") or 0) > 1]
    return {
        "input_count": len(rows),
        "normalized_count": len(normalized_rows),
        "deduplicated_count": len(deduped),
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_record_count": sum(int(row.get("source_record_count") or 0) - 1 for row in duplicate_groups),
        "invalid_or_blank_endpoint_count": sum(
            1
            for row in normalized_rows
            if not row.get("normalized_source_smiles") or not row.get("normalized_target_smiles")
        ),
        "top_duplicate_groups": [
            {
                "normalized_pair_key": row.get("normalized_pair_key"),
                "normalized_source_smiles": row.get("normalized_source_smiles"),
                "normalized_target_smiles": row.get("normalized_target_smiles"),
                "source_record_count": row.get("source_record_count"),
                "aggregate_edge_weight": row.get("aggregate_edge_weight"),
                "source_replacement_ids": row.get("source_replacement_ids"),
                "layers": row.get("layers"),
                "source_names": row.get("source_names"),
                "source_confidence_tiers": row.get("source_confidence_tiers"),
                "max_source_confidence_score": row.get("max_source_confidence_score"),
            }
            for row in duplicate_groups[:max_duplicate_examples]
        ],
    }


def normalized_payload(row: dict) -> str:
    payload = {
        key: value
        for key, value in row.items()
        if key
        not in {
            "payload_json",
        }
    }
    return json.dumps(payload, sort_keys=True)
