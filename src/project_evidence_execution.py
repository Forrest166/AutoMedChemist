from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .project_evidence_expansion_plan import (
    DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
    DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
    load_project_evidence_expansion_plan,
    update_project_evidence_expansion_task_status,
)


DEFAULT_PROJECT_EVIDENCE_EXECUTION_REPORT_PATH = Path("data/projects/demo/project_evidence_execution_report.json")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _pending_scaffold_draft_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(
            1
            for row in csv.DictReader(handle)
            if str(row.get("draft_status") or "") not in {"applied", "deferred", "rejected", "retired"}
        )


def _residual_status_by_id(registry: dict) -> dict[str, str]:
    return {str(row.get("task_id") or ""): str(row.get("status") or "") for row in registry.get("tasks") or [] if row.get("task_id")}


def _public_validation_by_task(report: dict) -> dict[str, dict]:
    return {str(row.get("task_id") or ""): dict(row) for row in report.get("rows") or [] if row.get("task_id")}


def _contradiction_triage_by_signal(report: dict) -> dict[str, dict]:
    lookup = {}
    for row in report.get("rows") or []:
        for key in [str(row.get("source_signal_id") or ""), str(row.get("signal_key") or "")]:
            if key:
                lookup[key] = dict(row)
    return lookup


def _measurement_plan_by_id(report: dict) -> dict[str, dict]:
    return {str(row.get("measurement_plan_id") or ""): dict(row) for row in report.get("rows") or [] if row.get("measurement_plan_id")}


def _infer_execution(
    task: dict,
    *,
    root: Path,
    registry_status: dict[str, str],
    pending_scaffold_drafts: int,
    residual_adjustment: dict,
    public_sar_validation: dict[str, dict],
    contradiction_triage: dict[str, dict],
    measurement_plan: dict[str, dict],
) -> tuple[str, str]:
    task_type = str(task.get("task_type") or "")
    if task_type == "residual_experiment_followup":
        source_status = registry_status.get(str(task.get("source_task_id") or ""), "")
        if source_status in {"closed", "resolved_by_calibration"}:
            return "closed", f"Residual task is {source_status}; no additional follow-up is open."
        if source_status in {"outcomes_imported"}:
            return "evidence_imported", "Residual outcome rows were imported; reviewer sign-off remains available."
        return "in_progress", "Residual experiment plan/template exists; awaiting measured result payload, not fabricated data."
    if task_type == "public_sar_validation":
        validation = public_sar_validation.get(str(task.get("task_id") or ""))
        if validation:
            status = validation.get("validation_status")
            recommendation = validation.get("execution_recommendation")
            if recommendation in {"close_as_project_context_mapped_evidence", "close_as_reference_only_evidence"}:
                return "closed", f"Public SAR validation {status}; {recommendation}."
            return "in_progress", f"Public SAR validation {status or 'needs review'}."
        return "evidence_imported", "Public SAR signal is mapped into the project evidence pack; build public SAR validation report to close."
    if task_type == "public_sar_contradiction_triage":
        triage = (
            contradiction_triage.get(str(task.get("source_signal_id") or ""))
            or contradiction_triage.get(str(task.get("signal_key") or ""))
        )
        if triage:
            action = str(triage.get("triage_action") or "")
            if action == "keep_reference_only_contradiction_watch":
                return "closed", "Contradiction triage is reference-only; keep watch without changing project priors."
            return "in_progress", f"Contradiction triage action={action}; manual SAR prior review remains open."
        return "in_progress", "Build public SAR contradiction triage to decide candidate, analog-series, or reference-only handling."
    if task_type == "measurement_feedback_followup":
        measurement = measurement_plan.get(str(task.get("source_task_id") or ""))
        if measurement:
            return "in_progress", f"Measurement feedback row is planned: {measurement.get('measurement_type')}."
        return "in_progress", "Build measurement feedback plan and fill only real measured result rows."
    if task_type == "scaffold_review_signoff":
        if pending_scaffold_drafts:
            return "in_progress", f"{pending_scaffold_drafts} scaffold draft rows still need approve/defer/reject decisions."
        return "closed", "No pending scaffold review draft rows remain."
    if task_type == "endpoint_family_residual_resolution":
        if residual_adjustment.get("status") in {"applied", "no_approved_adjustments_applied"}:
            return "closed", f"Residual adjustment review status={residual_adjustment.get('status')}."
        return "in_progress", "Residual gap is quantified in the evidence pack; adjustment review or measured result import remains next."
    if task_type == "context_outcome_depth":
        return "in_progress", "Context has thin outcome depth; additional measured outcomes are planned before profile hardening."
    return str(task.get("execution_status") or "open"), "No automatic execution rule matched."


