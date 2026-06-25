from __future__ import annotations

from pathlib import Path

import yaml
from rdkit import Chem

from .chemistry import canonical_smiles
from .enumeration import Candidate
from .sites import ModificationSite


DEFAULT_SCAFFOLD_REPLACEMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "scaffold_replacements.yaml"


def load_scaffold_replacements(path: str | Path | None = None) -> list[dict]:
    rules_path = Path(path) if path is not None else DEFAULT_SCAFFOLD_REPLACEMENTS_PATH
    if not rules_path.exists():
        return []
    with rules_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("scaffold_replacements") or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported scaffold replacement shape: {rules_path}")


def validate_scaffold_replacements(rules: list[dict]) -> dict:
    issues = []
    seen = set()
    for rule in rules:
        rule_id = rule.get("scaffold_rule_id")
        if not rule_id:
            issues.append({"severity": "error", "check": "scaffold_rule_id", "item_id": None, "message": "Missing scaffold_rule_id"})
        elif rule_id in seen:
            issues.append({"severity": "error", "check": "scaffold_duplicate_id", "item_id": rule_id, "message": "Duplicate scaffold_rule_id"})
        seen.add(rule_id)
        for field in ["name", "from_smarts", "to_smiles", "attachment_count", "replacement_class"]:
            if rule.get(field) in {None, ""}:
                issues.append({"severity": "error", "check": "scaffold_required_field", "item_id": rule_id, "message": f"Missing {field}"})
        if rule.get("from_smarts") and Chem.MolFromSmarts(rule["from_smarts"]) is None:
            issues.append({"severity": "error", "check": "scaffold_from_smarts", "item_id": rule_id, "message": "Invalid from_smarts"})
        if rule.get("to_smiles"):
            mol = Chem.MolFromSmiles(rule["to_smiles"])
            if mol is None:
                issues.append({"severity": "error", "check": "scaffold_to_smiles", "item_id": rule_id, "message": "Invalid to_smiles"})
            else:
                dummy_count = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0)
                if dummy_count != int(rule.get("attachment_count") or 0):
                    issues.append(
                        {
                            "severity": "warning",
                            "check": "scaffold_attachment_count",
                            "item_id": rule_id,
                            "message": f"Expected {rule.get('attachment_count')} dummy atoms, found {dummy_count}",
                        }
                    )
    return {
        "scaffold_replacement_count": len(rules),
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "issues": issues,
    }


def scaffold_rule_as_scoring_record(rule: dict) -> dict:
    return {
        "substituent_id": rule["scaffold_rule_id"],
        "name": rule["name"],
        "smiles": rule.get("to_smiles"),
        "direction_tags": rule.get("direction_tags") or [],
        "class": [rule.get("replacement_class"), "scaffold_replacement"],
        "property_tags": {},
        "risk": rule.get("risk") or {"risk_tags": ["geometry_context_dependent"], "default_enabled": True},
        "priority": rule.get("priority") or {"default_rank": 70, "common_medchem": True},
        "ring_evidence": {
            "source_name": rule.get("source_name"),
            "source_reference": rule.get("source_reference"),
            "replacement_class": rule.get("replacement_class"),
            "attachment_count": rule.get("attachment_count"),
            "scaffold_rule_id": rule.get("scaffold_rule_id"),
            "from_smarts": rule.get("from_smarts"),
            "to_smiles": rule.get("to_smiles"),
        },
    }


def _external_connections(parent: Chem.Mol, match: tuple[int, ...]) -> list[tuple[int, int, Chem.BondType]]:
    match_set = set(match)
    connections = []
    for source_idx in match:
        atom = parent.GetAtomWithIdx(source_idx)
        for nbr in atom.GetNeighbors():
            nbr_idx = nbr.GetIdx()
            if nbr_idx in match_set:
                continue
            bond = parent.GetBondBetweenAtoms(source_idx, nbr_idx)
            connections.append((source_idx, nbr_idx, bond.GetBondType()))
    return connections


def _adjust_index_after_removal(idx: int, removed: set[int]) -> int:
    return idx - sum(1 for removed_idx in removed if removed_idx < idx)


def _replacement_dummy_pairs(fragment: Chem.Mol) -> list[tuple[int, int, int]]:
    pairs = []
    for atom in fragment.GetAtoms():
        if atom.GetAtomicNum() != 0:
            continue
        neighbors = list(atom.GetNeighbors())
        if len(neighbors) != 1:
            raise ValueError("Replacement dummy atoms must each have one neighbor.")
        atom_map = atom.GetAtomMapNum() or (len(pairs) + 1)
        pairs.append((atom_map, atom.GetIdx(), neighbors[0].GetIdx()))
    pairs.sort(key=lambda item: item[0])
    return pairs


def _shortest_path_length(mol: Chem.Mol, start: int, end: int) -> int | None:
    if int(start) == int(end):
        return 0
    try:
        path = Chem.rdmolops.GetShortestPath(mol, int(start), int(end))
    except Exception:
        return None
    if not path:
        return None
    return len(path) - 1


