from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_REMEDIATION_JSON = Path("data/projects/demo/review_remediation_queue.json")
DEFAULT_REVIEW_REMEDIATION_CSV = Path("data/projects/demo/review_remediation_queue.csv")
DEFAULT_REVIEW_REMEDIATION_MD = Path("docs/review_remediation_queue.md")
DEFAULT_REVIEW_REMEDIATION_CLOSURE_LEDGER = Path("data/projects/demo/review_remediation_closure_ledger.csv")
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


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _details_value(details: object, key: str) -> str:
    for part in str(details or "").split(";"):
        name, _, value = part.partition("=")
        if name.strip() == key:
            return value.strip()
    return ""


def _priority_from_status(status: object) -> str:
    value = str(status or "").strip().lower()
    if value in {"attention_required", "overdue", "critical", "fail", "stale_pending"}:
        return "high"
    if value in {"watch", "aging", "needs_attention", "changed", "entered", "exited", "needs_measurement"}:
        return "medium"
    return "low"


def _due_at(now: datetime, priority: str) -> str:
    days = 3 if priority == "high" else 7 if priority == "medium" else 14
    return (now + timedelta(days=days)).date().isoformat()


def _closure_lookup(rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    latest: dict[str, dict[str, str]] = {}
    audit_rows: list[dict[str, str]] = []
    for row in rows:
        task_id = str(row.get("task_id") or "").strip()
        if not task_id:
            continue
        closure_status = str(row.get("closure_status") or "open").strip() or "open"
        if closure_status == "reopened":
            closure_status = "open"
        audit = {
            "task_id": task_id,
            "closure_status": closure_status,
            "closure_reason": str(row.get("closure_reason") or "").strip(),
            "closure_note": str(row.get("closure_note") or "").strip(),
            "closed_by": str(row.get("closed_by") or row.get("reviewer") or "").strip(),
            "closed_at": str(row.get("closed_at") or row.get("created_at") or "").strip(),
            "evidence_link": str(row.get("evidence_link") or "").strip(),
            "owner": str(row.get("owner") or row.get("assigned_owner") or "").strip(),
            "due_at": str(row.get("due_at") or row.get("due_date") or "").strip(),
            "event_action": str(row.get("event_action") or row.get("action") or "").strip(),
            "batch_id": str(row.get("batch_id") or "").strip(),
        }
        audit_rows.append(audit)
        latest[task_id] = audit
    return latest, audit_rows


def _task(
    *,
    task_id: str,
    task_type: str,
    source_id: str,
    priority: str,
    owner: str,
    status: object,
    due_at: str,
    source_artifact: str,
    target_filter: str = "",
    details: object = "",
    next_action: object = "",
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_type": task_type,
        "source_id": source_id,
        "priority": priority,
        "owner": owner or "unassigned",
        "due_at": due_at,
        "closure_status": "open",
        "status": status,
        "target_filter": target_filter,
        "source_artifact": source_artifact,
        "details": details,
        "next_action": next_action,
        "closure_note": "",
        "closure_reason": "",
        "closed_by": "",
        "closed_at": "",
        "evidence_link": "",
        "audit_event_count": 0,
    }


def build_review_remediation_queue(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    closure_ledger_path: str | Path | None = DEFAULT_REVIEW_REMEDIATION_CLOSURE_LEDGER,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    evidence_quality = _read_json(project_dir / "evidence_quality_scorecard.json")
    reviewer_operations = _read_json(project_dir / "reviewer_operations.json")
    decision_qa = _read_json(project_dir / "candidate_decision_qa.json")
    baseline_lineage = _read_json(project_dir / "baseline_lineage_compare.json")
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for row in evidence_quality.get("rows") or []:
        bucket = str(row.get("quality_bucket") or "").strip()
        if bucket == "clear":
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        priority = _priority_from_status(bucket)
        rows.append(
            _task(
                task_id=f"EQ-{candidate_id or len(rows) + 1}",
                task_type="evidence_quality",
                source_id=candidate_id,
                priority=priority,
                owner=str(row.get("reviewer") or "evidence_owner"),
                status=bucket,
                due_at=_due_at(now, priority),
                source_artifact=str(project_dir / "evidence_quality_scorecard.json"),
                target_filter=f"candidate_id={candidate_id};site_class={row.get('site_class') or ''}",
                details=row.get("quality_flags"),
                next_action=row.get("next_action"),
            )
        )

    for row in reviewer_operations.get("rows") or []:
        status = str(row.get("status") or "").strip()
        if status in {"ready", "closed", "fresh"}:
            continue
        row_type = str(row.get("row_type") or "reviewer_operation")
        key = str(row.get("key") or "").strip()
        priority = _priority_from_status(status)
        reviewer = _details_value(row.get("details"), "reviewer")
        site = _details_value(row.get("details"), "site")
        rows.append(
            _task(
                task_id=f"RO-{row_type}-{key or len(rows) + 1}",
                task_type="reviewer_operations",
                source_id=key,
                priority=priority,
                owner=reviewer or "review_lead",
                status=status,
                due_at=_due_at(now, priority),
                source_artifact=str(project_dir / "reviewer_operations.json"),
                target_filter=f"candidate_id={key if row_type == 'candidate_sla' else ''};site_class={site};reviewer={reviewer}",
                details=row.get("details"),
                next_action=row.get("next_action"),
            )
        )

    for row in decision_qa.get("rows") or []:
        qa_bucket = str(row.get("qa_bucket") or "").strip()
        if qa_bucket == "clear":
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        priority = _priority_from_status(qa_bucket)
        rows.append(
            _task(
                task_id=f"QA-{candidate_id or len(rows) + 1}",
                task_type="decision_qa",
                source_id=candidate_id,
                priority=priority,
                owner=str(row.get("reviewer") or "decision_owner"),
                status=qa_bucket,
                due_at=_due_at(now, priority),
                source_artifact=str(project_dir / "candidate_decision_qa.json"),
                target_filter=f"candidate_id={candidate_id}",
                details=row.get("qa_reason"),
                next_action=row.get("next_action") or "Resolve non-clear decision QA before discussion handoff.",
            )
        )

    for row in baseline_lineage.get("rows") or []:
        lineage_status = str(row.get("lineage_status") or "").strip()
        if lineage_status == "unchanged":
            continue
        candidate_id = str(row.get("candidate_id") or row.get("candidate_key") or "").strip()
        priority = _priority_from_status(lineage_status)
        rows.append(
            _task(
                task_id=f"BL-{candidate_id or len(rows) + 1}",
                task_type="baseline_lineage",
                source_id=candidate_id,
                priority=priority,
                owner="baseline_owner",
                status=lineage_status,
                due_at=_due_at(now, priority),
                source_artifact=str(project_dir / "baseline_lineage_compare.json"),
                target_filter=f"candidate_id={candidate_id};site_class={row.get('site_class') or ''}",
                details=row.get("changed_fields"),
                next_action=row.get("rationale"),
            )
        )

    if closure_ledger_path is None or Path(closure_ledger_path) == DEFAULT_REVIEW_REMEDIATION_CLOSURE_LEDGER:
        ledger_file = project_dir / "review_remediation_closure_ledger.csv"
    else:
        ledger_file = root_path / closure_ledger_path
    closure_events = _read_csv_rows(ledger_file)
    closure_latest, closure_audit_rows = _closure_lookup(closure_events)
    event_counts = Counter(row["task_id"] for row in closure_audit_rows)
    for row in rows:
        closure = closure_latest.get(str(row.get("task_id") or "").strip())
        if not closure:
            continue
        row["closure_status"] = closure.get("closure_status") or "open"
        row["closure_note"] = closure.get("closure_note") or ""
        row["closure_reason"] = closure.get("closure_reason") or ""
        row["closed_by"] = closure.get("closed_by") or ""
        row["closed_at"] = closure.get("closed_at") or ""
        row["evidence_link"] = closure.get("evidence_link") or ""
        if closure.get("owner"):
            row["owner"] = closure.get("owner") or row.get("owner")
        if closure.get("due_at"):
            row["due_at"] = closure.get("due_at") or row.get("due_at")
        row["audit_event_count"] = event_counts.get(str(row.get("task_id") or ""), 0)

    type_counts = Counter(str(row.get("task_type") or "") for row in rows)
    priority_counts = Counter(str(row.get("priority") or "") for row in rows)
    owner_counts = Counter(str(row.get("owner") or "unassigned") for row in rows)
    closure_counts = Counter(str(row.get("closure_status") or "open") for row in rows)
    closed_count = sum(1 for row in rows if str(row.get("closure_status") or "open") != "open")
    return {
        "created_at": now.isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "review_remediation_queue",
        "project_name": project_name,
        "row_count": len(rows),
        "open_count": sum(1 for row in rows if row.get("closure_status") == "open"),
        "closed_count": closed_count,
        "closure_event_count": len(closure_audit_rows),
        "high_priority_count": priority_counts.get("high", 0),
        "medium_priority_count": priority_counts.get("medium", 0),
        "task_type_counts": dict(type_counts.most_common()),
        "priority_counts": dict(priority_counts.most_common()),
        "owner_counts": dict(owner_counts.most_common()),
        "closure_counts": dict(closure_counts.most_common()),
        "closure_ledger_path": str(ledger_file),
        "closure_audit_rows": closure_audit_rows[-200:],
        "rows": rows,
        "real_experiment_feedback_used": False,
        "recommended_next_actions": [
            "Work high-priority open tasks before candidate baseline pinning or discussion handoff.",
            "Record closure notes locally; do not treat queue closure as experiment execution or feedback import.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_review_remediation_queue_markdown(report: dict) -> str:
    lines = [
        "# Review Remediation Queue",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Open / closed / high priority: `{report.get('open_count')}` / `{report.get('closed_count')}` / `{report.get('high_priority_count')}`",
        f"- Closure ledger events: `{report.get('closure_event_count')}`",
        "",
        "| Task | Type | Source | Priority | Owner | Due | Closure | Status | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:180]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("task_id") or ""),
                    str(row.get("task_type") or ""),
                    str(row.get("source_id") or ""),
                    str(row.get("priority") or ""),
                    str(row.get("owner") or ""),
                    str(row.get("due_at") or ""),
                    str(row.get("closure_status") or ""),
                    str(row.get("status") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_review_remediation_queue(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_REMEDIATION_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_REMEDIATION_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_REMEDIATION_MD,
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
        "status",
        "target_filter",
        "source_artifact",
        "details",
        "next_action",
        "closure_note",
        "closure_reason",
        "closed_by",
        "closed_at",
        "evidence_link",
        "audit_event_count",
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
        md_file.write_text(render_review_remediation_queue_markdown(report), encoding="utf-8")
