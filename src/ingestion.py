from __future__ import annotations

import re
import hashlib
from pathlib import Path

import yaml
from rdkit import Chem

from .chemistry import calculate_substituent_descriptors, canonicalize_smiles
from .library import ensure_list, load_records, save_yaml, validate_library
from .review import default_review_block, default_version_history


SUB_ID_RE = re.compile(r"^SUB(\d{6})$")


def load_candidate_source(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _next_substituent_number(records: list[dict]) -> int:
    max_number = 0
    for record in records:
        match = SUB_ID_RE.match(str(record.get("substituent_id", "")))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return max_number + 1


def _reuse_existing_ids(records: list[dict]) -> dict[str, str]:
    mapping = {}
    for record in records:
        try:
            mapping[canonicalize_smiles(record["smiles"])] = record["substituent_id"]
        except Exception:
            continue
    return mapping


def candidate_id_for(canonical_smiles: str, source_type: str) -> str:
    digest = hashlib.sha1(f"{source_type}:{canonical_smiles}".encode("utf-8")).hexdigest()[:12].upper()
    return f"CAND-{digest}"


def _attachment_neighbor(smiles: str) -> Chem.Atom | None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    dummies = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
    if len(dummies) != 1:
        return None
    neighbors = list(dummies[0].GetNeighbors())
    return neighbors[0] if len(neighbors) == 1 else None


def infer_connection_type(smiles: str) -> str:
    atom = _attachment_neighbor(smiles)
    if atom is None:
        return "carbon_attachment"
    if atom.GetAtomicNum() != 6:
        return "heteroatom_attachment"
    if atom.GetIsAromatic():
        ring_atoms = set()
        mol = atom.GetOwningMol()
        for ring in mol.GetRingInfo().AtomRings():
            if atom.GetIdx() in ring:
                ring_atoms.update(ring)
        has_hetero = any(mol.GetAtomWithIdx(idx).GetAtomicNum() not in {6, 1, 0} for idx in ring_atoms)
        return "heteroaryl_attachment" if has_hetero else "aryl_attachment"
    if atom.IsInRing():
        return "ring_attachment"
    return "carbon_attachment"


def infer_allowed_site_types(connection_type: str) -> list[str]:
    if connection_type in {"carbon_attachment", "heteroatom_attachment", "aryl_attachment", "heteroaryl_attachment", "ring_attachment"}:
        return ["aromatic_CH", "aromatic_halide"]
    if connection_type == "single_atom_substitution":
        return ["aromatic_CH", "aromatic_halide"]
    return ["aromatic_CH", "aromatic_halide"]


def _has_substructure(smiles: str, smarts: str) -> bool:
    mol = Chem.MolFromSmiles(smiles)
    patt = Chem.MolFromSmarts(smarts)
    return bool(mol is not None and patt is not None and mol.HasSubstructMatch(patt))


def infer_classes(name: str, smiles: str, connection_type: str) -> list[str]:
    lowered = name.lower()
    classes = set()
    descriptors = calculate_substituent_descriptors(smiles)
    mol = Chem.MolFromSmiles(smiles)

    if connection_type == "aryl_attachment":
        classes.add("aryl")
    if connection_type == "heteroaryl_attachment":
        classes.update(["heteroaryl", "hbond_acceptor"])
    if connection_type == "ring_attachment":
        classes.add("small_ring" if descriptors["heavy_atom_count"] <= 6 else "cycloalkyl")
    if "fluoro" in lowered or (mol and any(atom.GetAtomicNum() == 9 for atom in mol.GetAtoms())):
        classes.add("fluorinated")
    if any(token in lowered for token in ["amide", "carboxamide", "glycolamide"]):
        classes.update(["amide", "polar_group", "hbond_acceptor"])
    if "ester" in lowered or _has_substructure(smiles, "[CX3](=O)[OX2][#6]"):
        classes.update(["ester", "hbond_acceptor"])
    if "sulfon" in lowered or _has_substructure(smiles, "[SX4](=O)(=O)"):
        classes.update(["sulfone", "polar_group", "hbond_acceptor"])
    if "boronic" in lowered or "boronate" in lowered:
        classes.update(["boron_reagent", "synthetic_handle"])
    if "phosphon" in lowered:
        classes.update(["phosphonate", "polar_group", "ionizable_group"])
    if any(token in lowered for token in ["piperidin", "pyrrolidin", "morpholino", "piperazine", "azetidin"]):
        classes.update(["polar_ring", "solubilizing_group", "hbond_acceptor"])
    if any(token in lowered for token in ["cyclo", "oxetan", "azetidin"]):
        classes.add("small_ring")
    if any(token in lowered for token in ["naphth", "benzoth", "benzimid", "indol"]):
        classes.add("fused_aryl")
    if any(token in lowered for token in ["alkyl", "butyl", "ethyl", "methyl"]):
        classes.add("alkyl")
    if not classes:
        classes.add("context_dependent")
    return sorted(classes)


def infer_direction_tags(smiles: str, classes: list[str]) -> list[str]:
    tags = set()
    cls = set(classes)
    descriptors = calculate_substituent_descriptors(smiles)
    if descriptors["heavy_atom_count"] <= 4:
        tags.add("small_scan")
    if descriptors["heavy_atom_count"] >= 4:
        tags.add("increase_size")
    if descriptors["tpsa"] > 10 or cls.intersection({"polar_group", "polar_ring", "heteroaryl", "hbond_acceptor"}):
        tags.update(["increase_polarity", "add_hba"])
    if descriptors["hbd"] > 0:
        tags.add("add_hbd")
    if cls.intersection({"fluorinated", "small_ring"}):
        tags.add("metabolism_blocking")
    if cls.intersection({"heteroaryl", "aryl", "fluorinated", "sulfone"}):
        tags.add("electronics_scan")
    if "heteroaryl" in cls:
        tags.add("heteroaryl_scan")
    if cls.intersection({"solubilizing_group", "polar_ring"}) or descriptors["tpsa"] >= 35:
        tags.add("improve_solubility")
    if cls.intersection({"aryl", "cycloalkyl", "alkyl", "fused_aryl"}):
        tags.add("hydrophobic_fill")
    if descriptors["clogp"] < 0.5 or descriptors["tpsa"] > 20:
        tags.add("reduce_lipophilicity")
    return sorted(tags or {"small_scan"})


def infer_risk(name: str, smiles: str, classes: list[str]) -> dict:
    lowered = name.lower()
    cls = set(classes)
    descriptors = calculate_substituent_descriptors(smiles)
    risk_tags = set()
    cautions = set()
    if descriptors["clogp"] > 1.2 or cls.intersection({"fused_aryl", "aryl"}):
        risk_tags.add("possible_lipophilicity_increase")
        cautions.add("can_increase_logp")
    if descriptors["tpsa"] > 55 or descriptors["hbd"] > 1:
        risk_tags.add("permeability_risk")
        cautions.add("may_reduce_passive_permeability")
    if any(token in lowered for token in ["piperidin", "piperazine", "pyrrolidin", "azetidin", "dimethylamino"]):
        risk_tags.add("possible_strong_basicity")
        cautions.add("basicity_context_dependent")
    if cls.intersection({"ester", "thioether"}):
        risk_tags.add("possible_soft_spot")
        cautions.add("metabolic_stability_context_dependent")
    if cls.intersection({"boron_reagent", "synthetic_handle"}):
        risk_tags.add("advanced_only")
        cautions.add("synthetic_handle_or_reactive_group")
    return {
        "risk_tags": sorted(risk_tags),
        "default_enabled": True,
        "cautions": sorted(cautions or {"context_dependent_effect"}),
    }


def infer_property_tags(smiles: str, classes: list[str]) -> dict:
    descriptors = calculate_substituent_descriptors(smiles)
    cls = set(classes)
    heavy_atoms = descriptors["heavy_atom_count"]
    size = "small" if heavy_atoms <= 4 else "medium" if heavy_atoms <= 8 else "large"
    polarity = "high" if descriptors["tpsa"] >= 45 else "medium" if descriptors["tpsa"] > 10 else "low"
    electronics = "electron_withdrawing" if cls.intersection({"fluorinated", "heteroaryl", "sulfone", "phosphonate"}) else "neutral"
    lipophilicity = "decrease" if descriptors["tpsa"] > 20 else "increase" if descriptors["clogp"] > 1.0 else "neutral"
    return {
        "size": size,
        "polarity": polarity,
        "electronics": electronics,
        "lipophilicity_effect": lipophilicity,
    }


def normalize_candidate(raw: dict, substituent_id: str, source_version: str) -> dict:
    name = raw["name"]
    smiles = raw["smiles"]
    connection_type = raw.get("connection_type") or infer_connection_type(smiles)
    canonical = canonicalize_smiles(smiles)
    source_type = raw.get("source_type") or "pubchem_query_expansion"
    candidate_id = raw.get("candidate_id") or candidate_id_for(canonical, source_type)
    classes = ensure_list(raw.get("class")) or infer_classes(name, smiles, connection_type)
    direction_tags = ensure_list(raw.get("direction_tags")) or infer_direction_tags(smiles, classes)
    record = {
        "substituent_id": substituent_id,
        "name": name,
        "short_name": raw.get("short_name") or name,
        "smiles": smiles,
        "connection_type": connection_type,
        "class": classes,
        "allowed_site_types": ensure_list(raw.get("allowed_site_types")) or infer_allowed_site_types(connection_type),
        "direction_tags": direction_tags,
        "property_tags": raw.get("property_tags") or infer_property_tags(smiles, classes),
        "risk": raw.get("risk") or infer_risk(name, smiles, classes),
        "priority": raw.get("priority")
        or {
            "mvp": True,
            "common_medchem": bool(raw.get("common_medchem", True)),
            "default_rank": int(raw.get("default_rank", 110)),
        },
        "source": {
            "type": source_type,
            "pubchem_query": raw.get("pubchem_query") or name,
            "reference": raw.get("reference"),
            "version": source_version,
            "candidate_id": candidate_id,
            "source_record_id": raw.get("source_record_id") or raw.get("pubchem_query") or name,
            "promotion_note": raw.get("promotion_note") or "Normalized from public-source candidate list.",
        },
    }
    record["review"] = raw.get("review") or default_review_block(record)
    record["version_history"] = raw.get("version_history") or default_version_history(record)
    return record


def generate_seed_from_candidates(
    source_path: str | Path,
    existing_seed_paths: list[str | Path],
    output_path: str | Path,
) -> dict:
    source = load_candidate_source(source_path)
    source_version = str(source.get("version", "0.3"))
    raw_candidates = list(source.get("candidates") or [])
    existing_records = load_records(existing_seed_paths)
    existing_by_canonical = _reuse_existing_ids(existing_records)

    previous_output = []
    output_path = Path(output_path)
    if output_path.exists():
        previous_output = load_records([output_path])
    previous_ids = _reuse_existing_ids(previous_output)

    next_number = _next_substituent_number(existing_records + previous_output)
    generated: list[dict] = []
    skipped: list[dict] = []
    for raw in raw_candidates:
        try:
            canonical = canonicalize_smiles(raw["smiles"])
        except Exception as exc:
            skipped.append({"name": raw.get("name"), "smiles": raw.get("smiles"), "reason": str(exc)})
            continue
        if canonical in existing_by_canonical:
            skipped.append({"name": raw.get("name"), "smiles": raw.get("smiles"), "reason": "duplicate_existing_library"})
            continue
        substituent_id = previous_ids.get(canonical)
        if not substituent_id:
            substituent_id = f"SUB{next_number:06d}"
            next_number += 1
        generated.append(normalize_candidate(raw, substituent_id, source_version))

    valid, errors = validate_library(generated)
    save_yaml(valid, output_path)
    return {
        "source": str(Path(source_path).resolve()),
        "output": str(output_path.resolve()),
        "candidate_count": len(raw_candidates),
        "generated_count": len(generated),
        "valid_count": len(valid),
        "skipped_count": len(skipped),
        "validation_error_count": len(errors),
        "skipped": skipped,
        "validation_errors": errors,
    }
