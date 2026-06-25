from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rdkit import Chem

from .chemistry import canonical_smiles
from .enumeration import Candidate, attach_substituent
from .ring_library import (
    DEFAULT_RGROUP_REPLACEMENTS_PATH,
    DEFAULT_RING_REPLACEMENTS_PATH,
    load_yaml_collection,
    normalize_attachment_smiles,
)
from .sites import ModificationSite


@lru_cache(maxsize=8)
def _load_ring_replacement_records_cached(path: str) -> tuple[dict, ...]:
    return tuple(load_yaml_collection(path, "ring_replacements"))


@lru_cache(maxsize=8)
def _load_rgroup_replacement_records_cached(path: str) -> tuple[dict, ...]:
    return tuple(load_yaml_collection(path, "rgroup_replacements"))


def load_ring_replacement_records(path: str | Path | None = None) -> list[dict]:
    return list(_load_ring_replacement_records_cached(str(Path(path or DEFAULT_RING_REPLACEMENTS_PATH))))


def load_rgroup_replacement_records(path: str | Path | None = None) -> list[dict]:
    return list(_load_rgroup_replacement_records_cached(str(Path(path or DEFAULT_RGROUP_REPLACEMENTS_PATH))))


def source_fragments_for_site(site: ModificationSite, explicit_source: str | None = None) -> set[str]:
    sources = set()
    if explicit_source:
        try:
            sources.add(normalize_attachment_smiles(explicit_source))
        except Exception:
            pass
    if site.leaving_atom_symbol:
        halogen = {"F": "F[*:1]", "Cl": "Cl[*:1]", "Br": "Br[*:1]", "I": "I[*:1]"}.get(site.leaving_atom_symbol)
        if halogen:
            sources.add(normalize_attachment_smiles(halogen))
    if site.site_type == "methoxy_position":
        sources.add(normalize_attachment_smiles("CO[*:1]"))
    return sources


