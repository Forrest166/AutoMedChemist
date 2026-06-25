from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MEASUREMENT_FEEDBACK_PLAN_PATH = Path("data/projects/demo/measurement_feedback_plan.json")
DEFAULT_MEASUREMENT_FEEDBACK_PLAN_CSV_PATH = Path("data/projects/demo/measurement_feedback_plan.csv")
DEFAULT_MEASUREMENT_FEEDBACK_TEMPLATE_PATH = Path("data/projects/demo/measurement_feedback_results_template.csv")
DEFAULT_MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH = Path("data/projects/demo/measurement_feedback_result_import_report.json")
DEFAULT_MEASUREMENT_FEEDBACK_IMPORT_CSV_PATH = Path("data/projects/demo/measurement_feedback_result_import_report.csv")
DEFAULT_MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH = Path("data/projects/demo/measurement_feedback_gap_closure.json")
DEFAULT_MEASUREMENT_FEEDBACK_GAP_CLOSURE_CSV_PATH = Path("data/projects/demo/measurement_feedback_gap_closure.csv")
DEFAULT_MEASUREMENT_GAP_EXACT_TEMPLATE_PATH = Path("data/projects/demo/measurement_gap_exact_results_template.csv")
DEFAULT_MEASUREMENT_GAP_EXACT_INTAKE_PATH = Path("data/projects/demo/measurement_gap_exact_result_intake.json")
DEFAULT_MEASUREMENT_GAP_EXACT_INTAKE_CSV_PATH = Path("data/projects/demo/measurement_gap_exact_result_intake.csv")

MEASUREMENT_GAP_DECISIONS = {"exact_measurement_required", "endpoint_remap_approved", "deferred"}
DECISIONED_GAP_STATUSES = {"exact_measurement_required", "manual_endpoint_remap_approved", "deferred"}


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _plan_id(*parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"MFB-{digest}"


def _value_lookup(report: dict) -> dict[str, dict]:
    lookup = {}
    for row in report.get("rows") or []:
        for field in ["queue_id", "candidate_id", "smiles"]:
            value = str(row.get(field) or "")
            if value:
                lookup[f"{field}:{value}"] = dict(row)
    return lookup


def _linked_value(row: dict, lookup: dict[str, dict]) -> dict:
    for field in ["queue_id", "candidate_id", "smiles", "candidate_key"]:
        value = str(row.get(field) or "")
        if not value:
            continue
        key = "smiles:" + value if field == "candidate_key" else f"{field}:{value}"
        if key in lookup:
            return lookup[key]
    return {}


def read_measurement_feedback_result_rows_csv(path: str | Path) -> list[dict]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_experiment_result_rows_csv(path: str | Path) -> list[dict]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _plan_lookup(plan: dict) -> dict[str, dict]:
    return {str(row.get("measurement_plan_id") or ""): dict(row) for row in plan.get("rows") or [] if row.get("measurement_plan_id")}


def _evidence_lookup(report: dict) -> dict[str, dict]:
    lookup = {}
    for row in report.get("rows") or []:
        for field in ["queue_id", "candidate_id", "smiles"]:
            value = str(row.get(field) or "")
            if value:
                lookup[f"{field}:{value}"] = dict(row)
    return lookup


def _linked_evidence(plan_row: dict, evidence: dict[str, dict]) -> dict:
    for field in ["queue_id", "candidate_id", "smiles"]:
        value = str(plan_row.get(field) or "")
        if value and f"{field}:{value}" in evidence:
            return evidence[f"{field}:{value}"]
    return {}


def _has_real_measurement(row: dict) -> bool:
    return bool(str(row.get("observed_value") or "").strip() or str(row.get("observed_unit") or "").strip())


def _normalize_score(value: object) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, score)), 4)


def _normalized_observed_score(row: dict) -> float | None:
    explicit = _normalize_score(row.get("normalized_observed_score"))
    if explicit is not None:
        return explicit
    unit = str(row.get("observed_unit") or "").strip().lower()
    if unit in {"score", "evidence_score", "normalized_score", "0-100", "percent", "%"} or "score" in unit:
        return _normalize_score(row.get("observed_value"))
    return None


