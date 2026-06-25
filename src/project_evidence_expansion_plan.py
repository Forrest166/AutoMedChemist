from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH = Path("data/projects/demo/project_evidence_expansion_plan.json")
DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH = Path("data/projects/demo/project_evidence_expansion_plan.csv")
PROJECT_EVIDENCE_EXPANSION_STATUSES = {"open", "in_progress", "evidence_imported", "blocked", "deferred", "closed"}
PROJECT_EVIDENCE_EXPANSION_TERMINAL_STATUSES = {"blocked", "deferred", "closed"}


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _task_id(*parts: Any) -> str:
    text = "|".join(str(part or "") for part in parts)
    return f"PEXP-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10].upper()}"


def _priority_from_residual(value: Any) -> str:
    try:
        numeric = abs(float(value))
    except (TypeError, ValueError):
        numeric = 0.0
    if numeric >= 0.35:
        return "high"
    if numeric >= 0.15:
        return "medium"
    return "low"


def _float_sort(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _context_key(row: dict) -> str:
    return "|".join(str(row.get(key) or "all") for key in ["endpoint_group", "target_family", "assay_type"])


def load_project_evidence_expansion_plan(path: str | Path = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH) -> dict:
    plan = _read_json(path)
    tasks = [dict(row) for row in plan.get("tasks") or [] if isinstance(row, dict)]
    return {
        **plan,
        "task_count": len(tasks),
        "execution_status_counts": dict(Counter(str(row.get("execution_status") or "open") for row in tasks).most_common()),
        "tasks": tasks,
    }


def _merge_execution_state(task: dict, previous: dict | None, now: str) -> dict:
    previous = previous or {}
    status = str(previous.get("execution_status") or "open")
    if status not in PROJECT_EVIDENCE_EXPANSION_STATUSES:
        status = "open"
    history = list(previous.get("status_history") or [])
    if not history:
        history.append({"status": status, "created_at": now, "reviewer": previous.get("reviewed_by") or "", "note": previous.get("execution_note") or ""})
    return {
        **task,
        "execution_status": status,
        "execution_owner": previous.get("execution_owner") or "",
        "execution_note": previous.get("execution_note") or "",
        "reviewed_at": previous.get("reviewed_at") or "",
        "reviewed_by": previous.get("reviewed_by") or "",
        "status_history": history[-20:],
    }


def _finalize_plan(report: dict) -> dict:
    tasks = [dict(row) for row in report.get("tasks") or []]
    execution_counts = Counter(str(row.get("execution_status") or "open") for row in tasks)
    active_tasks = [row for row in tasks if str(row.get("execution_status") or "open") not in PROJECT_EVIDENCE_EXPANSION_TERMINAL_STATUSES]
    return {
        **report,
        "task_count": len(tasks),
        "execution_status_counts": dict(execution_counts.most_common()),
        "open_execution_count": len(active_tasks),
        "tasks": tasks,
    }


def build_project_evidence_expansion_plan(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    max_public_signal_tasks: int = 12,
    max_contradiction_tasks: int = 12,
    max_measurement_tasks: int = 12,
    existing_plan: dict | None = None,
) -> dict:
    root_path = Path(root)
    pack = _read_json(root_path / "data/projects/demo/project_evidence_pack.json")
    public_signals = _read_json(root_path / "data/substituents/public_strategy_signal_report.json")
    measurement_plan = _read_json(root_path / "data/projects/demo/measurement_feedback_plan.json")
    registry = _read_json(root_path / "data/substituents/evidence_residual_task_registry.json")
    if existing_plan is None:
        existing_plan = load_project_evidence_expansion_plan(root_path / DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH)
    previous_tasks = {str(row.get("task_id") or ""): dict(row) for row in (existing_plan or {}).get("tasks") or [] if row.get("task_id")}
    now = datetime.now(timezone.utc).isoformat()
    tasks: list[dict] = []
    for row in pack.get("evidence_gaps") or []:
        tasks.append(
            {
                "task_id": _task_id("gap", row.get("endpoint_group"), row.get("target_family"), row.get("evidence_source")),
                "task_type": "endpoint_family_residual_resolution",
                "priority": _priority_from_residual(row.get("max_abs_residual")),
                "project_name": project_name,
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "assay_type": "all",
                "evidence_source": row.get("evidence_source"),
                "recommended_action": row.get("recommended_action"),
                "data_source_scope": "assay_outcome_and_residual_import",
                "next_step": "Fill residual result template with measured outcomes or mark task explicitly deferred before profile promotion.",
                "blocked_scope": "No vendor/procurement expansion.",
                "basis": f"max_abs_residual={row.get('max_abs_residual')}; confidence={row.get('confidence')}",
            }
        )
    for task in registry.get("tasks") or []:
        status = str(task.get("status") or "open")
        if status not in {"open", "planned", "outcomes_imported"}:
            continue
        task_id = _task_id("residual-task", task.get("task_id"))
        tasks.append(
            {
                "task_id": task_id,
                "source_task_id": task.get("task_id"),
                "task_type": "residual_experiment_followup",
                "priority": str(task.get("priority") or "medium"),
                "project_name": project_name,
                "endpoint_group": task.get("endpoint_group"),
                "target_family": task.get("target_family"),
                "assay_type": task.get("assay_type"),
                "evidence_source": task.get("evidence_source"),
                "recommended_action": task.get("recommended_action"),
                "data_source_scope": "assay_outcome",
                "next_step": "Import completed result rows, close if measured payload supports closure, otherwise keep as outcomes_imported.",
                "blocked_scope": "No vendor/procurement expansion.",
                "basis": f"task={task.get('task_id')}; status={status}; expected_information_gain={task.get('expected_information_gain')}",
            }
        )
    context_counts = {str(_context_key(row)): row for row in pack.get("context_summary") or []}
    for key, row in context_counts.items():
        count = int(row.get("outcome_count") or 0)
        if count >= 24:
            continue
        tasks.append(
            {
                "task_id": _task_id("context-depth", key),
                "task_type": "context_outcome_depth",
                "priority": "medium" if count < 12 else "low",
                "project_name": project_name,
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "assay_type": row.get("assay_type"),
                "evidence_source": "project_outcome",
                "recommended_action": "collect_more_outcomes",
                "data_source_scope": "assay_outcome",
                "next_step": "Prioritize additional measured outcomes for this endpoint/family/assay context before making broad scoring changes.",
                "blocked_scope": "No vendor/procurement expansion.",
                "basis": f"outcome_count={count}; positive_rate={row.get('positive_rate')}",
            }
        )
    for signal in (pack.get("top_public_signals") or [])[: int(max_public_signal_tasks)]:
        tasks.append(
            {
                "task_id": _task_id("public-sar", signal.get("signal_id")),
                "source_signal_id": signal.get("signal_id"),
                "signal_key": signal.get("signal_key"),
                "task_type": "public_sar_validation",
                "priority": "medium" if float(signal.get("public_evidence_score") or 0.0) >= 80.0 else "low",
                "project_name": project_name,
                "endpoint_group": signal.get("endpoint_group"),
                "target_family": signal.get("target_family"),
                "assay_type": "all",
                "evidence_source": signal.get("source_names"),
                "public_evidence_score": signal.get("public_evidence_score"),
                "public_evidence_count": signal.get("public_evidence_count"),
                "recommended_action": "validate_public_sar_prior",
                "data_source_scope": "mmp_sar_scaffold_ring",
                "next_step": "Map this public SAR signal to project candidates and measured outcomes before fixing it as a project prior.",
                "blocked_scope": "No vendor/procurement expansion.",
                "basis": f"signal={signal.get('signal_key')}; score={signal.get('public_evidence_score')}; operator={signal.get('operator')}",
            }
        )
    contradiction_signals = [
        signal
        for signal in public_signals.get("signals") or []
        if int(float(signal.get("contradiction_count") or 0)) > 0
    ]
    contradiction_signals.sort(
        key=lambda signal: (
            -(int(float(signal.get("contradiction_count") or 0)) - int(float(signal.get("support_count") or 0))),
            float(signal.get("public_evidence_score") or 0.0),
            str(signal.get("signal_id") or ""),
        )
    )
    for signal in contradiction_signals[: int(max_contradiction_tasks)]:
        contradiction_count = int(float(signal.get("contradiction_count") or 0))
        support_count = int(float(signal.get("support_count") or 0))
        tasks.append(
            {
                "task_id": _task_id("public-sar-contradiction", signal.get("signal_id") or signal.get("signal_key")),
                "source_signal_id": signal.get("signal_id"),
                "signal_key": signal.get("signal_key"),
                "task_type": "public_sar_contradiction_triage",
                "priority": "high" if contradiction_count > support_count else "medium",
                "project_name": project_name,
                "endpoint_group": signal.get("endpoint_group"),
                "target_family": signal.get("target_family"),
                "assay_type": "all",
                "evidence_source": signal.get("source_names"),
                "public_evidence_score": signal.get("public_evidence_score"),
                "public_evidence_count": signal.get("public_evidence_count"),
                "recommended_action": "triage_public_sar_contradiction",
                "data_source_scope": "mmp_sar_scaffold_ring",
                "next_step": "Map the contradiction to candidate, analog-series, or reference-only status before using it as a project prior.",
                "blocked_scope": "No vendor/procurement expansion.",
                "basis": (
                    f"signal={signal.get('signal_key')}; support={support_count}; "
                    f"contradiction={contradiction_count}; operator={signal.get('operator')}"
                ),
            }
        )
    measurement_rows = [row for row in measurement_plan.get("rows") or [] if str(row.get("planned_status") or "") == "planned"]
    measurement_rows.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("measurement_priority")), 9),
            -_float_sort(row.get("evidence_value_score")),
            str(row.get("measurement_plan_id") or ""),
        )
    )
    for row in measurement_rows[: int(max_measurement_tasks)]:
        tasks.append(
            {
                "task_id": _task_id("measurement-feedback", row.get("measurement_plan_id")),
                "source_task_id": row.get("measurement_plan_id"),
                "task_type": "measurement_feedback_followup",
                "priority": str(row.get("measurement_priority") or "medium"),
                "project_name": project_name,
                "endpoint_group": row.get("endpoint_group"),
                "target_family": "all",
                "assay_type": "all",
                "evidence_source": "measurement_feedback_plan",
                "recommended_action": row.get("measurement_type"),
                "data_source_scope": "assay_outcome",
                "next_step": row.get("next_step") or "Import real measured feedback for this planned row.",
                "blocked_scope": "No vendor/procurement expansion.",
                "basis": (
                    f"measurement_plan_id={row.get('measurement_plan_id')}; "
                    f"candidate_id={row.get('candidate_id')}; evidence_value_score={row.get('evidence_value_score')}"
                ),
            }
        )
    scaffold = pack.get("scaffold_review_drafts") or {}
    pending_scaffold = int(scaffold.get("pending_count") or 0)
    if pending_scaffold:
        tasks.append(
            {
                "task_id": _task_id("scaffold-drafts", pending_scaffold),
                "task_type": "scaffold_review_signoff",
                "priority": "high",
                "project_name": project_name,
                "endpoint_group": "all",
                "target_family": "all",
                "assay_type": "all",
                "evidence_source": "scaffold_review_workspace",
                "recommended_action": "approve_defer_or_reject_scaffold_drafts",
                "data_source_scope": "scaffold_ring",
                "next_step": "Review scaffold draft rows explicitly; only approved_for_apply drafts can be applied to rule reviews.",
                "blocked_scope": "No vendor/procurement expansion.",
                "basis": f"pending_scaffold_drafts={pending_scaffold}",
            }
        )
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda row: (priority_order.get(str(row.get("priority")), 9), str(row.get("task_type")), str(row.get("task_id"))))
    tasks = [_merge_execution_state(task, previous_tasks.get(str(task.get("task_id") or "")), now) for task in tasks]
    return _finalize_plan({
        "created_at": now,
        "project_name": project_name,
        "status": "ready" if tasks else "empty",
        "task_type_counts": dict(Counter(str(row.get("task_type") or "unknown") for row in tasks).most_common()),
        "priority_counts": dict(Counter(str(row.get("priority") or "unknown") for row in tasks).most_common()),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "tasks": tasks,
        "recommended_next_actions": [
            "Use high-priority residual and scaffold signoff tasks before score-profile promotion.",
            "Use public SAR validation tasks as evidence mapping work, not as fixed project priors.",
            "Keep procurement/vendor data out of this expansion plan.",
        ],
    })


