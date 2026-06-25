from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_CLOSURE_WORKBENCH_JSON = Path("data/projects/demo/review_closure_workbench.json")
DEFAULT_REVIEW_CLOSURE_WORKBENCH_CSV = Path("data/projects/demo/review_closure_workbench.csv")
DEFAULT_REVIEW_CLOSURE_WORKBENCH_MD = Path("docs/review_closure_workbench.md")
DEFAULT_REVIEW_REMEDIATION_QUEUE_JSON = Path("data/projects/demo/review_remediation_queue.json")
DEFAULT_REVIEW_REMEDIATION_CLOSURE_LEDGER = Path("data/projects/demo/review_remediation_closure_ledger.csv")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


REASON_TAXONOMY = [
    {
        "reason_id": "local_review_resolved",
        "default_status": "closed",
        "label": "Local review resolved",
        "description": "Reviewer resolved the local evidence or routing issue inside the local workflow.",
    },
    {
        "reason_id": "evidence_reconciled",
        "default_status": "closed",
        "label": "Evidence reconciled",
        "description": "Conflicting local/public evidence was reconciled or documented as context-dependent.",
    },
    {
        "reason_id": "accepted_risk",
        "default_status": "accepted_risk",
        "label": "Accepted local risk",
        "description": "Risk remains known and intentionally accepted for local discussion or watchlist use.",
    },
    {
        "reason_id": "duplicate_task",
        "default_status": "duplicate",
        "label": "Duplicate task",
        "description": "Task duplicates another remediation item and should not be worked twice.",
    },
    {
        "reason_id": "deferred_low_priority",
        "default_status": "deferred",
        "label": "Deferred low priority",
        "description": "Task is intentionally deferred while higher-priority local review items are handled.",
    },
    {
        "reason_id": "reopened_new_evidence",
        "default_status": "reopened",
        "label": "Reopened after new evidence",
        "description": "A previously closed task needs local re-review after new evidence or baseline movement.",
    },
]


DUE_DATE_POLICY = [
    {"priority": "high", "target_days": 3, "batch_group": "high_open", "label": "High-priority open review"},
    {"priority": "medium", "target_days": 7, "batch_group": "medium_open", "label": "Medium-priority review"},
    {"priority": "low", "target_days": 14, "batch_group": "low_open", "label": "Low-priority review"},
]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _priority_policy(priority: object) -> dict[str, Any]:
    value = str(priority or "").strip().lower()
    for row in DUE_DATE_POLICY:
        if row["priority"] == value:
            return dict(row)
    return dict(DUE_DATE_POLICY[-1])


def _reason_for(row: dict[str, Any]) -> str:
    status = str(row.get("closure_status") or "open").strip()
    if status == "accepted_risk":
        return "accepted_risk"
    if status == "duplicate":
        return "duplicate_task"
    if status == "deferred":
        return "deferred_low_priority"
    details = f"{row.get('details') or ''} {row.get('next_action') or ''}".lower()
    if "contradiction" in details or "conflict" in details:
        return "evidence_reconciled"
    return "local_review_resolved"


