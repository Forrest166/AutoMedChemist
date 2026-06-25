from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .assay_learning import assay_result_decision, build_assay_learning_report
from .database import initialize_database
from .feedback import _boolish, _float_or_none, import_feedback_rows
from .target_context import normalize_endpoint_group


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH = Path("data/substituents/evidence_residual_task_registry.json")
DEFAULT_RESIDUAL_RESULT_TEMPLATE_PATH = Path("data/projects/demo/residual_experiment_results_template.csv")
DEFAULT_EXPERIMENT_RESULT_IMPORT_MANIFEST_PATH = Path("data/projects/experiment_result_import_manifest.json")
DEMO_RESULT_MARKER = "DEMO_OBSERVED_RESULT_FOR_PIPELINE_VERIFICATION_NOT_LAB_DATA"
EXPERIMENT_STATUSES = ["planned", "completed", "failed", "retest"]

EXPERIMENT_PLAN_FIELDS = [
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
    "replicate_count",
    "replicate_cv",
    "assay_confidence",
    "assay_confidence_score",
    "stop_go_decision",
    "retest_reason",
    "result_recorded_at",
]
EXPERIMENT_RESULT_TEMPLATE_EXTRA_FIELDS = [
    "close_residual_task",
    "residual_task_id",
    "residual_task_priority",
    "residual_task_action",
    "target_family",
    "evidence_source",
]
EXPERIMENT_RESULT_PAYLOAD_FIELDS = [
    "value",
    "result_value",
    "normalized_score",
    "classification",
    "stop_go_decision",
]
EXPERIMENT_RESULT_IMPORT_STATUSES = {"completed", "failed", "retest"}


def read_experiment_plan_csv(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_experiment_import_report() -> dict:
    return {
        "processed_count": 0,
        "event_count": 0,
        "feedback_inserted_count": 0,
        "feedback_skipped_count": 0,
        "residual_task_updated_count": 0,
        "residual_task_closed_count": 0,
        "stop_go_counts": {},
        "retest_event_count": 0,
    }


def _read_result_import_manifest(path: str | Path | None) -> dict:
    if path is None:
        return {"imports": []}
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {"imports": []}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"imports": []}
    imports = payload.get("imports") if isinstance(payload, dict) else []
    return {"imports": [dict(row) for row in imports or [] if isinstance(row, dict)]}


def _write_result_import_manifest(path: str | Path, manifest: dict) -> None:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _manifest_entry_for_sha(manifest: dict, source_sha256: str) -> dict | None:
    for entry in manifest.get("imports") or []:
        if str(entry.get("source_sha256") or "") == source_sha256:
            return dict(entry)
    return None


def _append_result_import_manifest(
    path: str | Path,
    manifest: dict,
    *,
    source_path: str,
    source_sha256: str,
    report: dict,
    demo_source: bool,
) -> None:
    entries = list(manifest.get("imports") or [])
    if _manifest_entry_for_sha({"imports": entries}, source_sha256):
        return
    entries.append(
        {
            "imported_at": report.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "source_path": source_path,
            "source_sha256": source_sha256,
            "status": report.get("status"),
            "event_count": (report.get("import") or {}).get("event_count", 0),
            "validation_error_count": (report.get("validation") or {}).get("error_count", 0),
            "demo_source": bool(demo_source),
        }
    )
    _write_result_import_manifest(path, {"imports": entries})


def _looks_like_demo_result_source(path: str | Path, rows: Iterable[dict]) -> bool:
    name = Path(path).name.lower()
    if "demo_observed" in name or "demo_result" in name:
        return True
    for row in rows:
        values = " ".join(str(value) for value in dict(row).values() if value not in {None, ""})
        if DEMO_RESULT_MARKER in values:
            return True
    return False


