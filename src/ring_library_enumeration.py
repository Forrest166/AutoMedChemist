from __future__ import annotations

import hashlib
import math
from pathlib import Path

from rdkit import Chem
from rdkit import DataStructs
from rdkit.Chem import rdFingerprintGenerator

from .chemistry import canonical_smiles, calculate_substituent_descriptors, mol_from_smiles
from .enumeration import Candidate, attach_substituent
from .library import SubstituentIndex, ensure_list
from .ring_library import normalize_attachment_smiles
from .ring_recommender import recommend_ring_systems
from .sites import ModificationSite, detect_modification_sites

RING_FP_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=1024)


def ring_system_attachment_fragment(smiles: str) -> str | None:
    """Convert a free ring-system SMILES into a one-attachment R-group fragment."""
    mol = Chem.MolFromSmiles(str(smiles or "").strip())
    if mol is None:
        return None
    anchor_idx = _preferred_attachment_atom(mol)
    if anchor_idx is None:
        return None
    rw = Chem.RWMol(mol)
    dummy = Chem.Atom(0)
    dummy.SetAtomMapNum(1)
    dummy_idx = rw.AddAtom(dummy)
    rw.AddBond(anchor_idx, dummy_idx, Chem.BondType.SINGLE)
    fragment = rw.GetMol()
    try:
        Chem.SanitizeMol(fragment)
        return normalize_attachment_smiles(Chem.MolToSmiles(fragment, canonical=True, isomericSmiles=True))
    except Exception:
        return None


def _preferred_attachment_atom(mol: Chem.Mol) -> int | None:
    candidates = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() > 0]
    if not candidates:
        candidates = [
            atom
            for atom in mol.GetAtoms()
            if atom.GetAtomicNum() in {6, 7} and not atom.GetIsAromatic() and atom.GetTotalNumHs() > 0
        ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda atom: (
            0 if atom.GetIsAromatic() and atom.GetAtomicNum() == 6 else 1,
            0 if atom.IsInRing() else 1,
            atom.GetIdx(),
        )
    )
    return int(candidates[0].GetIdx())


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _rank_to_priority(source_rank: object) -> int:
    rank = max(1, _safe_int(source_rank, 999999))
    return int(max(15, min(95, 20 + math.log10(rank + 1) * 14)))


def _ring_direction_tags(row: dict, direction_tags: list[str] | tuple[str, ...] | None = None) -> list[str]:
    tags = list(direction_tags or [])
    hetero_count = _safe_int(row.get("hetero_atom_count"))
    aromatic_count = _safe_int(row.get("aromatic_ring_count"))
    fsp3 = _safe_float(row.get("fsp3"))
    if hetero_count:
        tags.extend(["increase_polarity", "reduce_lipophilicity"])
    if hetero_count and aromatic_count:
        tags.append("heteroaryl_scan")
    elif aromatic_count:
        tags.append("aryl_scan")
    if fsp3 >= 0.35:
        tags.append("increase_3d_character")
    tags.append("ring_library_recommendation")
    return list(dict.fromkeys(str(tag) for tag in tags if tag))


def _ring_classes(row: dict) -> list[str]:
    classes = ["ring_library_recommendation"]
    ring_class = row.get("ring_class")
    if ring_class:
        classes.append(str(ring_class))
    if _safe_int(row.get("hetero_atom_count")):
        classes.append("heterocycle")
    if _safe_int(row.get("aromatic_ring_count")):
        classes.append("aromatic_ring")
    return list(dict.fromkeys(classes))


