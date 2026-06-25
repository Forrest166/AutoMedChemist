from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from .database import initialize_database
from .feedback import _float_or_none
from .target_context import normalize_assay_type, normalize_endpoint_group


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")

DEFAULT_ENDPOINT_THRESHOLDS = {
    "potency": {"go_score": 70.0, "stop_score": 35.0, "min_replicates": 2, "max_replicate_cv": 0.35},
    "metabolic_stability": {"go_score": 68.0, "stop_score": 38.0, "min_replicates": 2, "max_replicate_cv": 0.40},
    "solubility": {"go_score": 65.0, "stop_score": 35.0, "min_replicates": 2, "max_replicate_cv": 0.45},
    "permeability": {"go_score": 65.0, "stop_score": 35.0, "min_replicates": 2, "max_replicate_cv": 0.45},
    "default": {"go_score": 70.0, "stop_score": 35.0, "min_replicates": 2, "max_replicate_cv": 0.40},
}

POSITIVE_CLASSES = {"active", "pass", "positive", "improved", "go", "hit"}
NEGATIVE_CLASSES = {"inactive", "fail", "failed", "negative", "worse", "stop"}
WATCH_CLASSES = {"watch", "mixed", "neutral", "inconclusive"}
STOP_GO_DECISIONS = ["go", "watch", "stop", "retest"]