def build_experiment_result_template_rows(plan_rows: Iterable[dict], *, blank_results: bool = True) -> list[dict]:
    rows = []
    for raw in plan_rows:
        row = dict(raw)
        template = {field: row.get(field, "") for field in EXPERIMENT_PLAN_FIELDS + EXPERIMENT_RESULT_TEMPLATE_EXTRA_FIELDS}
        if blank_results:
            for field in [
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
            ]:
                template[field] = ""
        if not blank_results:
            template["status"] = template.get("status") or "completed"
        template["close_residual_task"] = row.get("close_residual_task") or "false"
        rows.append(template)
    return rows


def write_experiment_result_template(
    plan_rows: Iterable[dict],
    output_path: str | Path = DEFAULT_RESIDUAL_RESULT_TEMPLATE_PATH,
    *,
    blank_results: bool = True,
) -> list[dict]:
    rows = build_experiment_result_template_rows(plan_rows, blank_results=blank_results)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    extras = sorted({key for row in rows for key in row if key not in EXPERIMENT_PLAN_FIELDS + EXPERIMENT_RESULT_TEMPLATE_EXTRA_FIELDS})
    fieldnames = EXPERIMENT_PLAN_FIELDS + EXPERIMENT_RESULT_TEMPLATE_EXTRA_FIELDS + extras
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return rows


def _clean_status(value: str | None, *, default: str = "planned") -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    aliases = {
        "complete": "completed",
        "done": "completed",
        "pass": "completed",
        "fail": "failed",
        "redo": "retest",
        "repeat": "retest",
    }
    text = aliases.get(text, text)
    return text if text in EXPERIMENT_STATUSES else default