def validate_measurement_feedback_result_rows(rows: list[dict], plan: dict) -> dict:
    plan_by_id = _plan_lookup(plan)
    importable = []
    rejected = []
    skipped = []
    issues = []
    for index, raw in enumerate(rows, start=1):
        row = dict(raw)
        if not _has_real_measurement(row):
            skipped.append(index)
            continue
        plan_id = str(row.get("measurement_plan_id") or "").strip()
        if not plan_id:
            rejected.append(row)
            issues.append({"row_index": index, "severity": "error", "field": "measurement_plan_id", "issue": "missing_plan_id"})
            continue
        plan_row = plan_by_id.get(plan_id)
        if not plan_row:
            rejected.append(row)
            issues.append({"row_index": index, "severity": "error", "field": "measurement_plan_id", "issue": "unknown_plan_id", "value": plan_id})
            continue
        observed_value = str(row.get("observed_value") or "").strip()
        if observed_value == "":
            rejected.append(row)
            issues.append({"row_index": index, "severity": "error", "field": "observed_value", "issue": "missing_observed_value"})
            continue
        try:
            float(observed_value)
        except ValueError:
            rejected.append(row)
            issues.append({"row_index": index, "severity": "error", "field": "observed_value", "issue": "non_numeric_observed_value", "value": observed_value})
            continue
        if not str(row.get("observed_unit") or "").strip():
            rejected.append(row)
            issues.append({"row_index": index, "severity": "error", "field": "observed_unit", "issue": "missing_observed_unit"})
            continue
        assay_confidence = str(row.get("assay_confidence") or "").strip()
        if assay_confidence:
            confidence = _float(assay_confidence, -1)
            if confidence < 0 or confidence > 100:
                rejected.append(row)
                issues.append({"row_index": index, "severity": "error", "field": "assay_confidence", "issue": "confidence_out_of_range", "value": assay_confidence})
                continue
        if _normalized_observed_score(row) is None:
            issues.append(
                {
                    "row_index": index,
                    "severity": "warn",
                    "field": "normalized_observed_score",
                    "issue": "missing_normalized_score_for_calibration",
                    "measurement_plan_id": plan_id,
                }
            )
        importable.append({"row_index": index, "row": row, "plan_row": plan_row})
    status = "valid" if importable and not rejected else "valid_with_warnings" if importable else "needs_real_measurement_feedback" if skipped and not rejected else "invalid"
    return {
        "status": status,
        "input_row_count": len(rows),
        "importable_row_count": len(importable),
        "rejected_row_count": len(rejected),
        "skipped_blank_row_count": len(skipped),
        "calibration_ready_row_count": sum(1 for item in importable if _normalized_observed_score(item["row"]) is not None),
        "importable_rows": importable,
        "rejected_rows": rejected,
        "issues": issues,
    }


def measurement_feedback_rows_from_experiment_results(
    experiment_rows: list[dict],
    plan: dict,
    *,
    reviewer: str = "historical_experiment_import",
) -> dict:
    result_lookup: dict[tuple[str, str], dict] = {}
    for row in experiment_rows:
        if str(row.get("status") or "").strip().lower() not in {"completed", "imported", "measured", "accepted"}:
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        endpoint_group = str(row.get("endpoint_group") or "").strip()
        normalized = str(row.get("normalized_score") or row.get("normalized_observed_score") or "").strip()
        if not candidate_id or not endpoint_group or not normalized:
            continue
        key = (candidate_id, endpoint_group)
        existing = result_lookup.get(key)
        if existing is None or _float(row.get("assay_confidence_score"), _float(row.get("assay_confidence"))) > _float(
            existing.get("assay_confidence_score"), _float(existing.get("assay_confidence"))
        ):
            result_lookup[key] = dict(row)
    generated = []
    unmatched = []
    for plan_row in plan.get("rows") or []:
        key = (str(plan_row.get("candidate_id") or "").strip(), str(plan_row.get("endpoint_group") or "").strip())
        result_row = result_lookup.get(key)
        if not result_row:
            unmatched.append(
                {
                    "measurement_plan_id": plan_row.get("measurement_plan_id"),
                    "candidate_id": plan_row.get("candidate_id"),
                    "endpoint_group": plan_row.get("endpoint_group"),
                    "measurement_type": plan_row.get("measurement_type"),
                }
            )
            continue
        generated.append(
            {
                "measurement_plan_id": plan_row.get("measurement_plan_id"),
                "project_name": plan_row.get("project_name"),
                "candidate_id": plan_row.get("candidate_id"),
                "smiles": plan_row.get("smiles"),
                "endpoint_group": plan_row.get("endpoint_group"),
                "observed_value": result_row.get("result_value"),
                "observed_unit": result_row.get("result_unit"),
                "normalized_observed_score": result_row.get("normalized_score") or result_row.get("normalized_observed_score"),
                "outcome_direction": result_row.get("classification") or result_row.get("stop_go_decision") or "",
                "assay_confidence": result_row.get("assay_confidence_score") or result_row.get("assay_confidence") or "",
                "reviewer": reviewer,
                "result_note": result_row.get("notes") or f"Mapped from historical experiment result {result_row.get('plan_id') or ''}".strip(),
                "source_plan_id": result_row.get("plan_id") or "",
                "source_run_id": result_row.get("run_id") or "",
            }
        )
    type_counts = Counter(str(row.get("measurement_type") or "unknown") for row in plan.get("rows") or [] if row.get("measurement_plan_id"))
    return {
        "status": "mapped" if generated else "no_matching_experiment_results",
        "generated_row_count": len(generated),
        "unmatched_plan_count": len(unmatched),
        "plan_row_count": len(plan.get("rows") or []),
        "measurement_type_counts": dict(type_counts.most_common()),
        "rows": generated,
        "unmatched_plan_rows": unmatched,
    }