def _attachment_topology(distance: int | None) -> str:
    if distance is None:
        return "unknown"
    if distance <= 1:
        return "ortho_or_adjacent"
    if distance == 2:
        return "meta_like"
    if distance == 3:
        return "para_like"
    return "long_bridge"


def _fused_or_annulated_context(parent: Chem.Mol, match: tuple[int, ...]) -> bool:
    match_set = set(match)
    for ring in parent.GetRingInfo().AtomRings():
        ring_set = set(ring)
        if ring_set.intersection(match_set) and not ring_set.issubset(match_set):
            return True
    return False


def _replacement_asymmetry(fragment: Chem.Mol, dummy_pairs: list[tuple[int, int, int]]) -> bool:
    if len(dummy_pairs) != 2:
        return False
    hetero_atoms = [atom.GetIdx() for atom in fragment.GetAtoms() if atom.GetAtomicNum() not in {0, 1, 6}]
    if not hetero_atoms:
        return False
    distances = []
    for _map_no, _dummy_idx, attach_idx in dummy_pairs:
        atom_distances = [_shortest_path_length(fragment, attach_idx, hetero_idx) for hetero_idx in hetero_atoms]
        atom_distances = [distance for distance in atom_distances if distance is not None]
        distances.append(min(atom_distances) if atom_distances else None)
    return distances[0] != distances[1]


def _scaffold_context(
    parent: Chem.Mol,
    *,
    match: tuple[int, ...],
    connections: list[tuple[int, int, Chem.BondType]],
    rule: dict,
    reverse: bool,
) -> dict:
    fragment = Chem.MolFromSmiles(rule["to_smiles"])
    dummy_pairs = _replacement_dummy_pairs(fragment) if fragment is not None else []
    original_distance = None
    replacement_distance = None
    if len(connections) == 2:
        ordered_connections = sorted(connections, key=lambda item: match.index(item[0]))
        if reverse:
            ordered_connections = list(reversed(ordered_connections))
        original_distance = _shortest_path_length(parent, ordered_connections[0][0], ordered_connections[1][0])
        if len(dummy_pairs) == 2 and fragment is not None:
            replacement_distance = _shortest_path_length(fragment, dummy_pairs[0][2], dummy_pairs[1][2])

    flags = []
    score = 100.0
    if original_distance is not None and replacement_distance is not None:
        delta = abs(replacement_distance - original_distance)
        score -= min(45.0, 15.0 * delta)
        if delta:
            flags.append("linker_length_shift")
    else:
        delta = None
    topology = _attachment_topology(original_distance)
    if topology == "ortho_or_adjacent" and rule.get("replacement_class") == "saturated_benzene_bioisostere":
        score -= 20.0
        flags.append("ortho_geometry_risk")
    elif topology == "meta_like" and rule.get("replacement_class") == "saturated_benzene_bioisostere":
        score -= 8.0
    fused_context = _fused_or_annulated_context(parent, match)
    if rule.get("replacement_class") in {"ring_expansion", "ring_contraction"}:
        flags.append(str(rule.get("replacement_class")))
        if len(connections) == 1:
            score += 4.0
        if fused_context:
            score -= 20.0
            flags.append("fused_size_edit_risk")
        flags.append("meta_geometry_shift")

    if fused_context:
        score -= 25.0
        flags.append("fused_or_annulated_context")

    asymmetric = fragment is not None and _replacement_asymmetry(fragment, dummy_pairs)
    orientation = "reverse" if reverse else "forward"
    if asymmetric and reverse:
        score -= 8.0
        flags.append("asymmetric_reverse_orientation")
    if len(connections) == 1:
        orientation = "single_attachment"

    score = max(0.0, min(100.0, score))
    return {
        "scaffold_orientation": orientation,
        "scaffold_original_attachment_distance": original_distance,
        "scaffold_replacement_attachment_distance": replacement_distance,
        "scaffold_linker_length_delta": delta,
        "scaffold_attachment_topology": topology,
        "scaffold_fused_context": fused_context,
        "scaffold_asymmetric_replacement": asymmetric,
        "scaffold_context_score": round(score, 2),
        "scaffold_context_flags": ";".join(flags),
    }


