from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .experiment_tracking import validate_experiment_result_rows


DEFAULT_RING_OUTCOME_PLAN_PATH = Path("data/projects/demo/ring_outcome_experiment_plan.csv")
DEFAULT_RING_OUTCOME_RESULT_TEMPLATE_PATH = Path("data/projects/demo/ring_outcome_results_template.csv")
DEFAULT_RING_OUTCOME_INTAKE_MANIFEST_PATH = Path("data/projects/demo/ring_outcome_result_intake_manifest.json")
DEFAULT_RING_OUTCOME_LEARNING_PATH = Path("data/projects/demo/ring_outcome_learning_report.json")
DEFAULT_RING_OUTCOME_OVERLAY_PATH = Path("data/profiles/calibrated/ring_outcome_scoring_overlay.json")
DEFAULT_RING_OUTCOME_ACTIVATION_PATH = Path("data/profiles/calibrated/ring_outcome_overlay_activation.json")
DEFAULT_RING_OUTCOME_REPLAY_PATH = Path("data/projects/demo/ring_outcome_overlay_replay.json")
DEFAULT_RING_OUTCOME_PRODUCTION_READINESS_PATH = Path("data/projects/demo/ring_outcome_production_readiness.json")
DEFAULT_RING_OUTCOME_PRODUCTION_READINESS_CSV_PATH = Path("data/projects/demo/ring_outcome_production_readiness.csv")
DEFAULT_RING_OUTCOME_RESULT_PACKAGE_DIR = Path("data/projects/demo/ring_outcome_result_drops")
DEFAULT_RING_OUTCOME_RESULT_PACKAGE_PATH = Path("data/projects/demo/ring_outcome_result_package.json")
DEFAULT_RING_OUTCOME_RESULT_PACKAGE_CSV_PATH = Path("data/projects/demo/ring_outcome_result_package.csv")
DEFAULT_RING_OUTCOME_RESULT_PACKAGE_REVIEW_PATH = Path("data/projects/demo/ring_outcome_result_package_review.json")
DEFAULT_RING_OUTCOME_RESULT_PACKAGE_REVIEW_CSV_PATH = Path("data/projects/demo/ring_outcome_result_package_review.csv")
DEFAULT_RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH = Path("data/projects/demo/ring_outcome_result_drops/production_ring_outcome_results_pending.csv")
DEFAULT_RING_OUTCOME_RESULT_PACKAGE_IMPORT_GATE_PATH = Path("data/projects/demo/ring_outcome_result_package_import_gate.json")
RING_OUTCOME_PAYLOAD_FIELDS = ["result_value", "value", "classification", "normalized_score", "stop_go_decision"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(path: str | Path) -> list[dict]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _is_template_source(path: str | Path | None) -> bool:
    if not path:
        return True
    name = Path(path).name.lower()
    return "template" in name or "demo_result" in name or "demo_observed" in name


def _payload_present(row: dict) -> bool:
    return any(
        str(row.get(field) or "").strip()
        for field in ["value", "result_value", "normalized_score", "classification", "stop_go_decision"]
    )


def _row_state(row: dict, validation: dict, row_number: int) -> str:
    importable = {int(index) for index in validation.get("importable_row_indices") or []}
    row_errors = [
        issue
        for issue in validation.get("issues") or []
        if int(issue.get("row_number") or 0) == row_number and issue.get("severity") == "error"
    ]
    if row_number in importable:
        return "importable"
    if _payload_present(row) or str(row.get("status") or "").strip():
        return "blocked_by_validation" if row_errors else "not_importable"
    return "awaiting_result_payload"


def build_ring_outcome_production_readiness(
    *,
    plan_path: str | Path = DEFAULT_RING_OUTCOME_PLAN_PATH,
    result_csv: str | Path = DEFAULT_RING_OUTCOME_RESULT_TEMPLATE_PATH,
    intake_manifest_path: str | Path = DEFAULT_RING_OUTCOME_INTAKE_MANIFEST_PATH,
    learning_path: str | Path = DEFAULT_RING_OUTCOME_LEARNING_PATH,
    overlay_path: str | Path = DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    activation_path: str | Path = DEFAULT_RING_OUTCOME_ACTIVATION_PATH,
    replay_path: str | Path = DEFAULT_RING_OUTCOME_REPLAY_PATH,
) -> dict:
    """Build the production gate for ring-outcome result intake and overlay activation.

    This report does not synthesize or infer assay outcomes. It only says whether
    the current ring outcome loop has real importable rows, activation-ready
    contexts, or an explicit wait state.
    """
    plan_rows = _read_csv_rows(plan_path)
    result_rows = _read_csv_rows(result_csv)
    validation = validate_experiment_result_rows(result_rows, residual_only=True) if result_rows else {}
    intake = _read_json(intake_manifest_path)
    learning = _read_json(learning_path)
    overlay = _read_json(overlay_path)
    activation = _read_json(activation_path)
    replay = _read_json(replay_path)

    importable_count = int((validation or {}).get("importable_row_count") or 0)
    raw_validation_error_count = int((validation or {}).get("error_count") or 0)
    material_validation_errors = [
        issue
        for issue in validation.get("issues") or []
        if issue.get("severity") == "error"
        and 0 < int(issue.get("row_number") or 0) <= len(result_rows)
        and (_payload_present(result_rows[int(issue.get("row_number") or 0) - 1]) or str(result_rows[int(issue.get("row_number") or 0) - 1].get("status") or "").strip())
    ]
    validation_error_count = len(material_validation_errors)
    payload_count = int((validation or {}).get("result_payload_count") or 0)
    pending_result_count = sum(1 for row in result_rows if not _payload_present(row) and not str(row.get("status") or "").strip())
    template_source = _is_template_source(result_csv)
    active_nonzero = int(activation.get("active_nonzero_context_count") or 0)
    activation_status = str(activation.get("status") or "missing")

    blockers: list[str] = []
    if template_source:
        blockers.append("result_source_is_template_or_demo_named")
    if not importable_count:
        blockers.append("no_importable_real_result_rows")
    if validation_error_count:
        blockers.append("result_validation_errors")
    if active_nonzero <= 0:
        blockers.append("no_active_nonzero_ring_outcome_context")
    if activation_status == "blocked":
        blockers.extend(str(item) for item in activation.get("blockers") or [])

    if activation_status == "activated" and active_nonzero:
        status = "activated"
    elif importable_count and not validation_error_count and not template_source:
        status = "ready_for_strict_import"
    elif result_rows or plan_rows:
        status = "awaiting_production_results"
    else:
        status = "no_ring_outcome_plan"

    gate_status = "pass" if status in {"activated", "ready_for_strict_import", "awaiting_production_results"} else "warn"
    if status == "ready_for_strict_import" and active_nonzero <= 0:
        gate_status = "pass"
    if validation_error_count:
        gate_status = "fail"

    rows = []
    plan_by_id = {str(row.get("plan_id") or ""): row for row in plan_rows}
    for index, row in enumerate(result_rows, start=1):
        plan = plan_by_id.get(str(row.get("plan_id") or ""), {})
        rows.append(
            {
                "row_number": index,
                "plan_id": row.get("plan_id") or plan.get("plan_id") or "",
                "residual_task_id": row.get("residual_task_id") or plan.get("residual_task_id") or "",
                "endpoint_group": row.get("endpoint_group") or plan.get("endpoint_group") or "",
                "enumeration_type": row.get("enumeration_type") or plan.get("enumeration_type") or "",
                "replacement_label": row.get("replacement_label") or plan.get("replacement_label") or "",
                "status": row.get("status") or "",
                "has_result_payload": _payload_present(row),
                "readiness_state": _row_state(row, validation, index),
            }
        )

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "gate_status": gate_status,
        "plan_path": str(plan_path),
        "result_csv": str(result_csv),
        "result_source_kind": "template_or_demo" if template_source else "candidate_production_source",
        "plan_row_count": len(plan_rows),
        "result_row_count": len(result_rows),
        "pending_result_count": pending_result_count,
        "result_payload_count": payload_count,
        "importable_result_count": importable_count,
        "validation_error_count": validation_error_count,
        "raw_validation_error_count": raw_validation_error_count,
        "intake_status": intake.get("status") or "",
        "learning_status": learning.get("status") or "",
        "observed_outcome_count": learning.get("observed_outcome_count"),
        "overlay_context_count": overlay.get("context_count"),
        "overlay_active_context_count": overlay.get("active_context_count"),
        "activation_status": activation_status,
        "active_nonzero_context_count": active_nonzero,
        "replay_status": replay.get("status") or activation.get("replay_status") or "",
        "blockers": sorted(set(blockers)),
        "validation": validation,
        "rows": rows,
        "strict_import_command": (
            f"python scripts/import_ring_outcome_results.py --csv {Path(result_csv)} "
            "--strict --require-production-source --no-feedback"
        ),
        "recommended_next_actions": [
            "Fill a production-named ring outcome result CSV with measured payload before strict import.",
            "Run strict import with --require-production-source so blank templates and demo-named files cannot activate scoring.",
            "Approve only replay-backed nonzero contexts before activation; keep zero/blocked contexts as residual tasks.",
        ],
    }


