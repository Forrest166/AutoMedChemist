from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from statistics import mean

from rdkit import Chem

from .mmp import DEFAULT_MMP_EVIDENCE_PATH, load_mmp_evidence
from .ring_library import load_yaml_collection
from .target_context import normalize_assay_type, normalize_endpoint_group
from .target_families import normalize_target_context, normalize_target_family


DEFAULT_RING_REPLACEMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "replacements" / "ring_replacements.yaml"
DEFAULT_RGROUP_REPLACEMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "replacements" / "rgroup_replacements.yaml"


@lru_cache(maxsize=8)
def _load_replacement_rows(ring_path: str, rgroup_path: str, mmp_path: str = "") -> tuple[dict, ...]:
    rows = []
    ring_file = Path(ring_path)
    rgroup_file = Path(rgroup_path)
    if ring_file.exists():
        for row in load_yaml_collection(ring_file, "ring_replacements"):
            rows.append(
                {
                    **row,
                    "local_evidence_type": "ring_replacement",
                    "source_smiles": row.get("query_canonical_smiles") or row.get("query_smiles"),
                    "target_smiles": row.get("replacement_canonical_smiles") or row.get("replacement_smiles"),
                    "weight": row.get("evidence_count"),
                }
            )
    if rgroup_file.exists():
        for row in load_yaml_collection(rgroup_file, "rgroup_replacements"):
            rows.append(
                {
                    **row,
                    "local_evidence_type": "rgroup_replacement",
                    "source_smiles": row.get("source_canonical_smiles") or row.get("source_smiles"),
                    "target_smiles": row.get("target_canonical_smiles") or row.get("target_smiles"),
                    "weight": row.get("edge_weight"),
                }
            )
    mmp_file = Path(mmp_path) if mmp_path else None
    if mmp_file and mmp_file.exists():
        for row in load_mmp_evidence(mmp_file):
            rows.append(
                {
                    **row,
                    "replacement_id": row.get("transform_id"),
                    "local_evidence_type": "public_mmp",
                    "source_smiles": row.get("variable_from_smiles"),
                    "target_smiles": row.get("variable_to_smiles"),
                    "weight": row.get("pair_count") or row.get("core_count") or row.get("example_count"),
                    "activity_delta": row.get("mean_delta_pchembl"),
                }
            )
    return tuple(rows)


def _mol_without_dummies(smiles: str | None) -> Chem.Mol | None:
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        return None
    rw = Chem.RWMol(mol)
    for atom in sorted((atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0), reverse=True):
        rw.RemoveAtom(atom)
    cleaned = rw.GetMol()
    try:
        Chem.SanitizeMol(cleaned)
    except Exception:
        return None
    return cleaned


def _query_mol(smarts: str | None) -> Chem.Mol | None:
    if not smarts:
        return None
    return Chem.MolFromSmarts(str(smarts))


def _matches(query: Chem.Mol | None, target: Chem.Mol | None) -> bool:
    if query is None or target is None:
        return False
    return target.HasSubstructMatch(query) or query.HasSubstructMatch(target)


def _strength(hit_count: int, total_weight: int) -> tuple[str, float]:
    if hit_count >= 6 or total_weight >= 250:
        return "high", 88.0
    if hit_count >= 2 or total_weight >= 40:
        return "medium", 74.0
    if hit_count:
        return "low", 58.0
    return "none", 42.0


def _item_target_families(item: dict) -> set[str]:
    families: set[str] = set()
    for field in ["target_family_normalized", "target_family", "target_family_label"]:
        value = item.get(field)
        if value:
            if field == "target_family_normalized":
                families.add(str(value))
            else:
                families.add(str(normalize_target_family(str(value)).get("target_family_normalized") or ""))
    context = item.get("target_context") if isinstance(item.get("target_context"), dict) else {}
    if context:
        normalized = normalize_target_context(context).get("target_family_normalized")
        if normalized:
            families.add(str(normalized))
    for summary_field in ["target_family_summaries", "target_family_summary", "family_summaries"]:
        summaries = item.get(summary_field) or []
        if isinstance(summaries, dict):
            summaries = [summaries]
        for summary in summaries:
            if not isinstance(summary, dict):
                continue
            normalized = summary.get("target_family_normalized")
            if not normalized and summary.get("target_family"):
                normalized = normalize_target_family(str(summary.get("target_family"))).get("target_family_normalized")
            if normalized:
                families.add(str(normalized))
    return {family for family in families if family}


def _item_assay_types(item: dict) -> set[str]:
    assays = set()
    for field in ["assay_type", "standard_type", "assay_name"]:
        normalized = normalize_assay_type(item.get(field))
        if normalized:
            assays.add(normalized)
    context = item.get("target_context") if isinstance(item.get("target_context"), dict) else {}
    if context:
        normalized = normalize_assay_type(context.get("assay_type") or context.get("standard_type"))
        if normalized:
            assays.add(normalized)
    return assays


