from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml
from rdkit import Chem
from rdkit.Chem import AllChem


def load_transform_rules(path: str | Path = "data/rules/functional_group_replacements.yaml") -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("functional_group_replacements") or [])
    return list(data or [])


def issue(rule: dict, severity: str, category: str, message: str, field: str = "", value: object | None = None) -> dict:
    return {
        "rule_id": rule.get("rule_id"),
        "name": rule.get("name"),
        "severity": severity,
        "category": category,
        "field": field,
        "value": "" if value is None else str(value),
        "message": message,
    }


def mapped_atom_numbers(smarts: str) -> set[int]:
    mol = Chem.MolFromSmarts(smarts)
    if mol is None:
        return set()
    return {atom.GetAtomMapNum() for atom in mol.GetAtoms() if atom.GetAtomMapNum()}


def validate_reaction_smarts(rule: dict) -> list[dict]:
    reaction_smarts = rule.get("reaction_smarts")
    if not reaction_smarts:
        return []
    issues: list[dict] = []
    try:
        rxn = AllChem.ReactionFromSmarts(reaction_smarts)
    except Exception as exc:
        return [issue(rule, "error", "reaction_smarts", f"Invalid reaction SMARTS: {exc}", "reaction_smarts", reaction_smarts)]
    if rxn is None:
        return [issue(rule, "error", "reaction_smarts", "Reaction SMARTS could not be parsed.", "reaction_smarts", reaction_smarts)]

    validate_errors, validate_warnings = rxn.Validate()
    if validate_errors:
        issues.append(issue(rule, "error", "reaction_smarts", f"RDKit validation reported {validate_errors} errors.", "reaction_smarts", reaction_smarts))
    if validate_warnings:
        issues.append(issue(rule, "warning", "reaction_smarts", f"RDKit validation reported {validate_warnings} warnings.", "reaction_smarts", reaction_smarts))

    if ">>" in reaction_smarts:
        reactant, product = reaction_smarts.split(">>", 1)
        reactant_maps = mapped_atom_numbers(reactant)
        product_maps = mapped_atom_numbers(product)
        if not product_maps:
            issues.append(issue(rule, "warning", "atom_mapping", "No mapped atoms are present in the product.", "reaction_smarts", reaction_smarts))
        if product_maps - reactant_maps:
            issues.append(issue(rule, "error", "atom_mapping", "Product contains atom maps not present in reactants.", "reaction_smarts", sorted(product_maps - reactant_maps)))
        lost_maps = reactant_maps - product_maps
        if lost_maps and not rule.get("allow_unmapped_reactant_atoms", True):
            issues.append(issue(rule, "warning", "atom_mapping", "Reactant mapped atoms are absent from product.", "reaction_smarts", sorted(lost_maps)))
    return issues


PRODUCT_SMILES_SENTINELS = {"aryl_N_scan", "basic_amine_N_oxide", "basic_amine_dealkylated"}


def validate_product_smiles(rule: dict) -> list[dict]:
    product_smiles = rule.get("product_smiles")
    if not product_smiles or product_smiles in PRODUCT_SMILES_SENTINELS:
        return []
    mol = Chem.MolFromSmiles(product_smiles)
    if mol is None:
        return [issue(rule, "error", "product_smiles", "product_smiles could not be parsed.", "product_smiles", product_smiles)]
    dummy_count = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0)
    if dummy_count != 1:
        return [issue(rule, "warning", "product_smiles", "product_smiles should contain one attachment dummy when it represents a substituent.", "product_smiles", product_smiles)]
    return []


def validate_transform_rules(rules: list[dict]) -> dict:
    issues: list[dict] = []
    ids = Counter(str(rule.get("rule_id")) for rule in rules)
    for rule in rules:
        for field in ["rule_id", "name", "replacement_label", "strategy", "site_types", "direction_tags", "priority"]:
            if not rule.get(field):
                issues.append(issue(rule, "error", "schema", f"Missing required field: {field}", field))
        if rule.get("rule_id") and ids[str(rule.get("rule_id"))] > 1:
            issues.append(issue(rule, "error", "schema", "Duplicate rule_id.", "rule_id", rule.get("rule_id")))
        if rule.get("strategy") == "reaction_smarts" and not rule.get("reaction_smarts"):
            issues.append(issue(rule, "error", "schema", "reaction_smarts strategy requires reaction_smarts.", "reaction_smarts"))
        issues.extend(validate_reaction_smarts(rule))
        issues.extend(validate_product_smiles(rule))

    counts = Counter(item["severity"] for item in issues)
    return {
        "rule_count": len(rules),
        "issue_count": len(issues),
        "error_count": counts.get("error", 0),
        "warning_count": counts.get("warning", 0),
        "issues": issues,
    }