def _experiment_rows_by_candidate(experiment_rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in experiment_rows:
        if str(row.get("status") or "").strip().lower() not in {"completed", "imported", "measured", "accepted"}:
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        grouped.setdefault(candidate_id, []).append(dict(row))
    return grouped


def _resolve(root_path: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root_path / item


def _existing_gap_decisions(path: Path) -> dict[str, dict]:
    report = _read_json(path)
    decisions = {}
    for row in report.get("rows") or []:
        plan_id = str(row.get("measurement_plan_id") or "")
        if plan_id and row.get("closure_status") in DECISIONED_GAP_STATUSES:
            decisions[plan_id] = dict(row)
    return decisions


def build_measurement_feedback_gap_closure(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    plan_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_PLAN_PATH,
    import_report_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH,
    experiment_result_path: str | Path = "data/projects/demo/historical_experiment_results.csv",
    gap_closure_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH,
    update_plan: bool = True,
) -> dict:
    root_path = Path(root)
    plan_file = _resolve(root_path, plan_path)
    import_file = _resolve(root_path, import_report_path)
    experiment_file = _resolve(root_path, experiment_result_path)
    gap_file = _resolve(root_path, gap_closure_path)
    plan = _read_json(plan_file)
    import_report = _read_json(import_file)
    existing_decisions = _existing_gap_decisions(gap_file)
    imported_ids = {str(row.get("measurement_plan_id") or "") for row in import_report.get("rows") or [] if row.get("measurement_plan_id")}
    mapping = import_report.get("experiment_mapping") or {}
    unmatched_rows = [dict(row) for row in mapping.get("unmatched_plan_rows") or []]
    if not unmatched_rows:
        unmatched_rows = [
            {
                "measurement_plan_id": row.get("measurement_plan_id"),
                "candidate_id": row.get("candidate_id"),
                "endpoint_group": row.get("endpoint_group"),
                "measurement_type": row.get("measurement_type"),
            }
            for row in plan.get("rows") or []
            if row.get("measurement_plan_id") and str(row.get("measurement_plan_id")) not in imported_ids
        ]
    plan_by_id = _plan_lookup(plan)
    experiment_by_candidate = _experiment_rows_by_candidate(read_experiment_result_rows_csv(experiment_file))
    rows = []
    for raw in unmatched_rows:
        plan_id = str(raw.get("measurement_plan_id") or "")
        plan_row = dict(plan_by_id.get(plan_id) or raw)
        candidate_id = str(plan_row.get("candidate_id") or raw.get("candidate_id") or "").strip()
        endpoint = str(plan_row.get("endpoint_group") or raw.get("endpoint_group") or "").strip()
        candidate_results = experiment_by_candidate.get(candidate_id) or []
        exact = [row for row in candidate_results if str(row.get("endpoint_group") or "").strip() == endpoint]
        mismatched = [row for row in candidate_results if str(row.get("endpoint_group") or "").strip() != endpoint]
        if exact:
            closure_status = "exact_result_available_for_import"
            review_action = "rerun_exact_endpoint_import"
            blocked_reason = ""
        elif mismatched:
            closure_status = "manual_endpoint_confirmation_required"
            review_action = "collect_exact_endpoint_or_record_manual_endpoint_remap"
            blocked_reason = "historical result exists for the candidate, but endpoint_group differs; no automatic cross-endpoint mapping"
        else:
            closure_status = "needs_new_measured_feedback"
            review_action = "collect_exact_endpoint_measurement"
            blocked_reason = "no completed historical result for this candidate and endpoint"
        row = {
                "measurement_plan_id": plan_id,
                "project_name": project_name,
                "candidate_id": candidate_id,
                "queue_id": plan_row.get("queue_id", ""),
                "smiles": plan_row.get("smiles", ""),
                "required_endpoint_group": endpoint,
                "measurement_type": plan_row.get("measurement_type") or raw.get("measurement_type"),
                "measurement_priority": plan_row.get("measurement_priority", ""),
                "closure_status": closure_status,
                "review_action": review_action,
                "blocked_reason": blocked_reason,
                "available_endpoint_groups": ";".join(
                    dict.fromkeys(str(row.get("endpoint_group") or "") for row in candidate_results if row.get("endpoint_group"))
                ),
                "available_result_count": len(candidate_results),
                "exact_result_count": len(exact),
                "endpoint_mismatch_count": len(mismatched),
                "source_path": str(experiment_file),
                "review_status": "open",
                "gap_decision_status": "",
                "gap_decision": "",
                "reviewed_by": "",
                "reviewed_at": "",
                "review_note": "",
                "review_history": [],
            }
        preserved = existing_decisions.get(plan_id)
        if preserved:
            for field in [
                "closure_status",
                "review_action",
                "blocked_reason",
                "review_status",
                "gap_decision_status",
                "gap_decision",
                "reviewed_by",
                "reviewed_at",
                "review_note",
                "review_history",
            ]:
                row[field] = preserved.get(field, row.get(field))
        rows.append(row)
    if update_plan and rows and plan_file.exists():
        closure_by_id = {str(row.get("measurement_plan_id") or ""): row for row in rows}
        updated_rows = []
        for row in plan.get("rows") or []:
            plan_id = str(row.get("measurement_plan_id") or "")
            updated = dict(row)
            closure = closure_by_id.get(plan_id)
            if closure and str(updated.get("planned_status") or "") != "evidence_imported":
                updated["planned_status"] = closure.get("closure_status")
                updated["next_step"] = closure.get("review_action")
            updated_rows.append(updated)
        plan["rows"] = updated_rows
        plan["planned_status_counts"] = dict(Counter(str(row.get("planned_status") or "planned") for row in updated_rows).most_common())
        write_measurement_feedback_plan(
            plan,
            plan_file,
            csv_path=plan_file.parent / DEFAULT_MEASUREMENT_FEEDBACK_PLAN_CSV_PATH.name,
            template_path=plan_file.parent / DEFAULT_MEASUREMENT_FEEDBACK_TEMPLATE_PATH.name,
        )
    status_counts = Counter(str(row.get("closure_status") or "unknown") for row in rows)
    resolved_statuses = {"exact_result_available_for_import", *DECISIONED_GAP_STATUSES}
    open_gap_count = sum(1 for row in rows if row.get("closure_status") not in resolved_statuses)
    decision_recorded_count = sum(1 for row in rows if row.get("closure_status") in DECISIONED_GAP_STATUSES)
    pending_exact_measurement_count = status_counts.get("exact_measurement_required", 0) + status_counts.get("needs_new_measured_feedback", 0)
    if not rows:
        status = "no_unmatched_plan_rows"
    elif open_gap_count:
        status = "manual_review_required"
    elif status_counts.get("exact_result_available_for_import") == len(rows):
        status = "ready_for_exact_import"
    else:
        status = "decision_recorded"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "row_count": len(rows),
        "open_gap_count": open_gap_count,
        "endpoint_mismatch_count": status_counts.get("manual_endpoint_confirmation_required", 0),
        "needs_new_measurement_count": status_counts.get("needs_new_measured_feedback", 0),
        "exact_result_available_count": status_counts.get("exact_result_available_for_import", 0),
        "decision_recorded_count": decision_recorded_count,
        "pending_exact_measurement_count": pending_exact_measurement_count,
        "closure_status_counts": dict(status_counts.most_common()),
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Do not auto-map historical results across endpoint groups.",
            "For endpoint mismatches, collect the exact endpoint or record an explicit manual endpoint-remap decision.",
            "Use this closure report to keep unmatched measurement rows visible in Project Memory.",
        ],
    }


