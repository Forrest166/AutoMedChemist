from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_REMEDIATION_JSON = Path("data/projects/demo/candidate_remediation_queue.json")
DEFAULT_REMEDIATION_CSV = Path("data/projects/demo/candidate_remediation_queue.csv")
DEFAULT_REMEDIATION_MD = Path("docs/candidate_remediation_queue.md")
DEFAULT_REMEDIATION_HISTORY_JSON = Path("data/projects/demo/candidate_remediation_queue_history.json")
DEFAULT_REMEDIATION_HISTORY_CSV = Path("data/projects/demo/candidate_remediation_queue_history.csv")
DEFAULT_REMEDIATION_HISTORY_MD = Path("docs/candidate_remediation_queue_history.md")
DEFAULT_REMEDIATION_SAVED_VIEWS_CSV = Path("data/projects/demo/candidate_remediation_saved_views.csv")
DEFAULT_REMEDIATION_TRENDS_CSV = Path("data/projects/demo/candidate_remediation_trends.csv")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]
EDITABLE_FIELDS = ["status", "owner", "due_date", "closure_note"]
OPEN_STATUSES = {"open", "reopened", "needs_follow_up", "blocked"}


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _task_id(prefix: str, value: object, index: int) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value or index)).strip("_")
    return f"{prefix}_{text or index:0>3}"[:96]


def _join_flags(*values: object) -> str:
    flags: list[str] = []
    for value in values:
        for item in str(value or "").replace(",", ";").split(";"):
            item = item.strip()
            if item and item not in flags:
                flags.append(item)
    return ";".join(flags)


def _history_paths(root_path: Path, project_name: str) -> tuple[Path, Path, Path]:
    project_dir = root_path / "data" / "projects" / project_name
    return (
        project_dir / "candidate_remediation_queue_history.json",
        project_dir / "candidate_remediation_queue_history.csv",
        root_path / "docs" / "candidate_remediation_queue_history.md",
    )