def ring_recommendation_as_scoring_record(row: dict, fragment_smiles: str, direction_tags: list[str] | tuple[str, ...] | None = None) -> dict:
    descriptors = {}
    try:
        descriptors = calculate_substituent_descriptors(fragment_smiles)
    except Exception:
        descriptors = {}
    source_rank = _safe_int(row.get("source_rank"), 999999)
    substituent_id = f"RINGLIB-{row.get('ring_id') or _digest(fragment_smiles)}"
    return {
        "substituent_id": substituent_id,
        "name": f"Ring library {row.get('ring_id') or row.get('canonical_smiles')}",
        "short_name": row.get("canonical_smiles"),
        "smiles": fragment_smiles,
        "canonical_smiles": fragment_smiles,
        "connection_type": "ring_attachment",
        "allowed_site_types": ["aromatic_CH", "aromatic_halide", "alkyl_terminal"],
        "direction_tags": _ring_direction_tags(row, direction_tags),
        "class": _ring_classes(row),
        "property_tags": {},
        "calculated_descriptors": descriptors,
        "risk": {"risk_tags": ["ring_library_context_dependent"], "default_enabled": True},
        "priority": {
            "default_rank": _rank_to_priority(source_rank),
            "common_medchem": source_rank <= 5000,
            "mvp": False,
        },
        "ring_evidence": {
            "ring_id": row.get("ring_id"),
            "source_dataset": row.get("source_dataset"),
            "source_rank": source_rank,
            "source_name": row.get("source_name") or row.get("source_dataset"),
            "source_reference": row.get("source_reference"),
            "ring_novelty_bucket": row.get("ring_novelty_bucket"),
            "ring_diversity_bucket": row.get("ring_diversity_bucket"),
            "replacement_class": "ring_library_recommendation",
        },
        "network_evidence": {
            "replacement_kind": "ring_library",
            "target_smiles": fragment_smiles,
            "source_dataset": row.get("source_dataset"),
            "source_rank": source_rank,
            "source_name": row.get("source_name") or row.get("source_dataset"),
            "source_reference": row.get("source_reference"),
        },
    }


