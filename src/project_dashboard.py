from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .database import initialize_database
from .experiment_tracking import summarize_experiment_plans
from .feedback import summarize_project_feedback
from .priority_queue import build_next_design_queue_decision_quality_report


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_PROJECT_DASHBOARD_PATH = Path("data/projects/demo/project_closed_loop_dashboard.json")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_yaml(path: str | Path) -> dict:
    yaml_path = Path(path)
    if not yaml_path.exists():
        return {}
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _latest_file(directory: Path, pattern: str) -> Path | None:
    paths = [path for path in directory.glob(pattern) if path.is_file()]
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _latest_next_design_queue_file(directory: Path) -> Path | None:
    paths = [
        path
        for path in directory.glob("next_design_queue*.json")
        if path.is_file() and "decision" not in path.stem
    ]
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def _active_queue_policy_summary(root: Path) -> dict:
    document = _read_yaml(root / "data/rules/queue_analog_series_policy.yaml")
    active_version = document.get("active_version")
    active = next((item for item in document.get("versions") or [] if item.get("version") == active_version), {})
    return {
        "active_version": active_version,
        "version_count": len(document.get("versions") or []),
        "training_series_count": active.get("training_series_count", 0),
        "training_candidate_count": active.get("training_candidate_count", 0),
        "context_count": len(active.get("context_action_base_adjustments") or {}),
        "context_summary_count": len(active.get("context_summaries") or []),
        "latest_change": (document.get("change_log") or [])[-1] if document.get("change_log") else {},
    }


def _multi_objective_summary(root: Path) -> dict:
    report = _read_json(root / "data/projects/demo/multi_objective_calibration_report.json")
    profile = report.get("calibrated_profile") or {}
    return {
        "status": report.get("status", "missing"),
        "observation_count": report.get("observation_count", 0),
        "profile_id": profile.get("profile_id"),
        "score_weights": profile.get("score_weights") or {},
        "component_count": len(report.get("component_diagnostics") or []),
    }


