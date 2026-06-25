from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator


MORGAN_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
DEFAULT_DIRECTION_RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "direction_rules.yaml"


DEFAULT_COMPONENT_WEIGHTS = {
    "direction": 0.36,
    "property": 0.22,
    "similarity": 0.13,
    "synthetic": 0.10,
    "risk": 0.09,
    "transform_prior": 0.05,
    "transform_activity": 0.0,
    "mmp_precedent": 0.03,
    "evidence_consistency": 0.03,
    "evidence_confidence_calibration": 0.015,
    "sar_neighborhood": 0.02,
    "ring_frequency": 0.02,
    "scaffold_context": 0.03,
    "scaffold_local_evidence": 0.02,
    "strategy_learning_prior": 0.02,
    "public_strategy_signal": 0.015,
    "vendor": 0.04,
    "route": 0.01,
}


DEFAULT_PROPERTY_RANGES = {
    "mw": (150, 600, 0.4),
    "clogp": (-1, 6, 8.0),
    "tpsa": (0, 140, 0.3),
    "hbd": (0, 5, 7.0),
    "hba": (0, 12, 5.0),
    "rotatable_bonds": (0, 12, 4.0),
    "formal_charge": (-1, 1, 12.0),
}


def _delta(parent: dict, candidate: dict, key: str) -> float:
    return float(candidate.get(key, 0) or 0) - float(parent.get(key, 0) or 0)


def load_direction_rules(path: str | Path | None = None) -> dict:
    rule_path = Path(path) if path is not None else DEFAULT_DIRECTION_RULES_PATH
    with rule_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def direction_include_tags(direction: str, rules: dict | None = None) -> list[str]:
    rules = rules or load_direction_rules()
    direction_def = (rules.get("directions") or {}).get(direction) or {}
    tags = direction_def.get("include_tags") or [direction]
    return list(dict.fromkeys(tags))


def component_weights(rules: dict | None = None, overrides: dict | None = None) -> dict[str, float]:
    weights = dict(DEFAULT_COMPONENT_WEIGHTS)
    if rules:
        weights.update((rules.get("scoring") or {}).get("component_weights") or {})
    if overrides:
        weights.update(overrides)

    total = sum(max(float(value), 0.0) for value in weights.values())
    if total <= 0:
        return dict(DEFAULT_COMPONENT_WEIGHTS)
    return {key: max(float(value), 0.0) / total for key, value in weights.items()}


def _compare(left: float, op: str, right: float) -> bool:
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    raise ValueError(f"Unsupported scoring operator: {op}")


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _tag_source(substituent: dict, source: str | None = None) -> set[str]:
    if source == "direction_tags":
        return set(substituent.get("direction_tags") or [])
    if source == "class":
        return set(substituent.get("class") or [])
    if source == "risk_tags":
        return set((substituent.get("risk") or {}).get("risk_tags") or [])

    tags = set(substituent.get("direction_tags") or [])
    tags.update(substituent.get("class") or [])
    tags.update((substituent.get("risk") or {}).get("risk_tags") or [])
    for value in (substituent.get("property_tags") or {}).values():
        if isinstance(value, list):
            tags.update(str(item) for item in value)
        elif value is not None:
            tags.add(str(value))
    return tags


def _rule_matches(rule: dict, parent_props: dict, candidate_props: dict, substituent: dict) -> bool:
    when = rule.get("when")
    if when == "tag_match":
        wanted = set(rule.get("tags") or [])
        return bool(wanted.intersection(_tag_source(substituent, rule.get("source"))))

    if when == "delta":
        value = _delta(parent_props, candidate_props, rule["property"])
        return _compare(value, rule.get("op", ">"), _as_float(rule.get("value")))

    if when == "candidate_property":
        value = _as_float(candidate_props.get(rule["property"]))
        return _compare(value, rule.get("op", ">"), _as_float(rule.get("value")))

    if when == "candidate_vs_parent":
        key = rule["property"]
        offset = _as_float(rule.get("offset"))
        left = _as_float(candidate_props.get(key))
        right = _as_float(parent_props.get(key)) + offset
        return _compare(left, rule.get("op", ">="), right)

    return False


def score_direction(
    direction: str,
    parent_props: dict,
    candidate_props: dict,
    substituent: dict,
    rules: dict | None = None,
) -> float:
    rules = rules or load_direction_rules()
    scoring_config = rules.get("scoring") or {}
    direction_def = (rules.get("directions") or {}).get(direction) or {}
    score = float(direction_def.get("base_score", 0.0))

    score_rules = direction_def.get("score_rules")
    if score_rules:
        for rule in score_rules:
            if _rule_matches(rule, parent_props, candidate_props, substituent):
                score += float(rule.get("points", 0.0))
    else:
        score += 35.0 if direction in _tag_source(substituent, "direction_tags") else 10.0

    return max(0.0, min(float(scoring_config.get("direction_score_cap", 100.0)), score))


