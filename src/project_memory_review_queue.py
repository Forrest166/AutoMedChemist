from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_PATH = Path("data/projects/demo/project_memory_review_queue.json")
DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH = Path("data/projects/demo/project_memory_review_queue.csv")
DEFAULT_PROJECT_MEMORY_REVIEW_DASHBOARD_PATH = Path("data/projects/demo/project_memory_review_dashboard.json")
DEFAULT_PROJECT_MEMORY_REVIEW_DASHBOARD_CSV_PATH = Path("data/projects/demo/project_memory_review_dashboard.csv")
PROJECT_MEMORY_OPERATOR_STATUSES = {"open", "assigned", "in_review", "closed", "deferred"}
_OPERATOR_FIELDS = ["operator_status", "assigned_to", "last_reviewed_by", "last_reviewed_at", "operator_note", "operator_history"]


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _priority_rank(priority: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "watch": 4}.get(str(priority or ""), 9)


def _existing_operator_lookup(path: Path) -> dict[str, dict]:
    report = _read_json(path)
    lookup = {}
    for row in report.get("rows") or []:
        item_id = str(row.get("review_item_id") or "")
        if not item_id:
            continue
        lookup[item_id] = {field: row.get(field, [] if field == "operator_history" else "") for field in _OPERATOR_FIELDS}
    return lookup


def _add_policy_rows(rows: list[dict], proposal: dict, replay: dict) -> None:
    if not proposal:
        return
    if proposal.get("activation_status") == "active":
        return
    approval = str(proposal.get("approval_status") or "")
    if proposal.get("status") in {"review_required", "approved_not_active"} or approval in {"pending_review", "approved"}:
        rows.append(
            {
                "review_item_id": f"PMRQ-policy-{proposal.get('proposal_id') or 'missing'}",
                "review_lane": "evidence_value_policy",
                "priority": "high" if approval == "pending_review" else "medium",
                "source_artifact": "evidence_value_policy_proposal",
                "source_id": proposal.get("proposal_id"),
                "candidate_id": "",
                "queue_id": "",
                "endpoint_group": "",
                "status": proposal.get("status") or "missing",
                "review_action": "review_policy_proposal_and_replay_before_activation",
                "decision_needed": "approve_reject_or_defer",
                "details": (
                    f"approval={approval}; activation={proposal.get('activation_status')}; "
                    f"changes={proposal.get('weight_change_count')}; replay_gate={replay.get('activation_gate_status') or 'missing'}"
                ),
            }
        )
    if replay and replay.get("activation_gate_status") == "blocked_replay_drift_review":
        rows.append(
            {
                "review_item_id": f"PMRQ-policy-replay-{proposal.get('proposal_id') or 'missing'}",
                "review_lane": "evidence_value_policy",
                "priority": "critical",
                "source_artifact": "evidence_value_policy_replay",
                "source_id": proposal.get("proposal_id"),
                "candidate_id": "",
                "queue_id": "",
                "endpoint_group": "",
                "status": replay.get("activation_gate_status"),
                "review_action": "reduce_policy_delta_or_split_policy_version",
                "decision_needed": "manual_replay_drift_review",
                "details": (
                    f"top_n_changes={replay.get('top_n_change_count')}; "
                    f"max_score_delta={replay.get('max_abs_score_delta')}; max_rank_delta={replay.get('max_abs_rank_delta')}"
                ),
            }
        )


def _add_driver_rows(rows: list[dict], calibration: dict) -> None:
    for driver in calibration.get("priority_driver_weight_adjustments") or []:
        weight = str(driver.get("weight") or "")
        if weight not in {"contradiction", "material_ab", "sufficiency_gap"}:
            continue
        rows.append(
            {
                "review_item_id": f"PMRQ-driver-{weight}",
                "review_lane": "calibration_driver",
                "priority": "medium",
                "source_artifact": "evidence_value_calibration_report",
                "source_id": driver.get("value_driver"),
                "candidate_id": "",
                "queue_id": "",
                "endpoint_group": "",
                "status": "needs_weight_review",
                "review_action": "review_driver_error_before_policy_activation",
                "decision_needed": f"{driver.get('direction')}_or_hold_{weight}",
                "details": (
                    f"driver={driver.get('value_driver')}; rows={driver.get('row_count')}; "
                    f"mean_signed_error={driver.get('mean_signed_error')}; mae={driver.get('mean_absolute_error')}"
                ),
            }
        )


