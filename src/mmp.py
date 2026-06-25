from __future__ import annotations

import hashlib
import itertools
from collections import defaultdict
from pathlib import Path

import yaml
from rdkit import Chem
from rdkit.Chem import rdMMPA

from .chemistry import calculate_substituent_descriptors


DEFAULT_MMP_EVIDENCE_PATH = Path(__file__).resolve().parents[2] / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"


def _canonical_fragment(smiles: str) -> str | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        return None
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def _single_cut_fragments(smiles: str, max_cut_bonds: int = 20) -> list[tuple[str, str]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []
    try:
        fragments = rdMMPA.FragmentMol(mol, maxCuts=1, maxCutBonds=max_cut_bonds, resultsAsMols=False)
    except Exception:
        return []

    pairs = []
    for _unused, fragment_pair in fragments:
        parts = [part for part in str(fragment_pair).split(".") if part]
        if len(parts) != 2:
            continue
        left = _canonical_fragment(parts[0])
        right = _canonical_fragment(parts[1])
        if not left or not right:
            continue
        pairs.append((left, right))
    return pairs


def build_mmp_transform_evidence(
    molecules: list[dict],
    *,
    min_pair_count: int = 2,
    max_transforms: int = 250,
    source_name: str = "ChEMBL rdMMPA",
) -> list[dict]:
    core_to_variables: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for molecule in molecules:
        structures = molecule.get("molecule_structures") or {}
        smiles = structures.get("canonical_smiles") or molecule.get("canonical_smiles") or molecule.get("smiles")
        chembl_id = str(molecule.get("molecule_chembl_id") or molecule.get("id") or "")
        if not smiles:
            continue
        for left, right in _single_cut_fragments(smiles):
            core_to_variables[left][right].add(chembl_id)
            core_to_variables[right][left].add(chembl_id)

    aggregate: dict[tuple[str, str], dict] = {}
    for core, variables in core_to_variables.items():
        if len(variables) < 2:
            continue
        for left, right in itertools.combinations(sorted(variables), 2):
            key = (left, right)
            item = aggregate.setdefault(
                key,
                {
                    "variable_from_smiles": left,
                    "variable_to_smiles": right,
                    "cores": set(),
                    "examples": set(),
                    "from_examples": set(),
                    "to_examples": set(),
                },
            )
            item["cores"].add(core)
            item["examples"].update(variables[left])
            item["examples"].update(variables[right])
            item["from_examples"].update(variables[left])
            item["to_examples"].update(variables[right])

    rows = []
    for (left, right), item in aggregate.items():
        pair_count = len(item["cores"])
        if pair_count < min_pair_count:
            continue
        left_desc = calculate_substituent_descriptors(left)
        right_desc = calculate_substituent_descriptors(right)
        transform_key = f"{left}>{right}"
        digest = hashlib.sha1(transform_key.encode("utf-8")).hexdigest()[:12].upper()
        rows.append(
            {
                "transform_id": f"MMP-{digest}",
                "variable_from_smiles": left,
                "variable_to_smiles": right,
                "pair_count": pair_count,
                "core_count": pair_count,
                "example_count": len(item["examples"]),
                "example_molecule_ids": sorted(example for example in item["examples"] if example)[:20],
                "from_example_molecule_ids": sorted(example for example in item["from_examples"] if example)[:20],
                "to_example_molecule_ids": sorted(example for example in item["to_examples"] if example)[:20],
                "mean_delta_fragment_mw": round(right_desc["fragment_mw"] - left_desc["fragment_mw"], 4),
                "mean_delta_clogp": round(right_desc["clogp"] - left_desc["clogp"], 4),
                "mean_delta_tpsa": round(right_desc["tpsa"] - left_desc["tpsa"], 4),
                "source_name": source_name,
            }
        )

    rows.sort(key=lambda row: (row["pair_count"], row["example_count"]), reverse=True)
    return rows[:max_transforms]


def load_mmp_evidence(path: str | Path | None = None) -> list[dict]:
    evidence_path = Path(path) if path is not None else DEFAULT_MMP_EVIDENCE_PATH
    if not evidence_path.exists():
        return []
    with evidence_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("transforms") or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported MMP evidence shape: {evidence_path}")


def validate_mmp_evidence(rows: list[dict]) -> dict:
    issues = []
    seen = set()
    for row in rows:
        transform_id = row.get("transform_id")
        if not transform_id:
            issues.append({"severity": "error", "check": "mmp_transform_id", "message": "Missing transform_id", "item_id": None})
        elif transform_id in seen:
            issues.append({"severity": "error", "check": "mmp_duplicate_transform_id", "message": "Duplicate transform_id", "item_id": transform_id})
        seen.add(transform_id)
        for field in ["variable_from_smiles", "variable_to_smiles"]:
            value = row.get(field)
            if not value or Chem.MolFromSmiles(value) is None:
                issues.append({"severity": "error", "check": "mmp_fragment_smiles", "message": f"Invalid {field}: {value}", "item_id": transform_id})
        if int(row.get("pair_count") or 0) <= 0:
            issues.append({"severity": "warning", "check": "mmp_pair_count", "message": "pair_count should be positive", "item_id": transform_id})
    return {
        "evidence_count": len(rows),
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "issues": issues,
    }


def save_mmp_evidence(rows: list[dict], path: str | Path, metadata: dict | None = None) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_name": "ChEMBL rdMMPA",
        "version": "mmp-0.1",
        "description": "Single-cut matched molecular pair transform evidence mined from ChEMBL molecule records.",
        "metadata": metadata or {},
        "transforms": rows,
    }
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