def _replace_scaffold_once(
    parent: Chem.Mol,
    *,
    match: tuple[int, ...],
    connections: list[tuple[int, int, Chem.BondType]],
    rule: dict,
    reverse: bool = False,
) -> str:
    fragment = Chem.MolFromSmiles(rule["to_smiles"])
    if fragment is None:
        raise ValueError(f"Invalid replacement scaffold: {rule['to_smiles']}")
    dummy_pairs = _replacement_dummy_pairs(fragment)
    if len(dummy_pairs) != len(connections):
        raise ValueError("Attachment count mismatch.")

    removed = set(match)
    rw = Chem.RWMol(parent)
    for idx in sorted(removed, reverse=True):
        rw.RemoveAtom(idx)
    remainder = rw.GetMol()
    Chem.SanitizeMol(remainder)

    ordered_connections = sorted(connections, key=lambda item: match.index(item[0]))
    if reverse:
        ordered_connections = list(reversed(ordered_connections))
    offset = remainder.GetNumAtoms()
    combined = Chem.CombineMols(remainder, fragment)
    rw = Chem.RWMol(combined)
    for (_, outside_idx, bond_type), (_map_no, _dummy_idx, attach_idx) in zip(ordered_connections, dummy_pairs):
        rw.AddBond(_adjust_index_after_removal(outside_idx, removed), offset + attach_idx, bond_type)
    for _map_no, dummy_idx, _attach_idx in sorted(dummy_pairs, key=lambda item: item[1], reverse=True):
        rw.RemoveAtom(offset + dummy_idx)
    product = rw.GetMol()
    Chem.SanitizeMol(product)
    return canonical_smiles(product)


def enumerate_scaffold_replacements(
    parent: Chem.Mol,
    site: ModificationSite,
    rules: list[dict],
    *,
    direction_tags: list[str] | tuple[str, ...] | None = None,
    include_advanced: bool = False,
    max_candidates: int | None = 20,
    calibration_lookup: dict[str, dict] | None = None,
) -> tuple[list[Candidate], list[dict], list[dict]]:
    wanted_tags = set(direction_tags or [])
    candidates: list[Candidate] = []
    errors: list[dict] = []
    scoring_records: list[dict] = []
    seen: set[str] = {canonical_smiles(parent)}

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        risk_tags = set((rule.get("risk") or {}).get("risk_tags") or [])
        if "advanced_only" in risk_tags and not include_advanced:
            continue
        rule_tags = set(rule.get("direction_tags") or []).union({rule.get("replacement_class")})
        if wanted_tags and not wanted_tags.intersection(rule_tags):
            continue
        query = Chem.MolFromSmarts(rule["from_smarts"])
        if query is None:
            errors.append({"scaffold_rule_id": rule.get("scaffold_rule_id"), "name": rule.get("name"), "error": "Invalid from_smarts"})
            continue
        added_for_rule = False
        for match in parent.GetSubstructMatches(query, uniquify=True):
            if site.atom_idx not in set(match):
                continue
            connections = _external_connections(parent, match)
            if len(connections) != int(rule.get("attachment_count") or 0):
                continue
            for reverse in ([False, True] if len(connections) == 2 else [False]):
                try:
                    smiles = _replace_scaffold_once(parent, match=match, connections=connections, rule=rule, reverse=reverse)
                    context = _scaffold_context(parent, match=match, connections=connections, rule=rule, reverse=reverse)
                    calibration = (calibration_lookup or {}).get(str(rule.get("scaffold_rule_id"))) or {}
                    if calibration:
                        adjustment = float(calibration.get("score_adjustment") or 0.0)
                        flags = [flag for flag in str(context.get("scaffold_context_flags") or "").split(";") if flag]
                        action = str(calibration.get("calibration_action") or "watch")
                        if action == "boost":
                            flags.append("calibration_supported")
                        elif action == "deprioritize":
                            flags.append("calibration_deprioritized")
                        elif action:
                            flags.append(f"calibration_{action}")
                        context["scaffold_context_score"] = round(max(0.0, min(100.0, float(context.get("scaffold_context_score") or 0.0) + adjustment)), 2)
                        context["scaffold_context_flags"] = ";".join(dict.fromkeys(flags))
                        context["scaffold_calibration_action"] = action
                        context["scaffold_calibration_case_count"] = calibration.get("case_count")
                        context["scaffold_calibration_score_adjustment"] = adjustment
                    context["scaffold_rule_id"] = rule.get("scaffold_rule_id")
                    context["scaffold_from_smarts"] = rule.get("from_smarts")
                    context["scaffold_to_smiles"] = rule.get("to_smiles")
                except Exception as exc:
                    errors.append({"scaffold_rule_id": rule.get("scaffold_rule_id"), "name": rule.get("name"), "error": str(exc)})
                    continue
                if smiles in seen:
                    continue
                seen.add(smiles)
                candidate_no = len(candidates) + 1
                candidates.append(
                    Candidate(
                        candidate_id=f"S{candidate_no:04d}",
                        smiles=smiles,
                        substituent_id=rule["scaffold_rule_id"],
                        substituent_name=rule["name"],
                        substituent_smiles=rule["to_smiles"],
                        site_id=site.site_id,
                        site_type=site.site_type,
                        replacement_label=rule["name"],
                        enumeration_type="scaffold_replacement",
                        functional_rule_id=None,
                        metadata=context,
                    )
                )
                added_for_rule = True
                if max_candidates is not None and len(candidates) >= max_candidates:
                    break
            if max_candidates is not None and len(candidates) >= max_candidates:
                break
        if added_for_rule:
            scoring_records.append(scaffold_rule_as_scoring_record(rule))
        if max_candidates is not None and len(candidates) >= max_candidates:
            break

    return candidates, errors, scoring_records