def review_measurement_feedback_gap_closure(
    *,
    gap_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH,
    plan_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_PLAN_PATH,
    measurement_plan_ids: list[str] | None = None,
    decision: str,
    reviewer: str | None = None,
    note: str | None = None,
    update_plan: bool = True,
) -> dict:
    if decision not in MEASUREMENT_GAP_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(MEASUREMENT_GAP_DECISIONS)}")
    gap_file = Path(gap_path)
    report = _read_json(gap_file)
    selected = {str(item) for item in (measurement_plan_ids or []) if str(item)}
    if not selected:
        selected = {str(row.get("measurement_plan_id") or "") for row in report.get("rows") or [] if row.get("measurement_plan_id")}
    now = datetime.now(timezone.utc).isoformat()
    status_map = {
        "exact_measurement_required": (
            "exact_measurement_required",
            "collect_exact_endpoint_measurement",
            "manual decision recorded: collect the exact endpoint; no cross-endpoint remap approved",
        ),
        "endpoint_remap_approved": (
            "manual_endpoint_remap_approved",
            "import_with_recorded_endpoint_remap_only",
            "manual endpoint-remap decision recorded; keep provenance attached to import",
        ),
        "deferred": (
            "deferred",
            "defer_gap_until_project_context_changes",
            "manual decision recorded: defer this gap without importing mismatched endpoint data",
        ),
    }
    closure_status, review_action, blocked_reason = status_map[decision]
    rows = []
    reviewed_count = 0
    for raw in report.get("rows") or []:
        row = dict(raw)
        if str(row.get("measurement_plan_id") or "") in selected:
            history = list(row.get("review_history") or [])
            history.append(
                {
                    "reviewed_at": now,
                    "decision": decision,
                    "reviewer": reviewer or "",
                    "note": note or "",
                    "previous_closure_status": row.get("closure_status"),
                }
            )
            row.update(
                {
                    "closure_status": closure_status,
                    "review_action": review_action,
                    "blocked_reason": blocked_reason,
                    "review_status": "resolved",
                    "gap_decision_status": "decision_recorded",
                    "gap_decision": decision,
                    "reviewed_by": reviewer or "",
                    "reviewed_at": now,
                    "review_note": note or "",
                    "review_history": history,
                }
            )
            reviewed_count += 1
        rows.append(row)
    report["rows"] = rows
    status_counts = Counter(str(row.get("closure_status") or "unknown") for row in rows)
    resolved_statuses = {"exact_result_available_for_import", *DECISIONED_GAP_STATUSES}
    report["updated_at"] = now
    report["status"] = "manual_review_required" if any(row.get("closure_status") not in resolved_statuses for row in rows) else "decision_recorded" if rows else "no_unmatched_plan_rows"
    report["open_gap_count"] = sum(1 for row in rows if row.get("closure_status") not in resolved_statuses)
    report["endpoint_mismatch_count"] = status_counts.get("manual_endpoint_confirmation_required", 0)
    report["needs_new_measurement_count"] = status_counts.get("needs_new_measured_feedback", 0)
    report["exact_result_available_count"] = status_counts.get("exact_result_available_for_import", 0)
    report["decision_recorded_count"] = sum(1 for row in rows if row.get("closure_status") in DECISIONED_GAP_STATUSES)
    report["pending_exact_measurement_count"] = status_counts.get("exact_measurement_required", 0) + status_counts.get("needs_new_measured_feedback", 0)
    report["closure_status_counts"] = dict(status_counts.most_common())
    report["last_reviewed_count"] = reviewed_count

    if update_plan:
        plan_file = Path(plan_path)
        plan = _read_json(plan_file)
        closure_by_id = {str(row.get("measurement_plan_id") or ""): row for row in rows}
        updated_rows = []
        for raw in plan.get("rows") or []:
            row = dict(raw)
            closure = closure_by_id.get(str(row.get("measurement_plan_id") or ""))
            if closure and str(row.get("planned_status") or "") != "evidence_imported":
                row["planned_status"] = closure.get("closure_status")
                row["next_step"] = closure.get("review_action")
            updated_rows.append(row)
        if updated_rows:
            plan["rows"] = updated_rows
            plan["planned_status_counts"] = dict(Counter(str(row.get("planned_status") or "planned") for row in updated_rows).most_common())
            write_measurement_feedback_plan(
                plan,
                plan_file,
                csv_path=plan_file.parent / DEFAULT_MEASUREMENT_FEEDBACK_PLAN_CSV_PATH.name,
                template_path=plan_file.parent / DEFAULT_MEASUREMENT_FEEDBACK_TEMPLATE_PATH.name,
            )

    gap_file.parent.mkdir(parents=True, exist_ok=True)
    gap_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _measurement_type(row: dict, value_row: dict) -> str:
    action = str(value_row.get("next_evidence_action") or "")
    status = str(row.get("evidence_sufficiency_status") or "")
    if action == "resolve_public_sar_contradiction" or _int(row.get("public_sar_contradiction_count")):
        return "public_sar_contradiction_resolution"
    if status == "conflict_review":
        return "replicate_conflict_endpoint"
    if status.startswith("needs"):
        return "residual_endpoint_followup"
    if _int(row.get("material_ab_diff_count")):
        return "profile_sensitive_rank_retest"
    return "candidate_priority_confirmation"


