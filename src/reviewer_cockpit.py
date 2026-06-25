from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_JSON = Path("data/projects/demo/reviewer_cockpit.json")
DEFAULT_CSV = Path("data/projects/demo/reviewer_cockpit.csv")
DEFAULT_MD = Path("docs/reviewer_cockpit.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]
OPEN_STATUSES = {"open", "reopened", "needs_follow_up", "blocked", "pending", "pending_review", ""}


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


def _is_open(row: dict) -> bool:
    return str(row.get("closure_status") or row.get("status") or "open").strip().lower() in OPEN_STATUSES


def _priority_from_count(count: int, status: object = "") -> str:
    text = str(status or "").lower()
    if "blocked" in text or count >= 8:
        return "high"
    if count >= 3 or "review" in text:
        return "medium"
    return "low"


def build_reviewer_cockpit(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    reason = _read_json(project_dir / "candidate_review_reason_workbench.json")
    reason_audit = _read_json(project_dir / "candidate_review_reason_workbench_audit.json")
    closure = _read_json(project_dir / "review_closure_workbench.json")
    remediation = _read_json(project_dir / "candidate_remediation_queue.json") or _read_json(project_dir / "review_remediation_queue.json")
    board = _read_json(project_dir / "candidate_review_board.json")

    rows: list[dict[str, Any]] = []
    audit_by_reason = Counter(str(row.get("reason_cluster") or "unknown") for row in reason_audit.get("rows") or reason.get("audit_rows") or [])
    for index, cluster in enumerate(reason.get("rows") or [], start=1):
        reason_key = str(cluster.get("reason_cluster") or cluster.get("key") or "").strip() or "unknown"
        cluster_rows = _int(cluster.get("cluster_row_count"))
        closed_count = _int(cluster.get("closed_batch_count"))
        open_count = max(0, cluster_rows - closed_count)
        rows.append(
            {
                "cockpit_id": f"RCPT-RSN-{index:03d}",
                "lane": "reason_audit",
                "row_type": "reason_cluster",
                "key": reason_key,
                "status": cluster.get("cluster_status") or ("closed" if open_count == 0 and cluster_rows else "needs_review"),
                "priority": _priority_from_count(open_count, cluster.get("cluster_status")),
                "open_count": open_count,
                "audit_event_count": audit_by_reason.get(reason_key, 0),
                "owner": "local_review_owner",
                "target_filter": f"pending_reason={reason_key}",
                "artifact_path": str(project_dir / "candidate_review_reason_workbench.json"),
                "next_action": "Open this reason cluster, inspect evidence, then batch note or close visible rows.",
            }
        )

    closure_rows = [dict(row) for row in closure.get("rows") or [] if _is_open(dict(row))]
    for index, row in enumerate(closure_rows[:40], start=1):
        rows.append(
            {
                "cockpit_id": f"RCPT-CLS-{index:03d}",
                "lane": "closure",
                "row_type": row.get("task_type") or "closure_task",
                "key": row.get("task_id") or row.get("source_id") or "",
                "status": row.get("closure_status") or row.get("status") or "",
                "priority": row.get("priority") or "medium",
                "open_count": 1,
                "audit_event_count": _int(row.get("audit_event_count")),
                "owner": row.get("owner") or "",
                "target_filter": f"task_id={row.get('task_id') or ''}",
                "artifact_path": str(project_dir / "review_closure_workbench.json"),
                "next_action": row.get("next_action") or "Resolve or defer the closure item with a local reason code.",
            }
        )

    grouped_remediation: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in remediation.get("rows") or []:
        row = dict(row)
        if _is_open(row):
            grouped_remediation[(str(row.get("priority") or "medium"), str(row.get("owner") or "unassigned"))].append(row)
    for index, ((priority, owner), group) in enumerate(sorted(grouped_remediation.items()), start=1):
        sample = group[0]
        rows.append(
            {
                "cockpit_id": f"RCPT-REM-{index:03d}",
                "lane": "remediation",
                "row_type": "remediation_group",
                "key": f"{priority}:{owner}",
                "status": "open",
                "priority": priority,
                "open_count": len(group),
                "audit_event_count": 0,
                "owner": owner,
                "target_filter": f"priority={priority};owner={owner}",
                "artifact_path": str(project_dir / "candidate_remediation_queue.json"),
                "next_action": sample.get("next_action") or "Assign, postpone, or close the visible remediation group.",
            }
        )

    pending_board = [
        dict(row)
        for row in board.get("rows") or []
        if str(row.get("local_review_status") or row.get("local_status") or "").lower() in {"", "pending", "pending_review"}
    ]
    if pending_board:
        rows.append(
            {
                "cockpit_id": "RCPT-BOARD-001",
                "lane": "candidate_board",
                "row_type": "pending_candidate_rows",
                "key": "pending_local_review",
                "status": "pending_review",
                "priority": _priority_from_count(len(pending_board), "pending_review"),
                "open_count": len(pending_board),
                "audit_event_count": 0,
                "owner": "local_review_owner",
                "target_filter": "local_status=pending_review",
                "artifact_path": str(project_dir / "candidate_review_board.json"),
                "next_action": "Filter pending local review rows and resolve the top evidence drawer first.",
            }
        )

    lane_counts = Counter(str(row.get("lane") or "unknown") for row in rows)
    priority_counts = Counter(str(row.get("priority") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "reviewer_cockpit",
        "project_name": project_name,
        "row_count": len(rows),
        "lane_counts": dict(lane_counts.most_common()),
        "priority_counts": dict(priority_counts.most_common()),
        "high_priority_count": priority_counts.get("high", 0),
        "audit_event_count": sum(_int(row.get("audit_event_count")) for row in rows),
        "open_remediation_count": sum(_int(row.get("open_count")) for row in rows if row.get("lane") == "remediation"),
        "open_closure_count": sum(_int(row.get("open_count")) for row in rows if row.get("lane") == "closure"),
        "reason_lane_count": lane_counts.get("reason_audit", 0),
        "rows": rows,
        "recommended_next_actions": [
            "Use the cockpit as the first review page: reason cluster, closure, and remediation rows are routed from one table.",
            "Keep actions local to reviewer notes and closure ledgers.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
        "scope_note": "Local reviewer operations only; external operational workflows are out of scope.",
    }


def render_reviewer_cockpit_markdown(report: dict) -> str:
    lines = [
        "# Reviewer Cockpit",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        f"- Lanes: `{report.get('lane_counts')}`",
        "",
        "| Lane | Key | Status | Priority | Open | Audit | Owner | Next Action |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("lane") or ""),
                    str(row.get("key") or "").replace("|", "/"),
                    str(row.get("status") or ""),
                    str(row.get("priority") or ""),
                    str(row.get("open_count") or 0),
                    str(row.get("audit_event_count") or 0),
                    str(row.get("owner") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reviewer_cockpit(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_JSON,
    csv_path: str | Path | None = DEFAULT_CSV,
    markdown_path: str | Path | None = DEFAULT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "cockpit_id",
        "lane",
        "row_type",
        "key",
        "status",
        "priority",
        "open_count",
        "audit_event_count",
        "owner",
        "target_filter",
        "artifact_path",
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
        md_file.write_text(render_reviewer_cockpit_markdown(report), encoding="utf-8")