def _target_record_tags(smiles: str, replacement_kind: str) -> tuple[list[str], list[str]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return [], []
    has_hetero = any(atom.GetAtomicNum() not in {0, 1, 6} for atom in mol.GetAtoms())
    has_aromatic = any(atom.GetIsAromatic() for atom in mol.GetAtoms())
    has_ring = any(atom.IsInRing() for atom in mol.GetAtoms())
    direction_tags: list[str] = []
    classes: list[str] = [replacement_kind]
    if has_hetero:
        direction_tags.extend(["increase_polarity", "reduce_lipophilicity"])
        classes.append("heteroatom")
    if has_aromatic and has_hetero:
        direction_tags.append("heteroaryl_scan")
        classes.append("heteroaryl")
    elif has_aromatic:
        direction_tags.append("aryl_scan")
        classes.append("aryl")
    if has_ring:
        direction_tags.append("increase_rigidity")
        classes.append("ring")
    return list(dict.fromkeys(direction_tags)), list(dict.fromkeys(classes))


def replacement_as_scoring_record(row: dict, replacement_kind: str) -> dict:
    target_smiles = row.get("target_canonical_smiles") or row.get("replacement_canonical_smiles")
    direction_tags, classes = _target_record_tags(str(target_smiles or ""), replacement_kind)
    evidence = row.get("edge_weight") or row.get("evidence_count") or 1
    try:
        rank = max(1, 120 - int(float(evidence)))
    except Exception:
        rank = 120
    return {
        "substituent_id": row["replacement_id"],
        "name": f"{replacement_kind} {row['replacement_id']}",
        "smiles": target_smiles,
        "direction_tags": direction_tags,
        "class": classes,
        "property_tags": {},
        "risk": {"risk_tags": ["network_context_dependent"], "default_enabled": True},
        "priority": {"default_rank": rank, "common_medchem": True},
        "network_evidence": {
            "replacement_kind": replacement_kind,
            "source_smiles": row.get("source_canonical_smiles") or row.get("query_canonical_smiles"),
            "target_smiles": target_smiles,
            "edge_weight": row.get("edge_weight"),
            "evidence_count": row.get("evidence_count"),
            "activity_delta": row.get("activity_delta"),
            "ring_novelty_bucket": row.get("ring_novelty_bucket"),
            "ring_diversity_bucket": row.get("ring_diversity_bucket"),
            "ring_sampling_score": row.get("ring_sampling_score"),
            "ring_sampling_basis": row.get("ring_sampling_basis"),
            "source_name": row.get("source_name"),
            "source_reference": row.get("source_reference"),
            "replacement_id": row.get("replacement_id"),
        },
    }


def _replacement_sort_key(row: dict) -> tuple[float, float, int]:
    sampling_score = float(row.get("ring_sampling_score") or 0.0)
    if "edge_weight" in row:
        return sampling_score, float(row.get("edge_weight") or 0), 0
    return sampling_score, float(row.get("evidence_count") or 0), int(float(row.get("activity_delta") or 0))


def _candidate_from_replacement(
    *,
    smiles: str,
    row: dict,
    site: ModificationSite,
    candidate_no: int,
    source_smiles: str,
    target_smiles: str,
    replacement_kind: str,
) -> Candidate:
    metadata = {}
    if replacement_kind == "ring":
        metadata = {
            key: row.get(key)
            for key in ["ring_novelty_bucket", "ring_diversity_bucket", "ring_sampling_score", "ring_sampling_basis"]
            if row.get(key) is not None
        }
    return Candidate(
        candidate_id=f"RN{candidate_no:04d}",
        smiles=smiles,
        substituent_id=row["replacement_id"],
        substituent_name=f"{replacement_kind} {target_smiles}",
        substituent_smiles=target_smiles,
        site_id=site.site_id,
        site_type=site.site_type,
        replacement_label=f"{source_smiles}->{target_smiles}",
        enumeration_type=f"{replacement_kind}_network_replacement",
        functional_rule_id=None,
        metadata=metadata,
    )


def enumerate_replacement_network_candidates(
    parent: Chem.Mol,
    site: ModificationSite,
    *,
    rgroup_replacements: list[dict] | None = None,
    ring_replacements: list[dict] | None = None,
    source_fragment: str | None = None,
    direction_tags: list[str] | tuple[str, ...] | None = None,
    max_candidates: int | None = 25,
) -> tuple[list[Candidate], list[dict], list[dict]]:
    sources = source_fragments_for_site(site, explicit_source=source_fragment)
    if not sources:
        return [], [], []

    wanted_tags = set(direction_tags or [])
    rows: list[tuple[dict, str, str, str]] = []
    for row in rgroup_replacements or []:
        source = row.get("source_canonical_smiles")
        target = row.get("target_canonical_smiles")
        if source in sources and target:
            rows.append((row, source, target, "rgroup"))
    for row in ring_replacements or []:
        source = row.get("query_canonical_smiles")
        target = row.get("replacement_canonical_smiles")
        if source in sources and target:
            rows.append((row, source, target, "ring"))

    rows.sort(key=lambda item: _replacement_sort_key(item[0]), reverse=True)
    candidates: list[Candidate] = []
    errors: list[dict] = []
    scoring_records: dict[str, dict] = {}
    seen: set[str] = set()

    for row, source, target, replacement_kind in rows:
        try:
            scoring_record = replacement_as_scoring_record(row, replacement_kind)
            if wanted_tags and not wanted_tags.intersection(scoring_record.get("direction_tags") or scoring_record.get("class") or []):
                continue
            mol = attach_substituent(parent, site, target)
            smiles = canonical_smiles(mol)
            if smiles in seen:
                continue
            seen.add(smiles)
            candidate_no = len(candidates) + 1
            candidates.append(
                _candidate_from_replacement(
                    smiles=smiles,
                    row=row,
                    site=site,
                    candidate_no=candidate_no,
                    source_smiles=source,
                    target_smiles=target,
                    replacement_kind=replacement_kind,
                )
            )
            scoring_records[row["replacement_id"]] = scoring_record
            if max_candidates is not None and len(candidates) >= max_candidates:
                break
        except Exception as exc:
            errors.append({"replacement_id": row.get("replacement_id"), "source_smiles": source, "target_smiles": target, "error": str(exc)})

    return candidates, errors, list(scoring_records.values())


def replacement_network_summary(
    *,
    rgroup_replacements: list[dict],
    ring_replacements: list[dict],
) -> dict:
    return {
        "rgroup_replacement_count": len(rgroup_replacements),
        "ring_replacement_count": len(ring_replacements),
        "rgroup_source_count": len({row.get("source_canonical_smiles") for row in rgroup_replacements if row.get("source_canonical_smiles")}),
        "ring_source_count": len({row.get("query_canonical_smiles") for row in ring_replacements if row.get("query_canonical_smiles")}),
    }
