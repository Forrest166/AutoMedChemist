from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_OPS_JSON = Path("data/projects/demo/candidate_review_ops_console.json")
DEFAULT_REVIEW_OPS_CSV = Path("data/projects/demo/candidate_review_ops_console.csv")
DEFAULT_REVIEW_OPS_MD = Path("docs/candidate_review_ops_console.md")
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


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _group_by_candidate(report: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_id") or row.get("source_id") or "").strip()
        if not candidate_id:
            target_filter = str(row.get("target_filter") or "")
            for part in target_filter.split(";"):
                key, _, value = part.partition("=")
                if key.strip() == "candidate_id":
                    candidate_id = value.strip()
                    break
        if candidate_id:
            grouped[candidate_id].append(dict(row))
    return grouped


def _open_task(row: dict) -> bool:
    return str(row.get("status") or row.get("closure_status") or "open").lower() in {"open", "reopened", "needs_follow_up", "blocked"}


def _blocker_reason(board: dict, tasks: list[dict]) -> str:
    reasons = [
        board.get("blocked_contexts"),
        board.get("why_review"),
        board.get("site_class_governance_action"),
        board.get("risk_bucket"),
    ]
    reasons.extend(row.get("reason") for row in tasks[:3])
    return " | ".join(str(item) for item in reasons if item)[:360]


def _lane(local_status: str, risk: str, overdue: int, high: int, blocker: str) -> str:
    if overdue:
        return "overdue_review"
    if high:
        return "high_priority_remediation"
    if "blocked" in local_status or "blocked" in blocker.lower():
        return "blocked_context"
    if risk not in {"", "clear", "unknown"}:
        return "risk_review"
    if local_status in {"pending_review", "unreviewed", "needs_follow_up", ""}:
        return "pending_review"
    return "ready_or_reviewed"


def build_candidate_review_ops_console(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    board = _read_json(project_dir / "candidate_review_board.json")
    analytics = _read_json(project_dir / "candidate_review_analytics.json")
    remediation = _read_json(project_dir / "candidate_remediation_queue.json") or _read_json(project_dir / "review_remediation_queue.json")
    tasks_by_candidate = _group_by_candidate(remediation)
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for board_row in board.get("rows") or []:
        if not isinstance(board_row, dict):
            continue
        candidate_id = str(board_row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        tasks = [row for row in tasks_by_candidate.get(candidate_id, []) if _open_task(row)]
        due_dates = [_parse_date(row.get("due_date") or row.get("due_at")) for row in tasks]
        overdue_tasks = [row for row, due in zip(tasks, due_dates) if due is not None and due < today]
        high_tasks = [row for row in tasks if str(row.get("priority") or "").lower() == "high"]
        owners = sorted({str(row.get("owner") or "").strip() for row in tasks if row.get("owner")} or {str(board_row.get("reviewer") or "unassigned")})
        blocker = _blocker_reason(board_row, tasks)
        local_status = str(board_row.get("local_review_status") or board_row.get("review_status") or "pending_review")
        risk = str(board_row.get("risk_bucket") or "unknown")
        lane = _lane(local_status, risk, len(overdue_tasks), len(high_tasks), blocker)
        rows.append(
            {
                "candidate_id": candidate_id,
                "owner": ";".join(owners),
                "operation_lane": lane,
                "risk_bucket": risk,
                "local_review_status": local_status,
                "review_bucket": board_row.get("review_bucket") or "",
                "site_class": board_row.get("site_class") or "",
                "score": board_row.get("score") or "",
                "open_task_count": len(tasks),
                "high_priority_task_count": len(high_tasks),
                "overdue_task_count": len(overdue_tasks),
                "next_due_date": min((due for due in due_dates if due is not None), default=None).isoformat() if any(due_dates) else "",
                "blocker_reason": blocker,
                "task_ids": ";".join(str(row.get("task_id") or "") for row in tasks if row.get("task_id")),
                "next_action": "Work this lane in the native review/remediation view before changing local priority.",
                "export_scope": "local_candidate_review_ops_console",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    lane_counts = Counter(str(row.get("operation_lane") or "unknown") for row in rows)
    owner_counts = Counter(str(row.get("owner") or "unassigned") for row in rows)
    risk_counts = Counter(str(row.get("risk_bucket") or "unknown") for row in rows)
    cards = [
        {"card_id": "lanes", "label": "Operation lanes", "status": "ready", "value": len(lane_counts), "details": dict(lane_counts.most_common())},
        {"card_id": "owners", "label": "Owner load", "status": "ready", "value": len(owner_counts), "details": dict(owner_counts.most_common())},
        {"card_id": "risks", "label": "Risk buckets", "status": "needs_attention" if any(key not in {"clear", "unknown", ""} for key in risk_counts) else "ready", "value": sum(risk_counts.values()), "details": dict(risk_counts.most_common())},
        {"card_id": "overdue", "label": "Overdue tasks", "status": "needs_attention" if any(row.get("overdue_task_count") for row in rows) else "ready", "value": sum(int(row.get("overdue_task_count") or 0) for row in rows), "details": "Due dates are local review due dates only."},
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_review_board",
        "mode": "candidate_review_ops_console",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_count": len(rows),
        "open_task_count": sum(int(row.get("open_task_count") or 0) for row in rows),
        "overdue_task_count": sum(int(row.get("overdue_task_count") or 0) for row in rows),
        "high_priority_task_count": sum(int(row.get("high_priority_task_count") or 0) for row in rows),
        "analytics_status": analytics.get("status") or "missing",
        "lane_counts": dict(lane_counts.most_common()),
        "owner_counts": dict(owner_counts.most_common()),
        "risk_counts": dict(risk_counts.most_common()),
        "cards": cards,
        "rows": rows,
        "recommended_next_actions": [
            "Use operation_lane to work review and remediation together from one native table.",
            "Resolve overdue and high-priority local review tasks before pinning new candidate rankings.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_review_ops_console_markdown(report: dict) -> str:
    lines = [
        "# Candidate Review Ops Console",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Open / overdue: `{report.get('open_task_count')}` / `{report.get('overdue_task_count')}`",
        "",
        "| Candidate | Lane | Owner | Risk | Local | Open | High | Overdue | Blocker |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("operation_lane") or ""),
                    str(row.get("owner") or ""),
                    str(row.get("risk_bucket") or ""),
                    str(row.get("local_review_status") or ""),
                    str(row.get("open_task_count") or 0),
                    str(row.get("high_priority_task_count") or 0),
                    str(row.get("overdue_task_count") or 0),
                    str(row.get("blocker_reason") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_review_ops_console(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_OPS_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_OPS_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_OPS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "owner",
        "operation_lane",
        "risk_bucket",
        "local_review_status",
        "review_bucket",
        "site_class",
        "score",
        "open_task_count",
        "high_priority_task_count",
        "overdue_task_count",
        "next_due_date",
        "blocker_reason",
        "task_ids",
        "next_action",
        "export_scope",
        "procurement_allowed",
        "feedback_import_allowed",
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
        md_file.write_text(render_candidate_review_ops_console_markdown(report), encoding="utf-8")