def _text(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in {None, ""}:
            return str(value).strip()
    return ""


def _int_or_none(value) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _replicate_cv(row: dict) -> float | None:
    direct = _float_or_none(_text(row, "replicate_cv", "result_cv", "cv"))
    if direct is not None:
        return abs(direct)
    stdev = _float_or_none(_text(row, "replicate_stdev", "result_stdev", "stdev", "sd"))
    mean_value = _float_or_none(_text(row, "replicate_mean", "result_mean", "mean", "value", "result_value"))
    if stdev is None or mean_value in {None, 0}:
        return None
    return round(abs(stdev / mean_value), 4)


def endpoint_thresholds(endpoint_group: str | None) -> dict:
    endpoint = normalize_endpoint_group(endpoint_group) or "default"
    return dict(DEFAULT_ENDPOINT_THRESHOLDS.get(endpoint) or DEFAULT_ENDPOINT_THRESHOLDS["default"])


def assay_confidence_for_row(row: dict) -> dict:
    replicate_count = _int_or_none(_text(row, "replicate_count", "result_replicate_count", "replicates", "n"))
    replicate_cv = _replicate_cv(row)
    score = 45.0
    if _float_or_none(row.get("normalized_score")) is not None:
        score += 10.0
    if _text(row, "classification"):
        score += 5.0
    if _float_or_none(_text(row, "value", "result_value")) is not None:
        score += 5.0
    if replicate_count is not None:
        if replicate_count >= 2:
            score += 15.0
        if replicate_count >= 3:
            score += 8.0
        if replicate_count <= 1:
            score -= 10.0
    if replicate_cv is not None:
        if replicate_cv <= 0.20:
            score += 12.0
        elif replicate_cv <= 0.35:
            score += 6.0
        elif replicate_cv > 0.50:
            score -= 20.0
        elif replicate_cv > 0.35:
            score -= 8.0
    assay_type = normalize_assay_type(_text(row, "assay_type", "standard_type", "assay_name", "planned_assay"))
    if assay_type in {"IC50", "EC50", "KI", "KD", "POTENCY"}:
        score += 5.0
    score = round(max(20.0, min(95.0, score)), 2)
    bucket = "high" if score >= 75 else "medium" if score >= 55 else "low"
    return {
        "replicate_count": replicate_count,
        "replicate_cv": replicate_cv,
        "assay_confidence": bucket,
        "assay_confidence_score": score,
    }


def assay_result_decision(row: dict, *, endpoint_group: str | None = None) -> dict:
    endpoint = normalize_endpoint_group(
        endpoint_group or _text(row, "endpoint_group", "endpoint"),
        assay_type=_text(row, "assay_type"),
        assay_name=_text(row, "assay_name", "planned_assay"),
    ) or "default"
    thresholds = endpoint_thresholds(endpoint)
    confidence = assay_confidence_for_row(row)
    normalized_score = _float_or_none(row.get("normalized_score"))
    classification = _text(row, "classification").lower().replace(" ", "_")
    explicit_decision = _text(row, "stop_go_decision", "decision").lower().replace(" ", "_")
    decision = explicit_decision if explicit_decision in STOP_GO_DECISIONS else "watch"
    reasons: list[str] = []

    replicate_count = confidence["replicate_count"]
    replicate_cv = confidence["replicate_cv"]
    if replicate_count is not None and replicate_count < int(thresholds["min_replicates"]):
        reasons.append(f"replicate_count<{int(thresholds['min_replicates'])}")
    if replicate_cv is not None and replicate_cv > float(thresholds["max_replicate_cv"]):
        reasons.append(f"replicate_cv>{thresholds['max_replicate_cv']}")
    if confidence["assay_confidence_score"] < 50:
        reasons.append("low_assay_confidence")

    if explicit_decision not in STOP_GO_DECISIONS:
        if reasons:
            decision = "retest"
        elif normalized_score is not None:
            if normalized_score >= float(thresholds["go_score"]):
                decision = "go"
            elif normalized_score <= float(thresholds["stop_score"]):
                decision = "stop"
            else:
                decision = "watch"
        elif classification in POSITIVE_CLASSES:
            decision = "go"
        elif classification in NEGATIVE_CLASSES:
            decision = "stop"
        elif classification in WATCH_CLASSES:
            decision = "watch"

    if decision == "go" and normalized_score is not None:
        reasons.append(f"normalized_score>={thresholds['go_score']}")
    elif decision == "stop" and normalized_score is not None:
        reasons.append(f"normalized_score<={thresholds['stop_score']}")
    elif decision == "watch" and not reasons:
        reasons.append("between_stop_go_thresholds")
    elif decision == "retest" and not reasons:
        reasons.append("explicit_retest")

    return {
        "endpoint_group_standard": endpoint,
        "stop_go_decision": decision,
        "retest_reason": ";".join(reasons) if decision == "retest" else "",
        "decision_basis": ";".join(reasons),
        "endpoint_thresholds": thresholds,
        **confidence,
    }


def _endpoint_learning_item(report: dict, endpoint_group: str | None = None) -> dict | None:
    endpoints = list(report.get("endpoints") or [])
    endpoint = normalize_endpoint_group(endpoint_group) if endpoint_group else None
    if endpoint:
        return next((item for item in endpoints if item.get("endpoint_group") == endpoint), None)
    if len(endpoints) == 1:
        return endpoints[0]
    return None


def endpoint_gate_from_learning(report: dict | None, endpoint_group: str | None = None) -> dict:
    """Build an endpoint-specific candidate gate from learned assay thresholds."""
    report = report or {}
    endpoint = normalize_endpoint_group(endpoint_group) or "default"
    item = _endpoint_learning_item(report, endpoint_group)
    if item:
        endpoint = str(item.get("endpoint_group") or endpoint)
    defaults = endpoint_thresholds(endpoint)
    go_score = _float_or_none((item or {}).get("learned_go_score"))
    stop_score = _float_or_none((item or {}).get("learned_stop_score"))
    mean_confidence = _float_or_none((item or {}).get("mean_assay_confidence_score"))
    decision_counts = (item or {}).get("decision_counts") or {}
    try:
        retest_count = int(decision_counts.get("retest") or 0)
    except (TypeError, ValueError):
        retest_count = 0
    if not retest_count and item:
        retest_count = sum(
            1
            for event in report.get("retest_events") or []
            if event.get("endpoint_group") == endpoint
        )
    event_count = int((item or {}).get("event_count") or 0)
    return {
        "endpoint_group": endpoint,
        "go_score": round(float(go_score if go_score is not None else defaults["go_score"]), 4),
        "stop_score": round(float(stop_score if stop_score is not None else defaults["stop_score"]), 4),
        "min_evidence_score": 60.0 if event_count else 65.0,
        "min_risk_score": 55.0,
        "hard_min_evidence_score": 45.0,
        "low_confidence_threshold": 55.0,
        "mean_assay_confidence_score": mean_confidence,
        "retest_event_count": retest_count,
        "event_count": event_count,
        "learning_basis": (item or {}).get("learning_basis") or "default_thresholds_until_more_data",
        "gate_source": "assay_learning" if item else "default_endpoint_thresholds",
    }


def candidate_endpoint_gate(row: dict, gate: dict | None = None) -> dict:
    """Apply an assay-learning gate to a scored candidate row."""
    gate = gate or endpoint_gate_from_learning({})
    score = _float_or_none(row.get("score"))
    evidence_score = _float_or_none(row.get("evidence_consistency_score"))
    risk_score = _float_or_none(row.get("risk_score"))
    evidence = 100.0 if evidence_score is None else float(evidence_score)
    risk = 100.0 if risk_score is None else float(risk_score)
    flags = {flag for flag in str(row.get("evidence_conflict_flags") or "").split(";") if flag}
    severe_flags = {
        "target_family_activity_contradiction",
        "target_family_activity_cliff_high",
        "project_negative_public_positive",
        "activity_cliff_high",
    }
    reasons: list[str] = []
    decision = "watch"
    if score is None:
        decision = "review"
        reasons.append("missing_candidate_score")
    elif flags.intersection(severe_flags):
        decision = "hold"
        reasons.append("severe_evidence_conflict")
    elif evidence < float(gate.get("hard_min_evidence_score") or 45.0):
        decision = "hold"
        reasons.append("evidence_below_hard_minimum")
    elif score <= float(gate.get("stop_score") or 35.0):
        decision = "hold"
        reasons.append("score_below_endpoint_stop")
    elif (
        score >= float(gate.get("go_score") or 70.0)
        and evidence >= float(gate.get("min_evidence_score") or 60.0)
        and risk >= float(gate.get("min_risk_score") or 55.0)
    ):
        decision = "advance"
        reasons.append("score_above_endpoint_go")
    else:
        reasons.append("between_endpoint_gate_thresholds")
        if evidence < float(gate.get("min_evidence_score") or 60.0):
            reasons.append("evidence_below_gate")
        if risk < float(gate.get("min_risk_score") or 55.0):
            reasons.append("risk_below_gate")

    mean_confidence = _float_or_none(gate.get("mean_assay_confidence_score"))
    if decision == "advance" and mean_confidence is not None and mean_confidence < float(gate.get("low_confidence_threshold") or 55.0):
        decision = "watch"
        reasons.append("endpoint_learning_low_confidence")
    if decision == "advance" and int(gate.get("retest_event_count") or 0) > 0:
        decision = "watch"
        reasons.append("endpoint_retest_queue_open")

    return {
        "endpoint_gate_decision": decision,
        "endpoint_gate_reason": ";".join(dict.fromkeys(reasons)),
        "endpoint_gate_score": round(float(score), 4) if score is not None else None,
        "endpoint_gate_go_score": gate.get("go_score"),
        "endpoint_gate_stop_score": gate.get("stop_score"),
        "endpoint_gate_min_evidence_score": gate.get("min_evidence_score"),
        "endpoint_gate_min_risk_score": gate.get("min_risk_score"),
        "endpoint_gate_endpoint": gate.get("endpoint_group"),
        "endpoint_gate_basis": gate.get("learning_basis"),
        "endpoint_gate_source": gate.get("gate_source"),
        "endpoint_gate_retest_event_count": gate.get("retest_event_count"),
        "endpoint_gate_mean_assay_confidence_score": gate.get("mean_assay_confidence_score"),
    }


def annotate_endpoint_gates(
    rows: list[dict],
    learning_report: dict | None,
    *,
    endpoint_group: str | None = None,
) -> list[dict]:
    gate = endpoint_gate_from_learning(learning_report or {}, endpoint_group=endpoint_group)
    return [{**row, **candidate_endpoint_gate(row, gate)} for row in rows]


def _event_rows(db_path: str | Path, project_name: str | None = None) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where = ""
        params: tuple = ()
        if project_name:
            where = "WHERE p.project_name = ?"
            params = (project_name,)
        rows = conn.execute(
            f"""
            SELECT
                e.*, p.project_name AS plan_project_name, p.planned_assay AS plan_assay_name
            FROM project_experiment_event e
            LEFT JOIN project_experiment_plan p ON p.plan_id=e.plan_id
            {where}
            ORDER BY e.recorded_at DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def build_assay_learning_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> dict:
    events = _event_rows(db_path, project_name=project_name)
    grouped: dict[str, list[dict]] = defaultdict(list)
    normalized_events = []
    for event in events:
        try:
            payload = json.loads(event.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        row = {**payload, **event}
        endpoint = normalize_endpoint_group(
            event.get("endpoint_group") or payload.get("endpoint_group") or payload.get("endpoint"),
            assay_type=event.get("assay_type") or payload.get("assay_type"),
            assay_name=event.get("assay_name") or payload.get("assay_name") or event.get("plan_assay_name"),
        ) or "default"
        decision = assay_result_decision(row, endpoint_group=endpoint)
        if event.get("stop_go_decision"):
            decision["stop_go_decision"] = event.get("stop_go_decision")
        item = {
            **event,
            **decision,
            "endpoint_group_standard": endpoint,
            "normalized_score": _float_or_none(event.get("normalized_score")),
        }
        grouped[endpoint].append(item)
        normalized_events.append(item)

    endpoints = []
    for endpoint, items in sorted(grouped.items()):
        scores = [item["normalized_score"] for item in items if item.get("normalized_score") is not None]
        confidence_scores = [
            _float_or_none(item.get("assay_confidence_score"))
            for item in items
            if _float_or_none(item.get("assay_confidence_score")) is not None
        ]
        decision_counts = Counter(item.get("stop_go_decision") or "watch" for item in items)
        go_scores = [item["normalized_score"] for item in items if item.get("stop_go_decision") == "go" and item.get("normalized_score") is not None]
        stop_scores = [item["normalized_score"] for item in items if item.get("stop_go_decision") == "stop" and item.get("normalized_score") is not None]
        thresholds = endpoint_thresholds(endpoint)
        learned_go = min(go_scores) if len(go_scores) >= 3 else thresholds["go_score"]
        learned_stop = max(stop_scores) if len(stop_scores) >= 3 else thresholds["stop_score"]
        next_actions = []
        if decision_counts.get("retest", 0):
            next_actions.append("Resolve retest rows before using this endpoint for calibration.")
        if len(scores) < 3:
            next_actions.append("Collect at least three completed observations for stable endpoint learning.")
        if confidence_scores and mean(confidence_scores) < 65:
            next_actions.append("Increase replicate depth or tighten assay variance before changing score weights.")
        endpoints.append(
            {
                "endpoint_group": endpoint,
                "event_count": len(items),
                "completed_count": sum(1 for item in items if item.get("status") == "completed"),
                "decision_counts": dict(decision_counts.most_common()),
                "mean_normalized_score": round(mean(scores), 4) if scores else None,
                "mean_assay_confidence_score": round(mean(confidence_scores), 4) if confidence_scores else None,
                "default_go_score": thresholds["go_score"],
                "default_stop_score": thresholds["stop_score"],
                "learned_go_score": round(float(learned_go), 4),
                "learned_stop_score": round(float(learned_stop), 4),
                "learning_basis": "observed_thresholds" if len(go_scores) >= 3 or len(stop_scores) >= 3 else "default_thresholds_until_more_data",
                "next_actions": next_actions,
            }
        )

    return {
        "project_name": project_name,
        "event_count": len(normalized_events),
        "endpoint_count": len(endpoints),
        "decision_counts": dict(Counter(item.get("stop_go_decision") or "watch" for item in normalized_events).most_common()),
        "endpoints": endpoints,
        "retest_events": [
            {
                "event_id": item.get("event_id"),
                "plan_id": item.get("plan_id"),
                "candidate_id": item.get("candidate_id"),
                "endpoint_group": item.get("endpoint_group_standard"),
                "retest_reason": item.get("retest_reason"),
                "assay_confidence_score": item.get("assay_confidence_score"),
            }
            for item in normalized_events
            if item.get("stop_go_decision") == "retest"
        ][:25],
    }
