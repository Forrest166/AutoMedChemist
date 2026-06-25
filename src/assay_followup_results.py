from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .assay_event_triage import (
    DEFAULT_ASSAY_EVENT_TRIAGE_CSV_PATH,
    DEFAULT_ASSAY_EVENT_TRIAGE_PATH,
    build_assay_event_triage_report,
    write_assay_event_triage_report,
)
from .experiment_tracking import (
    DEFAULT_DB_PATH,
    EXPERIMENT_PLAN_FIELDS,
    import_experiment_results_rows,
    read_experiment_plan_csv,
    validate_experiment_result_rows,
)


DEFAULT_ASSAY_FOLLOWUP_TEMPLATE_PATH = Path("data/projects/demo/assay_followup_results_template.csv")
DEFAULT_ASSAY_FOLLOWUP_IMPORT_REPORT_PATH = Path("data/projects/demo/assay_followup_result_import_report.json")
DEFAULT_ASSAY_FOLLOWUP_IMPORT_CSV_PATH = Path("data/projects/demo/assay_followup_result_import_report.csv")

FOLLOWUP_REFERENCE_FIELDS = [
    "reference_event_id",
    "reference_issue_types",
    "reference_assay_confidence",
    "reference_stop_go_decision",
    "reference_retest_reason",
    "followup_resolution_note",
]

FOLLOWUP_RESULT_FIELDS = [
    "status",
    "result_value",
    "result_unit",
    "result_relation",
    "classification",
    "normalized_score",
    "replicate_count",
    "replicate_cv",
    "assay_confidence",
    "assay_confidence_score",
    "stop_go_decision",
    "retest_reason",
    "result_recorded_at",
]


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def build_assay_followup_result_template_rows(triage_report: dict) -> list[dict]:
    """Create blank follow-up rows from unresolved assay triage items.

    The template intentionally leaves measured-result fields empty. Importing
    this file without a real result payload will fail validation.
    """
    rows = []
    for index, triage_row in enumerate(triage_report.get("rows") or [], start=1):
        status = str(triage_row.get("triage_status") or "")
        if status == "resolved_by_followup":
            continue
        row = {field: "" for field in EXPERIMENT_PLAN_FIELDS + FOLLOWUP_REFERENCE_FIELDS}
        row.update(
            {
                "plan_id": triage_row.get("plan_id") or "",
                "plan_rank": index,
                "plan_role": "assay_followup",
                "project_name": triage_row.get("project_name") or triage_report.get("project_name") or "",
                "run_id": triage_row.get("run_id") or "",
                "candidate_id": triage_row.get("candidate_id") or "",
                "endpoint_group": triage_row.get("endpoint_group") or "",
                "planned_assay": triage_row.get("assay_name") or "",
                "assay_type": triage_row.get("assay_type") or "",
                "owner": "assay_followup",
                "notes": "Fill with measured follow-up result before import.",
                "reference_event_id": triage_row.get("event_id") or "",
                "reference_issue_types": triage_row.get("issue_types") or "",
                "reference_assay_confidence": triage_row.get("assay_confidence") or "",
                "reference_stop_go_decision": triage_row.get("stop_go_decision") or "",
                "reference_retest_reason": triage_row.get("retest_reason") or "",
            }
        )
        for field in FOLLOWUP_RESULT_FIELDS:
            row[field] = ""
        rows.append(row)
    return rows


def write_assay_followup_result_template(
    triage_report: dict,
    output_path: str | Path = DEFAULT_ASSAY_FOLLOWUP_TEMPLATE_PATH,
) -> list[dict]:
    rows = build_assay_followup_result_template_rows(triage_report)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = EXPERIMENT_PLAN_FIELDS + [field for field in FOLLOWUP_REFERENCE_FIELDS if field not in EXPERIMENT_PLAN_FIELDS]
    extras = sorted({key for row in rows for key in row if key not in fieldnames})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames + extras)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames + extras})
    return rows


def build_assay_followup_result_template(
    *,
    triage_report_path: str | Path = DEFAULT_ASSAY_EVENT_TRIAGE_PATH,
    output_path: str | Path = DEFAULT_ASSAY_FOLLOWUP_TEMPLATE_PATH,
) -> dict:
    triage = _read_json(triage_report_path)
    rows = write_assay_followup_result_template(triage, output_path)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "triage_report_path": str(triage_report_path),
        "template_path": str(output_path),
        "template_row_count": len(rows),
        "source_triage_event_count": triage.get("event_count", 0),
        "recommended_next_actions": [
            "Fill measured result fields before import; blank template rows are rejected.",
            "Use completed + result payload to resolve low-confidence/retest triage rows.",
            "Retest or low-confidence follow-up rows stay review-gated after import.",
        ],
    }