def execute_project_evidence_expansion_plan(
    *,
    root: str | Path = ".",
    plan_path: str | Path = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
    csv_path: str | Path | None = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
    priorities: set[str] | None = None,
    task_types: set[str] | None = None,
    reviewer: str = "evidence_execution",
) -> dict:
    """Advance evidence tasks using existing local evidence only."""
    root_path = Path(root)
    plan_file = root_path / plan_path if not Path(plan_path).is_absolute() else Path(plan_path)
    csv_file = root_path / csv_path if csv_path is not None and not Path(csv_path).is_absolute() else csv_path
    registry = _read_json(root_path / "data/substituents/evidence_residual_task_registry.json")
    residual_adjustment = _read_json(root_path / "data/profiles/calibrated/endpoint_family_residual_adjustment_apply_report.json")
    public_sar_report = _read_json(root_path / "data/projects/demo/public_sar_validation_report.json")
    contradiction_triage_report = _read_json(root_path / "data/projects/demo/public_sar_contradiction_triage.json")
    measurement_feedback_plan = _read_json(root_path / "data/projects/demo/measurement_feedback_plan.json")
    pending_scaffold = _pending_scaffold_draft_count(root_path / "data/substituents/scaffold_rule_review_drafts.csv")
    registry_status = _residual_status_by_id(registry)
    public_sar_validation = _public_validation_by_task(public_sar_report)
    contradiction_triage = _contradiction_triage_by_signal(contradiction_triage_report)
    measurement_plan = _measurement_plan_by_id(measurement_feedback_plan)
    priorities = {item.lower() for item in priorities} if priorities else None
    task_types = {item for item in task_types} if task_types else None
    plan = load_project_evidence_expansion_plan(plan_file)
    updated_rows = []
    skipped_rows = []
    for task in plan.get("tasks") or []:
        priority = str(task.get("priority") or "").lower()
        task_type = str(task.get("task_type") or "")
        if priorities and priority not in priorities:
            skipped_rows.append({"task_id": task.get("task_id"), "reason": "priority_filter"})
            continue
        if task_types and task_type not in task_types:
            skipped_rows.append({"task_id": task.get("task_id"), "reason": "task_type_filter"})
            continue
        status, note = _infer_execution(
            task,
            root=root_path,
            registry_status=registry_status,
            pending_scaffold_drafts=pending_scaffold,
            residual_adjustment=residual_adjustment,
            public_sar_validation=public_sar_validation,
            contradiction_triage=contradiction_triage,
            measurement_plan=measurement_plan,
        )
        if status == task.get("execution_status") and note == task.get("execution_note"):
            skipped_rows.append({"task_id": task.get("task_id"), "reason": "unchanged"})
            continue
        result = update_project_evidence_expansion_task_status(
            str(task.get("task_id")),
            status=status,
            plan_path=plan_file,
            csv_path=csv_file,
            reviewer=reviewer,
            owner=task.get("execution_owner") or reviewer,
            note=note,
        )
        updated_rows.append(
            {
                "task_id": task.get("task_id"),
                "task_type": task_type,
                "priority": priority,
                "execution_status": status,
                "note": note,
            }
        )
        plan = result.get("plan") or plan
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "executed" if updated_rows else "no_changes",
        "plan_path": str(plan_file),
        "updated_count": len(updated_rows),
        "skipped_count": len(skipped_rows),
        "updated_tasks": updated_rows,
        "skipped_tasks": skipped_rows,
        "plan_execution_status_counts": plan.get("execution_status_counts") or {},
        "open_execution_count": plan.get("open_execution_count"),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
    }


def write_project_evidence_execution_report(
    report: dict,
    output_path: str | Path = DEFAULT_PROJECT_EVIDENCE_EXECUTION_REPORT_PATH,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
