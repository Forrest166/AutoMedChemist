from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

from .chemistry import calculate_descriptors, canonicalize_smiles, mol_from_smiles


DEFAULT_RING_LIBRARY_PATH = Path(__file__).resolve().parents[2] / "data" / "rings" / "ring_system_library.yaml"
DEFAULT_LITERATURE_SUBSTITUENT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "substituents" / "literature_substituent_library.yaml"
)
DEFAULT_RING_REPLACEMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "replacements" / "ring_replacements.yaml"
DEFAULT_RGROUP_REPLACEMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "replacements" / "rgroup_replacements.yaml"
DEFAULT_RING_IMPORT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "substituents" / "ring_import_state.json"


def _digest_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def normalize_attachment_smiles(smiles: str) -> str:
    text = smiles.strip()
    text = text.replace("[R]", "[*:1]")
    if text.startswith("*") and not text.startswith("[*:1]"):
        text = "[*:1]" + text[1:]
    mol = mol_from_smiles(text)
    dummy_atoms = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
    if len(dummy_atoms) != 1:
        raise ValueError(f"Expected one attachment point in {smiles!r}, found {len(dummy_atoms)}")
    dummy_atoms[0].SetAtomMapNum(1)
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def ring_classification(mol: Chem.Mol) -> tuple[str, int]:
    hetero_atom_count = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() not in {0, 1, 6})
    desc = calculate_descriptors(mol).to_dict()
    if desc["aromatic_ring_count"] and hetero_atom_count:
        return "aromatic_heterocycle", hetero_atom_count
    if desc["aromatic_ring_count"]:
        return "aromatic_carbocycle", hetero_atom_count
    if hetero_atom_count:
        return "saturated_or_partially_saturated_heterocycle", hetero_atom_count
    return "saturated_or_partially_saturated_carbocycle", hetero_atom_count


def normalize_ring_record(smiles: str, source_name: str, source_dataset: str, source_rank: int, reference: str) -> dict | None:
    try:
        mol = mol_from_smiles(smiles.strip())
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        desc = calculate_descriptors(mol).to_dict()
        ring_class, hetero_count = ring_classification(mol)
    except Exception:
        return None
    return {
        "ring_id": _digest_id("RING", canonical, source_dataset),
        "smiles": smiles.strip(),
        "canonical_smiles": canonical,
        "source_name": source_name,
        "source_dataset": source_dataset,
        "source_rank": source_rank,
        "ring_class": ring_class,
        "ring_count": desc["ring_count"],
        "hetero_atom_count": hetero_count,
        "aromatic_ring_count": desc["aromatic_ring_count"],
        "heavy_atom_count": desc["heavy_atom_count"],
        "fsp3": desc["fsp3"],
        "source_reference": reference,
    }


def normalize_literature_substituent(smiles: str, source_name: str, source_dataset: str, source_rank: int, reference: str) -> dict | None:
    try:
        normalized = normalize_attachment_smiles(smiles)
        mol = mol_from_smiles(normalized)
        desc = {
            "fragment_mw": round(float(Descriptors.MolWt(mol)), 4),
            "clogp": round(float(Crippen.MolLogP(mol)), 4),
            "tpsa": round(float(rdMolDescriptors.CalcTPSA(mol)), 4),
            "hbd": int(Lipinski.NumHDonors(mol)),
            "hba": int(Lipinski.NumHAcceptors(mol)),
            "heavy_atom_count": sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() > 1),
        }
    except Exception:
        return None
    return {
        "literature_substituent_id": _digest_id("LITSUB", normalized, source_dataset),
        "smiles": normalized,
        "canonical_smiles": normalized,
        "source_name": source_name,
        "source_dataset": source_dataset,
        "source_rank": source_rank,
        "substituent_class": classify_substituent(normalized),
        "fragment_mw": desc["fragment_mw"],
        "clogp": desc["clogp"],
        "tpsa": desc["tpsa"],
        "hbd": desc["hbd"],
        "hba": desc["hba"],
        "heavy_atom_count": desc["heavy_atom_count"],
        "source_reference": reference,
    }