def validate_assay_followup_result_rows(rows: Iterable[dict]) -> dict:
    materialized = [{str(key).strip(): value for key, value in dict(row).items()} for row in rows]
    validation = validate_experiment_result_rows(materialized, residual_only=False, require_result_payload=True)
    issues = list(validation.get("issues") or [])
    missing_reference_count = 0
    for index, row in enumerate(materialized, start=1):
        if not str(row.get("reference_event_id") or "").strip():
            missing_reference_count += 1
            issues.append(
                {
                    "row_number": index,
                    "severity": "warn",
                    "issue": "missing_reference_event_id",
                    "message": "Follow-up result has no reference_event_id; it can still import if plan/candidate identity is present.",
                }
            )
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warn")
    error_count = sum(1 for issue in issues if issue.get("severity") == "error")
    return {
        **validation,
        "status": "error" if error_count else "warn" if warning_count else validation.get("status"),
        "issues": issues,
        "warning_count": warning_count,
        "error_count": error_count,
        "missing_reference_count": missing_reference_count,
    }


def import_assay_followup_results_rows(
    rows: Iterable[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    source_path: str | None = None,
    project_name: str | None = None,
    reviewer: str = "assay_followup_import",
    triage_output_path: str | Path = DEFAULT_ASSAY_EVENT_TRIAGE_PATH,
    triage_csv_path: str | Path | None = DEFAULT_ASSAY_EVENT_TRIAGE_CSV_PATH,
) -> dict:
    materialized = [{str(key).strip(): value for key, value in dict(row).items()} for row in rows]
    validation = validate_assay_followup_result_rows(materialized)
    importable = [
        materialized[index - 1]
        for index in validation.get("importable_row_indices") or []
        if 0 < int(index) <= len(materialized)
    ]
    import_report = {
        "processed_count": 0,
        "event_count": 0,
        "feedback_inserted_count": 0,
        "feedback_skipped_count": 0,
        "stop_go_counts": {},
        "retest_event_count": 0,
    }
    if importable:
        import_report = import_experiment_results_rows(
            importable,
            db_path=db_path,
            source_path=source_path,
            update_feedback=True,
        )
    triage = build_assay_event_triage_report(db_path=db_path, project_name=project_name, reviewer=reviewer)
    write_assay_event_triage_report(triage, triage_output_path, csv_path=triage_csv_path)
    imported_count = int(import_report.get("event_count") or 0)
    status = (
        "imported_with_validation_errors"
        if imported_count and validation.get("error_count")
        else "imported"
        if imported_count
        else "validation_failed"
        if validation.get("error_count")
        else "no_importable_results"
    )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_path": source_path,
        "validation": validation,
        "import": import_report,
        "triage_status": triage.get("status"),
        "triage_event_count": triage.get("event_count", 0),
        "real_followup_resolved_count": triage.get("real_followup_resolved_count", 0),
        "planned_followup_count": triage.get("planned_followup_count", 0),
        "followup_review_count": triage.get("followup_review_count", 0),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
    }


def import_assay_followup_results_csv(
    path: str | Path,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    reviewer: str = "assay_followup_import",
    triage_output_path: str | Path = DEFAULT_ASSAY_EVENT_TRIAGE_PATH,
    triage_csv_path: str | Path | None = DEFAULT_ASSAY_EVENT_TRIAGE_CSV_PATH,
) -> dict:
    source = str(Path(path).resolve())
    return import_assay_followup_results_rows(
        read_experiment_plan_csv(path),
        db_path=db_path,
        source_path=source,
        project_name=project_name,
        reviewer=reviewer,
        triage_output_path=triage_output_path,
        triage_csv_path=triage_csv_path,
    )


def write_assay_followup_import_report(
    report: dict,
    output_path: str | Path = DEFAULT_ASSAY_FOLLOWUP_IMPORT_REPORT_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_ASSAY_FOLLOWUP_IMPORT_CSV_PATH,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    validation = report.get("validation") or {}
    rows = validation.get("issues") or []
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["row_number", "severity", "issue", "message"]
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