def _text(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in {None, ""}:
            return str(value).strip()
    return ""


def _close_requested(row: dict) -> bool:
    return str(row.get("close_residual_task") or row.get("residual_task_status") or "").strip().lower() in {
        "true",
        "1",
        "yes",
        "closed",
        "close",
    }


def _has_result_payload(row: dict) -> bool:
    return any(_text(row, field) for field in EXPERIMENT_RESULT_PAYLOAD_FIELDS)


def validate_experiment_result_rows(
    rows: Iterable[dict],
    *,
    residual_only: bool = False,
    require_result_payload: bool = True,
) -> dict:
    """Validate result-import rows and identify rows safe to import.

    This intentionally treats the blank residual template as not importable. A
    completed result needs at least one measured/classified payload field.
    """
    materialized = [{str(key).strip(): value for key, value in dict(row).items()} for row in rows]
    issues: list[dict] = []
    importable_indices: list[int] = []
    status_counts: Counter = Counter()
    close_request_count = 0
    result_payload_count = 0
    blank_count = 0
    for index, row in enumerate(materialized, start=1):
        row_issues = []
        plan_id = _text(row, "plan_id")
        residual_task_id = _text(row, "residual_task_id")
        run_id = _text(row, "run_id")
        candidate_id = _text(row, "candidate_id")
        status = _clean_status(_text(row, "status", "result_status"), default="")
        has_payload = _has_result_payload(row)
        close_requested = _close_requested(row)
        has_identity = bool(plan_id or residual_task_id or (run_id and candidate_id))
        if status:
            status_counts[status] += 1
        if has_payload:
            result_payload_count += 1
        if close_requested:
            close_request_count += 1
        if not has_identity and not has_payload and not status:
            blank_count += 1
            issues.append(
                {
                    "row_number": index,
                    "severity": "warn",
                    "issue": "blank_row",
                    "message": "Row is empty and will be skipped.",
                }
            )
            continue
        if residual_only and not residual_task_id:
            row_issues.append(
                {
                    "severity": "error",
                    "issue": "missing_residual_task_id",
                    "message": "Residual result imports require residual_task_id.",
                }
            )
        if not has_identity:
            row_issues.append(
                {
                    "severity": "error",
                    "issue": "missing_plan_or_candidate_identity",
                    "message": "Provide plan_id, residual_task_id, or run_id + candidate_id.",
                }
            )
        if not status:
            row_issues.append(
                {
                    "severity": "error",
                    "issue": "missing_result_status",
                    "message": "Provide status/result_status as completed, failed, or retest.",
                }
            )
        elif status not in EXPERIMENT_RESULT_IMPORT_STATUSES:
            row_issues.append(
                {
                    "severity": "error",
                    "issue": "unsupported_result_status",
                    "message": f"Unsupported result status: {status}.",
                }
            )
        if require_result_payload and status == "completed" and not has_payload:
            row_issues.append(
                {
                    "severity": "error",
                    "issue": "completed_missing_result_payload",
                    "message": "Completed rows need result_value, normalized_score, classification, value, or stop_go_decision.",
                }
            )
        if close_requested and (status != "completed" or not has_payload):
            row_issues.append(
                {
                    "severity": "error",
                    "issue": "invalid_residual_close_request",
                    "message": "Residual tasks can only be closed by completed rows with result payload.",
                }
            )
        if not row_issues:
            importable_indices.append(index)
        for issue in row_issues:
            issues.append({"row_number": index, **issue})
    error_count = sum(1 for issue in issues if issue.get("severity") == "error")
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warn")
    status = "error" if error_count else "warn" if warning_count or not importable_indices else "pass"
    return {
        "status": status,
        "row_count": len(materialized),
        "importable_row_count": len(importable_indices),
        "skipped_row_count": len(materialized) - len(importable_indices),
        "blank_row_count": blank_count,
        "result_payload_count": result_payload_count,
        "close_request_count": close_request_count,
        "status_counts": dict(status_counts.most_common()),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
        "importable_row_indices": importable_indices,
    }


def _plan_id(row: dict) -> str:
    value = _text(row, "plan_id")
    if value:
        return value
    parts = [
        _text(row, "project_name") or "project",
        _text(row, "run_id") or "run",
        _text(row, "candidate_id") or "candidate",
        _text(row, "endpoint_group") or "endpoint",
        _text(row, "plan_rank") or uuid.uuid4().hex[:8].upper(),
    ]
    safe = "-".join(part.replace(" ", "_") for part in parts)
    return f"EPL-{safe}"[:96]


def _existing_plan(conn: sqlite3.Connection, plan_id: str) -> dict:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM project_experiment_plan WHERE plan_id=?", (plan_id,)).fetchone()
    return dict(row) if row else {}


def _payload_json(value: str | None) -> dict:
    try:
        payload = json.loads(value or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def upsert_experiment_plan_rows(
    rows: Iterable[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    source_path: str | None = None,
) -> dict:
    conn = initialize_database(db_path)
    try:
        upserted = _upsert_experiment_plan_rows_on_conn(conn, rows, source_path=source_path)
        conn.commit()
        return {"upserted_count": upserted}
    finally:
        conn.close()


def _upsert_experiment_plan_rows_on_conn(
    conn: sqlite3.Connection,
    rows: Iterable[dict],
    *,
    source_path: str | None = None,
    now: str | None = None,
) -> int:
    now = now or datetime.now(timezone.utc).isoformat()
    upserted = 0
    for raw in rows:
        row = {str(key).strip(): value for key, value in dict(raw).items()}
        plan_id = _plan_id(row)
        existing = _existing_plan(conn, plan_id)
        status = _clean_status(row.get("status"), default=existing.get("status") or "planned")
        created_at = _text(row, "created_at") or existing.get("created_at") or now
        conn.execute(
            """
            INSERT OR REPLACE INTO project_experiment_plan (
                plan_id, project_name, run_id, candidate_id, plan_rank, plan_role,
                endpoint_group, site_type, direction, enumeration_type, replacement_label,
                candidate_score, priority_score, rationale, owner, planned_assay,
                status, source_path, created_at, updated_at, notes, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                _text(row, "project_name") or existing.get("project_name"),
                _text(row, "run_id") or existing.get("run_id") or None,
                _text(row, "candidate_id") or existing.get("candidate_id") or None,
                int(float(row.get("plan_rank") or existing.get("plan_rank") or 0)),
                _text(row, "plan_role") or existing.get("plan_role") or "candidate_assay",
                _text(row, "endpoint_group") or existing.get("endpoint_group"),
                _text(row, "site_type") or existing.get("site_type"),
                _text(row, "direction") or existing.get("direction"),
                _text(row, "enumeration_type") or existing.get("enumeration_type"),
                _text(row, "replacement_label") or existing.get("replacement_label"),
                _float_or_none(row.get("candidate_score")) if row.get("candidate_score") not in {None, ""} else existing.get("candidate_score"),
                _float_or_none(row.get("priority_score")) if row.get("priority_score") not in {None, ""} else existing.get("priority_score"),
                _text(row, "rationale") or existing.get("rationale"),
                _text(row, "owner") or existing.get("owner"),
                _text(row, "planned_assay") or existing.get("planned_assay"),
                status,
                source_path or _text(row, "source_path") or existing.get("source_path"),
                created_at,
                now,
                _text(row, "notes", "note") or existing.get("notes"),
                json.dumps({**existing, **row, "plan_id": plan_id, "status": status}, sort_keys=True),
            ),
        )
        upserted += 1
    return upserted


def _lookup_plan(conn: sqlite3.Connection, row: dict) -> dict:
    plan_id = _text(row, "plan_id")
    conn.row_factory = sqlite3.Row
    if plan_id:
        plan = conn.execute("SELECT * FROM project_experiment_plan WHERE plan_id=?", (plan_id,)).fetchone()
        if plan:
            return dict(plan)
    run_id = _text(row, "run_id")
    candidate_id = _text(row, "candidate_id")
    endpoint = _text(row, "endpoint_group", "endpoint")
    if run_id and candidate_id:
        plan = conn.execute(
            """
            SELECT * FROM project_experiment_plan
            WHERE run_id=? AND candidate_id=? AND COALESCE(endpoint_group, '')=COALESCE(NULLIF(?, ''), endpoint_group, '')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (run_id, candidate_id, endpoint),
        ).fetchone()
        if plan:
            return dict(plan)
    return {}


def _result_feedback_row(row: dict, plan: dict, source_path: str | None) -> dict | None:
    run_id = _text(row, "run_id") or plan.get("run_id")
    candidate_id = _text(row, "candidate_id") or plan.get("candidate_id")
    if not run_id or not candidate_id:
        return None
    has_value = any(row.get(key) not in {None, ""} for key in ["value", "result_value", "normalized_score", "classification"])
    if not has_value:
        return None
    plan_id = _text(row, "plan_id") or plan.get("plan_id")
    return {
        "feedback_id": _text(row, "feedback_id") or (f"FBK-{plan_id}" if plan_id else ""),
        "run_id": run_id,
        "candidate_id": candidate_id,
        "project_name": _text(row, "project_name") or plan.get("project_name"),
        "assay_name": _text(row, "assay_name", "planned_assay") or plan.get("planned_assay"),
        "assay_type": _text(row, "assay_type"),
        "endpoint": _text(row, "endpoint", "endpoint_group") or plan.get("endpoint_group"),
        "value": _text(row, "value", "result_value"),
        "unit": _text(row, "unit", "result_unit"),
        "relation": _text(row, "relation", "result_relation"),
        "higher_is_better": row.get("higher_is_better"),
        "normalized_score": row.get("normalized_score"),
        "classification": _text(row, "classification"),
        "source_path": source_path or _text(row, "source_path"),
        "note": _text(row, "notes", "note"),
        "recorded_at": _text(row, "recorded_at", "result_recorded_at"),
    }


def import_experiment_results_rows(
    rows: Iterable[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    source_path: str | None = None,
    update_feedback: bool = True,
    residual_task_registry_path: str | Path | None = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
) -> dict:
    conn = initialize_database(db_path)
    now = datetime.now(timezone.utc).isoformat()
    processed = 0
    inserted_events = 0
    feedback_rows: list[dict] = []
    residual_result_rows: list[dict] = []
    try:
        for raw in rows:
            row = {str(key).strip(): value for key, value in dict(raw).items()}
            plan = _lookup_plan(conn, row)
            if not plan:
                plan_id = _plan_id(row)
                _upsert_experiment_plan_rows_on_conn(conn, [row], source_path=source_path, now=now)
                plan = _lookup_plan(conn, {**row, "plan_id": plan_id})
            plan_id = _text(row, "plan_id") or plan.get("plan_id") or _plan_id(row)
            plan_payload = _payload_json(plan.get("payload_json"))
            residual_task_id = _text(row, "residual_task_id") or str(plan_payload.get("residual_task_id") or "")
            if residual_task_id:
                row["residual_task_id"] = residual_task_id
            status = _clean_status(_text(row, "status", "result_status"), default=plan.get("status") or "planned")
            run_id = _text(row, "run_id") or plan.get("run_id")
            candidate_id = _text(row, "candidate_id") or plan.get("candidate_id")
            endpoint = _text(row, "endpoint_group", "endpoint") or plan.get("endpoint_group")
            assay_decision = assay_result_decision(row, endpoint_group=endpoint)
            endpoint_standard = assay_decision.get("endpoint_group_standard") or normalize_endpoint_group(endpoint) or endpoint
            plan_status = "retest" if assay_decision["stop_go_decision"] == "retest" else status
            conn.execute(
                """
                UPDATE project_experiment_plan
                SET status=?, last_stop_go_decision=?, last_assay_confidence=?,
                    last_assay_confidence_score=?, last_retest_reason=?,
                    owner=COALESCE(NULLIF(?, ''), owner),
                    planned_assay=COALESCE(NULLIF(?, ''), planned_assay),
                    notes=COALESCE(NULLIF(?, ''), notes),
                    updated_at=?
                WHERE plan_id=?
                """,
                (
                    plan_status,
                    assay_decision["stop_go_decision"],
                    assay_decision["assay_confidence"],
                    assay_decision["assay_confidence_score"],
                    assay_decision["retest_reason"],
                    _text(row, "owner"),
                    _text(row, "planned_assay", "assay_name"),
                    _text(row, "notes", "note"),
                    now,
                    plan_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO project_experiment_event (
                    event_id, plan_id, run_id, candidate_id, status, endpoint_group,
                    assay_name, assay_type, value, unit, relation, higher_is_better,
                    normalized_score, classification, replicate_count, replicate_cv,
                    assay_confidence, assay_confidence_score, stop_go_decision,
                    retest_reason, source_path, note, recorded_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"EXP-{uuid.uuid4().hex[:12].upper()}",
                    plan_id,
                    run_id,
                    candidate_id,
                    status,
                    endpoint_standard,
                    _text(row, "assay_name", "planned_assay") or plan.get("planned_assay"),
                    _text(row, "assay_type"),
                    _float_or_none(_text(row, "value", "result_value")),
                    _text(row, "unit", "result_unit"),
                    _text(row, "relation", "result_relation"),
                    1 if _boolish(row.get("higher_is_better")) else 0,
                    _float_or_none(row.get("normalized_score")),
                    _text(row, "classification"),
                    assay_decision["replicate_count"],
                    assay_decision["replicate_cv"],
                    assay_decision["assay_confidence"],
                    assay_decision["assay_confidence_score"],
                    assay_decision["stop_go_decision"],
                    assay_decision["retest_reason"],
                    source_path or _text(row, "source_path"),
                    _text(row, "notes", "note"),
                    _text(row, "recorded_at", "result_recorded_at") or now,
                    json.dumps({**row, "plan_id": plan_id, "status": status, "assay_decision": assay_decision}, sort_keys=True),
                ),
            )
            processed += 1
            inserted_events += 1
            if residual_task_id:
                residual_result_rows.append({**row, "plan_id": plan_id, "status": status})
            if update_feedback and status == "completed":
                feedback = _result_feedback_row(row, plan, source_path)
                if feedback:
                    feedback_rows.append(feedback)
        conn.commit()
    finally:
        conn.close()

    feedback_report = {"inserted_count": 0, "skipped_count": 0}
    if feedback_rows:
        feedback_report = import_feedback_rows(feedback_rows, db_path=db_path, source_path=source_path)
    residual_task_report = {"updated_task_count": 0, "closed_task_count": 0}
    if residual_result_rows and residual_task_registry_path is not None:
        from .evidence_confidence import update_residual_tasks_from_experiment_results

        registry = update_residual_tasks_from_experiment_results(
            residual_result_rows,
            registry_path=residual_task_registry_path,
            reviewer="experiment_results_import",
        )
        residual_task_report = registry.get("last_result_sync") or residual_task_report
    learning_report = build_assay_learning_report(db_path=db_path)
    return {
        "processed_count": processed,
        "event_count": inserted_events,
        "feedback_inserted_count": feedback_report.get("inserted_count", 0),
        "feedback_skipped_count": feedback_report.get("skipped_count", 0),
        "residual_task_updated_count": residual_task_report.get("updated_task_count", 0),
        "residual_task_closed_count": residual_task_report.get("closed_task_count", 0),
        "stop_go_counts": learning_report.get("decision_counts", {}),
        "retest_event_count": len(learning_report.get("retest_events") or []),
    }


def import_experiment_results_csv(
    path: str | Path,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    update_feedback: bool = True,
    residual_task_registry_path: str | Path | None = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
) -> dict:
    source = str(Path(path).resolve())
    return import_experiment_results_rows(
        read_experiment_plan_csv(path),
        db_path=db_path,
        source_path=source,
        update_feedback=update_feedback,
        residual_task_registry_path=residual_task_registry_path,
    )


def import_residual_experiment_results_rows(
    rows: Iterable[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    source_path: str | None = None,
    update_feedback: bool = True,
    residual_task_registry_path: str | Path | None = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    strict: bool = False,
) -> dict:
    materialized = [{str(key).strip(): value for key, value in dict(row).items()} for row in rows]
    validation = validate_experiment_result_rows(materialized, residual_only=True)
    if strict and validation["error_count"]:
        raise ValueError(f"Residual result CSV has {validation['error_count']} validation errors.")
    importable = [
        materialized[index - 1]
        for index in validation.get("importable_row_indices") or []
        if 0 < int(index) <= len(materialized)
    ]
    import_report = _empty_experiment_import_report()
    if importable:
        import_report = import_experiment_results_rows(
            importable,
            db_path=db_path,
            source_path=source_path,
            update_feedback=update_feedback,
            residual_task_registry_path=residual_task_registry_path,
        )
    status = (
        "imported_with_validation_errors"
        if import_report.get("event_count") and validation.get("error_count")
        else "imported"
        if import_report.get("event_count")
        else "validation_failed"
        if validation.get("error_count")
        else "no_importable_results"
    )
    registry_snapshot = {}
    if residual_task_registry_path is not None and Path(residual_task_registry_path).exists():
        try:
            registry_snapshot = json.loads(Path(residual_task_registry_path).read_text(encoding="utf-8")) or {}
        except Exception:
            registry_snapshot = {}
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_path": source_path,
        "validation": validation,
        "import": import_report,
        "residual_task_status_counts": registry_snapshot.get("status_counts") or {},
        "residual_task_count": registry_snapshot.get("task_count", 0),
    }


def import_residual_experiment_results_csv(
    path: str | Path,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    update_feedback: bool = True,
    residual_task_registry_path: str | Path | None = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    strict: bool = False,
    import_manifest_path: str | Path | None = DEFAULT_EXPERIMENT_RESULT_IMPORT_MANIFEST_PATH,
    allow_duplicate_source: bool = False,
    require_production_source: bool = False,
) -> dict:
    source_path = Path(path).resolve()
    rows = read_experiment_plan_csv(source_path)
    source_sha256 = _file_sha256(source_path)
    demo_source = _looks_like_demo_result_source(source_path, rows)
    validation = validate_experiment_result_rows(rows, residual_only=True)
    if require_production_source and demo_source:
        if strict:
            return {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "demo_source_rejected",
                "source_path": str(source_path),
                "source_sha256": source_sha256,
                "demo_source": True,
                "validation": validation,
                "import": _empty_experiment_import_report(),
                "residual_task_status_counts": {},
                "residual_task_count": 0,
            }
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "demo_source_rejected",
            "source_path": str(source_path),
            "source_sha256": source_sha256,
            "demo_source": True,
            "validation": validation,
            "import": _empty_experiment_import_report(),
            "residual_task_status_counts": {},
            "residual_task_count": 0,
        }

    manifest = _read_result_import_manifest(import_manifest_path)
    existing_entry = _manifest_entry_for_sha(manifest, source_sha256) if import_manifest_path is not None else None
    if existing_entry and not allow_duplicate_source:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "duplicate_source_skipped",
            "source_path": str(source_path),
            "source_sha256": source_sha256,
            "demo_source": bool(demo_source),
            "existing_import": existing_entry,
            "validation": validation,
            "import": _empty_experiment_import_report(),
            "residual_task_status_counts": {},
            "residual_task_count": 0,
        }

    report = import_residual_experiment_results_rows(
        rows,
        db_path=db_path,
        source_path=str(source_path),
        update_feedback=update_feedback,
        residual_task_registry_path=residual_task_registry_path,
        strict=strict,
    )
    report["source_sha256"] = source_sha256
    report["demo_source"] = bool(demo_source)
    report["import_manifest_path"] = str(Path(import_manifest_path).resolve()) if import_manifest_path is not None else None
    if import_manifest_path is not None and (report.get("import") or {}).get("event_count", 0):
        _append_result_import_manifest(
            import_manifest_path,
            manifest,
            source_path=str(source_path),
            source_sha256=source_sha256,
            report=report,
            demo_source=demo_source,
        )
    return report


def summarize_experiment_plans(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> dict:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params: tuple = ()
        where = ""
        if project_name:
            where = "WHERE project_name=?"
            params = (project_name,)
        plans = [dict(row) for row in conn.execute(f"SELECT * FROM project_experiment_plan {where}", params).fetchall()]
        events = [dict(row) for row in conn.execute("SELECT * FROM project_experiment_event").fetchall()]
    finally:
        conn.close()

    status_counts = Counter(row.get("status") or "unknown" for row in plans)
    endpoint_counts = Counter(row.get("endpoint_group") or "unspecified" for row in plans)
    event_counts = Counter(row.get("status") or "unknown" for row in events)
    decision_counts = Counter(row.get("stop_go_decision") or "unclassified" for row in events)
    confidence_counts = Counter(row.get("assay_confidence") or "unknown" for row in events)
    return {
        "project_name": project_name,
        "plan_count": len(plans),
        "event_count": len(events),
        "status_counts": dict(status_counts.most_common()),
        "endpoint_counts": dict(endpoint_counts.most_common()),
        "event_status_counts": dict(event_counts.most_common()),
        "stop_go_counts": dict(decision_counts.most_common()),
        "assay_confidence_counts": dict(confidence_counts.most_common()),
        "open_plan_count": sum(status_counts.get(status, 0) for status in ["planned", "retest"]),
        "assay_learning": build_assay_learning_report(db_path=db_path, project_name=project_name),
    }


def write_experiment_tracking_report(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