def _add_gap_rows(rows: list[dict], gap_closure: dict) -> None:
    for row in gap_closure.get("rows") or []:
        closure_status = str(row.get("closure_status") or "")
        priority = "high" if closure_status == "manual_endpoint_confirmation_required" else "medium"
        decision_needed = (
            "collect_exact_endpoint_measurement"
            if closure_status == "exact_measurement_required"
            else "execute_recorded_endpoint_remap"
            if closure_status == "manual_endpoint_remap_approved"
            else "none_deferred"
            if closure_status == "deferred"
            else "exact_endpoint_measurement_or_manual_endpoint_remap"
        )
        rows.append(
            {
                "review_item_id": f"PMRQ-gap-{row.get('measurement_plan_id')}",
                "review_lane": "measurement_gap",
                "priority": priority,
                "source_artifact": "measurement_feedback_gap_closure",
                "source_id": row.get("measurement_plan_id"),
                "candidate_id": row.get("candidate_id"),
                "queue_id": row.get("queue_id"),
                "endpoint_group": row.get("required_endpoint_group"),
                "status": closure_status,
                "review_action": row.get("review_action"),
                "decision_needed": decision_needed,
                "operator_status": "deferred" if closure_status == "deferred" else "open",
                "assigned_to": "",
                "last_reviewed_by": row.get("reviewed_by") or "",
                "last_reviewed_at": row.get("reviewed_at") or "",
                "operator_note": row.get("review_note") or "",
                "details": (
                    f"available_endpoints={row.get('available_endpoint_groups')}; "
                    f"decision={row.get('gap_decision') or 'open'}; blocked_reason={row.get('blocked_reason')}"
                ),
            }
        )


def _add_sar_rows(rows: list[dict], watchlist: dict) -> None:
    for row in watchlist.get("rows") or []:
        rows.append(
            {
                "review_item_id": f"PMRQ-sar-{row.get('triage_id')}",
                "review_lane": "sar_contradiction",
                "priority": row.get("priority") or "medium",
                "source_artifact": "public_sar_contradiction_watchlist",
                "source_id": row.get("triage_id"),
                "candidate_id": row.get("candidate_ids"),
                "queue_id": row.get("queue_ids"),
                "endpoint_group": row.get("endpoint_group"),
                "status": row.get("review_status") or "open",
                "review_action": row.get("review_action"),
                "decision_needed": "candidate_or_analog_series_sar_resolution",
                "details": (
                    f"candidate_links={row.get('candidate_link_count')}; analog_links={row.get('analog_series_link_count')}; "
                    f"deferred_reference_only={watchlist.get('deferred_reference_only_count')}"
                ),
            }
        )


def _profile_operator_status(review_status: str) -> str:
    status = str(review_status or "open")
    return {
        "accepted": "closed",
        "closed": "closed",
        "deferred": "deferred",
        "assigned": "assigned",
        "in_review": "in_review",
        "rollback_requested": "in_review",
    }.get(status, "open")


def _add_profile_impact_rows(rows: list[dict], profile_review: dict) -> None:
    severity_priority = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
    for row in profile_review.get("rows") or []:
        operator_history = []
        for event in row.get("review_history") or []:
            operator_history.append(
                {
                    "reviewed_at": event.get("reviewed_at"),
                    "previous_operator_status": _profile_operator_status(event.get("previous_review_status")),
                    "operator_status": _profile_operator_status(event.get("review_status")),
                    "assigned_to": event.get("assigned_to") or row.get("assigned_to") or "",
                    "reviewer": event.get("reviewer") or "",
                    "note": event.get("note") or "",
                    "source": "profile_impact_review_queue",
                }
            )
        rows.append(
            {
                "review_item_id": f"PMRQ-profile-{row.get('review_id')}",
                "review_lane": "profile_impact",
                "priority": severity_priority.get(str(row.get("severity") or ""), "medium"),
                "source_artifact": "profile_impact_review_queue",
                "source_id": row.get("review_id"),
                "candidate_id": row.get("candidate_id"),
                "queue_id": row.get("queue_id"),
                "endpoint_group": row.get("endpoint_group"),
                "status": row.get("review_status") or "open",
                "review_action": row.get("review_action"),
                "decision_needed": "accept_watch_defer_or_request_policy_rollback",
                "operator_status": _profile_operator_status(str(row.get("review_status") or "open")),
                "assigned_to": row.get("assigned_to") or "",
                "last_reviewed_by": row.get("reviewed_by") or "",
                "last_reviewed_at": row.get("reviewed_at") or "",
                "operator_note": row.get("review_note") or "",
                "operator_history": operator_history,
                "details": (
                    f"severity={row.get('severity')}; active_rank={row.get('active_rank')}; "
                    f"profile_score_delta={row.get('profile_rollback_score_delta')}; "
                    f"profile_rank_delta={row.get('profile_rollback_rank_delta')}; "
                    f"rollback_action={row.get('profile_rollback_action')}"
                ),
            }
        )