def update_project_evidence_expansion_task_status(
    task_id: str,
    *,
    status: str,
    plan_path: str | Path = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
    reviewer: str | None = None,
    owner: str | None = None,
    note: str | None = None,
    csv_path: str | Path | None = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
    write_back: bool = True,
) -> dict:
    normalized = str(status or "").strip().lower()
    if normalized not in PROJECT_EVIDENCE_EXPANSION_STATUSES:
        raise ValueError(f"Unsupported project evidence expansion status: {status}")
    plan = load_project_evidence_expansion_plan(plan_path)
    now = datetime.now(timezone.utc).isoformat()
    updated = None
    tasks = []
    for row in plan.get("tasks") or []:
        if str(row.get("task_id") or "") != str(task_id):
            tasks.append(row)
            continue
        history = list(row.get("status_history") or [])
        history.append({"status": normalized, "created_at": now, "reviewer": reviewer or "", "note": note or ""})
        updated = {
            **row,
            "execution_status": normalized,
            "execution_owner": owner or row.get("execution_owner") or "",
            "execution_note": note or row.get("execution_note") or "",
            "reviewed_at": now,
            "reviewed_by": reviewer or row.get("reviewed_by") or "",
            "status_history": history[-20:],
        }
        tasks.append(updated)
    if updated is None:
        raise ValueError(f"Project evidence expansion task not found: {task_id}")
    plan = _finalize_plan({**plan, "updated_at": now, "tasks": tasks})
    if write_back:
        write_project_evidence_expansion_plan(plan, plan_path, csv_path=csv_path)
    return {
        "created_at": now,
        "task_id": task_id,
        "status": normalized,
        "updated": updated,
        "plan": plan,
    }


def write_project_evidence_expansion_plan(
    report: dict,
    output_path: str | Path = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is not None:
        rows = [dict(row) for row in report.get("tasks") or []]
        preferred = [
            "task_id",
            "source_task_id",
            "task_type",
            "priority",
            "execution_status",
            "execution_owner",
            "execution_note",
            "reviewed_at",
            "reviewed_by",
            "project_name",
            "endpoint_group",
            "target_family",
            "assay_type",
            "source_signal_id",
            "signal_key",
            "evidence_source",
            "public_evidence_score",
            "public_evidence_count",
            "recommended_action",
            "data_source_scope",
            "blocked_scope",
            "next_step",
            "basis",
        ]
        extras = sorted({key for row in rows for key in row if key not in preferred})
        fieldnames = preferred + extras if rows else ["task_id"]
        csv_out = Path(csv_path)
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        field: json.dumps(row.get(field), sort_keys=True) if field == "status_history" else row.get(field, "")
                        for field in fieldnames
                    }
                )
