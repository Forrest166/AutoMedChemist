from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from .database import initialize_database


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")


def _float_or_none(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _recommendation_map(report: dict | None) -> dict[tuple[str, str], dict]:
    mapped = {}
    for row in (report or {}).get("recommended_next_experiments") or []:
        key = (str(row.get("run_id") or ""), str(row.get("candidate_id") or ""))
        if key[0] and key[1]:
            mapped[key] = row
    return mapped


def _candidate_feedback_rows(conn: sqlite3.Connection, project_name: str | None) -> list[dict]:
    conn.row_factory = sqlite3.Row
    params: tuple = ()
    where = ""
    if project_name:
        where = "WHERE pr.project_name=?"
        params = (project_name,)
    rows = conn.execute(
        f"""
        SELECT
            pr.project_name,
            pr.run_id,
            pc.candidate_id,
            pc.rank,
            pc.score AS stored_score,
            pc.payload_json,
            pf.feedback_id,
            pf.normalized_score,
            pf.endpoint,
            pf.assay_name,
            pf.assay_type,
            pf.value,
            pf.unit,
            pf.relation,
            pf.classification,
            pf.source_path,
            pf.note,
            pf.recorded_at
        FROM project_candidate pc
        JOIN project_run pr ON pr.run_id = pc.run_id
        LEFT JOIN project_feedback pf
            ON pf.run_id = pc.run_id AND pf.candidate_id = pc.candidate_id
        {where}
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_calibration_deltas(conn: sqlite3.Connection, project_name: str | None) -> list[dict]:
    conn.row_factory = sqlite3.Row
    params: tuple = ()
    where = ""
    if project_name:
        where = "WHERE project_name=?"
        params = (project_name,)
    rows = conn.execute(
        f"""
        SELECT calibration_id, project_name, endpoint_group, score_weights_json,
               property_windows_json, metrics_json, created_at
        FROM project_model_calibration
        {where}
        ORDER BY endpoint_group ASC, created_at ASC
        """,
        params,
    ).fetchall()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        for field in ["score_weights_json", "property_windows_json", "metrics_json"]:
            try:
                item[field.replace("_json", "")] = json.loads(item.get(field) or "{}")
            except Exception:
                item[field.replace("_json", "")] = {}
        grouped[str(item.get("endpoint_group") or "unspecified")].append(item)

    deltas = []
    for endpoint, items in grouped.items():
        if len(items) < 2:
            continue
        previous, current = items[-2], items[-1]
        prev_weights = previous.get("score_weights") or {}
        cur_weights = current.get("score_weights") or {}
        weight_changes = []
        for component in sorted(set(prev_weights).union(cur_weights)):
            before = _float_or_none(prev_weights.get(component)) or 0.0
            after = _float_or_none(cur_weights.get(component)) or 0.0
            delta = round(after - before, 4)
            if delta:
                weight_changes.append({"component": component, "before": before, "after": after, "delta": delta})
        deltas.append(
            {
                "endpoint_group": endpoint,
                "previous_calibration_id": previous.get("calibration_id"),
                "current_calibration_id": current.get("calibration_id"),
                "previous_created_at": previous.get("created_at"),
                "current_created_at": current.get("created_at"),
                "weight_changes": weight_changes,
                "property_windows_before": previous.get("property_windows") or {},
                "property_windows_after": current.get("property_windows") or {},
            }
        )
    return deltas


def _endpoint_control_deltas(before_control: dict | None, after_control: dict | None) -> list[dict]:
    before_map = {
        str(item.get("endpoint_group") or "unspecified"): item
        for item in (before_control or {}).get("endpoint_controls") or []
    }
    after_map = {
        str(item.get("endpoint_group") or "unspecified"): item
        for item in (after_control or {}).get("endpoint_controls") or []
    }
    rows = []
    for endpoint in sorted(set(before_map).union(after_map)):
        before = before_map.get(endpoint) or {}
        after = after_map.get(endpoint) or {}
        before_score = _float_or_none(before.get("mean_normalized_score"))
        after_score = _float_or_none(after.get("mean_normalized_score"))
        score_delta = round(after_score - before_score, 4) if before_score is not None and after_score is not None else None
        before_feedback = int(before.get("feedback_count") or 0)
        after_feedback = int(after.get("feedback_count") or 0)
        rows.append(
            {
                "endpoint_group": endpoint,
                "status_before": before.get("status"),
                "status_after": after.get("status"),
                "uncertainty_before": before.get("uncertainty_level"),
                "uncertainty_after": after.get("uncertainty_level"),
                "feedback_count_before": before_feedback,
                "feedback_count_after": after_feedback,
                "feedback_count_delta": after_feedback - before_feedback,
                "mean_normalized_score_before": before_score,
                "mean_normalized_score_after": after_score,
                "mean_normalized_score_delta": score_delta,
            }
        )
    return rows


def _feedback_digest(rows: list[dict], *, max_rows: int = 8) -> list[dict]:
    compact = []
    feedback_rows = [
        row
        for row in rows
        if row.get("feedback_id") or row.get("endpoint") or row.get("normalized_score") is not None
    ]
    for row in sorted(feedback_rows, key=lambda item: str(item.get("recorded_at") or ""), reverse=True)[:max_rows]:
        compact.append(
            {
                "feedback_id": row.get("feedback_id"),
                "endpoint": row.get("endpoint"),
                "assay_name": row.get("assay_name"),
                "assay_type": row.get("assay_type"),
                "value": row.get("value"),
                "unit": row.get("unit"),
                "relation": row.get("relation"),
                "normalized_score": row.get("normalized_score"),
                "classification": row.get("classification"),
                "source_path": row.get("source_path"),
                "note": row.get("note"),
                "recorded_at": row.get("recorded_at"),
            }
        )
    return compact


def _change_explanations(
    *,
    status: str,
    delta: float | None,
    before_reasons,
    after_reasons,
    feedback_rows: list[dict],
    endpoint_deltas: list[dict],
    calibration_deltas: list[dict],
) -> list[str]:
    explanations = []
    if delta is not None and abs(delta) >= 2:
        explanations.append(f"priority_score changed by {delta:+.2f}.")
    if before_reasons != after_reasons:
        explanations.append(f"priority reasons changed from {before_reasons or 'none'} to {after_reasons or 'none'}.")
    if feedback_rows:
        ids = [str(row.get("feedback_id") or row.get("recorded_at") or "") for row in feedback_rows if row.get("feedback_id") or row.get("recorded_at")]
        explanations.append(f"{len(feedback_rows)} linked feedback row(s) contributed context: {', '.join(ids[:4])}.")
    for row in endpoint_deltas:
        if row.get("feedback_count_delta") or row.get("status_before") != row.get("status_after"):
            explanations.append(
                "endpoint {endpoint} shifted {before}->{after} with feedback delta {delta}.".format(
                    endpoint=row.get("endpoint_group"),
                    before=row.get("status_before") or "missing",
                    after=row.get("status_after") or "missing",
                    delta=row.get("feedback_count_delta"),
                )
            )
    for row in calibration_deltas:
        changes = row.get("weight_changes") or []
        if changes:
            top = changes[0]
            explanations.append(
                "calibration {endpoint} changed weight {component} by {delta:+.2f}.".format(
                    endpoint=row.get("endpoint_group"),
                    component=top.get("component"),
                    delta=top.get("delta") or 0.0,
                )
            )
    if not explanations:
        explanations.append(f"status remained {status}; no linked feedback or calibration movement exceeded report thresholds.")
    return explanations[:6]


def build_priority_delta_report(
    before_control: dict | None,
    after_control: dict,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    max_rows: int = 100,
) -> dict:
    """Compare active-learning priority before/after a closed-loop update."""
    before = _recommendation_map(before_control)
    after = _recommendation_map(after_control)
    keys = sorted(set(before).union(after))

    conn = initialize_database(db_path)
    try:
        feedback_rows = _candidate_feedback_rows(conn, project_name)
        calibration_deltas = _latest_calibration_deltas(conn, project_name)
    finally:
        conn.close()

    by_candidate: dict[tuple[str, str], list[dict]] = defaultdict(list)
    payloads = {}
    for row in feedback_rows:
        key = (str(row.get("run_id") or ""), str(row.get("candidate_id") or ""))
        by_candidate[key].append(row)
        if key not in payloads:
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except Exception:
                payload = {}
            payloads[key] = payload

    rows = []
    for key in keys:
        prior = before.get(key) or {}
        current = after.get(key) or {}
        before_score = _float_or_none(prior.get("priority_score"))
        after_score = _float_or_none(current.get("priority_score"))
        delta = None
        if before_score is not None and after_score is not None:
            delta = round(after_score - before_score, 4)
        elif before_score is None and after_score is not None:
            delta = after_score
        elif before_score is not None and after_score is None:
            delta = -before_score

        feedback_scores = [
            _float_or_none(item.get("normalized_score"))
            for item in by_candidate.get(key, [])
            if _float_or_none(item.get("normalized_score")) is not None
        ]
        payload = payloads.get(key) or {}
        candidate_score = _float_or_none(payload.get("score")) or _float_or_none(current.get("candidate_score")) or _float_or_none(prior.get("candidate_score"))
        observed_mean = round(mean(feedback_scores), 4) if feedback_scores else None
        observed_delta = round(observed_mean - candidate_score, 4) if observed_mean is not None and candidate_score is not None else None
        compact_feedback = _feedback_digest(by_candidate.get(key, []))
        endpoint_names = {str(item.get("endpoint") or "") for item in compact_feedback if item.get("endpoint")}
        endpoint_deltas = [
            item
            for item in _endpoint_control_deltas(before_control, after_control)
            if not endpoint_names or str(item.get("endpoint_group") or "") in endpoint_names
        ]
        row_calibration_deltas = [
            item
            for item in calibration_deltas
            if not endpoint_names or str(item.get("endpoint_group") or "") in endpoint_names
        ]

        if before_score is None and after_score is not None:
            status = "new_priority"
        elif before_score is not None and after_score is None:
            status = "resolved_or_removed"
        elif delta is not None and delta >= 2:
            status = "priority_up"
        elif delta is not None and delta <= -2:
            status = "priority_down"
        else:
            status = "unchanged"

        rows.append(
            {
                "run_id": key[0],
                "candidate_id": key[1],
                "project_name": project_name,
                "status": status,
                "priority_score_before": before_score,
                "priority_score_after": after_score,
                "priority_score_delta": delta,
                "candidate_score": candidate_score,
                "observed_feedback_mean": observed_mean,
                "observed_vs_candidate_delta": observed_delta,
                "feedback_count": len(feedback_scores),
                "feedback_rows": compact_feedback,
                "endpoint_control_deltas": endpoint_deltas,
                "calibration_weight_deltas": row_calibration_deltas,
                "change_explanations": _change_explanations(
                    status=status,
                    delta=delta,
                    before_reasons=prior.get("reasons"),
                    after_reasons=current.get("reasons"),
                    feedback_rows=compact_feedback,
                    endpoint_deltas=endpoint_deltas,
                    calibration_deltas=row_calibration_deltas,
                ),
                "before_reasons": prior.get("reasons"),
                "after_reasons": current.get("reasons"),
                "replacement_label": current.get("replacement_label") or prior.get("replacement_label") or payload.get("replacement_label"),
                "enumeration_type": current.get("enumeration_type") or prior.get("enumeration_type") or payload.get("enumeration_type"),
                "smiles": current.get("smiles") or prior.get("smiles") or payload.get("smiles"),
            }
        )

    rows.sort(key=lambda row: abs(float(row.get("priority_score_delta") or 0.0)), reverse=True)
    limited = rows[:max_rows]
    counts = Counter(row["status"] for row in rows)
    return {
        "project_name": project_name,
        "candidate_count": len(rows),
        "status_counts": dict(counts.most_common()),
        "feedback_linked_count": sum(1 for row in rows if row.get("feedback_count")),
        "endpoint_control_delta_summary": _endpoint_control_deltas(before_control, after_control),
        "calibration_delta_summary": calibration_deltas,
        "priority_delta_rows": limited,
    }