def build_project_memory_review_queue(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    proposal_path: str | Path = "data/projects/demo/evidence_value_policy_proposal.json",
    policy_replay_path: str | Path = "data/projects/demo/evidence_value_policy_replay.json",
    calibration_path: str | Path = "data/projects/demo/evidence_value_calibration_report.json",
    gap_closure_path: str | Path = "data/projects/demo/measurement_feedback_gap_closure.json",
    profile_impact_review_path: str | Path = "data/projects/demo/profile_impact_review_queue.json",
    sar_watchlist_path: str | Path = "data/projects/demo/public_sar_contradiction_watchlist.json",
    existing_queue_path: str | Path = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_PATH,
) -> dict:
    root_path = Path(root)

    def resolve(path: str | Path) -> Path:
        item = Path(path)
        return item if item.is_absolute() else root_path / item

    proposal = _read_json(resolve(proposal_path))
    replay = _read_json(resolve(policy_replay_path))
    calibration = _read_json(resolve(calibration_path))
    gap_closure = _read_json(resolve(gap_closure_path))
    profile_review = _read_json(resolve(profile_impact_review_path))
    sar_watchlist = _read_json(resolve(sar_watchlist_path))
    existing_operator = _existing_operator_lookup(resolve(existing_queue_path))
    rows: list[dict] = []
    _add_policy_rows(rows, proposal, replay)
    _add_driver_rows(rows, calibration)
    _add_gap_rows(rows, gap_closure)
    _add_profile_impact_rows(rows, profile_review)
    _add_sar_rows(rows, sar_watchlist)
    rows.sort(key=lambda row: (_priority_rank(str(row.get("priority") or "")), str(row.get("review_lane") or ""), str(row.get("review_item_id") or "")))
    lane_counts = Counter(str(row.get("review_lane") or "unknown") for row in rows)
    priority_counts = Counter(str(row.get("priority") or "unknown") for row in rows)
    for row in rows:
        preserved = existing_operator.get(str(row.get("review_item_id") or "")) or {}
        for field in _OPERATOR_FIELDS:
            if field == "operator_history":
                row[field] = list(preserved.get(field) or row.get(field) or [])
            else:
                default_value = row.get(field) or ("open" if field == "operator_status" else "")
                preserved_value = preserved.get(field)
                if field == "operator_status" and default_value in {"closed", "deferred"}:
                    row[field] = default_value
                elif field == "operator_status" and default_value not in {"", "open"} and preserved_value in {None, "", "open"}:
                    row[field] = default_value
                elif field in {"assigned_to", "last_reviewed_by", "last_reviewed_at", "operator_note"} and default_value and not preserved_value:
                    row[field] = default_value
                else:
                    row[field] = preserved_value or default_value
    operator_status_counts = Counter(str(row.get("operator_status") or "open") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "project_name": project_name,
        "row_count": len(rows),
        "lane_counts": dict(lane_counts.most_common()),
        "priority_counts": dict(priority_counts.most_common()),
        "operator_status_counts": dict(operator_status_counts.most_common()),
        "open_operator_item_count": sum(1 for row in rows if str(row.get("operator_status") or "open") not in {"closed", "deferred"}),
        "sar_deferred_reference_only_count": sar_watchlist.get("deferred_reference_only_count", 0),
        "measurement_open_gap_count": gap_closure.get("open_gap_count", 0),
        "profile_impact_open_count": profile_review.get("open_review_count", 0),
        "policy_activation_gate_status": replay.get("activation_gate_status") or "missing",
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "rows": rows,
        "recommended_next_actions": [
            "Work this queue from critical/high to lower-priority watch rows.",
            "Keep evidence-value activation blocked until proposal approval and replay gate both pass.",
            "Resolve measurement gaps with strict endpoint governance; do not use real experiment feedback as the default path.",
            "Review profile-impact rows before accepting another active evidence-value policy change.",
        ],
    }