def _residual_registry_summary(root: Path) -> dict:
    registry = _read_json(root / "data/substituents/evidence_residual_task_registry.json")
    tasks = registry.get("tasks") or []
    tasks_by_eig = sorted(tasks, key=lambda row: float(row.get("expected_information_gain") or 0.0), reverse=True)
    return {
        "task_count": registry.get("task_count", len(tasks)),
        "active_task_count": registry.get("active_task_count"),
        "status_counts": registry.get("status_counts") or dict(Counter(str(row.get("status") or "unknown") for row in tasks).most_common()),
        "last_plan_sync": registry.get("last_plan_sync") or {},
        "top_information_gain_tasks": [
            {
                "task_id": row.get("task_id"),
                "status": row.get("status"),
                "priority": row.get("priority"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "evidence_source": row.get("evidence_source"),
                "expected_information_gain": row.get("expected_information_gain"),
                "recommended_action": row.get("recommended_action"),
            }
            for row in tasks_by_eig[:8]
        ],
    }


def _project_run_summary(db_path: str | Path, project_name: str | None = None) -> dict:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if project_name:
            rows = conn.execute(
                """
                SELECT pr.run_id, pr.project_name, pr.created_at, COUNT(pc.candidate_id) AS candidate_count
                FROM project_run pr
                LEFT JOIN project_candidate pc ON pc.run_id=pr.run_id
                WHERE pr.project_name=?
                GROUP BY pr.run_id
                ORDER BY pr.created_at DESC
                LIMIT 20
                """,
                (project_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT pr.run_id, pr.project_name, pr.created_at, COUNT(pc.candidate_id) AS candidate_count
                FROM project_run pr
                LEFT JOIN project_candidate pc ON pc.run_id=pr.run_id
                GROUP BY pr.run_id
                ORDER BY pr.created_at DESC
                LIMIT 20
                """
            ).fetchall()
    finally:
        conn.close()
    run_rows = [dict(row) for row in rows]
    return {
        "run_count": len(run_rows),
        "candidate_count": sum(int(row.get("candidate_count") or 0) for row in run_rows),
        "latest_runs": run_rows[:8],
    }


def _accepted_candidate_summary(decision_quality: dict) -> dict:
    outcomes = decision_quality.get("candidate_outcomes") or []
    accepted = [row for row in outcomes if str(row.get("queue_decision") or "") == "accepted"]
    observed = [row for row in accepted if int(row.get("observed_count") or 0)]
    positive = [row for row in observed if int(row.get("positive_count") or 0)]
    return {
        "accepted_count": len(accepted),
        "accepted_observed_count": len(observed),
        "accepted_positive_count": len(positive),
        "accepted_hit_rate": round(len(positive) / len(observed), 4) if observed else None,
        "top_accepted_candidates": accepted[:10],
    }


def build_project_closed_loop_dashboard(
    *,
    project_name: str | None = None,
    root: str | Path = ".",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    root_path = Path(root)
    queue_dir = root_path / "data/projects/closed_loop"
    latest_queue = _latest_next_design_queue_file(queue_dir)
    queue_payload = _read_json(latest_queue) if latest_queue else {}
    decision_quality = build_next_design_queue_decision_quality_report(db_path=db_path, project_name=project_name)
    feedback = summarize_project_feedback(db_path=db_path, project_name=project_name)
    experiments = summarize_experiment_plans(db_path=db_path, project_name=project_name)
    closed_loop_acceptance = _read_json(root_path / "data/projects/closed_loop_drill/closed_loop_drill_acceptance.json")
    dashboard = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "project_runs": _project_run_summary(db_path, project_name=project_name),
        "feedback": {
            "feedback_count": feedback.get("feedback_count", 0),
            "endpoint_counts": feedback.get("endpoint_counts") or {},
            "outcome_counts": feedback.get("outcome_counts") or {},
        },
        "experiments": {
            "plan_count": experiments.get("plan_count", 0),
            "event_count": experiments.get("event_count", 0),
            "status_counts": experiments.get("status_counts") or {},
            "event_status_counts": experiments.get("event_status_counts") or {},
            "stop_go_counts": experiments.get("stop_go_counts") or {},
            "open_plan_count": experiments.get("open_plan_count", 0),
        },
        "queue_policy": _active_queue_policy_summary(root_path),
        "multi_objective": _multi_objective_summary(root_path),
        "residual_tasks": _residual_registry_summary(root_path),
        "next_design_queue": {
            "path": str(latest_queue) if latest_queue else None,
            "queue_count": len(queue_payload.get("queue") or []),
            "created_at": queue_payload.get("created_at"),
            "top_rows": (queue_payload.get("queue") or [])[:8],
        },
        "queue_decisions": {
            "decision_event_count": decision_quality.get("decision_event_count", 0),
            "observed_decision_count": decision_quality.get("observed_decision_count", 0),
            "decision_counts": decision_quality.get("decision_counts") or {},
            "reviewer_calibration_hint_count": len(decision_quality.get("reviewer_calibration_hints") or []),
            "accepted_candidates": _accepted_candidate_summary(decision_quality),
        },
        "closed_loop_acceptance": {
            "status": closed_loop_acceptance.get("status", "missing"),
            "passed": closed_loop_acceptance.get("passed"),
            "warning_count": closed_loop_acceptance.get("warning_count"),
            "error_count": closed_loop_acceptance.get("error_count"),
            "snapshot": closed_loop_acceptance.get("snapshot") or {},
        },
    }
    dashboard["overall_status"] = (
        "needs_attention"
        if dashboard["closed_loop_acceptance"]["status"] == "fail"
        or dashboard["residual_tasks"]["status_counts"].get("open", 0)
        or dashboard["experiments"]["open_plan_count"]
        else "ready"
    )
    dashboard["recommended_next_actions"] = [
        "Close or import outcomes for planned residual-task experiments before the next policy promotion.",
        "Use queue decision quality and replay reports before changing active policy defaults.",
        "Package each next-design iteration so policy/profile/residual context can be compared later.",
    ]
    return dashboard


def write_project_closed_loop_dashboard(report: dict, output_path: str | Path = DEFAULT_PROJECT_DASHBOARD_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
