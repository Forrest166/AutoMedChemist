from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_CLOSURE_FILTER_VIEWS_JSON = Path("data/projects/demo/review_closure_filter_views.json")
DEFAULT_REVIEW_CLOSURE_FILTER_VIEWS_CSV = Path("data/projects/demo/review_closure_filter_views.csv")
DEFAULT_REVIEW_CLOSURE_FILTER_VIEWS_MD = Path("docs/review_closure_filter_views.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _bucket_overdue(days: int) -> str:
    if days <= 0:
        return "not_overdue"
    if days <= 3:
        return "overdue_1_3d"
    if days <= 7:
        return "overdue_4_7d"
    return "overdue_gt_7d"


def _join_ids(rows: list[dict[str, Any]], limit: int = 24) -> str:
    ids = [str(row.get("task_id") or "").strip() for row in rows if str(row.get("task_id") or "").strip()]
    return ";".join(ids[:limit])


def _filter_expr(column: str, value: str) -> str:
    return f"{column}={value}"


def _view_row(view_type: str, value: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_count = sum(1 for row in rows if str(row.get("closure_status") or "open") == "open")
    overdue_count = sum(1 for row in rows if _int(row.get("overdue_days")) > 0)
    audit_count = sum(_int(row.get("audit_event_count")) for row in rows)
    status_counts = Counter(str(row.get("closure_status") or "open") for row in rows)
    priority_counts = Counter(str(row.get("priority") or "") for row in rows)
    return {
        "view_id": f"{view_type}:{value}",
        "view_type": view_type,
        "filter_value": value,
        "task_count": len(rows),
        "open_count": open_count,
        "closed_count": len(rows) - open_count,
        "overdue_count": overdue_count,
        "audit_event_count": audit_count,
        "status_counts": ";".join(f"{key}={count}" for key, count in status_counts.most_common()),
        "priority_counts": ";".join(f"{key}={count}" for key, count in priority_counts.most_common()),
        "task_ids": _join_ids(rows),
        "filter_expression": _filter_expr(view_type, value),
        "batch_action": "batch_review_overdue" if overdue_count else "batch_review_open" if open_count else "audit_closed_tasks",
        "next_action": "Open this filtered view, inspect audit history, then batch edit only rows with a reviewer note.",
    }


def build_review_closure_filter_views(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    selected_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    workbench = _read_json(project_dir / "review_closure_workbench.json")
    task_rows = [dict(row) for row in workbench.get("rows") or []]
    selected = {str(item).strip() for item in (selected_task_ids or []) if str(item).strip()}

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in task_rows:
        owner = str(row.get("owner") or "unassigned")
        reason = str(row.get("suggested_reason") or "unknown")
        batch = str(row.get("batch_group") or "ungrouped")
        status = str(row.get("closure_status") or "open")
        overdue = _bucket_overdue(_int(row.get("overdue_days")))
        audit = "has_audit" if _int(row.get("audit_event_count")) else "no_audit"
        priority = str(row.get("priority") or "unknown")
        for view_type, value in [
            ("owner", owner),
            ("reason", reason),
            ("batch_group", batch),
            ("closure_status", status),
            ("overdue_band", overdue),
            ("audit_state", audit),
            ("priority", priority),
        ]:
            grouped[(view_type, value)].append(row)

    rows = [_view_row(view_type, value, group_rows) for (view_type, value), group_rows in sorted(grouped.items())]
    selected_rows = [row for row in task_rows if str(row.get("task_id") or "").strip() in selected] if selected else []
    selected_action_rows = []
    if selected_rows:
        selected_action_rows.append(
            {
                "view_id": "selected:tasks",
                "view_type": "selected_tasks",
                "filter_value": "selected",
                "task_count": len(selected_rows),
                "open_count": sum(1 for row in selected_rows if str(row.get("closure_status") or "open") == "open"),
                "closed_count": sum(1 for row in selected_rows if str(row.get("closure_status") or "open") != "open"),
                "overdue_count": sum(1 for row in selected_rows if _int(row.get("overdue_days")) > 0),
                "audit_event_count": sum(_int(row.get("audit_event_count")) for row in selected_rows),
                "status_counts": "",
                "priority_counts": "",
                "task_ids": _join_ids(selected_rows, limit=80),
                "filter_expression": f"task_id in ({','.join(sorted(selected))})",
                "batch_action": "selected_batch_edit",
                "next_action": "Apply closure status, owner, due date, reason, and evidence link to the selected rows.",
            }
        )

    view_counts = Counter(row["view_type"] for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if task_rows else "empty",
        "mode": "review_closure_filter_views",
        "project_name": project_name,
        "row_count": len(rows),
        "task_row_count": len(task_rows),
        "selected_task_count": len(selected_rows),
        "view_type_counts": dict(view_counts.most_common()),
        "available_filters": ["owner", "reason", "batch_group", "closure_status", "overdue_band", "audit_state", "priority"],
        "rows": rows,
        "selected_action_rows": selected_action_rows,
        "recommended_next_actions": [
            "Use view rows to narrow closure batches by owner, reason, overdue band, or audit state.",
            "Use selected_action_rows for local batch edits; never treat closure as procurement or experiment execution.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_review_closure_filter_views_markdown(report: dict) -> str:
    lines = [
        "# Review Closure Filter Views",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Views / tasks: `{report.get('row_count')}` / `{report.get('task_row_count')}`",
        "",
        "| View | Value | Tasks | Open | Overdue | Audit | Action |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:180]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("view_type") or ""),
                    str(row.get("filter_value") or "").replace("|", "/"),
                    str(row.get("task_count") or 0),
                    str(row.get("open_count") or 0),
                    str(row.get("overdue_count") or 0),
                    str(row.get("audit_event_count") or 0),
                    str(row.get("batch_action") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_review_closure_filter_views(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_CLOSURE_FILTER_VIEWS_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_CLOSURE_FILTER_VIEWS_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_CLOSURE_FILTER_VIEWS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "view_id",
        "view_type",
        "filter_value",
        "task_count",
        "open_count",
        "closed_count",
        "overdue_count",
        "audit_event_count",
        "status_counts",
        "priority_counts",
        "task_ids",
        "filter_expression",
        "batch_action",
        "next_action",
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
        md_file.write_text(render_review_closure_filter_views_markdown(report), encoding="utf-8")
