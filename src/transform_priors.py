from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml


DEFAULT_TRANSFORM_PRIORS_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "transform_priors.yaml"


def load_transform_priors(path: str | Path | None = None) -> list[dict]:
    prior_path = Path(path) if path is not None else DEFAULT_TRANSFORM_PRIORS_PATH
    with prior_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("priors") or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported transform-prior shape: {prior_path}")


def issue(prior: dict, severity: str, category: str, message: str, field: str = "", value: object | None = None) -> dict:
    return {
        "rule_id": prior.get("rule_id"),
        "replacement_label": prior.get("replacement_label"),
        "severity": severity,
        "category": category,
        "field": field,
        "value": "" if value is None else str(value),
        "message": message,
    }


def validate_transform_priors(priors: list[dict], known_rule_ids: set[str] | None = None) -> dict:
    issues: list[dict] = []
    ids = Counter(str(prior.get("rule_id")) for prior in priors)
    allowed_risks = {"low", "medium", "high"}
    allowed_evidence = {"low", "medium", "high"}

    for prior in priors:
        for field in ["rule_id", "replacement_label", "evidence_level", "prior_score", "confidence"]:
            if prior.get(field) in {None, ""}:
                issues.append(issue(prior, "error", "schema", f"Missing required field: {field}", field))
        rule_id = str(prior.get("rule_id"))
        if ids[rule_id] > 1:
            issues.append(issue(prior, "error", "schema", "Duplicate rule_id.", "rule_id", rule_id))
        if known_rule_ids is not None and rule_id not in known_rule_ids:
            issues.append(issue(prior, "warning", "linkage", "Prior references a rule_id not present in transform rules.", "rule_id", rule_id))

        try:
            score = float(prior.get("prior_score"))
            if score < 0 or score > 100:
                issues.append(issue(prior, "error", "range", "prior_score must be between 0 and 100.", "prior_score", score))
        except (TypeError, ValueError):
            issues.append(issue(prior, "error", "range", "prior_score must be numeric.", "prior_score", prior.get("prior_score")))

        try:
            confidence = float(prior.get("confidence"))
            if confidence < 0 or confidence > 1:
                issues.append(issue(prior, "error", "range", "confidence must be between 0 and 1.", "confidence", confidence))
        except (TypeError, ValueError):
            issues.append(issue(prior, "error", "range", "confidence must be numeric.", "confidence", prior.get("confidence")))

        if prior.get("activity_cliff_risk") and prior.get("activity_cliff_risk") not in allowed_risks:
            issues.append(issue(prior, "warning", "schema", "Unexpected activity_cliff_risk.", "activity_cliff_risk", prior.get("activity_cliff_risk")))
        if prior.get("evidence_level") and prior.get("evidence_level") not in allowed_evidence:
            issues.append(issue(prior, "warning", "schema", "Unexpected evidence_level.", "evidence_level", prior.get("evidence_level")))

    counts = Counter(item["severity"] for item in issues)
    return {
        "prior_count": len(priors),
        "issue_count": len(issues),
        "error_count": counts.get("error", 0),
        "warning_count": counts.get("warning", 0),
        "issues": issues,
    }


def transform_prior_lookup(priors: list[dict]) -> dict[str, dict]:
    return {str(prior["rule_id"]): prior for prior in priors if prior.get("rule_id")}


def score_transform_prior(rule_id: str | None, priors_by_rule_id: dict[str, dict]) -> float | None:
    if not rule_id:
        return None
    prior = priors_by_rule_id.get(rule_id)
    if not prior:
        return None
    return max(0.0, min(100.0, float(prior.get("prior_score", 50.0))))

