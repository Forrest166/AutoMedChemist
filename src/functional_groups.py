from __future__ import annotations

from pathlib import Path

import yaml
from rdkit import Chem
from rdkit.Chem import AllChem

from .chemistry import canonical_smiles
from .enumeration import Candidate
from .sites import ModificationSite


DEFAULT_FUNCTIONAL_RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "functional_group_replacements.yaml"


def load_functional_group_rules(path: str | Path | None = None) -> list[dict]:
    rule_path = Path(path) if path is not None else DEFAULT_FUNCTIONAL_RULES_PATH
    with rule_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("functional_group_replacements", []))
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported functional-group rule shape: {rule_path}")


def _rule_direction_tags(rule: dict) -> set[str]:
    return set(rule.get("direction_tags") or [])


def filter_functional_group_rules(
    rules: list[dict],
    site_type: str,
    direction_tags: list[str] | tuple[str, ...] | None = None,
    include_advanced: bool = False,
) -> list[dict]:
    wanted_tags = set(direction_tags or [])
    filtered: list[dict] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if not include_advanced and rule.get("advanced_only", False):
            continue
        if site_type not in set(rule.get("site_types") or []):
            continue
        if wanted_tags and not wanted_tags.intersection(_rule_direction_tags(rule).union(rule.get("class") or [])):
            continue
        filtered.append(rule)
    filtered.sort(key=lambda item: item.get("priority", {}).get("default_rank", 999))
    return filtered


def rule_as_scoring_record(rule: dict) -> dict:
    return {
        "substituent_id": rule["rule_id"],
        "name": rule["name"],
        "smiles": rule.get("product_smiles") or rule.get("product_smarts") or rule.get("reaction_smarts") or rule.get("strategy"),
        "direction_tags": rule.get("direction_tags") or [],
        "class": rule.get("class") or [],
        "property_tags": rule.get("property_tags") or {},
        "risk": rule.get("risk") or {"risk_tags": [], "default_enabled": True},
        "priority": rule.get("priority") or {"default_rank": 999, "common_medchem": False},
    }


def _make_candidate(smiles: str, rule: dict, site: ModificationSite, candidate_no: int) -> Candidate:
    return Candidate(
        candidate_id=f"F{candidate_no:04d}",
        smiles=smiles,
        substituent_id=rule["rule_id"],
        substituent_name=rule["name"],
        substituent_smiles=rule.get("product_smiles") or rule.get("product_smarts") or "",
        site_id=site.site_id,
        site_type=site.site_type,
        replacement_label=rule.get("replacement_label") or rule["name"],
        enumeration_type="functional_group_replacement",
        functional_rule_id=rule["rule_id"],
    )