def classify_substituent(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "unknown"
    if any(atom.GetAtomicNum() not in {0, 1, 6} for atom in mol.GetAtoms()):
        if any(atom.GetIsAromatic() for atom in mol.GetAtoms()):
            return "heteroatom_or_heteroaryl"
        return "polar_or_heteroatom"
    if any(atom.GetIsAromatic() for atom in mol.GetAtoms()):
        return "aryl_or_benzylic"
    return "hydrocarbon"


def noncomment_lines(path: str | Path) -> list[str]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            rows.append(stripped)
    return rows


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_shearer_ring_records(drug_path: str | Path, clinical_path: str | Path) -> list[dict]:
    reference = "https://doi.org/10.5281/zenodo.6556752"
    records: dict[str, dict] = {}
    for dataset, path in [("approved_drug_ring_systems", drug_path), ("clinical_trial_ring_systems", clinical_path)]:
        for idx, smiles in enumerate(noncomment_lines(path), start=1):
            record = normalize_ring_record(
                smiles,
                source_name="Shearer/Taylor Rings in Clinical Trials and Drugs",
                source_dataset=dataset,
                source_rank=idx,
                reference=reference,
            )
            if record:
                key = record["canonical_smiles"]
                current = records.get(key)
                if current is None or dataset == "approved_drug_ring_systems":
                    records[key] = record
    return list(records.values())


def iter_ertl_ring_records(zip_path: str | Path, limit: int = 10000, offset: int = 0):
    reference = "https://peter-ertl.com/molecular/data/"
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("rings.smi") as handle:
            rank = 0
            emitted = 0
            for raw in handle:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if not parts:
                    continue
                rank += 1
                if rank <= offset:
                    continue
                record = normalize_ring_record(
                    parts[0],
                    source_name="Ertl medicinal chemistry relevant ring systems",
                    source_dataset="ertl_4m_ring_systems",
                    source_rank=rank,
                    reference=reference,
                )
                if record:
                    emitted += 1
                    yield record
                if limit and emitted >= limit:
                    break


def load_ertl_ring_records(zip_path: str | Path, limit: int = 10000, offset: int = 0) -> list[dict]:
    records: dict[str, dict] = {}
    for record in iter_ertl_ring_records(zip_path, limit=limit, offset=offset):
        records.setdefault(record["canonical_smiles"], record)
    return list(records.values())


def merge_records_by_key(existing: list[dict], incoming: list[dict], key: str) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in existing:
        value = row.get(key)
        if value is not None:
            merged[str(value)] = row
    for row in incoming:
        value = row.get(key)
        if value is not None:
            merged.setdefault(str(value), row)
    return list(merged.values())


def load_import_state(path: str | Path = DEFAULT_RING_IMPORT_STATE_PATH) -> dict:
    state_path = Path(path)
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_import_state(state: dict, path: str | Path = DEFAULT_RING_IMPORT_STATE_PATH) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def load_natural_product_substituents(path: str | Path) -> list[dict]:
    reference = "https://peter-ertl.com/molecular/data/"
    rows = []
    seen = set()
    for idx, smiles in enumerate(noncomment_lines(path), start=1):
        record = normalize_literature_substituent(
            smiles,
            source_name="Ertl natural product substituent patterns",
            source_dataset="natural_product_substituents",
            source_rank=idx,
            reference=reference,
        )
        if record and record["canonical_smiles"] not in seen:
            rows.append(record)
            seen.add(record["canonical_smiles"])
    return rows


def load_ring_replacements(path: str | Path, limit: int = 5000) -> list[dict]:
    replacements = []
    current_query = None
    reference = "https://peter-ertl.com/molecular/data/"
    for line in noncomment_lines(path):
        parts = re.split(r"\s+", line)
        if len(parts) < 3:
            continue
        try:
            normalized = normalize_attachment_smiles(parts[0])
        except Exception:
            continue
        score = float(parts[1])
        evidence = None if parts[2] == "*" else int(float(parts[2]))
        if parts[2] == "*":
            current_query = normalized
            continue
        if current_query is None:
            continue
        row = {
            "replacement_id": _digest_id("RINGREP", current_query, normalized, score, evidence),
            "query_smiles": current_query,
            "replacement_smiles": normalized,
            "query_canonical_smiles": current_query,
            "replacement_canonical_smiles": normalized,
            "activity_delta": score,
            "evidence_count": evidence,
            "source_name": "Ertl ring replacement recommender",
            "source_reference": reference,
        }
        replacements.append(row)
        if limit and len(replacements) >= limit:
            break
    return replacements


def load_rgroup_replacements(path: str | Path, limit: int = 5000) -> list[dict]:
    reference = "https://zenodo.org/records/4741973"
    root = ET.parse(path).getroot()
    rows = []
    for center in root.findall("center"):
        try:
            center_smiles = normalize_attachment_smiles(center.attrib["SMILES"])
        except Exception:
            continue
        for first in center.findall("first_layer"):
            try:
                first_smiles = normalize_attachment_smiles(first.attrib["SMILES"])
            except Exception:
                continue
            rows.append(
                {
                    "replacement_id": _digest_id("RGREP", center_smiles, first_smiles, "first"),
                    "source_smiles": center_smiles,
                    "target_smiles": first_smiles,
                    "source_canonical_smiles": center_smiles,
                    "target_canonical_smiles": first_smiles,
                    "edge_weight": int(first.attrib.get("edge_weight") or 0),
                    "layer": "first",
                    "center_smiles": center_smiles,
                    "source_name": "Bajorath R-group replacement database top500",
                    "source_reference": reference,
                }
            )
            for second in first.findall("second_layer"):
                try:
                    second_smiles = normalize_attachment_smiles(second.attrib["SMILES"])
                except Exception:
                    continue
                rows.append(
                    {
                        "replacement_id": _digest_id("RGREP", first_smiles, second_smiles, "second"),
                        "source_smiles": first_smiles,
                        "target_smiles": second_smiles,
                        "source_canonical_smiles": first_smiles,
                        "target_canonical_smiles": second_smiles,
                        "edge_weight": int(second.attrib.get("edge_weight") or 0),
                        "layer": "second",
                        "center_smiles": center_smiles,
                        "source_name": "Bajorath R-group replacement database top500",
                        "source_reference": reference,
                    }
                )
                if limit and len(rows) >= limit:
                    return rows
            if limit and len(rows) >= limit:
                return rows
    return rows


def deduplicate_records(records: list[dict], key: str) -> list[dict]:
    seen = set()
    result = []
    for record in records:
        value = record.get(key)
        if value in seen:
            continue
        seen.add(value)
        result.append(record)
    return result


def save_structures(
    *,
    ring_records: list[dict],
    literature_substituents: list[dict],
    ring_replacements: list[dict],
    rgroup_replacements: list[dict],
    ring_out: str | Path = DEFAULT_RING_LIBRARY_PATH,
    substituent_out: str | Path = DEFAULT_LITERATURE_SUBSTITUENT_PATH,
    ring_replacements_out: str | Path = DEFAULT_RING_REPLACEMENTS_PATH,
    rgroup_replacements_out: str | Path = DEFAULT_RGROUP_REPLACEMENTS_PATH,
) -> None:
    outputs = [
        (ring_out, {"ring_systems": ring_records}),
        (substituent_out, {"literature_substituents": literature_substituents}),
        (ring_replacements_out, {"ring_replacements": ring_replacements}),
        (rgroup_replacements_out, {"rgroup_replacements": rgroup_replacements}),
    ]
    for path, payload in outputs:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def load_yaml_collection(path: str | Path, key: str) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get(key) or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported YAML collection shape: {path}")


def validate_ring_substituent_collections(
    ring_records: list[dict],
    literature_substituents: list[dict],
    ring_replacements: list[dict],
    rgroup_replacements: list[dict],
) -> dict:
    issues = []
    for collection, id_key, smiles_key in [
        (ring_records, "ring_id", "canonical_smiles"),
        (literature_substituents, "literature_substituent_id", "canonical_smiles"),
    ]:
        seen_ids = set()
        for row in collection:
            row_id = row.get(id_key)
            if not row_id:
                issues.append({"severity": "error", "check": f"{id_key}_missing", "item_id": None, "message": f"Missing {id_key}"})
            elif row_id in seen_ids:
                issues.append({"severity": "error", "check": f"{id_key}_duplicate", "item_id": row_id, "message": f"Duplicate {id_key}"})
            seen_ids.add(row_id)
            try:
                canonicalize_smiles(row[smiles_key])
            except Exception as exc:
                issues.append({"severity": "error", "check": "structure_parse", "item_id": row_id, "message": str(exc)})
    for row in ring_replacements:
        if not row.get("replacement_id"):
            issues.append({"severity": "error", "check": "ring_replacement_id", "item_id": None, "message": "Missing replacement_id"})
    for row in rgroup_replacements:
        if not row.get("replacement_id"):
            issues.append({"severity": "error", "check": "rgroup_replacement_id", "item_id": None, "message": "Missing replacement_id"})
    return {
        "ring_count": len(ring_records),
        "literature_substituent_count": len(literature_substituents),
        "ring_replacement_count": len(ring_replacements),
        "rgroup_replacement_count": len(rgroup_replacements),
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "issues": issues,
    }
