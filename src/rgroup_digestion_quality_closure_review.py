from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LEDGER_JSON = Path("data/substituents/rgroup_digestion_quality_closure_ledger.json")
DEFAULT_LEDGER_CSV = Path("data/substituents/rgroup_digestion_quality_closure_ledger.csv")
DEFAULT_LEDGER_MD = Path("docs/rgroup_digestion_quality_closure_ledger.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _closure_for_task(task: dict[str, Any], *, reviewer: str, reviewed_at: str) -> dict[str, Any]:
    issue_type = str(task.get("issue_type") or "quality_watch")
    severity = str(task.get("severity") or "low")
    if severity == "high":
        decision = "requires_source_fix"
        status = "open_blocker"
        note = "High-severity provenance or license issue remains open until source metadata is fixed."
        next_required = "Fix source metadata and rebuild digestion quality metrics."
    elif issue_type == "endpoint_unassigned":
        decision = "closed_endpoint_holdout"
        status = "closed_holdout"
        note = "Endpoint assignment is not inferred automatically; affected slice is closed as promotion holdout."
        next_required = "Assign endpoint group or explicitly mark endpoint-independent before any future approval."
    elif issue_type == "low_confidence":
        decision = "closed_source_confidence_holdout"
        status = "closed_holdout"
        note = "Low-confidence source slice is acknowledged and kept out of promotion."
        next_required = "Upgrade source-confidence evidence or keep deferred in the next approval batch."
    elif issue_type == "duplicate_pressure":
        decision = "closed_duplicate_watch"
        status = "closed_holdout"
        note = "Duplicate-pressure slice is acknowledged and held for normalization review."
        next_required = "Collapse duplicates or document why repeated replacements should stay separate."
    elif "candidate_impact" in issue_type:
        decision = "closed_candidate_impact_holdout"
        status = "closed_holdout"
        note = "Candidate-impact slice is acknowledged and held for medchem review."
        next_required = "Resolve candidate score/rank impact before approval."
    else:
        decision = "closed_watch_acknowledged"
        status = "closed_watch"
        note = "Watch slice acknowledged; no production scoring action is taken."
        next_required = "Rebuild metrics and keep monitoring."

    return {
        "task_id": task.get("task_id", ""),
        "metric_id": task.get("metric_id", ""),
        "metric_type": task.get("metric_type", ""),
        "group_key": task.get("group_key", ""),
        "issue_type": issue_type,
        "severity": severity,
        "owner_role": task.get("owner_role", ""),
        "closure_decision": decision,
        "closure_status": status,
        "resolved_for_promotion": False,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "closure_note": note,
        "next_required_evidence": next_required,
    }


def build_rgroup_digestion_quality_closure_review(
    *,
    root: str | Path = ".",
    reviewer: str = "local_quality_closure",
) -> dict[str, Any]:
    root_path = Path(root)
    queue = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_queue.json")
    reviewed_at = datetime.now(timezone.utc).isoformat()
    rows = [_closure_for_task(row, reviewer=reviewer, reviewed_at=reviewed_at) for row in queue.get("rows") or []]
    status_counts = Counter(str(row.get("closure_status") or "") for row in rows)
    decision_counts = Counter(str(row.get("closure_decision") or "") for row in rows)
    issue_counts = Counter(str(row.get("issue_type") or "") for row in rows)
    open_count = sum(1 for row in rows if not str(row.get("closure_status") or "").startswith("closed"))
    holdout_count = sum(1 for row in rows if row.get("closure_status") == "closed_holdout")
    return {
        "created_at": reviewed_at,
        "status": "closed_holdout" if rows and open_count == 0 else "blocked" if open_count else "awaiting_queue",
        "mode": "rgroup_digestion_quality_closure_ledger",
        "source_queue_status": queue.get("status", ""),
        "task_count": len(rows),
        "closed_count": len(rows) - open_count,
        "open_count": open_count,
        "holdout_count": holdout_count,
        "resolved_for_promotion_count": sum(1 for row in rows if row.get("resolved_for_promotion") is True),
        "closure_status_counts": dict(status_counts.most_common()),
        "closure_decision_counts": dict(decision_counts.most_common()),
        "issue_type_counts": dict(issue_counts.most_common()),
        "production_scoring_affected": False,
        "production_promotion_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Treat closed_holdout as an explicit quality decision, not as production approval.",
            "Reopen a task only when new endpoint, confidence, duplicate, or candidate-impact evidence is supplied.",
        ],
    }


def render_rgroup_digestion_quality_closure_review_markdown(report: dict) -> str:
    lines = [
        "# R-group Digestion Quality Closure Ledger",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Closed / open: `{report.get('closed_count')}` / `{report.get('open_count')}`",
        f"- Resolved for promotion: `{report.get('resolved_for_promotion_count')}`",
        "",
        "| Task | Metric | Issue | Status | Decision | Owner | Next Required Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("task_id") or ""),
                    str(row.get("metric_id") or ""),
                    str(row.get("issue_type") or ""),
                    str(row.get("closure_status") or ""),
                    str(row.get("closure_decision") or ""),
                    str(row.get("owner_role") or ""),
                    str(row.get("next_required_evidence") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_digestion_quality_closure_review(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_LEDGER_JSON,
    csv_path: str | Path | None = DEFAULT_LEDGER_CSV,
    markdown_path: str | Path | None = DEFAULT_LEDGER_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "task_id",
        "metric_id",
        "metric_type",
        "group_key",
        "issue_type",
        "severity",
        "owner_role",
        "closure_decision",
        "closure_status",
        "resolved_for_promotion",
        "reviewer",
        "reviewed_at",
        "closure_note",
        "next_required_evidence",
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
        md_file.write_text(render_rgroup_digestion_quality_closure_review_markdown(report), encoding="utf-8")