def _priority(score: float, measurement_type: str) -> str:
    if measurement_type == "public_sar_contradiction_resolution":
        return "high"
    if score >= 36:
        return "high"
    if score >= 22:
        return "medium"
    return "low"


def _candidate_plan_row(row: dict, value_row: dict, *, project_name: str | None) -> dict:
    value_score = _float(value_row.get("evidence_value_score"), _float(row.get("candidate_evidence_priority_score")))
    measurement_type = _measurement_type(row, value_row)
    return {
        "measurement_plan_id": _plan_id("candidate", row.get("queue_id"), row.get("candidate_id"), measurement_type),
        "project_name": project_name,
        "plan_source": "candidate_evidence_priority",
        "measurement_priority": _priority(value_score, measurement_type),
        "measurement_type": measurement_type,
        "queue_id": row.get("queue_id"),
        "candidate_id": row.get("candidate_id"),
        "smiles": row.get("smiles") or row.get("candidate_key"),
        "endpoint_group": row.get("endpoint_group") or "all",
        "analog_series_key": row.get("analog_series_key"),
        "evidence_value_score": value_score,
        "candidate_evidence_priority_score": row.get("candidate_evidence_priority_score"),
        "public_sar_link_count": row.get("public_sar_link_count"),
        "public_sar_contradiction_count": row.get("public_sar_contradiction_count"),
        "material_ab_diff_count": row.get("material_ab_diff_count"),
        "evidence_sufficiency_status": row.get("evidence_sufficiency_status"),
        "planned_status": "planned",
        "next_step": _next_step(measurement_type),
    }


def _next_step(measurement_type: str) -> str:
    mapping = {
        "public_sar_contradiction_resolution": "Run or import a focused measured endpoint to decide whether the public contradiction applies to this project context.",
        "replicate_conflict_endpoint": "Repeat or orthogonally confirm the conflicting endpoint before using the series as a profile prior.",
        "residual_endpoint_followup": "Fill the endpoint/family residual gap with a measured result payload.",
        "profile_sensitive_rank_retest": "Retest the endpoint most affected by profile A/B rank movement before activation.",
        "candidate_priority_confirmation": "Confirm the candidate priority with a measured project outcome when capacity allows.",
    }
    return mapping.get(measurement_type, "Collect measured feedback before changing score weights.")


def _series_plan_rows(analog_report: dict, existing_series: set[str], *, project_name: str | None) -> list[dict]:
    rows = []
    for series in analog_report.get("series") or []:
        series_key = str(series.get("series_key") or "")
        if not series_key or series_key in existing_series:
            continue
        status = str(series.get("evidence_sufficiency_status") or "")
        if status == "sufficient":
            continue
        value_score = max(0.0, 26.0 + _float(series.get("evidence_sufficiency_gap")) * 0.45)
        measurement_type = "replicate_conflict_endpoint" if status == "conflict_review" else "residual_endpoint_followup"
        rows.append(
            {
                "measurement_plan_id": _plan_id("series", series_key, measurement_type),
                "project_name": project_name,
                "plan_source": "analog_series_sufficiency",
                "measurement_priority": _priority(value_score, measurement_type),
                "measurement_type": measurement_type,
                "queue_id": "",
                "candidate_id": "",
                "smiles": "",
                "endpoint_group": series.get("primary_endpoint_group") or series.get("endpoint_group") or "all",
                "analog_series_key": series_key,
                "evidence_value_score": round(value_score, 2),
                "candidate_evidence_priority_score": "",
                "public_sar_link_count": "",
                "public_sar_contradiction_count": "",
                "material_ab_diff_count": "",
                "evidence_sufficiency_status": status,
                "planned_status": "planned",
                "next_step": _next_step(measurement_type),
            }
        )
    return rows


