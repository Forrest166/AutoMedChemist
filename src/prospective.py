from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
import csv

from .database import initialize_database, insert_project_feedback_control
from .feedback import _candidate_payload, _float_or_none, _rows_for_project, endpoint_group_from_text


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")


def _payload(row: dict) -> dict:
    try:
        return _candidate_payload(row) or {}
    except Exception:
        return {}


def _candidate_key(row: dict) -> tuple[str, str]:
    return str(row.get("run_id")), str(row.get("candidate_id"))


def _feedback_observations(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        if not row.get("feedback_id"):
            continue
        score = _float_or_none(row.get("normalized_score"))
        if score is None:
            continue
        endpoint = endpoint_group_from_text(row.get("endpoint"), row.get("assay_type"), row.get("assay_name"))
        key = (endpoint, *_candidate_key(row))
        item = grouped.setdefault(
            key,
            {
                "endpoint_group": endpoint,
                "run_id": row.get("run_id"),
                "candidate_id": row.get("candidate_id"),
                "direction": row.get("direction"),
                "site_type": row.get("site_type"),
                "payload": _payload(row),
                "scores": [],
            },
        )
        item["scores"].append(score)
    observations = []
    for item in grouped.values():
        observations.append({**item, "normalized_score": round(mean(item["scores"]), 4), "feedback_count": len(item["scores"])})
    return observations


def _candidate_population(rows: list[dict]) -> list[dict]:
    seen = set()
    candidates = []
    for row in rows:
        key = _candidate_key(row)
        if key in seen or not row.get("candidate_id"):
            continue
        seen.add(key)
        candidates.append(
            {
                "run_id": row.get("run_id"),
                "candidate_id": row.get("candidate_id"),
                "direction": row.get("direction"),
                "site_type": row.get("site_type"),
                "project_name": row.get("project_name"),
                "payload": _payload(row),
            }
        )
    return candidates


def _endpoint_controls(observations: list[dict], min_feedback: int) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for obs in observations:
        grouped[obs["endpoint_group"]].append(obs)
    controls = []
    for endpoint, items in sorted(grouped.items()):
        sites = Counter(str(item.get("site_type") or "unspecified") for item in items)
        directions = Counter(str(item.get("direction") or "unspecified") for item in items)
        scores = [float(item["normalized_score"]) for item in items]
        controls.append(
            {
                "endpoint_group": endpoint,
                "candidate_count": len(items),
                "feedback_count": sum(int(item.get("feedback_count") or 0) for item in items),
                "status": "controlled" if len(items) >= min_feedback else "under_sampled",
                "uncertainty_level": "low" if len(items) >= min_feedback * 2 else "medium" if len(items) >= min_feedback else "high",
                "mean_normalized_score": round(mean(scores), 4) if scores else None,
                "site_type_counts": dict(sites.most_common()),
                "direction_counts": dict(directions.most_common()),
            }
        )
    return controls


def _uncertainty_flags(candidates: list[dict], observations: list[dict], min_feedback: int) -> list[dict]:
    observed_keys = {(obs["endpoint_group"], obs["run_id"], obs["candidate_id"]) for obs in observations}
    endpoint_counts = Counter(obs["endpoint_group"] for obs in observations)
    site_counts = Counter(str(obs.get("site_type") or "unspecified") for obs in observations)
    direction_counts = Counter(str(obs.get("direction") or "unspecified") for obs in observations)
    scaffold_counts = Counter(str((obs.get("payload") or {}).get("enumeration_type") or "unspecified") for obs in observations)
    flags = []
    endpoints = set(endpoint_counts) or {"potency"}
    for endpoint in sorted(endpoints):
        if endpoint_counts[endpoint] < min_feedback:
            flags.append(
                {
                    "flag_type": "endpoint_under_sampled",
                    "endpoint_group": endpoint,
                    "observed_count": endpoint_counts[endpoint],
                    "threshold": min_feedback,
                    "priority": "high",
                }
            )
    for candidate in candidates:
        payload = candidate.get("payload") or {}
        site_type = str(candidate.get("site_type") or "unspecified")
        direction = str(candidate.get("direction") or "unspecified")
        scaffold = str(payload.get("enumeration_type") or "unspecified")
        if site_counts[site_type] < min_feedback:
            flags.append({"flag_type": "site_under_sampled", "site_type": site_type, "observed_count": site_counts[site_type], "candidate_id": candidate["candidate_id"], "priority": "medium"})
        if direction_counts[direction] < min_feedback:
            flags.append({"flag_type": "direction_under_sampled", "direction": direction, "observed_count": direction_counts[direction], "candidate_id": candidate["candidate_id"], "priority": "medium"})
        if scaffold_counts[scaffold] < min_feedback:
            flags.append({"flag_type": "scaffold_under_sampled", "scaffold_bucket": scaffold, "observed_count": scaffold_counts[scaffold], "candidate_id": candidate["candidate_id"], "priority": "medium"})
        if not any((endpoint, candidate["run_id"], candidate["candidate_id"]) in observed_keys for endpoint in endpoints):
            flags.append({"flag_type": "candidate_unmeasured", "candidate_id": candidate["candidate_id"], "run_id": candidate["run_id"], "priority": "low"})
    unique = {}
    for flag in flags:
        key = json.dumps(flag, sort_keys=True)
        unique.setdefault(key, flag)
    return list(unique.values())[:500]


def _calibration_payloads(db_path: str | Path, project_name: str | None) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = None
    try:
        if project_name:
            rows = conn.execute(
                """
                SELECT calibration_id, endpoint_group, payload_json, created_at
                FROM project_model_calibration
                WHERE project_name=?
                ORDER BY endpoint_group ASC, created_at ASC
                """,
                (project_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT calibration_id, endpoint_group, payload_json, created_at
                FROM project_model_calibration
                ORDER BY endpoint_group ASC, created_at ASC
                """
            ).fetchall()
    finally:
        conn.close()
    payloads = []
    for calibration_id, endpoint, payload_json, created_at in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            payload = {}
        payloads.append({"calibration_id": calibration_id, "endpoint_group": endpoint, "created_at": created_at, "payload": payload})
    return payloads


def _drift_flags(calibrations: list[dict], threshold: float = 0.12) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in calibrations:
        grouped[str(item.get("endpoint_group") or "unspecified")].append(item)
    flags = []
    for endpoint, items in grouped.items():
        if len(items) < 2:
            continue
        previous, current = items[-2], items[-1]
        prev_weights = (previous.get("payload") or {}).get("score_weights") or {}
        cur_weights = (current.get("payload") or {}).get("score_weights") or {}
        for key in sorted(set(prev_weights).union(cur_weights)):
            delta = float(cur_weights.get(key) or 0) - float(prev_weights.get(key) or 0)
            if abs(delta) >= threshold:
                flags.append(
                    {
                        "flag_type": "calibration_weight_drift",
                        "endpoint_group": endpoint,
                        "component": key,
                        "previous_calibration_id": previous.get("calibration_id"),
                        "current_calibration_id": current.get("calibration_id"),
                        "delta": round(delta, 4),
                        "priority": "high" if abs(delta) >= threshold * 1.5 else "medium",
                    }
                )
    return flags


def _recommended_next_experiments(candidates: list[dict], flags: list[dict], limit: int) -> list[dict]:
    by_candidate: dict[tuple[str, str], dict] = {}
    for candidate in candidates:
        by_candidate[(str(candidate["run_id"]), str(candidate["candidate_id"]))] = candidate
    flag_counts: Counter[tuple[str, str]] = Counter()
    reasons: dict[tuple[str, str], list[str]] = defaultdict(list)
    for flag in flags:
        candidate_id = flag.get("candidate_id")
        run_id = flag.get("run_id")
        if not candidate_id:
            continue
        matches = [key for key in by_candidate if key[1] == str(candidate_id) and (run_id is None or key[0] == str(run_id))]
        for key in matches:
            weight = {"high": 4, "medium": 2, "low": 1}.get(str(flag.get("priority") or "low"), 1)
            flag_counts[key] += weight
            reasons[key].append(flag["flag_type"])
    ranked = []
    for key, score in flag_counts.most_common(limit):
        candidate = by_candidate.get(key) or {}
        payload = candidate.get("payload") or {}
        ranked.append(
            {
                "run_id": key[0],
                "candidate_id": key[1],
                "priority_score": int(score),
                "site_type": candidate.get("site_type"),
                "direction": candidate.get("direction"),
                "enumeration_type": payload.get("enumeration_type"),
                "candidate_score": payload.get("score"),
                "replacement_label": payload.get("replacement_label"),
                "smiles": payload.get("smiles"),
                "reasons": ";".join(dict.fromkeys(reasons[key])),
            }
        )
    return ranked


def build_experiment_plan(
    report: dict,
    *,
    batch_size: int = 24,
    endpoint_groups: list[str] | tuple[str, ...] | None = None,
    include_endpoint_controls: bool = True,
) -> list[dict]:
    endpoint_filter = {str(endpoint) for endpoint in endpoint_groups or [] if endpoint}
    plan: list[dict] = []
    created_at = datetime.now(timezone.utc).isoformat()
    plan_batch_id = f"EPL-{uuid.uuid4().hex[:10].upper()}"
    flags_by_candidate: dict[str, list[dict]] = defaultdict(list)
    for flag in report.get("uncertainty_flags") or []:
        candidate_id = flag.get("candidate_id")
        if candidate_id:
            flags_by_candidate[str(candidate_id)].append(flag)

    for rec in report.get("recommended_next_experiments") or []:
        candidate_id = str(rec.get("candidate_id") or "")
        flags = flags_by_candidate.get(candidate_id, [])
        candidate_endpoints = {
            str(flag.get("endpoint_group"))
            for flag in flags
            if flag.get("endpoint_group")
        }
        if endpoint_filter and candidate_endpoints and not endpoint_filter.intersection(candidate_endpoints):
            continue
        endpoint_group = next(iter(sorted(candidate_endpoints)), None)
        plan.append(
            {
                "plan_id": f"{plan_batch_id}-{len(plan) + 1:03d}",
                "plan_rank": len(plan) + 1,
                "plan_role": "candidate_assay",
                "project_name": report.get("project_name"),
                "run_id": rec.get("run_id"),
                "candidate_id": rec.get("candidate_id"),
                "endpoint_group": endpoint_group or "project_panel",
                "site_type": rec.get("site_type"),
                "direction": rec.get("direction"),
                "enumeration_type": rec.get("enumeration_type"),
                "replacement_label": rec.get("replacement_label"),
                "candidate_score": rec.get("candidate_score"),
                "priority_score": rec.get("priority_score"),
                "rationale": rec.get("reason") or rec.get("reasons"),
                "created_at": created_at,
                "owner": "",
                "planned_assay": "",
                "status": "planned",
                "notes": "",
                "result_value": "",
                "result_unit": "",
                "result_relation": "",
                "classification": "",
                "normalized_score": "",
                "result_recorded_at": "",
            }
        )
        if len(plan) >= batch_size:
            return plan

    if include_endpoint_controls:
        seen_controls = set()
        for flag in report.get("uncertainty_flags") or []:
            if flag.get("flag_type") != "endpoint_under_sampled":
                continue
            endpoint = str(flag.get("endpoint_group") or "unspecified")
            if endpoint_filter and endpoint not in endpoint_filter:
                continue
            if endpoint in seen_controls:
                continue
            seen_controls.add(endpoint)
            plan.append(
                {
                    "plan_id": f"{plan_batch_id}-{len(plan) + 1:03d}",
                    "plan_rank": len(plan) + 1,
                    "plan_role": "endpoint_control",
                    "project_name": report.get("project_name"),
                    "run_id": "",
                    "candidate_id": "",
                    "endpoint_group": endpoint,
                    "site_type": "",
                    "direction": "",
                    "enumeration_type": "",
                    "replacement_label": "",
                    "candidate_score": "",
                    "priority_score": flag.get("threshold", 0) - flag.get("observed_count", 0),
                    "rationale": f"Endpoint has {flag.get('observed_count', 0)} observations; target minimum is {flag.get('threshold')}.",
                    "created_at": created_at,
                    "owner": "",
                    "planned_assay": "",
                    "status": "planned",
                    "notes": "",
                    "result_value": "",
                    "result_unit": "",
                    "result_relation": "",
                    "classification": "",
                    "normalized_score": "",
                    "result_recorded_at": "",
                }
            )
            if len(plan) >= batch_size:
                break
    return plan


def write_experiment_plan_csv(rows: list[dict], output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "plan_id",
        "plan_rank",
        "plan_role",
        "project_name",
        "run_id",
        "candidate_id",
        "endpoint_group",
        "site_type",
        "direction",
        "enumeration_type",
        "replacement_label",
        "candidate_score",
        "priority_score",
        "rationale",
        "created_at",
        "owner",
        "planned_assay",
        "status",
        "notes",
        "result_value",
        "result_unit",
        "result_relation",
        "classification",
        "normalized_score",
        "result_recorded_at",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def build_feedback_control_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    min_feedback: int = 3,
    next_experiment_limit: int = 30,
) -> dict:
    conn = initialize_database(db_path)
    try:
        rows = _rows_for_project(conn, project_name=project_name)
    finally:
        conn.close()
    observations = _feedback_observations(rows)
    candidates = _candidate_population(rows)
    endpoint_controls = _endpoint_controls(observations, min_feedback)
    uncertainty_flags = _uncertainty_flags(candidates, observations, min_feedback)
    drift_flags = _drift_flags(_calibration_payloads(db_path, project_name))
    recommendations = _recommended_next_experiments(candidates, [*uncertainty_flags, *drift_flags], next_experiment_limit)
    created_at = datetime.now(timezone.utc).isoformat()
    return {
        "control_id": f"PFC-{uuid.uuid4().hex[:12].upper()}",
        "created_at": created_at,
        "project_name": project_name,
        "min_feedback": min_feedback,
        "candidate_count": len(candidates),
        "feedback_observation_count": len(observations),
        "endpoint_controls": endpoint_controls,
        "uncertainty_flags": uncertainty_flags,
        "drift_flags": drift_flags,
        "recommended_next_experiments": recommendations,
    }


def save_feedback_control_report(
    report: dict,
    *,
    output_path: str | Path,
    db_path: str | Path | None = None,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if db_path is not None:
        conn = initialize_database(db_path)
        try:
            insert_project_feedback_control(conn, report)
        finally:
            conn.close()