def _item_endpoint_groups(item: dict) -> set[str]:
    endpoints = set()
    for field in ["endpoint_group", "endpoint", "assay_type", "assay_name", "standard_type"]:
        normalized = normalize_endpoint_group(item.get(field), assay_type=item.get("assay_type"), assay_name=item.get("assay_name"))
        if normalized:
            endpoints.add(normalized)
    context = item.get("target_context") if isinstance(item.get("target_context"), dict) else {}
    if context:
        normalized = normalize_endpoint_group(
            context.get("endpoint_group") or context.get("endpoint"),
            assay_type=context.get("assay_type") or context.get("standard_type"),
            assay_name=context.get("assay_name"),
        )
        if normalized:
            endpoints.add(normalized)
    return endpoints


def _target_context_match(item: dict, target_context: dict | None) -> bool:
    context = normalize_target_context(target_context or {})
    context_family = context.get("target_family_normalized")
    if not context_family:
        return False
    item_families = _item_target_families(item)
    if context_family not in item_families:
        return False
    context_assay = normalize_assay_type(context.get("assay_type") or context.get("standard_type"))
    item_assays = _item_assay_types(item)
    return not context_assay or not item_assays or context_assay in item_assays


def _endpoint_context_match(item: dict, target_context: dict | None) -> bool:
    target_context = target_context or {}
    endpoint = normalize_endpoint_group(
        target_context.get("endpoint_group") or target_context.get("endpoint"),
        assay_type=target_context.get("assay_type") or target_context.get("standard_type"),
        assay_name=target_context.get("assay_name"),
    )
    if not endpoint:
        return False
    item_endpoints = _item_endpoint_groups(item)
    return endpoint in item_endpoints


def _operator_prior(score: float, hits: list[dict], target_context: dict | None) -> dict:
    family_hits = [item for item in hits if item.get("target_context_match")]
    endpoint_hits = [item for item in hits if item.get("endpoint_context_match")]
    type_counts = {str(item.get("local_evidence_type")) for item in hits if item.get("local_evidence_type")}
    context_weight = 1.0
    basis = []
    if family_hits:
        context_weight += min(0.35, 0.10 * len(family_hits))
        basis.append("target_family_matched")
    if endpoint_hits:
        context_weight += min(0.25, 0.08 * len(endpoint_hits))
        basis.append("endpoint_matched")
    if "public_mmp" in type_counts:
        context_weight += 0.05
        basis.append("public_mmp")
    if not basis and hits:
        basis.append("scaffold_local_precedent")
    prior_score = min(96.0, max(score, score + (context_weight - 1.0) * 20.0))
    return {
        "scaffold_operator_prior_score": round(prior_score, 2) if hits else None,
        "scaffold_operator_prior_context_weight": round(context_weight, 4) if hits else None,
        "scaffold_operator_prior_basis": ";".join(dict.fromkeys(basis)),
        "scaffold_operator_prior_family_match_count": len(family_hits),
        "scaffold_operator_prior_endpoint_match_count": len(endpoint_hits),
    }