def build_measurement_feedback_plan(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    candidate_priority_path: str | Path = "data/projects/demo/candidate_evidence_priority_report.json",
    analog_series_path: str | Path = "data/projects/demo/analog_series_report.json",
    evidence_value_path: str | Path = "data/projects/demo/evidence_value_report.json",
    max_rows: int = 48,
) -> dict:
    root_path = Path(root)
    priority_file = Path(candidate_priority_path)
    analog_file = Path(analog_series_path)
    value_file = Path(evidence_value_path)
    priority = _read_json(priority_file if priority_file.is_absolute() else root_path / priority_file)
    analog = _read_json(analog_file if analog_file.is_absolute() else root_path / analog_file)
    value = _read_json(value_file if value_file.is_absolute() else root_path / value_file)
    values = _value_lookup(value)
    rows = []
    represented_series = set()
    for source in priority.get("rows") or []:
        value_row = _linked_value(source, values)
        measurement_type = _measurement_type(source, value_row)
        candidate_tier = str(source.get("candidate_evidence_priority_tier") or "")
        value_tier = str(value_row.get("evidence_value_tier") or "")
        if candidate_tier != "high" and value_tier != "high_value" and measurement_type == "candidate_priority_confirmation":
            continue
        plan_row = _candidate_plan_row(source, value_row, project_name=project_name)
        if plan_row.get("analog_series_key"):
            represented_series.add(str(plan_row.get("analog_series_key")))
        rows.append(plan_row)
    rows.extend(_series_plan_rows(analog, represented_series, project_name=project_name))
    rows.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("measurement_priority")), 9),
            -_float(row.get("evidence_value_score")),
            str(row.get("measurement_plan_id") or ""),
        )
    )
    rows = rows[: int(max_rows)]
    priority_counts = Counter(str(row.get("measurement_priority") or "unknown") for row in rows)
    type_counts = Counter(str(row.get("measurement_type") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "project_name": project_name,
        "row_count": len(rows),
        "high_priority_count": priority_counts.get("high", 0),
        "candidate_row_count": sum(1 for row in rows if row.get("candidate_id")),
        "series_row_count": sum(1 for row in rows if row.get("plan_source") == "analog_series_sufficiency"),
        "priority_counts": dict(priority_counts.most_common()),
        "measurement_type_counts": dict(type_counts.most_common()),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "rows": rows,
        "template_columns": [
            "measurement_plan_id",
            "project_name",
            "candidate_id",
            "smiles",
            "endpoint_group",
            "observed_value",
            "observed_unit",
            "normalized_observed_score",
            "outcome_direction",
            "assay_confidence",
            "reviewer",
            "result_note",
        ],
        "recommended_next_actions": [
            "Fill the template only with real measured or imported assay feedback.",
            "Use high-priority rows to close contradiction, residual, and profile-sensitive uncertainty first.",
            "Keep this plan focused on medchem evidence; procurement/vendor steps are out of scope.",
        ],
    }


def write_measurement_feedback_plan(
    report: dict,
    output_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_PLAN_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_MEASUREMENT_FEEDBACK_PLAN_CSV_PATH,
    template_path: str | Path | None = DEFAULT_MEASUREMENT_FEEDBACK_TEMPLATE_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    rows = [dict(row) for row in report.get("rows") or []]
    fieldnames = [
        "measurement_plan_id",
        "project_name",
        "plan_source",
        "measurement_priority",
        "measurement_type",
        "queue_id",
        "candidate_id",
        "smiles",
        "endpoint_group",
        "analog_series_key",
        "evidence_value_score",
        "candidate_evidence_priority_score",
        "public_sar_link_count",
        "public_sar_contradiction_count",
        "material_ab_diff_count",
        "evidence_sufficiency_status",
        "planned_status",
        "last_observed_value",
        "last_observed_unit",
        "last_normalized_observed_score",
        "last_feedback_imported_at",
        "last_feedback_reviewer",
        "next_step",
    ]
    if csv_path is not None:
        csv_out = Path(csv_path)
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
    if template_path is None:
        return
    template_fields = list(report.get("template_columns") or [])
    template_out = Path(template_path)
    template_out.parent.mkdir(parents=True, exist_ok=True)
    with template_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=template_fields)
        writer.writeheader()
        for row in rows:
            values = {
                "measurement_plan_id": row.get("measurement_plan_id", ""),
                "project_name": row.get("project_name", ""),
                "candidate_id": row.get("candidate_id", ""),
                "smiles": row.get("smiles", ""),
                "endpoint_group": row.get("endpoint_group", ""),
                "observed_value": "",
                "observed_unit": "",
                "normalized_observed_score": "",
                "outcome_direction": "",
                "assay_confidence": "",
                "reviewer": "",
                "result_note": "",
            }
            writer.writerow({field: values.get(field, "") for field in template_fields})


def import_measurement_feedback_results_rows(
    rows: list[dict],
    *,
    root: str | Path = ".",
    plan_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_PLAN_PATH,
    evidence_value_path: str | Path = "data/projects/demo/evidence_value_report.json",
    source_path: str | Path | None = None,
    reviewer: str | None = None,
    update_plan: bool = True,
) -> dict:
    root_path = Path(root)
    plan_file = Path(plan_path)
    if not plan_file.is_absolute():
        plan_file = root_path / plan_file
    evidence_file = Path(evidence_value_path)
    if not evidence_file.is_absolute():
        evidence_file = root_path / evidence_file
    plan = _read_json(plan_file)
    evidence_report = _read_json(evidence_file)
    evidence = _evidence_lookup(evidence_report)
    validation = validate_measurement_feedback_result_rows(rows, plan)
    now = datetime.now(timezone.utc).isoformat()
    imported_rows = []
    imported_plan_ids = set()
    for item in validation.get("importable_rows") or []:
        result_row = dict(item.get("row") or {})
        plan_row = dict(item.get("plan_row") or {})
        linked_value = _linked_evidence(plan_row, evidence)
        observed_score = _normalized_observed_score(result_row)
        predicted_score = _float(linked_value.get("evidence_value_score"), _float(plan_row.get("evidence_value_score")))
        calibration_ready = observed_score is not None
        imported_plan_ids.add(str(plan_row.get("measurement_plan_id") or ""))
        imported_rows.append(
            {
                "measurement_plan_id": plan_row.get("measurement_plan_id"),
                "project_name": plan_row.get("project_name"),
                "measurement_type": plan_row.get("measurement_type"),
                "measurement_priority": plan_row.get("measurement_priority"),
                "queue_id": plan_row.get("queue_id"),
                "candidate_id": plan_row.get("candidate_id"),
                "smiles": plan_row.get("smiles"),
                "endpoint_group": plan_row.get("endpoint_group"),
                "analog_series_key": plan_row.get("analog_series_key"),
                "observed_value": result_row.get("observed_value"),
                "observed_unit": result_row.get("observed_unit"),
                "normalized_observed_score": observed_score if observed_score is not None else "",
                "outcome_direction": result_row.get("outcome_direction") or "",
                "assay_confidence": result_row.get("assay_confidence") or "",
                "reviewer": result_row.get("reviewer") or reviewer or "",
                "result_note": result_row.get("result_note") or "",
                "predicted_evidence_value_score": predicted_score,
                "score_error": round(observed_score - predicted_score, 4) if calibration_ready else "",
                "calibration_ready": calibration_ready,
                "evidence_value_id": linked_value.get("evidence_value_id") or "",
                "value_driver_flags": linked_value.get("value_driver_flags") or "",
                "next_evidence_action": linked_value.get("next_evidence_action") or "",
                "imported_at": now,
                "source_path": str(source_path or ""),
            }
        )
    if update_plan and plan_file.exists() and imported_plan_ids:
        updated_rows = []
        by_plan_id = {str(row.get("measurement_plan_id") or ""): row for row in imported_rows}
        for row in plan.get("rows") or []:
            plan_id = str(row.get("measurement_plan_id") or "")
            updated = dict(row)
            if plan_id in imported_plan_ids:
                imported = by_plan_id.get(plan_id) or {}
                updated.update(
                    {
                        "planned_status": "evidence_imported",
                        "last_observed_value": imported.get("observed_value"),
                        "last_observed_unit": imported.get("observed_unit"),
                        "last_normalized_observed_score": imported.get("normalized_observed_score"),
                        "last_feedback_imported_at": now,
                        "last_feedback_reviewer": imported.get("reviewer") or reviewer or "",
                    }
                )
            updated_rows.append(updated)
        plan["rows"] = updated_rows
        status_counts = Counter(str(row.get("planned_status") or "planned") for row in updated_rows)
        plan["planned_status_counts"] = dict(status_counts.most_common())
        write_measurement_feedback_plan(
            plan,
            plan_file,
            csv_path=plan_file.parent / DEFAULT_MEASUREMENT_FEEDBACK_PLAN_CSV_PATH.name,
            template_path=plan_file.parent / DEFAULT_MEASUREMENT_FEEDBACK_TEMPLATE_PATH.name,
        )
    importable_count = len(imported_rows)
    rejected_count = int(validation.get("rejected_row_count") or 0)
    calibration_ready_count = sum(1 for row in imported_rows if row.get("calibration_ready"))
    if importable_count and rejected_count:
        status = "imported_with_validation_issues"
    elif importable_count and calibration_ready_count:
        status = "imported"
    elif importable_count:
        status = "imported_uncalibrated_measurements"
    elif rejected_count:
        status = "validation_failed"
    else:
        status = "needs_real_measurement_feedback"
    type_counts = Counter(str(row.get("measurement_type") or "unknown") for row in imported_rows)
    return {
        "created_at": now,
        "status": status,
        "source_path": str(source_path or ""),
        "importable_row_count": importable_count,
        "rejected_row_count": rejected_count,
        "skipped_blank_row_count": validation.get("skipped_blank_row_count", 0),
        "calibration_ready_row_count": calibration_ready_count,
        "plan_update_count": len(imported_plan_ids),
        "measurement_type_counts": dict(type_counts.most_common()),
        "validation": {
            key: value
            for key, value in validation.items()
            if key not in {"importable_rows"}
        },
        "rows": imported_rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Import only real measured rows from the feedback template.",
            "Provide normalized_observed_score when the raw endpoint unit is not already a 0-100 score.",
            "Use imported calibration-ready rows to recalibrate evidence-value weights.",
        ],
    }