def write_ring_outcome_production_readiness(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_PRODUCTION_READINESS_PATH,
    csv_path: str | Path | None = DEFAULT_RING_OUTCOME_PRODUCTION_READINESS_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fields = [
        "row_number",
        "plan_id",
        "residual_task_id",
        "endpoint_group",
        "enumeration_type",
        "replacement_label",
        "status",
        "has_result_payload",
        "readiness_state",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_ring_outcome_result_package(
    *,
    plan_path: str | Path = DEFAULT_RING_OUTCOME_PLAN_PATH,
    output_dir: str | Path = DEFAULT_RING_OUTCOME_RESULT_PACKAGE_DIR,
    result_csv: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    """Create or validate a production-named ring outcome result CSV package.

    The package contains blank result slots copied from the ring outcome plan.
    It does not create measured outcomes; it is only a guarded intake target for
    future real assay or ADME payloads.
    """
    plan_rows = _read_csv_rows(plan_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = Path(result_csv) if result_csv is not None else out_dir / DEFAULT_RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH.name
    if not result_path.exists() or overwrite:
        template_path = Path(DEFAULT_RING_OUTCOME_RESULT_TEMPLATE_PATH)
        template_rows = _read_csv_rows(template_path)
        rows = plan_rows if plan_rows else template_rows
        fields = list(rows[0].keys()) if rows else [
            "plan_id",
            "residual_task_id",
            "endpoint_group",
            "enumeration_type",
            "replacement_label",
            "status",
            "result_value",
            "classification",
            "normalized_score",
            "stop_go_decision",
            "close_residual_task",
        ]
        for field in ["status", "result_value", "classification", "normalized_score", "stop_go_decision", "close_residual_task"]:
            if field not in fields:
                fields.append(field)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with result_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                item = {field: row.get(field, "") for field in fields}
                for field in ["status", "result_value", "classification", "normalized_score", "stop_go_decision"]:
                    item[field] = ""
                item["close_residual_task"] = "false"
                writer.writerow(item)
    readiness = build_ring_outcome_production_readiness(plan_path=plan_path, result_csv=result_path)
    if readiness.get("status") == "ready_for_strict_import":
        status = "ready_for_strict_import"
    elif readiness.get("validation_error_count"):
        status = "blocked_by_validation"
    elif readiness.get("result_row_count"):
        status = "awaiting_result_payload"
    else:
        status = "no_ring_outcome_plan"
    rows = [dict(row) for row in readiness.get("rows") or []]
    manifest_path = result_path.with_suffix(".manifest.json")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "result_csv": str(result_path),
        "plan_path": str(plan_path),
        "row_count": len(rows),
        "strict_import_command": readiness.get("strict_import_command"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "created_at": manifest["created_at"],
        "status": status,
        "result_csv": str(result_path),
        "manifest_path": str(manifest_path),
        "plan_path": str(plan_path),
        "plan_row_count": len(plan_rows),
        "result_row_count": readiness.get("result_row_count"),
        "pending_result_count": readiness.get("pending_result_count"),
        "importable_result_count": readiness.get("importable_result_count"),
        "validation_error_count": readiness.get("validation_error_count"),
        "result_source_kind": readiness.get("result_source_kind"),
        "strict_import_command": readiness.get("strict_import_command"),
        "rows": rows,
        "recommended_next_actions": [
            "Fill this production-named CSV with real measured result payloads.",
            "Run the strict import command only after importable_result_count is nonzero.",
            "Do not use the blank package rows as experimental evidence.",
        ],
    }


def write_ring_outcome_result_package(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_RESULT_PACKAGE_PATH,
    csv_path: str | Path | None = DEFAULT_RING_OUTCOME_RESULT_PACKAGE_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    fields = [
        "row_number",
        "plan_id",
        "residual_task_id",
        "endpoint_group",
        "enumeration_type",
        "replacement_label",
        "status",
        "has_result_payload",
        "readiness_state",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_ring_outcome_result_package_review(
    *,
    package_path: str | Path = DEFAULT_RING_OUTCOME_RESULT_PACKAGE_PATH,
    import_gate_path: str | Path = DEFAULT_RING_OUTCOME_RESULT_PACKAGE_IMPORT_GATE_PATH,
) -> dict:
    """Build an operator review view for a ring outcome result package."""
    package = _read_json(package_path)
    import_gate = _read_json(import_gate_path)
    result_csv = Path(package.get("result_csv") or DEFAULT_RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH)
    csv_rows = _read_csv_rows(result_csv)
    validation = validate_experiment_result_rows(csv_rows, residual_only=True) if csv_rows else {}
    importable_indices = {int(index) for index in validation.get("importable_row_indices") or []}
    validation_errors_by_row: dict[int, list[str]] = {}
    for issue in validation.get("issues") or []:
        if issue.get("severity") != "error":
            continue
        row_number = int(issue.get("row_number") or 0)
        csv_row = csv_rows[row_number - 1] if 0 < row_number <= len(csv_rows) else {}
        if not (_payload_present(csv_row) or str(csv_row.get("status") or "").strip()):
            continue
        validation_errors_by_row.setdefault(row_number, []).append(str(issue.get("message") or issue.get("issue") or issue))

    package_rows = [dict(row) for row in package.get("rows") or []]
    if package_rows:
        source_rows = package_rows
    else:
        source_rows = [
            {
                "row_number": index,
                "plan_id": row.get("plan_id", ""),
                "residual_task_id": row.get("residual_task_id", ""),
                "endpoint_group": row.get("endpoint_group", ""),
                "enumeration_type": row.get("enumeration_type", ""),
                "replacement_label": row.get("replacement_label", ""),
                "status": row.get("status", ""),
                "has_result_payload": _payload_present(row),
            }
            for index, row in enumerate(csv_rows, start=1)
        ]

    review_rows: list[dict] = []
    for index, row in enumerate(source_rows, start=1):
        row_number = int(row.get("row_number") or index)
        csv_row = csv_rows[row_number - 1] if 0 < row_number <= len(csv_rows) else {}
        state = str(row.get("readiness_state") or (_row_state(csv_row, validation, row_number) if csv_row else "awaiting_result_payload"))
        has_payload = bool(row.get("has_result_payload") or _payload_present(csv_row))
        missing_payload_fields = [
            field
            for field in RING_OUTCOME_PAYLOAD_FIELDS
            if field in (csv_row.keys() if csv_row else RING_OUTCOME_PAYLOAD_FIELDS) and not str(csv_row.get(field) or "").strip()
        ]
        errors = validation_errors_by_row.get(row_number, [])
        if state == "importable" or row_number in importable_indices:
            action = "run_strict_import_after_operator_review"
        elif errors:
            action = "fix_validation_errors"
        elif not has_payload:
            action = "fill_real_result_payload"
        else:
            action = "review_not_importable_payload"
        review_rows.append(
            {
                "row_number": row_number,
                "plan_id": row.get("plan_id") or csv_row.get("plan_id", ""),
                "residual_task_id": row.get("residual_task_id") or csv_row.get("residual_task_id", ""),
                "endpoint_group": row.get("endpoint_group") or csv_row.get("endpoint_group", ""),
                "enumeration_type": row.get("enumeration_type") or csv_row.get("enumeration_type", ""),
                "replacement_label": row.get("replacement_label") or csv_row.get("replacement_label", ""),
                "readiness_state": "importable" if row_number in importable_indices else state,
                "has_result_payload": has_payload,
                "missing_payload_fields": missing_payload_fields,
                "validation_errors": errors,
                "action": action,
            }
        )

    pending_count = sum(1 for row in review_rows if row.get("action") == "fill_real_result_payload")
    validation_error_count = sum(1 for row in review_rows if row.get("validation_errors"))
    importable_count = sum(1 for row in review_rows if row.get("readiness_state") == "importable")
    if validation_error_count or import_gate.get("status") == "import_failed":
        status = "blocked_by_validation"
    elif importable_count:
        status = "ready_for_strict_import"
    elif review_rows:
        status = "awaiting_result_payload"
    else:
        status = "no_ring_outcome_plan"

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "package_status": package.get("status") or "missing",
        "import_gate_status": import_gate.get("status") or "missing",
        "result_csv": str(result_csv),
        "result_csv_exists": result_csv.exists(),
        "row_count": len(review_rows),
        "pending_result_count": pending_count,
        "importable_result_count": importable_count,
        "validation_error_count": validation_error_count,
        "import_attempted": bool(import_gate.get("import_attempted")),
        "import_returncode": import_gate.get("import_returncode"),
        "rows": review_rows,
        "recommended_next_actions": [
            "Fill result_value/classification/normalized_score fields only from real measured ring outcome payloads.",
            "Run strict import only when importable_result_count is nonzero and validation_error_count is zero.",
            "After import, rebuild ring learning, overlay replay, holdout, production dashboard, and production CI.",
        ],
    }


def write_ring_outcome_result_package_review(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_RING_OUTCOME_RESULT_PACKAGE_REVIEW_PATH,
    csv_path: str | Path | None = DEFAULT_RING_OUTCOME_RESULT_PACKAGE_REVIEW_CSV_PATH,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    fields = [
        "row_number",
        "plan_id",
        "residual_task_id",
        "endpoint_group",
        "enumeration_type",
        "replacement_label",
        "readiness_state",
        "has_result_payload",
        "missing_payload_fields",
        "validation_errors",
        "action",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: ";".join(row.get(field) or []) if isinstance(row.get(field), list) else row.get(field, "") for field in fields})
