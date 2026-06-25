from __future__ import annotations

import json
from pathlib import Path


DEFAULT_TRANSFORM_ACTIVITY_REPORT = Path("data/substituents/transform_activity_report.json")


def load_transform_activity_report(path: str | Path = DEFAULT_TRANSFORM_ACTIVITY_REPORT) -> dict:
    report_path = Path(path)
    if not report_path.exists():
        return {}
    return json.loads(report_path.read_text(encoding="utf-8"))


def transform_activity_lookup(report: dict) -> dict[str, dict]:
    lookup: dict[str, list[dict]] = {}
    for row in report.get("summaries") or []:
        rule_id = row.get("rule_id")
        if not rule_id:
            continue
        lookup.setdefault(str(rule_id), []).append(row)

    result = {}
    for rule_id, rows in lookup.items():
        judgment_counts = {
            label: sum(1 for row in rows if row.get("rule_activity_judgment") == label)
            for label in ["supported", "contradicted", "inconclusive"]
        }
        supported = judgment_counts["supported"]
        contradicted = judgment_counts["contradicted"]
        if supported > contradicted:
            judgment = "supported"
        elif contradicted > supported:
            judgment = "contradicted"
        else:
            judgment = "inconclusive"
        confidence_values = [
            float(row.get("assay_confidence_score"))
            for row in rows
            if row.get("assay_confidence_score") not in {None, ""}
        ]
        uncertainty_values = [
            float(row.get("uncertainty_score"))
            for row in rows
            if row.get("uncertainty_score") not in {None, ""}
        ]
        result[rule_id] = {
            "rule_id": rule_id,
            "replacement_label": next((row.get("replacement_label") for row in rows if row.get("replacement_label")), None),
            "rule_activity_judgment": judgment,
            "rule_activity_judgment_counts": judgment_counts,
            "activity_summary_count": len(rows),
            "activity_cliff_count": sum(int(row.get("activity_cliff_count") or 0) for row in rows),
            "target_family_summary_count": sum(int(row.get("target_family_summary_count") or 0) for row in rows),
            "mean_family_delta_pchembl": _mean([row.get("mean_family_delta_pchembl") for row in rows]),
            "assay_confidence_score": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else None,
            "uncertainty_score": round(sum(uncertainty_values) / len(uncertainty_values), 3) if uncertainty_values else None,
            "rule_activity_judgment_note": next((row.get("rule_activity_judgment_note") for row in rows if row.get("rule_activity_judgment_note")), None),
        }
    return result


def _mean(values: list) -> float | None:
    parsed = []
    for value in values:
        if value in {None, ""}:
            continue
        try:
            parsed.append(float(value))
        except (TypeError, ValueError):
            continue
    return round(sum(parsed) / len(parsed), 4) if parsed else None


def score_transform_activity(
    rule_id: str | None,
    lookup: dict[str, dict],
    *,
    profile: dict | None = None,
) -> dict:
    if not rule_id:
        return {}
    evidence = lookup.get(str(rule_id))
    if not evidence:
        return {
            "transform_activity_score": None,
            "rule_activity_judgment": None,
            "rule_activity_confidence": None,
            "rule_activity_uncertainty": None,
        }
    config = (profile or {}).get("transform_activity_scoring") or {}
    if config and not config.get("enabled", True):
        return {
            **evidence,
            "transform_activity_score": None,
            "rule_activity_confidence": evidence.get("assay_confidence_score"),
            "rule_activity_uncertainty": evidence.get("uncertainty_score"),
        }

    judgment = evidence.get("rule_activity_judgment")
    base_by_judgment = {
        "supported": float(config.get("supported_score", 86.0)),
        "contradicted": float(config.get("contradicted_score", 34.0)),
        "inconclusive": float(config.get("inconclusive_score", 55.0)),
    }
    base = base_by_judgment.get(str(judgment), 55.0)
    confidence = evidence.get("assay_confidence_score")
    uncertainty = evidence.get("uncertainty_score")
    if confidence is not None:
        base = (base * 0.75) + (float(confidence) * 0.25)
    if uncertainty is not None:
        base -= float(config.get("uncertainty_penalty", 12.0)) * float(uncertainty)
    cliff_count = int(evidence.get("activity_cliff_count") or 0)
    if cliff_count:
        base -= min(float(config.get("cliff_penalty_cap", 12.0)), cliff_count * float(config.get("cliff_penalty", 3.0)))
    score = max(0.0, min(100.0, base))
    return {
        **evidence,
        "transform_activity_score": round(score, 2),
        "rule_activity_confidence": evidence.get("assay_confidence_score"),
        "rule_activity_uncertainty": evidence.get("uncertainty_score"),
    }