def write_measurement_feedback_import_report(
    report: dict,
    output_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_MEASUREMENT_FEEDBACK_IMPORT_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "measurement_plan_id",
        "project_name",
        "measurement_type",
        "measurement_priority",
        "queue_id",
        "candidate_id",
        "smiles",
        "endpoint_group",
        "analog_series_key",
        "observed_value",
        "observed_unit",
        "normalized_observed_score",
        "outcome_direction",
        "assay_confidence",
        "reviewer",
        "result_note",
        "predicted_evidence_value_score",
        "score_error",
        "calibration_ready",
        "evidence_value_id",
        "value_driver_flags",
        "next_evidence_action",
        "imported_at",
        "source_path",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_measurement_feedback_gap_closure(
    report: dict,
    output_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_MEASUREMENT_FEEDBACK_GAP_CLOSURE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "measurement_plan_id",
        "project_name",
        "candidate_id",
        "queue_id",
        "required_endpoint_group",
        "measurement_type",
        "measurement_priority",
        "closure_status",
        "review_action",
        "blocked_reason",
        "available_endpoint_groups",
        "available_result_count",
        "exact_result_count",
        "endpoint_mismatch_count",
        "source_path",
        "review_status",
        "gap_decision_status",
        "gap_decision",
        "reviewed_by",
        "reviewed_at",
        "review_note",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def build_measurement_gap_exact_result_template_rows(gap_closure: dict) -> list[dict]:
    rows = []
    for row in gap_closure.get("rows") or []:
        if row.get("closure_status") != "exact_measurement_required":
            continue
        rows.append(
            {
                "measurement_plan_id": row.get("measurement_plan_id", ""),
                "project_name": row.get("project_name", ""),
                "candidate_id": row.get("candidate_id", ""),
                "smiles": row.get("smiles", ""),
                "endpoint_group": row.get("required_endpoint_group", ""),
                "measurement_type": row.get("measurement_type", ""),
                "measurement_priority": row.get("measurement_priority", ""),
                "observed_value": "",
                "observed_unit": "",
                "normalized_observed_score": "",
                "outcome_direction": "",
                "assay_confidence": "",
                "reviewer": "",
                "result_note": "Exact endpoint required; do not use cross-endpoint remap.",
            }
        )
    return rows


def write_measurement_gap_exact_result_template(
    rows: list[dict],
    output_path: str | Path = DEFAULT_MEASUREMENT_GAP_EXACT_TEMPLATE_PATH,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "measurement_plan_id",
        "project_name",
        "candidate_id",
        "smiles",
        "endpoint_group",
        "measurement_type",
        "measurement_priority",
        "observed_value",
        "observed_unit",
        "normalized_observed_score",
        "outcome_direction",
        "assay_confidence",
        "reviewer",
        "result_note",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def build_measurement_gap_exact_result_intake(
    *,
    root: str | Path = ".",
    gap_closure_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH,
    plan_path: str | Path = DEFAULT_MEASUREMENT_FEEDBACK_PLAN_PATH,
    template_path: str | Path = DEFAULT_MEASUREMENT_GAP_EXACT_TEMPLATE_PATH,
    results_path: str | Path | None = None,
    project_name: str | None = "demo_learning",
) -> dict:
    root_path = Path(root)
    gap_file = _resolve(root_path, gap_closure_path)
    plan_file = _resolve(root_path, plan_path)
    template_file = _resolve(root_path, template_path)
    gap_closure = _read_json(gap_file)
    plan = _read_json(plan_file)
    template_rows = build_measurement_gap_exact_result_template_rows(gap_closure)
    write_measurement_gap_exact_result_template(template_rows, template_file)
    result_file = _resolve(root_path, results_path) if results_path else template_file
    result_rows = read_measurement_feedback_result_rows_csv(result_file)
    validation = validate_measurement_feedback_result_rows(result_rows, plan)
    exact_plan_ids = {str(row.get("measurement_plan_id") or "") for row in template_rows}
    importable_exact_ids = {
        str(item.get("plan_row", {}).get("measurement_plan_id") or "")
        for item in validation.get("importable_rows") or []
        if str(item.get("plan_row", {}).get("measurement_plan_id") or "") in exact_plan_ids
    }
    pending_ids = sorted(exact_plan_ids - importable_exact_ids)
    status = "ready_for_import" if importable_exact_ids else "awaiting_exact_results" if exact_plan_ids else "empty"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "gap_closure_path": str(gap_file),
        "plan_path": str(plan_file),
        "template_path": str(template_file),
        "results_path": str(result_file),
        "template_row_count": len(template_rows),
        "candidate_count": len({str(row.get("candidate_id") or "") for row in template_rows if row.get("candidate_id")}),
        "exact_endpoint_group_count": len({str(row.get("endpoint_group") or "") for row in template_rows if row.get("endpoint_group")}),
        "importable_exact_result_count": len(importable_exact_ids),
        "pending_exact_result_count": len(pending_ids),
        "pending_measurement_plan_ids": pending_ids,
        "validation": {
            key: value
            for key, value in validation.items()
            if key not in {"importable_rows", "rejected_rows"}
        },
        "rows": template_rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Keep observed_value and observed_unit blank until a project-approved local data source is explicitly supplied.",
            "Use this intake as a strict endpoint placeholder; keep endpoint_group equal to the required gap endpoint.",
            "Do not use metabolic_stability rows to close permeability gaps.",
        ],
    }


def write_measurement_gap_exact_result_intake(
    report: dict,
    output_path: str | Path = DEFAULT_MEASUREMENT_GAP_EXACT_INTAKE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_MEASUREMENT_GAP_EXACT_INTAKE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "measurement_plan_id",
        "project_name",
        "candidate_id",
        "endpoint_group",
        "measurement_type",
        "measurement_priority",
        "observed_value",
        "observed_unit",
        "normalized_observed_score",
        "result_note",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
