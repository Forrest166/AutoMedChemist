from __future__ import annotations

import csv
import json
import math
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable

from .database import initialize_database
from .scoring import component_weights


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
POSITIVE_DECISIONS = {"shortlisted", "selected"}
NEGATIVE_DECISIONS = {"rejected"}
POSITIVE_CLASSES = {"active", "pass", "improved", "selected", "shortlisted"}
NEGATIVE_CLASSES = {"inactive", "fail", "worse", "rejected"}
COMPONENT_FIELDS = [
    "direction_score",
    "property_score",
    "similarity_score",
    "synthetic_score",
    "risk_score",
    "transform_prior_score",
    "transform_activity_score",
    "mmp_precedent_score",
    "evidence_consistency_score",
    "sar_neighborhood_score",
    "ring_frequency_score",
    "scaffold_context_score",
    "scaffold_local_evidence_score",
    "vendor_score",
    "route_score",
]
WEIGHT_KEYS = {
    "direction_score": "direction",
    "property_score": "property",
    "similarity_score": "similarity",
    "synthetic_score": "synthetic",
    "risk_score": "risk",
    "transform_prior_score": "transform_prior",
    "transform_activity_score": "transform_activity",
    "mmp_precedent_score": "mmp_precedent",
    "evidence_consistency_score": "evidence_consistency",
    "sar_neighborhood_score": "sar_neighborhood",
    "ring_frequency_score": "ring_frequency",
    "scaffold_context_score": "scaffold_context",
    "scaffold_local_evidence_score": "scaffold_local_evidence",
    "vendor_score": "vendor",
    "route_score": "route",
}
PROPERTY_FIELDS = ["mw", "clogp", "tpsa", "hbd", "hba", "rotatable_bonds"]
LOWER_IS_BETTER_ENDPOINTS = {"potency", "clearance", "herg_inhibition", "toxicity"}
HIGHER_IS_BETTER_ENDPOINTS = {"solubility", "permeability", "stability", "herg_safety"}


def endpoint_group_from_text(*values: str | None) -> str:
    text = " ".join(str(value or "").lower() for value in values)
    if any(token in text for token in ["herg", "qt", "cardiac"]):
        if any(token in text for token in ["ic50", "ki", "margin", "safety", "block"]):
            return "herg_safety"
        return "herg_inhibition"
    if any(token in text for token in ["ic50", "ec50", "ki", "kd", "potency", "activity", "pchembl"]):
        return "potency"
    if any(token in text for token in ["solub", "kinetic", "thermodynamic"]):
        return "solubility"
    if any(token in text for token in ["clearance", "clint", "cl_int", "intrinsic"]):
        return "clearance"
    if any(token in text for token in ["microsom", "hepatocyte", "half-life", "half life", "stability", "t1/2"]):
        return "stability"
    if any(token in text for token in ["permeab", "mdck", "caco", "pampa"]):
        return "permeability"
    if any(token in text for token in ["tox", "cytotox", "viability"]):
        return "toxicity"
    return "unspecified"


def default_higher_is_better(row: dict) -> bool:
    endpoint = endpoint_group_from_text(row.get("endpoint"), row.get("assay_type"), row.get("assay_name"))
    if endpoint in HIGHER_IS_BETTER_ENDPOINTS:
        return True
    if endpoint in LOWER_IS_BETTER_ENDPOINTS:
        return False
    return False


def _boolish(value, default: bool = False) -> bool:
    if value in {None, ""}:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "higher", "high"}