def _set_operator_status(
    row: dict,
    *,
    status: str,
    assigned_to: str | None = None,
    reviewer: str | None = None,
    note: str | None = None,
    now: str | None = None,
) -> dict:
    timestamp = now or datetime.now(timezone.utc).isoformat()
    previous_status = row.get("operator_status") or "open"
    row["operator_status"] = status
    if assigned_to is not None:
        row["assigned_to"] = assigned_to
    if reviewer is not None:
        row["last_reviewed_by"] = reviewer
        row["last_reviewed_at"] = timestamp
    if note is not None:
        row["operator_note"] = note
    history = list(row.get("operator_history") or [])
    history.append(
        {
            "reviewed_at": timestamp,
            "previous_operator_status": previous_status,
            "operator_status": status,
            "assigned_to": assigned_to if assigned_to is not None else row.get("assigned_to", ""),
            "reviewer": reviewer or "",
            "note": note or "",
        }
    )
    row["operator_history"] = history
    return row


def write_project_memory_review_queue(
    report: dict,
    output_path: str | Path = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "review_item_id",
        "review_lane",
        "priority",
        "source_artifact",
        "source_id",
        "candidate_id",
        "queue_id",
        "endpoint_group",
        "status",
        "review_action",
        "decision_needed",
        "operator_status",
        "assigned_to",
        "last_reviewed_by",
        "last_reviewed_at",
        "operator_note",
        "details",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def update_project_memory_review_item(
    review_item_id: str,
    *,
    operator_status: str,
    assigned_to: str | None = None,
    reviewer: str | None = None,
    note: str | None = None,
    queue_path: str | Path = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_PATH,
    csv_path: str | Path | None = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH,
) -> dict:
    status = str(operator_status or "").strip().lower()
    if status not in PROJECT_MEMORY_OPERATOR_STATUSES:
        raise ValueError(f"Unsupported project-memory operator status: {operator_status}")
    path = Path(queue_path)
    report = _read_json(path)
    rows = [dict(row) for row in report.get("rows") or []]
    updated = False
    for row in rows:
        if str(row.get("review_item_id") or "") != str(review_item_id):
            continue
        _set_operator_status(row, status=status, assigned_to=assigned_to, reviewer=reviewer, note=note)
        updated = True
        break
    if not updated:
        raise ValueError(f"review_item_id not found: {review_item_id}")
    report["rows"] = rows
    report["operator_status_counts"] = dict(Counter(str(row.get("operator_status") or "open") for row in rows).most_common())
    report["open_operator_item_count"] = sum(1 for row in rows if str(row.get("operator_status") or "open") not in {"closed", "deferred"})
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_project_memory_review_queue(report, path, csv_path=csv_path)
    return {
        "status": "updated",
        "review_item_id": review_item_id,
        "operator_status": status,
        "open_operator_item_count": report["open_operator_item_count"],
        "queue": report,
    }


def apply_project_memory_review_batch(
    *,
    queue_path: str | Path = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_PATH,
    csv_path: str | Path | None = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH,
    review_item_ids: list[str] | None = None,
    review_lane: str | None = None,
    current_operator_status: str | None = None,
    operator_status: str,
    assigned_to: str | None = None,
    reviewer: str | None = None,
    note: str | None = None,
    limit: int | None = None,
) -> dict:
    status = str(operator_status or "").strip().lower()
    if status not in PROJECT_MEMORY_OPERATOR_STATUSES:
        raise ValueError(f"Unsupported project-memory operator status: {operator_status}")
    selected_ids = {str(item) for item in (review_item_ids or []) if str(item)}
    path = Path(queue_path)
    report = _read_json(path)
    rows = [dict(row) for row in report.get("rows") or []]
    applied = []
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        if selected_ids and str(row.get("review_item_id") or "") not in selected_ids:
            continue
        if review_lane and str(row.get("review_lane") or "") != str(review_lane):
            continue
        if current_operator_status and str(row.get("operator_status") or "open") != str(current_operator_status):
            continue
        if not selected_ids and not review_lane:
            continue
        if limit is not None and len(applied) >= int(limit):
            continue
        _set_operator_status(
            row,
            status=status,
            assigned_to=assigned_to,
            reviewer=reviewer,
            note=note,
            now=now,
        )
        applied.append(str(row.get("review_item_id") or ""))
    report["rows"] = rows
    report["operator_status_counts"] = dict(Counter(str(row.get("operator_status") or "open") for row in rows).most_common())
    report["open_operator_item_count"] = sum(1 for row in rows if str(row.get("operator_status") or "open") not in {"closed", "deferred"})
    report["updated_at"] = now
    report["last_batch_update"] = {
        "updated_at": now,
        "operator_status": status,
        "review_lane": review_lane or "",
        "current_operator_status": current_operator_status or "",
        "applied_count": len(applied),
        "review_item_ids": applied,
        "reviewer": reviewer or "",
        "note": note or "",
    }
    write_project_memory_review_queue(report, path, csv_path=csv_path)
    return {
        "status": "updated",
        "applied_count": len(applied),
        "operator_status": status,
        "review_lane": review_lane or "",
        "review_item_ids": applied,
        "open_operator_item_count": report["open_operator_item_count"],
        "queue": report,
    }


def build_project_memory_review_dashboard(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    queue_path: str | Path = DEFAULT_PROJECT_MEMORY_REVIEW_QUEUE_PATH,
) -> dict:
    root_path = Path(root)
    item = Path(queue_path)
    queue_file = item if item.is_absolute() else root_path / item
    queue = _read_json(queue_file)
    rows = [dict(row) for row in queue.get("rows") or []]
    lane_rows = []
    for lane in sorted({str(row.get("review_lane") or "unknown") for row in rows}):
        lane_items = [row for row in rows if str(row.get("review_lane") or "unknown") == lane]
        status_counts = Counter(str(row.get("operator_status") or "open") for row in lane_items)
        priority_counts = Counter(str(row.get("priority") or "unknown") for row in lane_items)
        unclosed = [row for row in lane_items if str(row.get("operator_status") or "open") not in {"closed", "deferred"}]
        lane_rows.append(
            {
                "review_lane": lane,
                "row_count": len(lane_items),
                "open_like_count": len(unclosed),
                "open_count": status_counts.get("open", 0),
                "assigned_count": status_counts.get("assigned", 0),
                "in_review_count": status_counts.get("in_review", 0),
                "closed_count": status_counts.get("closed", 0),
                "deferred_count": status_counts.get("deferred", 0),
                "critical_count": priority_counts.get("critical", 0),
                "high_count": priority_counts.get("high", 0),
                "next_action": (unclosed[0].get("review_action") if unclosed else "none") or "none",
            }
        )
    assignee_counts = Counter(str(row.get("assigned_to") or "unassigned") for row in rows if str(row.get("operator_status") or "open") not in {"closed", "deferred"})
    assignee_rows = [
        {"assigned_to": assignee, "open_like_count": count}
        for assignee, count in assignee_counts.most_common()
    ]
    attention_rows = [
        {
            "review_item_id": row.get("review_item_id"),
            "review_lane": row.get("review_lane"),
            "priority": row.get("priority"),
            "operator_status": row.get("operator_status") or "open",
            "assigned_to": row.get("assigned_to") or "",
            "review_action": row.get("review_action"),
            "decision_needed": row.get("decision_needed"),
        }
        for row in sorted(
            [row for row in rows if str(row.get("operator_status") or "open") not in {"closed", "deferred"}],
            key=lambda row: (_priority_rank(str(row.get("priority") or "")), str(row.get("review_lane") or ""), str(row.get("review_item_id") or "")),
        )[:12]
    ]
    open_like_count = sum(int(row.get("open_like_count") or 0) for row in lane_rows)
    status = "ready" if rows and not open_like_count else "needs_attention" if rows else "empty"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "non_experimental_project_memory_review_dashboard",
        "project_name": project_name,
        "queue_status": queue.get("status") or "missing",
        "row_count": len(rows),
        "open_like_count": open_like_count,
        "lane_row_count": len(lane_rows),
        "assignee_row_count": len(assignee_rows),
        "lane_status_rows": lane_rows,
        "assignee_rows": assignee_rows,
        "attention_rows": attention_rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase", "real_experiment_feedback"],
        "recommended_next_actions": [
            "Triage profile-impact and measurement-gap lanes before the next policy/profile promotion.",
            "Assign unowned open rows to a reviewer or defer with a Project Memory note.",
            "Keep dashboard health based on local queue state, not real experiment feedback.",
        ],
    }


def write_project_memory_review_dashboard(
    report: dict,
    output_path: str | Path = DEFAULT_PROJECT_MEMORY_REVIEW_DASHBOARD_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROJECT_MEMORY_REVIEW_DASHBOARD_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "review_lane",
        "row_count",
        "open_like_count",
        "open_count",
        "assigned_count",
        "in_review_count",
        "closed_count",
        "deferred_count",
        "critical_count",
        "high_count",
        "next_action",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("lane_status_rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