def build_review_closure_workbench(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    queue_path: str | Path | None = DEFAULT_REVIEW_REMEDIATION_QUEUE_JSON,
    ledger_path: str | Path | None = DEFAULT_REVIEW_REMEDIATION_CLOSURE_LEDGER,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    queue_file = root_path / queue_path if queue_path else project_dir / "review_remediation_queue.json"
    ledger_file = root_path / ledger_path if ledger_path else project_dir / "review_remediation_closure_ledger.csv"
    if Path(queue_file) == root_path / DEFAULT_REVIEW_REMEDIATION_QUEUE_JSON:
        queue_file = project_dir / "review_remediation_queue.json"
    if Path(ledger_file) == root_path / DEFAULT_REVIEW_REMEDIATION_CLOSURE_LEDGER:
        ledger_file = project_dir / "review_remediation_closure_ledger.csv"
    queue = _read_json(queue_file)
    task_rows = [dict(row) for row in queue.get("rows") or []]
    ledger_rows = _read_csv_rows(ledger_file)
    audit_by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ledger_rows:
        task_id = str(row.get("task_id") or "").strip()
        if task_id:
            audit_by_task[task_id].append(dict(row))
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for task in task_rows:
        task_id = str(task.get("task_id") or "").strip()
        due = _parse_date(task.get("due_at") or task.get("due_date"))
        closure_status = str(task.get("closure_status") or "open").strip() or "open"
        is_open = closure_status == "open"
        overdue_days = (today - due).days if is_open and due else 0
        policy = _priority_policy(task.get("priority"))
        audit_count = len(audit_by_task.get(task_id, []))
        if not is_open:
            batch_group = "closed_or_deferred"
        elif overdue_days > 0:
            batch_group = "overdue_open"
        else:
            batch_group = policy["batch_group"]
        rows.append(
            {
                "task_id": task_id,
                "task_type": task.get("task_type", ""),
                "source_id": task.get("source_id", ""),
                "priority": task.get("priority", ""),
                "owner": task.get("owner") or "unassigned",
                "due_at": task.get("due_at") or task.get("due_date") or "",
                "closure_status": closure_status,
                "suggested_reason": _reason_for(task),
                "due_policy_days": policy["target_days"],
                "batch_group": batch_group,
                "overdue_days": max(0, overdue_days),
                "audit_event_count": audit_count,
                "latest_note": task.get("closure_note", ""),
                "target_filter": task.get("target_filter", ""),
                "next_action": task.get("next_action", ""),
            }
        )
    open_rows = [row for row in rows if row["closure_status"] == "open"]
    batch_counts = Counter(row["batch_group"] for row in rows)
    owner_counts = Counter(str(row.get("owner") or "unassigned") for row in open_rows)
    status_counts = Counter(str(row.get("closure_status") or "open") for row in rows)
    filtered_audit_rows = [
        {
            "task_id": row.get("task_id", ""),
            "closure_status": row.get("closure_status", ""),
            "closure_reason": row.get("closure_reason", ""),
            "closure_note": row.get("closure_note", ""),
            "closed_by": row.get("closed_by") or row.get("reviewer", ""),
            "closed_at": row.get("closed_at") or row.get("created_at", ""),
            "owner": row.get("owner", ""),
            "due_at": row.get("due_at") or row.get("due_date", ""),
            "batch_id": row.get("batch_id", ""),
        }
        for row in ledger_rows
        if str(row.get("task_id") or "").strip() in {str(task.get("task_id") or "").strip() for task in task_rows}
    ][-240:]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "review_closure_workbench",
        "project_name": project_name,
        "row_count": len(rows),
        "open_count": len(open_rows),
        "closed_count": sum(1 for row in rows if row["closure_status"] != "open"),
        "overdue_count": sum(1 for row in rows if int(row.get("overdue_days") or 0) > 0),
        "audit_event_count": len(ledger_rows),
        "filtered_audit_event_count": len(filtered_audit_rows),
        "reason_taxonomy_count": len(REASON_TAXONOMY),
        "due_policy_count": len(DUE_DATE_POLICY),
        "batch_counts": dict(batch_counts.most_common()),
        "owner_counts": dict(owner_counts.most_common()),
        "status_counts": dict(status_counts.most_common()),
        "reason_taxonomy": REASON_TAXONOMY,
        "due_date_policy": DUE_DATE_POLICY,
        "batch_actions": [
            {
                "batch_group": group,
                "task_count": count,
                "recommended_action": "Batch close only after reviewer note and evidence link are recorded." if group != "closed_or_deferred" else "Use audit history for closed/deferred task review.",
            }
            for group, count in batch_counts.most_common()
        ],
        "filtered_audit_rows": filtered_audit_rows,
        "rows": rows,
        "recommended_next_actions": [
            "Use reason_taxonomy and due_date_policy when batch editing remediation tasks.",
            "Use filtered_audit_rows to review task history before reopening or accepting risk.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_review_closure_workbench_markdown(report: dict) -> str:
    lines = [
        "# Review Closure Workbench",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Open / closed / overdue: `{report.get('open_count')}` / `{report.get('closed_count')}` / `{report.get('overdue_count')}`",
        f"- Audit events: `{report.get('filtered_audit_event_count')}` filtered / `{report.get('audit_event_count')}` total",
        "",
        "| Task | Priority | Owner | Due | Closure | Reason | Batch | Audit | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:180]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("task_id") or ""),
                    str(row.get("priority") or ""),
                    str(row.get("owner") or ""),
                    str(row.get("due_at") or ""),
                    str(row.get("closure_status") or ""),
                    str(row.get("suggested_reason") or ""),
                    str(row.get("batch_group") or ""),
                    str(row.get("audit_event_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Reason Taxonomy", "", "| Reason | Default Status | Description |", "| --- | --- | --- |"])
    for row in report.get("reason_taxonomy") or []:
        lines.append(f"| {row.get('reason_id')} | {row.get('default_status')} | {str(row.get('description') or '').replace('|', '/')} |")
    lines.append("")
    return "\n".join(lines)


def write_review_closure_workbench(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_CLOSURE_WORKBENCH_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_CLOSURE_WORKBENCH_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_CLOSURE_WORKBENCH_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "task_id",
        "task_type",
        "source_id",
        "priority",
        "owner",
        "due_at",
        "closure_status",
        "suggested_reason",
        "due_policy_days",
        "batch_group",
        "overdue_days",
        "audit_event_count",
        "latest_note",
        "target_filter",
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
        md_file.write_text(render_review_closure_workbench_markdown(report), encoding="utf-8")