def score_property_profile(props: dict, ranges: dict | None = None) -> float:
    score = 100.0
    ranges = ranges or DEFAULT_PROPERTY_RANGES
    for key, (low, high, penalty) in ranges.items():
        value = props.get(key)
        if value is None:
            continue
        if value < low:
            score -= (low - value) * penalty
        elif value > high:
            score -= (value - high) * penalty
    return max(0.0, min(100.0, score))


def tanimoto_similarity(parent: Chem.Mol, candidate: Chem.Mol) -> float:
    fp1 = MORGAN_GENERATOR.GetFingerprint(parent)
    fp2 = MORGAN_GENERATOR.GetFingerprint(candidate)
    return float(DataStructs.TanimotoSimilarity(fp1, fp2))


def score_similarity(similarity: float) -> float:
    if similarity >= 0.8:
        return 100.0
    if similarity >= 0.65:
        return 80.0
    if similarity >= 0.5:
        return 55.0
    return 25.0


def score_synthetic_access(substituent: dict) -> float:
    priority = substituent.get("priority", {})
    rank = float(priority.get("default_rank", 999))
    score = 100.0 - min(rank, 100.0) * 0.55
    if priority.get("common_medchem", False):
        score += 15
    return max(0.0, min(100.0, score))


def score_risk(substituent: dict) -> float:
    risk = substituent.get("risk", {})
    tags = set(risk.get("risk_tags", []))
    score = 100.0
    high_penalty = {"reactive_alert", "toxicophore", "advanced_only"}
    medium_penalty = {"possible_strong_basicity", "possible_soft_spot", "permeability_risk"}
    score -= 35 * len(tags.intersection(high_penalty))
    score -= 12 * len(tags.intersection(medium_penalty))
    if not risk.get("default_enabled", True):
        score -= 40
    return max(0.0, min(100.0, score))


def final_score(
    direction_score: float,
    property_score: float,
    similarity_score_value: float,
    synthetic_score: float,
    risk_score: float,
    transform_prior_score: float | None = None,
    transform_activity_score: float | None = None,
    mmp_precedent_score: float | None = None,
    evidence_consistency_score: float | None = None,
    evidence_confidence_calibration_score: float | None = None,
    sar_neighborhood_score: float | None = None,
    ring_frequency_score: float | None = None,
    scaffold_context_score: float | None = None,
    scaffold_local_evidence_score: float | None = None,
    strategy_learning_prior_score: float | None = None,
    public_strategy_signal_score: float | None = None,
    vendor_score: float | None = None,
    route_score: float | None = None,
    weights: dict | None = None,
) -> float:
    weights = component_weights(overrides=weights)
    scores = {
        "direction": direction_score,
        "property": property_score,
        "similarity": similarity_score_value,
        "synthetic": synthetic_score,
        "risk": risk_score,
        "transform_prior": transform_prior_score,
        "transform_activity": transform_activity_score,
        "mmp_precedent": mmp_precedent_score,
        "evidence_consistency": evidence_consistency_score,
        "evidence_confidence_calibration": evidence_confidence_calibration_score,
        "sar_neighborhood": sar_neighborhood_score,
        "ring_frequency": ring_frequency_score,
        "scaffold_context": scaffold_context_score,
        "scaffold_local_evidence": scaffold_local_evidence_score,
        "strategy_learning_prior": strategy_learning_prior_score,
        "public_strategy_signal": public_strategy_signal_score,
        "vendor": vendor_score,
        "route": route_score,
    }
    active = {key: value for key, value in scores.items() if value is not None and weights.get(key, 0.0) > 0}
    active_weight = sum(weights[key] for key in active)
    if active_weight <= 0:
        return 0.0
    return round(sum(float(value) * (weights[key] / active_weight) for key, value in active.items()), 2)


def recommendation_reason(direction: str, parent_props: dict, candidate_props: dict, substituent: dict) -> str:
    parts: list[str] = []
    if direction in set(substituent.get("direction_tags", [])):
        parts.append(f"matches {direction}")
    d_mw = _delta(parent_props, candidate_props, "mw")
    d_logp = _delta(parent_props, candidate_props, "clogp")
    d_tpsa = _delta(parent_props, candidate_props, "tpsa")
    parts.append(f"dMW {d_mw:+.1f}")
    parts.append(f"dLogP {d_logp:+.2f}")
    parts.append(f"dTPSA {d_tpsa:+.1f}")
    risks = substituent.get("risk", {}).get("risk_tags", [])
    if risks:
        parts.append("risk tags: " + ",".join(risks))
    return "; ".join(parts)