def enumerate_ring_library_candidates(
    parent: Chem.Mol,
    site: ModificationSite,
    *,
    db_path: str | Path,
    direction_tags: list[str] | tuple[str, ...] | None = None,
    max_candidates: int = 12,
    max_source_rank: int | None = 5000,
    max_per_diversity_bucket: int | None = 2,
    max_ring_similarity: float | None = 0.86,
    cache_path: str | Path | None = None,
    cache_ttl_seconds: int | float | None = 86400,
) -> tuple[list[Candidate], list[dict], list[dict], dict]:
    if not site.enumeration_ready or "ring_attachment" not in set(site.compatible_connection_types):
        return [], [], [], {"status": "skipped", "reason": "site_not_ring_attachment_ready"}

    wanted = set(direction_tags or [])
    ring_class = "aromatic_heterocycle" if "heteroaryl_scan" in wanted else None
    min_hetero = 1 if wanted.intersection({"increase_polarity", "reduce_lipophilicity", "heteroaryl_scan"}) else None
    report = recommend_ring_systems(
        db_path=db_path,
        source_dataset="ertl_4m_ring_systems",
        ring_class=ring_class,
        min_heavy_atom_count=5,
        max_heavy_atom_count=10,
        min_hetero_atom_count=min_hetero,
        max_source_rank=max_source_rank,
        limit=max(1, max_candidates * 8),
        order_by="source_rank",
        cache_path=cache_path,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    candidates: list[Candidate] = []
    errors: list[dict] = []
    scoring_records: dict[str, dict] = {}
    seen: set[str] = set()
    parent_smiles = canonical_smiles(parent)

    selected_rows = diverse_ring_rows(
        report.get("rows") or [],
        max_rows=max_candidates * 4,
        max_per_diversity_bucket=max_per_diversity_bucket,
        max_similarity=max_ring_similarity,
    )
    report["diversity_selection"] = {
        "input_row_count": len(report.get("rows") or []),
        "selected_row_count": len(selected_rows),
        "max_per_diversity_bucket": max_per_diversity_bucket,
        "max_ring_similarity": max_ring_similarity,
    }

    for row in selected_rows:
        fragment = ring_system_attachment_fragment(str(row.get("canonical_smiles") or row.get("smiles") or ""))
        if not fragment:
            errors.append({"ring_id": row.get("ring_id"), "error": "no_attachment_atom"})
            continue
        try:
            record = ring_recommendation_as_scoring_record(row, fragment, direction_tags)
            mol = attach_substituent(parent, site, fragment)
            smiles = canonical_smiles(mol)
            if smiles == parent_smiles or smiles in seen:
                continue
            seen.add(smiles)
            candidate_no = len(candidates) + 1
            candidates.append(
                Candidate(
                    candidate_id=f"RL{candidate_no:04d}",
                    smiles=smiles,
                    substituent_id=record["substituent_id"],
                    substituent_name=str(record["name"]),
                    substituent_smiles=fragment,
                    site_id=site.site_id,
                    site_type=site.site_type,
                    replacement_label=f"ring-library->{row.get('canonical_smiles')}",
                    enumeration_type="ring_library_recommendation",
                    functional_rule_id=None,
                    metadata={
                        "ring_library_ring_id": row.get("ring_id"),
                        "ring_library_source_dataset": row.get("source_dataset"),
                        "ring_library_source_rank": row.get("source_rank"),
                        "ring_novelty_bucket": row.get("ring_novelty_bucket"),
                        "ring_diversity_bucket": row.get("ring_diversity_bucket"),
                        "ring_diversity_guard_bucket": row.get("ring_diversity_bucket"),
                        "ring_diversity_guard_max_similarity": max_ring_similarity,
                        "replacement_class": "ring_library_recommendation",
                    },
                )
            )
            scoring_records[record["substituent_id"]] = record
            if len(candidates) >= max_candidates:
                break
        except Exception as exc:
            errors.append({"ring_id": row.get("ring_id"), "fragment_smiles": fragment, "error": str(exc)})

    return candidates, errors, list(scoring_records.values()), report


def diverse_ring_rows(
    rows: list[dict],
    *,
    max_rows: int,
    max_per_diversity_bucket: int | None = 2,
    max_similarity: float | None = 0.86,
) -> list[dict]:
    selected: list[dict] = []
    bucket_counts: dict[str, int] = {}
    selected_fps = []
    for row in rows:
        bucket = str(row.get("ring_diversity_bucket") or "unknown")
        if max_per_diversity_bucket is not None and bucket_counts.get(bucket, 0) >= int(max_per_diversity_bucket):
            continue
        fp = _ring_fp(row)
        if fp is not None and max_similarity is not None and selected_fps:
            if max(DataStructs.TanimotoSimilarity(fp, existing) for existing in selected_fps) > float(max_similarity):
                continue
        selected.append(row)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if fp is not None:
            selected_fps.append(fp)
        if len(selected) >= max_rows:
            break
    return selected


def _ring_fp(row: dict):
    mol = Chem.MolFromSmiles(str(row.get("canonical_smiles") or row.get("smiles") or ""))
    if mol is None:
        return None
    return RING_FP_GENERATOR.GetFingerprint(mol)


def enumerate_ring_rgroup_joint_candidates(
    parent: Chem.Mol,
    ring_candidates: list[Candidate],
    ring_scoring_records: list[dict],
    library_records: list[dict],
    *,
    direction_tags: list[str] | tuple[str, ...] | None = None,
    max_candidates: int = 8,
    per_ring_limit: int = 1,
    include_risky: bool = False,
    include_advanced: bool = False,
) -> tuple[list[Candidate], list[dict], list[dict]]:
    if not ring_candidates or not library_records or max_candidates <= 0:
        return [], [], []

    parent_atom_count = parent.GetNumAtoms()
    ring_record_lookup = {record.get("substituent_id"): record for record in ring_scoring_records}
    candidates: list[Candidate] = []
    errors: list[dict] = []
    scoring_records: dict[str, dict] = {}
    seen: set[str] = set()

    for ring_candidate in ring_candidates:
        try:
            ring_parent = mol_from_smiles(ring_candidate.smiles)
        except Exception as exc:
            errors.append({"candidate_id": ring_candidate.candidate_id, "error": str(exc)})
            continue
        joint_sites = [
            site
            for site in detect_modification_sites(ring_parent)
            if site.enumeration_ready and site.atom_idx >= parent_atom_count and site.site_type in {"aromatic_CH", "alkyl_terminal"}
        ]
        if not joint_sites:
            continue
        joint_site = joint_sites[0]
        substituents = SubstituentIndex(library_records).query(
            direction_tags=direction_tags,
            site_type=joint_site.site_type,
            compatible_connection_types=joint_site.compatible_connection_types,
            max_fragment_mw=120,
            include_risky=include_risky,
            include_advanced=include_advanced,
            limit=max(3, per_ring_limit * 4),
        )
        for substituent in substituents[:per_ring_limit]:
            try:
                mol = attach_substituent(ring_parent, joint_site, str(substituent["smiles"]))
                smiles = canonical_smiles(mol)
                if smiles in seen:
                    continue
                seen.add(smiles)
                candidate_no = len(candidates) + 1
                synthetic_id = f"RINGRG-{_digest(ring_candidate.substituent_id, substituent.get('substituent_id'))}"
                scoring_record = _joint_scoring_record(
                    synthetic_id=synthetic_id,
                    ring_candidate=ring_candidate,
                    ring_record=ring_record_lookup.get(ring_candidate.substituent_id) or {},
                    substituent=substituent,
                    direction_tags=direction_tags,
                )
                candidates.append(
                    Candidate(
                        candidate_id=f"RJ{candidate_no:04d}",
                        smiles=smiles,
                        substituent_id=synthetic_id,
                        substituent_name=str(scoring_record["name"]),
                        substituent_smiles=str(substituent["smiles"]),
                        site_id=joint_site.site_id,
                        site_type=joint_site.site_type,
                        replacement_label=f"{ring_candidate.replacement_label}+{substituent.get('short_name') or substituent.get('name')}",
                        enumeration_type="ring_rgroup_joint_recommendation",
                        functional_rule_id=None,
                        metadata={
                            "first_stage_candidate_id": ring_candidate.candidate_id,
                            "first_stage_substituent_id": ring_candidate.substituent_id,
                            "second_stage_substituent_id": substituent.get("substituent_id"),
                            "second_stage_site_id": joint_site.site_id,
                            "ring_library_ring_id": ring_candidate.metadata.get("ring_library_ring_id"),
                            "ring_library_source_rank": ring_candidate.metadata.get("ring_library_source_rank"),
                            "ring_novelty_bucket": ring_candidate.metadata.get("ring_novelty_bucket"),
                            "ring_diversity_bucket": ring_candidate.metadata.get("ring_diversity_bucket"),
                            "replacement_class": "ring_rgroup_joint",
                        },
                    )
                )
                scoring_records[synthetic_id] = scoring_record
                if len(candidates) >= max_candidates:
                    return candidates, errors, list(scoring_records.values())
            except Exception as exc:
                errors.append(
                    {
                        "candidate_id": ring_candidate.candidate_id,
                        "substituent_id": substituent.get("substituent_id"),
                        "error": str(exc),
                    }
                )
    return candidates, errors, list(scoring_records.values())


def _joint_scoring_record(
    *,
    synthetic_id: str,
    ring_candidate: Candidate,
    ring_record: dict,
    substituent: dict,
    direction_tags: list[str] | tuple[str, ...] | None,
) -> dict:
    tags = list(direction_tags or [])
    tags.extend(ensure_list(substituent.get("direction_tags")))
    tags.extend(["ring_rgroup_joint", "ring_library_recommendation"])
    classes = ["ring_rgroup_joint"]
    classes.extend(ensure_list(ring_record.get("class")))
    classes.extend(ensure_list(substituent.get("class")))
    priority = dict(substituent.get("priority") or {})
    priority["default_rank"] = min(float(priority.get("default_rank", 999)), float((ring_record.get("priority") or {}).get("default_rank", 999))) + 12
    priority["common_medchem"] = bool(priority.get("common_medchem") or (ring_record.get("priority") or {}).get("common_medchem"))
    risk = dict(substituent.get("risk") or {})
    risk_tags = ensure_list(risk.get("risk_tags"))
    risk_tags.append("two_stage_enumeration_context_dependent")
    risk["risk_tags"] = list(dict.fromkeys(str(tag) for tag in risk_tags if tag))
    risk.setdefault("default_enabled", True)
    return {
        **substituent,
        "substituent_id": synthetic_id,
        "name": f"Ring + R-group {ring_candidate.metadata.get('ring_library_ring_id') or ring_candidate.substituent_name} / {substituent.get('name')}",
        "direction_tags": list(dict.fromkeys(str(tag) for tag in tags if tag)),
        "class": list(dict.fromkeys(str(item) for item in classes if item)),
        "risk": risk,
        "priority": priority,
        "ring_evidence": ring_record.get("ring_evidence"),
        "network_evidence": {
            **(ring_record.get("network_evidence") or {}),
            "replacement_kind": "ring_rgroup_joint",
            "second_stage_substituent_id": substituent.get("substituent_id"),
        },
    }


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12].upper()