def _enumerate_reaction_rule(parent: Chem.Mol, rule: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    products: list[str] = []
    rxn = AllChem.ReactionFromSmarts(rule["reaction_smarts"])
    if rxn is None:
        return products, [f"Invalid reaction SMARTS: {rule['reaction_smarts']}"]

    try:
        product_sets = rxn.RunReactants((parent,))
    except Exception as exc:
        return products, [str(exc)]

    for product_set in product_sets:
        if not product_set:
            continue
        mol = product_set[0]
        try:
            Chem.SanitizeMol(mol)
            products.append(canonical_smiles(mol))
        except Exception as exc:
            errors.append(str(exc))
    return products, errors


def _enumerate_aromatic_ch_to_n(parent: Chem.Mol, site: ModificationSite) -> tuple[list[str], list[str]]:
    if site.site_type not in {"aromatic_CH", "aromatic_halide"}:
        return [], []

    atom = parent.GetAtomWithIdx(site.atom_idx)
    if atom.GetAtomicNum() != 6 or not atom.GetIsAromatic() or atom.GetTotalNumHs() == 0:
        return [], []

    rw = Chem.RWMol(parent)
    target = rw.GetAtomWithIdx(site.atom_idx)
    target.SetAtomicNum(7)
    target.SetFormalCharge(0)
    target.SetNoImplicit(True)
    try:
        product = rw.GetMol()
        Chem.SanitizeMol(product)
        return [canonical_smiles(product)], []
    except Exception as exc:
        return [], [str(exc)]


def _enumerate_basic_amine_n_oxide(parent: Chem.Mol, site: ModificationSite) -> tuple[list[str], list[str]]:
    if site.site_type != "basic_amine":
        return [], []

    atom = parent.GetAtomWithIdx(site.atom_idx)
    if atom.GetAtomicNum() != 7 or atom.GetIsAromatic() or atom.GetDegree() > 3:
        return [], []

    rw = Chem.RWMol(parent)
    n_atom = rw.GetAtomWithIdx(site.atom_idx)
    n_atom.SetFormalCharge(1)
    oxygen_idx = rw.AddAtom(Chem.Atom(8))
    o_atom = rw.GetAtomWithIdx(oxygen_idx)
    o_atom.SetFormalCharge(-1)
    rw.AddBond(site.atom_idx, oxygen_idx, Chem.BondType.SINGLE)
    try:
        product = rw.GetMol()
        Chem.SanitizeMol(product)
        return [canonical_smiles(product)], []
    except Exception as exc:
        return [], [str(exc)]


def _branch_atoms(parent: Chem.Mol, start_idx: int, blocked_idx: int) -> set[int]:
    visited = {blocked_idx}
    stack = [start_idx]
    branch: set[int] = set()
    while stack:
        idx = stack.pop()
        if idx in visited:
            continue
        visited.add(idx)
        branch.add(idx)
        atom = parent.GetAtomWithIdx(idx)
        for nbr in atom.GetNeighbors():
            nbr_idx = nbr.GetIdx()
            if nbr_idx not in visited:
                stack.append(nbr_idx)
    return branch


def _enumerate_basic_amine_dealkylation(parent: Chem.Mol, site: ModificationSite) -> tuple[list[str], list[str]]:
    if site.site_type != "basic_amine":
        return [], []

    atom = parent.GetAtomWithIdx(site.atom_idx)
    if atom.GetAtomicNum() != 7 or atom.GetIsAromatic():
        return [], []

    products: list[str] = []
    errors: list[str] = []
    for nbr in atom.GetNeighbors():
        if nbr.GetAtomicNum() != 6 or nbr.GetIsAromatic():
            continue
        branch = _branch_atoms(parent, nbr.GetIdx(), site.atom_idx)
        if len(branch) > 4:
            continue
        rw = Chem.RWMol(parent)
        for idx in sorted(branch, reverse=True):
            rw.RemoveAtom(idx)
        try:
            product = rw.GetMol()
            Chem.SanitizeMol(product)
            products.append(canonical_smiles(product))
        except Exception as exc:
            errors.append(str(exc))
    return products, errors


def _add_acyl_or_sulfonyl(parent: Chem.Mol, site: ModificationSite, group: str) -> tuple[list[str], list[str]]:
    if site.site_type != "basic_amine":
        return [], []
    atom = parent.GetAtomWithIdx(site.atom_idx)
    if atom.GetAtomicNum() != 7 or atom.GetIsAromatic() or atom.GetDegree() >= 3:
        return [], []

    rw = Chem.RWMol(parent)
    if group == "acetyl":
        carbonyl_idx = rw.AddAtom(Chem.Atom(6))
        oxygen_idx = rw.AddAtom(Chem.Atom(8))
        methyl_idx = rw.AddAtom(Chem.Atom(6))
        rw.AddBond(site.atom_idx, carbonyl_idx, Chem.BondType.SINGLE)
        rw.AddBond(carbonyl_idx, oxygen_idx, Chem.BondType.DOUBLE)
        rw.AddBond(carbonyl_idx, methyl_idx, Chem.BondType.SINGLE)
    elif group == "mesyl":
        sulfur_idx = rw.AddAtom(Chem.Atom(16))
        oxygen_1_idx = rw.AddAtom(Chem.Atom(8))
        oxygen_2_idx = rw.AddAtom(Chem.Atom(8))
        methyl_idx = rw.AddAtom(Chem.Atom(6))
        rw.AddBond(site.atom_idx, sulfur_idx, Chem.BondType.SINGLE)
        rw.AddBond(sulfur_idx, oxygen_1_idx, Chem.BondType.DOUBLE)
        rw.AddBond(sulfur_idx, oxygen_2_idx, Chem.BondType.DOUBLE)
        rw.AddBond(sulfur_idx, methyl_idx, Chem.BondType.SINGLE)
    else:
        return [], [f"Unsupported amine lowering group: {group}"]

    try:
        product = rw.GetMol()
        Chem.SanitizeMol(product)
        return [canonical_smiles(product)], []
    except Exception as exc:
        return [], [str(exc)]


def _region_anchor_and_delete_atoms(parent: Chem.Mol, site: ModificationSite) -> tuple[int | None, set[int]]:
    carbonyl = parent.GetAtomWithIdx(site.atom_idx)
    if carbonyl.GetAtomicNum() != 6:
        return None, set()

    anchor_idx = None
    delete_atoms = {site.atom_idx}
    for nbr in carbonyl.GetNeighbors():
        bond = parent.GetBondBetweenAtoms(site.atom_idx, nbr.GetIdx())
        if nbr.GetAtomicNum() == 8 and bond.GetBondType() == Chem.BondType.DOUBLE:
            delete_atoms.add(nbr.GetIdx())
        elif nbr.GetAtomicNum() in {7, 8}:
            delete_atoms.update(_branch_atoms(parent, nbr.GetIdx(), site.atom_idx))
        else:
            anchor_idx = nbr.GetIdx()
    return anchor_idx, delete_atoms


def _replace_region_with_fragment(parent: Chem.Mol, site: ModificationSite, fragment_smiles: str) -> tuple[list[str], list[str]]:
    anchor_idx, delete_atoms = _region_anchor_and_delete_atoms(parent, site)
    if anchor_idx is None or not delete_atoms:
        return [], ["Could not identify carbonyl anchor for replacement."]

    rw = Chem.RWMol(parent)
    adjusted_anchor = anchor_idx
    for idx in sorted(delete_atoms, reverse=True):
        rw.RemoveAtom(idx)
        if idx < adjusted_anchor:
            adjusted_anchor -= 1
    scaffold = rw.GetMol()
    Chem.SanitizeMol(scaffold)

    fragment = Chem.MolFromSmiles(fragment_smiles)
    if fragment is None:
        return [], [f"Invalid replacement fragment: {fragment_smiles}"]
    dummy_atoms = [atom for atom in fragment.GetAtoms() if atom.GetAtomicNum() == 0]
    if len(dummy_atoms) != 1 or len(dummy_atoms[0].GetNeighbors()) != 1:
        return [], [f"Replacement fragment must have one attachment point: {fragment_smiles}"]
    dummy_idx = dummy_atoms[0].GetIdx()
    attach_idx = dummy_atoms[0].GetNeighbors()[0].GetIdx()

    offset = scaffold.GetNumAtoms()
    combined = Chem.CombineMols(scaffold, fragment)
    rw = Chem.RWMol(combined)
    rw.AddBond(adjusted_anchor, offset + attach_idx, Chem.BondType.SINGLE)
    rw.RemoveAtom(offset + dummy_idx)
    try:
        product = rw.GetMol()
        Chem.SanitizeMol(product)
        return [canonical_smiles(product)], []
    except Exception as exc:
        return [], [str(exc)]


def enumerate_functional_group_replacements(
    parent: Chem.Mol,
    site: ModificationSite,
    rules: list[dict],
    direction_tags: list[str] | tuple[str, ...] | None = None,
    max_candidates: int | None = None,
) -> tuple[list[Candidate], list[dict], list[dict]]:
    selected_rules = filter_functional_group_rules(rules, site.site_type, direction_tags=direction_tags)
    candidates: list[Candidate] = []
    errors: list[dict] = []
    scoring_records: list[dict] = []
    seen: set[str] = {canonical_smiles(parent)}

    for rule in selected_rules:
        strategy = rule.get("strategy", "reaction_smarts")
        if strategy == "reaction_smarts":
            products, product_errors = _enumerate_reaction_rule(parent, rule)
        elif strategy == "aromatic_ch_to_n":
            products, product_errors = _enumerate_aromatic_ch_to_n(parent, site)
        elif strategy == "basic_amine_n_oxide":
            products, product_errors = _enumerate_basic_amine_n_oxide(parent, site)
        elif strategy == "basic_amine_dealkylation":
            products, product_errors = _enumerate_basic_amine_dealkylation(parent, site)
        elif strategy == "basic_amine_acetylation":
            products, product_errors = _add_acyl_or_sulfonyl(parent, site, "acetyl")
        elif strategy == "basic_amine_mesylation":
            products, product_errors = _add_acyl_or_sulfonyl(parent, site, "mesyl")
        elif strategy == "carbonyl_region_to_fragment":
            products, product_errors = _replace_region_with_fragment(parent, site, rule["product_smiles"])
        else:
            products, product_errors = [], [f"Unsupported functional replacement strategy: {strategy}"]

        for message in product_errors:
            errors.append({"rule_id": rule.get("rule_id"), "name": rule.get("name"), "error": message})

        added_for_rule = False
        for smiles in products:
            if smiles in seen:
                continue
            seen.add(smiles)
            candidate_no = len(candidates) + 1
            candidates.append(_make_candidate(smiles, rule, site, candidate_no))
            added_for_rule = True
            if max_candidates is not None and len(candidates) >= max_candidates:
                break

        if added_for_rule:
            scoring_records.append(rule_as_scoring_record(rule))
        if max_candidates is not None and len(candidates) >= max_candidates:
            break

    return candidates, errors, scoring_records
