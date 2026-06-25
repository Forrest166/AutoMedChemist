from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .experiment_tracking import read_experiment_plan_csv, validate_experiment_result_rows


DEFAULT_RESIDUAL_EXPERIMENT_PLAN_PATH = Path("data/projects/demo/residual_experiment_plan.csv")
DEFAULT_RESIDUAL_RESULT_TEMPLATE_PATH = Path("data/projects/demo/residual_experiment_results_template.csv")
DEFAULT_RESIDUAL_RESULT_INTAKE_MANIFEST_PATH = Path("data/projects/demo/residual_result_intake_manifest.json")
DEFAULT_RESIDUAL_RESULT_INTAKE_CSV_PATH = Path("data/projects/demo/residual_result_intake_manifest.csv")
DEFAULT_RESIDUAL_TASK_REGISTRY_PATH = Path("data/substituents/evidence_residual_task_registry.json")

REQUIRED_REAL_RESULT_FIELDS = [
    "status",
    "residual_task_id",
    "result_value|normalized_score|classification|stop_go_decision",
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


def _payload_present(row: dict) -> bool:
    return any(str(row.get(field) or "").strip() for field in ["value", "result_value", "normalized_score", "classification", "stop_go_decision"])


def _task_lookup(registry: dict) -> dict[str, dict]:
    return {str(row.get("task_id") or ""): dict(row) for row in registry.get("tasks") or [] if row.get("task_id")}


def build_residual_result_intake_manifest(
    *,
    plan_path: str | Path = DEFAULT_RESIDUAL_EXPERIMENT_PLAN_PATH,
    result_csv: str | Path | None = None,
    registry_path: str | Path = DEFAULT_RESIDUAL_TASK_REGISTRY_PATH,
) -> dict:
    """Build a real-result intake checklist without fabricating assay payloads."""
    plan_file = Path(plan_path)
    registry = _read_json(registry_path)
    registry_by_id = _task_lookup(registry)
    plan_rows = read_experiment_plan_csv(plan_file) if plan_file.exists() else []
    result_rows = read_experiment_plan_csv(result_csv) if result_csv and Path(result_csv).exists() else []
    validation = validate_experiment_result_rows(result_rows, residual_only=True) if result_rows else {}

    rows = []
    for row in plan_rows:
        residual_task_id = str(row.get("residual_task_id") or "")
        task = registry_by_id.get(residual_task_id, {})
        rows.append(
            {
                "plan_id": row.get("plan_id"),
                "residual_task_id": residual_task_id,
                "residual_task_status": task.get("status") or "",
                "priority": task.get("priority") or row.get("residual_task_priority") or "",
                "project_name": row.get("project_name"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family") or task.get("target_family") or "",
                "assay_type": row.get("assay_type") or task.get("assay_type") or "",
                "planned_assay": row.get("planned_assay"),
                "required_status_values": "completed|failed|retest",
                "required_payload_rule": REQUIRED_REAL_RESULT_FIELDS[-1],
                "close_allowed_when": "status=completed and real payload is present",
                "current_intake_state": "awaiting_real_result_payload",
            }
        )

    importable_count = int((validation or {}).get("importable_row_count") or 0)
    error_count = int((validation or {}).get("error_count") or 0)
    payload_count = int((validation or {}).get("result_payload_count") or 0)
    close_count = int((validation or {}).get("close_request_count") or 0)
    status = "awaiting_real_results"
    if result_rows:
        if importable_count and not error_count:
            status = "ready_for_import"
        elif importable_count and error_count:
            status = "partially_ready_for_import"
        else:
            status = "validation_failed" if error_count else "no_importable_results"

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "plan_path": str(plan_file),
        "result_csv": str(Path(result_csv)) if result_csv else None,
        "required_real_result_fields": REQUIRED_REAL_RESULT_FIELDS,
        "plan_row_count": len(plan_rows),
        "pending_intake_count": sum(1 for row in rows if row["residual_task_status"] in {"open", "planned", ""}),
        "result_row_count": len(result_rows),
        "result_payload_count": payload_count,
        "close_request_count": close_count,
        "importable_row_count": importable_count,
        "validation_error_count": error_count,
        "validation": validation,
        "rows": rows,
        "recommended_next_actions": [
            "Fill the residual result template with measured assay outcomes before import.",
            "Do not close residual tasks from blank templates or status-only completed rows.",
            "Use close_residual_task=true only when completed rows include measured/classified payload.",
        ],
    }


def write_residual_result_intake_manifest(
    manifest: dict,
    output_path: str | Path = DEFAULT_RESIDUAL_RESULT_INTAKE_MANIFEST_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_RESIDUAL_RESULT_INTAKE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in manifest.get("rows") or []]
    fieldnames = [
        "plan_id",
        "residual_task_id",
        "residual_task_status",
        "priority",
        "project_name",
        "endpoint_group",
        "target_family",
        "assay_type",
        "planned_assay",
        "required_status_values",
        "required_payload_rule",
        "close_allowed_when",
        "current_intake_state",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