def _float_or_none(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_feedback_score(row: dict) -> float | None:
    explicit = _float_or_none(row.get("normalized_score"))
    if explicit is not None:
        return max(0.0, min(100.0, explicit))

    classification = str(row.get("classification") or "").strip().lower()
    if classification in POSITIVE_CLASSES:
        return 85.0
    if classification in NEGATIVE_CLASSES:
        return 15.0

    value = _float_or_none(row.get("value"))
    if value is None:
        return None

    unit = str(row.get("unit") or "").lower()
    higher_is_better = _boolish(row.get("higher_is_better"), default_higher_is_better(row))
    if unit in {"nm", "nanomolar"}:
        nm = max(value, 0.001)
        lower_better_score = 100.0 - (math.log10(nm) - 1.0) * 25.0
        higher_better_score = (math.log10(nm) - 1.0) * 25.0
        score = higher_better_score if higher_is_better else lower_better_score
        return max(0.0, min(100.0, score))
    if unit in {"um", "micromolar", "µm"}:
        nm = max(value * 1000.0, 0.001)
        lower_better_score = 100.0 - (math.log10(nm) - 1.0) * 25.0
        higher_better_score = (math.log10(nm) - 1.0) * 25.0
        score = higher_better_score if higher_is_better else lower_better_score
        return max(0.0, min(100.0, score))
    if "%" in unit or unit in {"percent", "pct"}:
        score = max(0.0, min(100.0, value))
        return score if higher_is_better else 100.0 - score

    score = max(0.0, min(100.0, value))
    return score if higher_is_better else 100.0 - score


def read_feedback_csv(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def import_feedback_rows(
    rows: Iterable[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    source_path: str | None = None,
) -> dict:
    conn = initialize_database(db_path)
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    skipped = 0
    try:
        for raw in rows:
            row = {str(key).strip(): value for key, value in dict(raw).items()}
            run_id = str(row.get("run_id") or "").strip()
            candidate_id = str(row.get("candidate_id") or "").strip()
            if not run_id or not candidate_id:
                skipped += 1
                continue
            exists = conn.execute(
                "SELECT 1 FROM project_candidate WHERE run_id=? AND candidate_id=?",
                (run_id, candidate_id),
            ).fetchone()
            if not exists:
                skipped += 1
                continue
            feedback_id = row.get("feedback_id") or f"FBK-{uuid.uuid4().hex[:12].upper()}"
            normalized = normalize_feedback_score(row)
            conn.execute(
                """
                INSERT OR REPLACE INTO project_feedback (
                    feedback_id, run_id, candidate_id, project_name, assay_name,
                    assay_type, endpoint, value, unit, relation, higher_is_better,
                    normalized_score, classification, source_path, note, recorded_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    run_id,
                    candidate_id,
                    row.get("project_name"),
                    row.get("assay_name"),
                    row.get("assay_type"),
                    row.get("endpoint"),
                    _float_or_none(row.get("value")),
                    row.get("unit"),
                    row.get("relation"),
                    1 if _boolish(row.get("higher_is_better")) else 0,
                    normalized,
                    row.get("classification"),
                    source_path or row.get("source_path"),
                    row.get("note"),
                    row.get("recorded_at") or now,
                    json.dumps(row, sort_keys=True),
                ),
            )
            inserted += 1
        conn.commit()
        return {"inserted_count": inserted, "skipped_count": skipped}
    finally:
        conn.close()


def import_feedback_csv(
    path: str | Path,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    return import_feedback_rows(read_feedback_csv(path), db_path=db_path, source_path=str(Path(path).resolve()))


def _rows_for_project(conn: sqlite3.Connection, project_name: str | None = None) -> list[dict]:
    conn.row_factory = sqlite3.Row
    params: tuple = ()
    where = ""
    if project_name:
        where = "WHERE pr.project_name = ?"
        params = (project_name,)
    rows = conn.execute(
        f"""
        SELECT
            pr.project_name,
            pr.direction,
            pr.site_type,
            pc.run_id,
            pc.candidate_id,
            pc.decision_status,
            pc.payload_json,
            pf.feedback_id,
            pf.assay_name,
            pf.assay_type,
            pf.endpoint,
            pf.value,
            pf.unit,
            pf.normalized_score,
            pf.classification
        FROM project_candidate pc
        JOIN project_run pr ON pr.run_id = pc.run_id
        LEFT JOIN project_feedback pf
            ON pf.run_id = pc.run_id AND pf.candidate_id = pc.candidate_id
        {where}
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _candidate_payload(row: dict) -> dict:
    try:
        return json.loads(row.get("payload_json") or "{}")
    except json.JSONDecodeError:
        return {}


def _outcome(row: dict) -> str:
    decision = str(row.get("decision_status") or "").lower()
    classification = str(row.get("classification") or "").lower()
    normalized = _float_or_none(row.get("normalized_score"))
    if decision in POSITIVE_DECISIONS or classification in POSITIVE_CLASSES or (normalized is not None and normalized >= 70):
        return "positive"
    if decision in NEGATIVE_DECISIONS or classification in NEGATIVE_CLASSES or (normalized is not None and normalized <= 30):
        return "negative"
    return "neutral"


def _average(rows: list[dict], field: str) -> float | None:
    values = []
    for row in rows:
        value = _float_or_none(_candidate_payload(row).get(field))
        if value is not None:
            values.append(value)
    return round(mean(values), 4) if values else None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = (len(values) - 1) * pct
    low = math.floor(idx)
    high = math.ceil(idx)
    if low == high:
        return values[int(idx)]
    return values[low] * (high - idx) + values[high] * (idx - low)


def _filter_suggestions(positive_rows: list[dict]) -> dict:
    suggestions: dict[str, dict] = {}
    for field in PROPERTY_FIELDS:
        values = []
        for row in positive_rows:
            value = _float_or_none(_candidate_payload(row).get(field))
            if value is not None:
                values.append(value)
        if len(values) < 2:
            continue
        low = _percentile(values, 0.1)
        high = _percentile(values, 0.9)
        margin = max((high - low) * 0.2, 0.5 if field in {"clogp", "hbd", "hba", "rotatable_bonds"} else 5.0)
        suggestions[field] = {
            "min": round(low - margin, 2),
            "max": round(high + margin, 2),
            "basis": f"{len(values)} positive candidates",
        }
    return suggestions


def _weight_suggestions(rows: list[dict]) -> dict:
    positives = [row for row in rows if _outcome(row) == "positive"]
    negatives = [row for row in rows if _outcome(row) == "negative"]
    weights = component_weights()
    if not positives or not negatives:
        return {"weights": weights, "basis": "Insufficient positive/negative contrast; using default weights."}

    adjusted = dict(weights)
    evidence = {}
    for component in COMPONENT_FIELDS:
        positive_mean = _average(positives, component)
        negative_mean = _average(negatives, component)
        if positive_mean is None or negative_mean is None:
            continue
        delta = positive_mean - negative_mean
        weight_key = WEIGHT_KEYS[component]
        if delta >= 8:
            adjusted[weight_key] = adjusted.get(weight_key, 0.0) + 0.03
        elif delta <= -8:
            adjusted[weight_key] = max(0.0, adjusted.get(weight_key, 0.0) - 0.02)
        evidence[weight_key] = {
            "positive_mean": positive_mean,
            "negative_mean": negative_mean,
            "delta": round(delta, 4),
        }
    return {
        "weights": component_weights(overrides=adjusted),
        "basis": f"{len(positives)} positive vs {len(negatives)} negative candidate outcomes.",
        "component_evidence": evidence,
    }


def summarize_project_feedback(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> dict:
    conn = initialize_database(db_path)
    try:
        rows = _rows_for_project(conn, project_name=project_name)
    finally:
        conn.close()

    outcomes = Counter(_outcome(row) for row in rows)
    feedback_rows = [row for row in rows if row.get("feedback_id")]
    positives = [row for row in rows if _outcome(row) == "positive"]
    endpoints = Counter(str(row.get("endpoint") or "unspecified") for row in feedback_rows)
    assays = Counter(str(row.get("assay_name") or "unspecified") for row in feedback_rows)

    return {
        "project_name": project_name,
        "candidate_count": len({(row.get("run_id"), row.get("candidate_id")) for row in rows}),
        "feedback_count": len(feedback_rows),
        "outcome_counts": dict(sorted(outcomes.items())),
        "assay_counts": dict(assays.most_common()),
        "endpoint_counts": dict(endpoints.most_common()),
        "score_weight_suggestion": _weight_suggestions(rows),
        "filter_suggestions": _filter_suggestions(positives),
    }


def write_feedback_report(report: dict, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
