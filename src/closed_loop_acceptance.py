from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CLOSED_LOOP_ACCEPTANCE_PATH = Path("data/rules/closed_loop_acceptance.yaml")

DEFAULT_CLOSED_LOOP_ACCEPTANCE = {
    "version": "closed-loop-acceptance-0.1",
    "criteria": {
        "min_first_candidate_count": 1,
        "min_second_candidate_count": 1,
        "min_feedback_inserted_count": 1,
        "min_priority_delta_count": 1,
        "min_next_design_queue_count": 1,
        "min_queue_analog_series_delta_count": 1,
        "min_series_adjusted_candidate_count": 1,
        "min_abs_series_adjustment": 0.25,
    },
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_criteria(path: str | Path | None = DEFAULT_CLOSED_LOOP_ACCEPTANCE_PATH) -> dict:
    if path is None:
        return DEFAULT_CLOSED_LOOP_ACCEPTANCE
    criteria_path = Path(path)
    if not criteria_path.exists():
        return DEFAULT_CLOSED_LOOP_ACCEPTANCE
    with criteria_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return {**DEFAULT_CLOSED_LOOP_ACCEPTANCE, **data, "criteria": {**DEFAULT_CLOSED_LOOP_ACCEPTANCE["criteria"], **(data.get("criteria") or {})}}


def closed_loop_drill_snapshot(report: dict) -> dict:
    adjusted = report.get("series_adjusted_candidates") or []
    return {
        "project_name": report.get("project_name"),
        "first_candidate_count": report.get("first_candidate_count"),
        "second_candidate_count": report.get("second_candidate_count"),
        "feedback_inserted_count": report.get("feedback_inserted_count"),
        "priority_delta_count": report.get("priority_delta_count"),
        "next_design_queue_count": report.get("next_design_queue_count"),
        "queue_analog_series_delta_count": report.get("queue_analog_series_delta_count"),
        "series_adjusted_candidate_count": report.get("series_adjusted_candidate_count"),
        "queue_analog_series_delta_action_counts": report.get("queue_analog_series_delta_action_counts"),
        "top_adjusted_candidate_ids": [row.get("candidate_id") for row in adjusted[:8]],
        "max_abs_series_adjustment": round(
            max((abs(_float(row.get("queue_analog_series_delta_score_delta"))) for row in adjusted), default=0.0),
            4,
        ),
    }


def evaluate_closed_loop_drill_acceptance(
    report: dict,
    *,
    criteria_path: str | Path | None = DEFAULT_CLOSED_LOOP_ACCEPTANCE_PATH,
) -> dict:
    policy = _load_criteria(criteria_path)
    criteria = policy.get("criteria") or {}
    snapshot = closed_loop_drill_snapshot(report)
    checks = []

    def add(check_id: str, observed: float, minimum: float, severity: str = "error") -> None:
        checks.append(
            {
                "check_id": check_id,
                "severity": severity,
                "passed": observed >= minimum,
                "observed": observed,
                "minimum": minimum,
            }
        )

    add("first_candidate_count", _float(snapshot.get("first_candidate_count")), _float(criteria.get("min_first_candidate_count")))
    add("second_candidate_count", _float(snapshot.get("second_candidate_count")), _float(criteria.get("min_second_candidate_count")))
    add("feedback_inserted_count", _float(snapshot.get("feedback_inserted_count")), _float(criteria.get("min_feedback_inserted_count")))
    add("priority_delta_count", _float(snapshot.get("priority_delta_count")), _float(criteria.get("min_priority_delta_count")))
    add("next_design_queue_count", _float(snapshot.get("next_design_queue_count")), _float(criteria.get("min_next_design_queue_count")))
    add(
        "queue_analog_series_delta_count",
        _float(snapshot.get("queue_analog_series_delta_count")),
        _float(criteria.get("min_queue_analog_series_delta_count")),
    )
    add(
        "series_adjusted_candidate_count",
        _float(snapshot.get("series_adjusted_candidate_count")),
        _float(criteria.get("min_series_adjusted_candidate_count")),
    )
    add("max_abs_series_adjustment", _float(snapshot.get("max_abs_series_adjustment")), _float(criteria.get("min_abs_series_adjustment")), severity="warning")

    outputs = report.get("outputs") or {}
    for key in ["packet_json", "feedback_rows", "priority_delta", "queue_analog_series_delta", "next_design_queue"]:
        path = outputs.get(key)
        checks.append(
            {
                "check_id": f"output_exists_{key}",
                "severity": "error",
                "passed": bool(path and Path(path).exists()),
                "observed": str(path or ""),
                "minimum": "existing file",
            }
        )
    error_failures = [check for check in checks if not check["passed"] and check["severity"] == "error"]
    warning_failures = [check for check in checks if not check["passed"] and check["severity"] == "warning"]
    status = "fail" if error_failures else "warn" if warning_failures else "pass"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": policy.get("version"),
        "status": status,
        "passed": status != "fail",
        "error_count": len(error_failures),
        "warning_count": len(warning_failures),
        "snapshot": snapshot,
        "checks": checks,
        "recommended_next_actions": [
            "Treat fail checks as blockers before using drill output for policy calibration.",
            "Review warning checks when score adjustments are too small to prove feedback is changing generation.",
            "Keep the snapshot stable enough to compare future drill behavior across code changes.",
        ],
    }


def write_closed_loop_drill_acceptance(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