def _default_history(*, project_name: str = "demo") -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "empty",
        "mode": "local_candidate_remediation_queue_history",
        "project_name": project_name,
        "row_count": 0,
        "event_count": 0,
        "rows": [],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def _load_history(path: str | Path, *, project_name: str = "demo") -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("mode") == "local_candidate_remediation_queue_history":
        return payload
    return _default_history(project_name=project_name)


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _due_age_band(value: object, *, today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    text = str(value or "").strip()
    if not text:
        return "no_due_date"
    try:
        due = date.fromisoformat(text[:10])
    except ValueError:
        return "invalid_due_date"
    delta = (due - today).days
    if delta < 0:
        return "overdue"
    if delta == 0:
        return "due_today"
    if delta <= 3:
        return "due_soon"
    return "later"


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _build_saved_views(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    open_rows = [row for row in rows if str(row.get("status") or "open") in OPEN_STATUSES]
    views: list[dict[str, Any]] = [
        {
            "view_id": "high_open",
            "label": "High priority open tasks",
            "row_count": sum(1 for row in open_rows if row.get("priority") == "high"),
            "filter_status": "open|reopened|needs_follow_up|blocked",
            "filter_priority": "high",
            "filter_task_type": "",
            "filter_owner": "",
            "filter_age_band": "",
            "next_action": "Resolve high-priority local review blockers first.",
        },
        {
            "view_id": "due_now",
            "label": "Overdue or due soon",
            "row_count": sum(1 for row in open_rows if _due_age_band(row.get("due_date")) in {"overdue", "due_today", "due_soon"}),
            "filter_status": "open|reopened|needs_follow_up|blocked",
            "filter_priority": "",
            "filter_task_type": "",
            "filter_owner": "",
            "filter_age_band": "overdue|due_today|due_soon",
            "next_action": "Update owner, due date, or closure note before discussion handoff.",
        },
        {
            "view_id": "blocked",
            "label": "Blocked local tasks",
            "row_count": sum(1 for row in rows if str(row.get("status") or "") == "blocked"),
            "filter_status": "blocked",
            "filter_priority": "",
            "filter_task_type": "",
            "filter_owner": "",
            "filter_age_band": "",
            "next_action": "Explain the local blocker and decide whether to reopen, defer, or close.",
        },
    ]
    for task_type, count in sorted(_count_by(open_rows, "task_type").items(), key=lambda item: (-item[1], item[0]))[:6]:
        views.append(
            {
                "view_id": f"type_{task_type}",
                "label": f"Open {task_type}",
                "row_count": count,
                "filter_status": "open|reopened|needs_follow_up|blocked",
                "filter_priority": "",
                "filter_task_type": task_type,
                "filter_owner": "",
                "filter_age_band": "",
                "next_action": "Work this task-type slice with the linked local artifact open.",
            }
        )
    for owner, count in sorted(_count_by(open_rows, "owner").items(), key=lambda item: (-item[1], item[0]))[:6]:
        views.append(
            {
                "view_id": f"owner_{owner}",
                "label": f"Open tasks for {owner}",
                "row_count": count,
                "filter_status": "open|reopened|needs_follow_up|blocked",
                "filter_priority": "",
                "filter_task_type": "",
                "filter_owner": owner,
                "filter_age_band": "",
                "next_action": "Use this owner queue to update due dates or close reviewed tasks.",
            }
        )
    return views


def _build_trend_rows(rows: list[dict[str, Any]], history: dict[str, Any]) -> list[dict[str, Any]]:
    trend_rows: list[dict[str, Any]] = []
    dimensions = {
        "status": _count_by(rows, "status"),
        "priority": _count_by(rows, "priority"),
        "task_type": _count_by(rows, "task_type"),
        "owner": _count_by(rows, "owner"),
    }
    age_counts: dict[str, int] = {}
    for row in rows:
        age = _due_age_band(row.get("due_date"))
        age_counts[age] = age_counts.get(age, 0) + 1
    dimensions["age_band"] = age_counts
    for dimension, counts in dimensions.items():
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            trend_rows.append(
                {
                    "dimension": dimension,
                    "key": key,
                    "value": value,
                    "history_event_count": history.get("event_count", history.get("row_count", 0)),
                    "next_action": "Use saved views to work this remediation slice locally.",
                }
            )
    return trend_rows


def _merge_existing_edits(rows: list[dict[str, Any]], existing: dict) -> list[dict[str, Any]]:
    existing_by_id = {str(row.get("task_id") or ""): row for row in existing.get("rows") or [] if row.get("task_id")}
    merged_rows: list[dict[str, Any]] = []
    for row in rows:
        merged = dict(row)
        previous = existing_by_id.get(str(row.get("task_id") or ""))
        if previous:
            for field in EDITABLE_FIELDS:
                value = previous.get(field)
                if value not in {None, ""}:
                    merged[field] = value
            if previous.get("updated_at"):
                merged["updated_at"] = previous.get("updated_at")
        merged_rows.append(merged)
    return merged_rows


def _refresh_report_counts(report: dict[str, Any]) -> dict[str, Any]:
    rows = [dict(row) for row in report.get("rows") or []]
    history = report.get("history") if isinstance(report.get("history"), dict) else {}
    priority_counts: dict[str, int] = {}
    for row in rows:
        priority = str(row.get("priority") or "unknown")
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
    status_counts = _status_counts(rows)
    open_count = sum(1 for row in rows if str(row.get("status") or "open") in OPEN_STATUSES)
    report["row_count"] = len(rows)
    report["open_count"] = open_count
    report["closed_count"] = sum(1 for row in rows if str(row.get("status") or "") in {"closed", "resolved", "not_applicable"})
    report["high_count"] = priority_counts.get("high", 0)
    report["medium_count"] = priority_counts.get("medium", 0)
    report["low_count"] = priority_counts.get("low", 0)
    report["status_counts"] = status_counts
    report["saved_views"] = _build_saved_views(rows)
    report["saved_view_count"] = len(report["saved_views"])
    report["trend_rows"] = _build_trend_rows(rows, history)
    report["trend_row_count"] = len(report["trend_rows"])
    report["status"] = "ready" if rows else "clear"
    report["rows"] = rows
    return report


def build_candidate_remediation_queue(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    due_days: int = 7,
    preserve_existing: bool = True,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    evidence_quality = _read_json(project_dir / "evidence_quality_scorecard.json")
    reviewer_ops = _read_json(project_dir / "reviewer_operations.json")
    command_center = _read_json(project_dir / "review_command_center.json")
    created_at = datetime.now(timezone.utc)
    due_at = (created_at + timedelta(days=int(due_days))).date().isoformat()
    rows: list[dict[str, Any]] = []

    for index, row in enumerate(evidence_quality.get("rows") or [], start=1):
        bucket = str(row.get("quality_bucket") or "")
        if bucket == "clear":
            continue
        flags = str(row.get("quality_flags") or "")
        rows.append(
            {
                "task_id": _task_id("EQ", row.get("candidate_id"), index),
                "source": "evidence_quality_scorecard",
                "source_artifact": str(project_dir / "evidence_quality_scorecard.json"),
                "candidate_id": row.get("candidate_id", ""),
                "task_type": "evidence_quality_review",
                "priority": "high" if bucket == "attention_required" else "medium",
                "status": "open",
                "owner": row.get("reviewer") or "local_review_owner",
                "due_date": due_at,
                "reason": _join_flags(bucket, flags),
                "next_action": row.get("next_action", ""),
                "closure_note": "",
                "blocked_scopes": ";".join(BLOCKED_SCOPES),
            }
        )

    for index, row in enumerate(reviewer_ops.get("candidate_rows") or [], start=1):
        local_status = str(row.get("local_review_status") or row.get("review_status") or "")
        age = int(float(row.get("review_age_days") or 0))
        if local_status not in {"pending_review", "needs_follow_up", "blocked", "deferred", ""} and age < int(due_days):
            continue
        candidate_id = row.get("candidate_id", "")
        if any(str(item.get("candidate_id") or "") == str(candidate_id) and item.get("task_type") == "reviewer_follow_up" for item in rows):
            continue
        rows.append(
            {
                "task_id": _task_id("RO", candidate_id, index),
                "source": "reviewer_operations",
                "source_artifact": str(project_dir / "reviewer_operations.json"),
                "candidate_id": candidate_id,
                "task_type": "reviewer_follow_up",
                "priority": "high" if age >= int(due_days) else "medium",
                "status": "open",
                "owner": row.get("reviewer") or "local_review_owner",
                "due_date": due_at,
                "reason": _join_flags(local_status, row.get("defer_reason"), row.get("risk_bucket")),
                "next_action": row.get("next_action") or "Close, defer with reason, or re-route this local review row.",
                "closure_note": "",
                "blocked_scopes": ";".join(BLOCKED_SCOPES),
            }
        )

    existing_candidate_tasks = {str(row.get("candidate_id") or "") for row in rows if row.get("candidate_id")}
    for index, row in enumerate(command_center.get("rows") or [], start=1):
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id and candidate_id in existing_candidate_tasks:
            continue
        if str(row.get("severity") or "") not in {"high", "medium"}:
            continue
        rows.append(
            {
                "task_id": _task_id("CC", row.get("command_id") or row.get("action_id"), index),
                "source": "review_command_center",
                "source_artifact": str(project_dir / "review_command_center.json"),
                "candidate_id": candidate_id,
                "task_type": "command_center_follow_up",
                "priority": row.get("severity", "medium"),
                "status": "open",
                "owner": "local_review_owner",
                "due_date": due_at,
                "reason": row.get("summary", ""),
                "next_action": row.get("next_action", ""),
                "closure_note": "",
                "blocked_scopes": ";".join(BLOCKED_SCOPES),
            }
        )

    existing = _read_json(project_dir / "candidate_remediation_queue.json") if preserve_existing else {}
    rows = _merge_existing_edits(rows, existing) if preserve_existing else rows
    history_json, _, _ = _history_paths(root_path, project_name)
    history = _load_history(history_json, project_name=project_name)
    report = {
        "created_at": created_at.isoformat(),
        "status": "ready" if rows else "clear",
        "mode": "local_candidate_remediation_queue",
        "project_name": project_name,
        "row_count": len(rows),
        "open_count": 0,
        "closed_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "status_counts": {},
        "rows": rows,
        "history": history,
        "history_event_count": history.get("row_count", 0),
        "history_path": str(history_json),
        "real_experiment_feedback_used": False,
        "recommended_next_actions": [
            "Use the queue as local review ownership and closure tracking only.",
            "Do not convert remediation rows into procurement, supplier, or real experiment-feedback automation.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }
    return _refresh_report_counts(report)


def render_candidate_remediation_queue_markdown(report: dict) -> str:
    lines = [
        "# Candidate Remediation Queue",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Open / high / medium: `{report.get('open_count')}` / `{report.get('high_count')}` / `{report.get('medium_count')}`",
        f"- Saved views / trend rows: `{report.get('saved_view_count')}` / `{report.get('trend_row_count')}`",
        "",
        "| Task | Candidate | Type | Priority | Owner | Due | Reason | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:160]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("task_id") or ""),
                    str(row.get("candidate_id") or ""),
                    str(row.get("task_type") or ""),
                    str(row.get("priority") or ""),
                    str(row.get("owner") or ""),
                    str(row.get("due_date") or ""),
                    str(row.get("reason") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    if report.get("saved_views"):
        lines.extend(["", "## Saved Views", "", "| View | Rows | Status | Priority | Type | Owner | Age | Next Action |", "| --- | ---: | --- | --- | --- | --- | --- | --- |"])
        for row in report.get("saved_views") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("label") or ""),
                        str(row.get("row_count") or 0),
                        str(row.get("filter_status") or ""),
                        str(row.get("filter_priority") or ""),
                        str(row.get("filter_task_type") or ""),
                        str(row.get("filter_owner") or ""),
                        str(row.get("filter_age_band") or ""),
                        str(row.get("next_action") or "").replace("|", "/"),
                    ]
                )
                + " |"
            )
    if report.get("trend_rows"):
        lines.extend(["", "## Trend Slices", "", "| Dimension | Key | Value | History Events |", "| --- | --- | ---: | ---: |"])
        for row in (report.get("trend_rows") or [])[:80]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("dimension") or ""),
                        str(row.get("key") or ""),
                        str(row.get("value") or 0),
                        str(row.get("history_event_count") or 0),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def render_candidate_remediation_history_markdown(history: dict) -> str:
    lines = [
        "# Candidate Remediation Queue History",
        "",
        f"- Created at: `{history.get('created_at')}`",
        f"- Status: `{history.get('status')}`",
        f"- Events: `{history.get('event_count', history.get('row_count'))}`",
        "",
        "| Event | Task | Candidate | Action | Status | Owner | Due | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in (history.get("rows") or [])[-240:]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("event_id") or ""),
                    str(row.get("task_id") or ""),
                    str(row.get("candidate_id") or ""),
                    str(row.get("action") or ""),
                    f"{row.get('previous_status') or ''}->{row.get('new_status') or ''}",
                    f"{row.get('previous_owner') or ''}->{row.get('new_owner') or ''}",
                    f"{row.get('previous_due_date') or ''}->{row.get('new_due_date') or ''}",
                    str(row.get("note") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_remediation_history(
    history: dict,
    *,
    json_path: str | Path = DEFAULT_REMEDIATION_HISTORY_JSON,
    csv_path: str | Path | None = DEFAULT_REMEDIATION_HISTORY_CSV,
    markdown_path: str | Path | None = DEFAULT_REMEDIATION_HISTORY_MD,
) -> None:
    history = dict(history)
    rows = [dict(row) for row in history.get("rows") or []]
    history["row_count"] = len(rows)
    history["event_count"] = len(rows)
    history["status"] = "tracking" if rows else "empty"
    history["rows"] = rows
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "event_id",
        "created_at",
        "task_id",
        "candidate_id",
        "action",
        "actor",
        "previous_status",
        "new_status",
        "previous_owner",
        "new_owner",
        "previous_due_date",
        "new_due_date",
        "previous_closure_note",
        "new_closure_note",
        "note",
        "blocked_scopes",
    ]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_remediation_history_markdown(history), encoding="utf-8")


def ensure_candidate_remediation_history(
    *,
    project_name: str = "demo",
    json_path: str | Path = DEFAULT_REMEDIATION_HISTORY_JSON,
    csv_path: str | Path | None = DEFAULT_REMEDIATION_HISTORY_CSV,
    markdown_path: str | Path | None = DEFAULT_REMEDIATION_HISTORY_MD,
) -> dict[str, Any]:
    history = _load_history(json_path, project_name=project_name)
    write_candidate_remediation_history(history, json_path=json_path, csv_path=csv_path, markdown_path=markdown_path)
    return history


def apply_candidate_remediation_updates(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    task_ids: list[str],
    status: str | None = None,
    owner: str | None = None,
    due_date: str | None = None,
    closure_note: str | None = None,
    actor: str = "native_ui",
    action: str = "manual_update",
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    queue_json = project_dir / "candidate_remediation_queue.json"
    queue_csv = project_dir / "candidate_remediation_queue.csv"
    history_json, history_csv, history_md = _history_paths(root_path, project_name)
    report = _read_json(queue_json)
    if not report:
        report = build_candidate_remediation_queue(root=root_path, project_name=project_name)
    wanted = {str(task_id).strip() for task_id in task_ids if str(task_id).strip()}
    if not wanted:
        raise ValueError("No task_ids supplied.")
    rows = [dict(row) for row in report.get("rows") or []]
    history = _load_history(history_json, project_name=project_name)
    events = [dict(row) for row in history.get("rows") or []]
    now = datetime.now(timezone.utc).isoformat()
    touched = 0
    for row in rows:
        if str(row.get("task_id") or "") not in wanted:
            continue
        previous = {field: row.get(field, "") for field in EDITABLE_FIELDS}
        if status is not None and status != "":
            row["status"] = status
        if owner is not None and owner != "":
            row["owner"] = owner
        if due_date is not None and due_date != "":
            row["due_date"] = due_date
        if closure_note is not None:
            row["closure_note"] = closure_note
        row["updated_at"] = now
        touched += 1
        events.append(
            {
                "event_id": f"CRM-{len(events) + 1:06d}",
                "created_at": now,
                "task_id": row.get("task_id", ""),
                "candidate_id": row.get("candidate_id", ""),
                "action": action,
                "actor": actor,
                "previous_status": previous.get("status", ""),
                "new_status": row.get("status", ""),
                "previous_owner": previous.get("owner", ""),
                "new_owner": row.get("owner", ""),
                "previous_due_date": previous.get("due_date", ""),
                "new_due_date": row.get("due_date", ""),
                "previous_closure_note": previous.get("closure_note", ""),
                "new_closure_note": row.get("closure_note", ""),
                "note": closure_note or "",
                "blocked_scopes": ";".join(BLOCKED_SCOPES),
            }
        )
    report["rows"] = rows
    report["updated_at"] = now
    report["history_event_count"] = len(events)
    report["history"] = {"event_count": len(events), "row_count": len(events)}
    report["history_path"] = str(history_json)
    report = _refresh_report_counts(report)
    write_candidate_remediation_queue(report, json_path=queue_json, csv_path=queue_csv, markdown_path=root_path / "docs" / "candidate_remediation_queue.md")
    history.update(
        {
            "created_at": history.get("created_at") or now,
            "last_updated_at": now,
            "status": "tracking" if events else "empty",
            "mode": "local_candidate_remediation_queue_history",
            "project_name": project_name,
            "row_count": len(events),
            "event_count": len(events),
            "rows": events,
            "blocked_scopes": BLOCKED_SCOPES,
        }
    )
    write_candidate_remediation_history(history, json_path=history_json, csv_path=history_csv, markdown_path=history_md)
    return {
        "status": "updated" if touched else "no_matching_tasks",
        "mode": "local_candidate_remediation_queue_update",
        "updated_count": touched,
        "task_ids": sorted(wanted),
        "queue_status": report.get("status"),
        "open_count": report.get("open_count"),
        "history_event_count": len(events),
        "blocked_scopes": BLOCKED_SCOPES,
    }


def write_candidate_remediation_queue(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REMEDIATION_JSON,
    csv_path: str | Path | None = DEFAULT_REMEDIATION_CSV,
    markdown_path: str | Path | None = DEFAULT_REMEDIATION_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    report.pop("history", None)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "task_id",
        "source",
        "source_artifact",
        "candidate_id",
        "task_type",
        "priority",
        "status",
        "owner",
        "due_date",
        "reason",
        "next_action",
        "closure_note",
        "updated_at",
        "blocked_scopes",
    ]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_remediation_queue_markdown(report), encoding="utf-8")
    saved_views_csv = json_file.parent / "candidate_remediation_saved_views.csv"
    with saved_views_csv.open("w", encoding="utf-8", newline="") as handle:
        fields = ["view_id", "label", "row_count", "filter_status", "filter_priority", "filter_task_type", "filter_owner", "filter_age_band", "next_action"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("saved_views") or []:
            writer.writerow({field: row.get(field, "") for field in fields})
    trends_csv = json_file.parent / "candidate_remediation_trends.csv"
    with trends_csv.open("w", encoding="utf-8", newline="") as handle:
        fields = ["dimension", "key", "value", "history_event_count", "next_action"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("trend_rows") or []:
            writer.writerow({field: row.get(field, "") for field in fields})
    history_json = json_file.parent / "candidate_remediation_queue_history.json"
    history_csv = json_file.parent / "candidate_remediation_queue_history.csv"
    history_md = Path("docs/candidate_remediation_queue_history.md")
    if markdown_path:
        history_md = Path(markdown_path).parent / "candidate_remediation_queue_history.md"
    ensure_candidate_remediation_history(
        project_name=str(report.get("project_name") or "demo"),
        json_path=history_json,
        csv_path=history_csv,
        markdown_path=history_md,
    )