def scaffold_local_evidence(
    row: dict,
    *,
    replacement_rows: list[dict] | tuple[dict, ...] | None = None,
    max_examples: int = 5,
    target_context: dict | None = None,
) -> dict:
    if row.get("enumeration_type") != "scaffold_replacement":
        return {
            "scaffold_local_evidence_count": 0,
            "scaffold_local_evidence_strength": "none",
            "scaffold_local_evidence_score": None,
            "scaffold_local_evidence_types": "",
            "scaffold_local_target_family_match_count": 0,
            "scaffold_local_target_family_strength": "none",
            "scaffold_local_target_family_score": None,
            "scaffold_operator_prior_score": None,
            "scaffold_operator_prior_context_weight": None,
            "scaffold_operator_prior_basis": "",
            "scaffold_operator_prior_family_match_count": 0,
            "scaffold_operator_prior_endpoint_match_count": 0,
            "scaffold_local_mmp_count": 0,
            "scaffold_local_mmp_strength": "none",
            "scaffold_local_mmp_score": None,
        }
    from_query = _query_mol(row.get("scaffold_from_smarts"))
    to_mol = _mol_without_dummies(row.get("scaffold_to_smiles") or row.get("substituent_smiles"))
    if from_query is None or to_mol is None:
        return {
            "scaffold_local_evidence_count": 0,
            "scaffold_local_evidence_strength": "none",
            "scaffold_local_evidence_score": 42.0,
            "scaffold_local_evidence_types": "",
            "scaffold_local_target_family_match_count": 0,
            "scaffold_local_target_family_strength": "none",
            "scaffold_local_target_family_score": 42.0,
            "scaffold_operator_prior_score": 42.0,
            "scaffold_operator_prior_context_weight": 1.0,
            "scaffold_operator_prior_basis": "missing_query_or_target_core",
            "scaffold_operator_prior_family_match_count": 0,
            "scaffold_operator_prior_endpoint_match_count": 0,
            "scaffold_local_mmp_count": 0,
            "scaffold_local_mmp_strength": "none",
            "scaffold_local_mmp_score": 42.0,
            "scaffold_local_evidence_note": "No scaffold-local query/target core was available.",
            "scaffold_local_mmp_note": "No scaffold-local query/target core was available.",
        }
    rows = replacement_rows if replacement_rows is not None else _load_replacement_rows(str(DEFAULT_RING_REPLACEMENTS_PATH), str(DEFAULT_RGROUP_REPLACEMENTS_PATH))
    hits = []
    for item in rows:
        source_mol = _mol_without_dummies(item.get("source_smiles"))
        target_mol = _mol_without_dummies(item.get("target_smiles"))
        reverse = False
        if _matches(from_query, source_mol) and _matches(to_mol, target_mol):
            reverse = False
        elif _matches(from_query, target_mol) and _matches(to_mol, source_mol):
            reverse = True
        else:
            continue
        try:
            weight = int(float(item.get("weight") or 0))
        except (TypeError, ValueError):
            weight = 0
        delta = item.get("activity_delta")
        try:
            delta = float(delta) if delta not in {None, ""} else None
        except (TypeError, ValueError):
            delta = None
        hits.append(
            {
                "replacement_id": item.get("replacement_id"),
                "local_evidence_type": item.get("local_evidence_type"),
                "source_smiles": item.get("source_smiles"),
                "target_smiles": item.get("target_smiles"),
                "reverse_match": reverse,
                "weight": weight,
                "activity_delta": -delta if reverse and delta is not None else delta,
                "source_name": item.get("source_name"),
                "target_context_match": _target_context_match(item, target_context),
                "endpoint_context_match": _endpoint_context_match(item, target_context),
            }
        )
    hits.sort(key=lambda item: int(item.get("weight") or 0), reverse=True)
    total_weight = sum(max(int(item.get("weight") or 0), 0) for item in hits)
    strength, score = _strength(len(hits), total_weight)
    context_hits = [item for item in hits if item.get("target_context_match")]
    context_weight = sum(max(int(item.get("weight") or 0), 0) for item in context_hits)
    context_strength, context_score = _strength(len(context_hits), context_weight)
    if context_hits:
        score = max(score, min(94.0, context_score + 4.0))
    prior = _operator_prior(score, hits, target_context)
    if prior.get("scaffold_operator_prior_score") is not None:
        score = max(score, float(prior["scaffold_operator_prior_score"]))
    deltas = [float(item["activity_delta"]) for item in hits if item.get("activity_delta") is not None]
    evidence_types = sorted({str(item.get("local_evidence_type")) for item in hits if item.get("local_evidence_type")})
    return {
        "scaffold_local_evidence_count": len(hits),
        "scaffold_local_evidence_weight": total_weight,
        "scaffold_local_evidence_strength": strength,
        "scaffold_local_evidence_score": score,
        "scaffold_local_evidence_types": ";".join(evidence_types),
        "scaffold_local_evidence_ids": ";".join(str(item.get("replacement_id")) for item in hits[:max_examples] if item.get("replacement_id")),
        "scaffold_local_target_family_match_count": len(context_hits),
        "scaffold_local_target_family_weight": context_weight,
        "scaffold_local_target_family_strength": context_strength,
        "scaffold_local_target_family_score": context_score if context_hits else None,
        **prior,
        "scaffold_local_mean_activity_delta": round(mean(deltas), 4) if deltas else None,
        "scaffold_local_evidence_examples": hits[:max_examples],
        "scaffold_local_evidence_note": (
            f"{strength} scaffold-local analog support from {len(hits)} ring/R-group replacement records."
            if hits
            else "No scaffold-local analog support beyond exact fragment evidence."
        ),
        "scaffold_local_mmp_count": len(hits),
        "scaffold_local_mmp_pair_count": total_weight,
        "scaffold_local_mmp_strength": strength,
        "scaffold_local_mmp_score": score,
        "scaffold_local_mmp_transform_ids": ";".join(str(item.get("replacement_id")) for item in hits[:max_examples] if item.get("replacement_id")),
        "scaffold_local_mmp_note": (
            f"{strength} scaffold-local MMP-neighborhood support from {len(hits)} ring/R-group replacement records."
            if hits
            else "No scaffold-local MMP-neighborhood support beyond exact fragment evidence."
        ),
    }


def annotate_scaffold_local_evidence(
    rows: list[dict],
    *,
    ring_replacements_path: str | Path = DEFAULT_RING_REPLACEMENTS_PATH,
    rgroup_replacements_path: str | Path = DEFAULT_RGROUP_REPLACEMENTS_PATH,
    mmp_evidence_path: str | Path = DEFAULT_MMP_EVIDENCE_PATH,
    target_context: dict | None = None,
) -> list[dict]:
    replacement_rows = _load_replacement_rows(
        str(Path(ring_replacements_path)),
        str(Path(rgroup_replacements_path)),
        str(Path(mmp_evidence_path)) if mmp_evidence_path else "",
    )
    return [
        {**row, **scaffold_local_evidence(row, replacement_rows=replacement_rows, target_context=target_context)}
        for row in rows
    ]
