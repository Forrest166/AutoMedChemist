from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .ring_library import load_yaml_collection, normalize_attachment_smiles


DEFAULT_RGROUP_REPLACEMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "replacements" / "rgroup_replacements.yaml"
DEFAULT_RING_REPLACEMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "replacements" / "ring_replacements.yaml"


def _canonical_attachment(value: str | None) -> str | None:
    if not value or "*" not in str(value):
        return None
    try:
        return normalize_attachment_smiles(str(value))
    except Exception:
        return None


@lru_cache(maxsize=8)
def _load_sar_neighborhood_data_cached(rgroup_path: str, ring_path: str) -> dict:
    rgroup_file = Path(rgroup_path) if rgroup_path is not None else DEFAULT_RGROUP_REPLACEMENTS_PATH
    ring_file = Path(ring_path) if ring_path is not None else DEFAULT_RING_REPLACEMENTS_PATH
    return {
        "rgroup_replacements": load_yaml_collection(rgroup_file, "rgroup_replacements") if rgroup_file.exists() else [],
        "ring_replacements": load_yaml_collection(ring_file, "ring_replacements") if ring_file.exists() else [],
    }


def load_sar_neighborhood_data(
    rgroup_path: str | Path | None = None,
    ring_path: str | Path | None = None,
) -> dict:
    rgroup_file = str(Path(rgroup_path) if rgroup_path is not None else DEFAULT_RGROUP_REPLACEMENTS_PATH)
    ring_file = str(Path(ring_path) if ring_path is not None else DEFAULT_RING_REPLACEMENTS_PATH)
    return _load_sar_neighborhood_data_cached(rgroup_file, ring_file)


def candidate_sar_neighborhood(row: dict, data: dict | None = None, *, max_examples: int = 5) -> dict:
    data = data or load_sar_neighborhood_data()
    target = _canonical_attachment(row.get("substituent_smiles"))
    if not target:
        return {
            "sar_neighborhood_count": 0,
            "sar_neighborhood_strength": "none",
            "sar_neighborhood_score": 40.0,
            "sar_neighbor_ids": "",
            "sar_neighbor_note": "No attachment fragment available for SAR neighborhood lookup.",
        }

    hits = []
    for item in data.get("rgroup_replacements") or []:
        source = item.get("source_canonical_smiles") or item.get("source_smiles")
        target_smiles = item.get("target_canonical_smiles") or item.get("target_smiles")
        if target in {source, target_smiles}:
            hits.append(
                {
                    "neighbor_id": item.get("replacement_id"),
                    "source_smiles": source,
                    "target_smiles": target_smiles,
                    "edge_weight": int(item.get("edge_weight") or 0),
                    "layer": item.get("layer"),
                    "source_name": item.get("source_name"),
                }
            )
    for item in data.get("ring_replacements") or []:
        source = item.get("query_canonical_smiles") or item.get("query_smiles")
        target_smiles = item.get("replacement_canonical_smiles") or item.get("replacement_smiles")
        if target in {source, target_smiles}:
            hits.append(
                {
                    "neighbor_id": item.get("replacement_id"),
                    "source_smiles": source,
                    "target_smiles": target_smiles,
                    "edge_weight": int(item.get("evidence_count") or 0),
                    "layer": "ring",
                    "source_name": item.get("source_name"),
                }
            )

    hits.sort(key=lambda item: int(item.get("edge_weight") or 0), reverse=True)
    total_weight = sum(max(int(item.get("edge_weight") or 0), 0) for item in hits)
    if total_weight >= 100 or len(hits) >= 5:
        strength = "high"
        score = 88.0
    elif total_weight >= 20 or len(hits) >= 2:
        strength = "medium"
        score = 74.0
    elif hits:
        strength = "low"
        score = 58.0
    else:
        strength = "none"
        score = 40.0
    examples = hits[:max_examples]
    return {
        "sar_neighborhood_count": len(hits),
        "sar_neighborhood_weight": total_weight,
        "sar_neighborhood_strength": strength,
        "sar_neighborhood_score": score,
        "sar_neighbor_ids": ";".join(str(item.get("neighbor_id")) for item in examples if item.get("neighbor_id")),
        "sar_neighbor_examples": examples,
        "sar_neighbor_note": (
            f"{strength} local SAR neighborhood from {len(hits)} ring/R-group replacement edges."
            if hits
            else "No local ring/R-group SAR neighborhood hit."
        ),
    }


def annotate_sar_neighborhoods(rows: list[dict], data: dict | None = None) -> list[dict]:
    data = data or load_sar_neighborhood_data()
    return [{**row, **candidate_sar_neighborhood(row, data)} for row in rows]
