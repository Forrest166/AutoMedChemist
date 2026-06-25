from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DECISIONS_JSON = Path("data/substituents/rgroup_approval_workbench_decisions.json")
DEFAULT_DECISIONS_CSV = Path("data/substituents/rgroup_approval_workbench_decisions.csv")
DEFAULT_DECISIONS_MD = Path("docs/rgroup_approval_workbench_decisions.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _decision_for_row(row: dict[str, Any], *, reviewer: str, reviewed_at: str) -> dict[str, Any]:
    action_bucket = str(row.get("action_bucket") or "")
    if action_bucket == "approved_positive_control":
        decision = "approve_positive_control_rehearsal"
        status = "approved_rehearsal"
        note = "Approved only for guarded positive-control rehearsal; production feed promotion remains disabled."
        next_action = "Keep rollback checkpoint and do not run non-dry-run promotion."
    elif action_bucket == "review_candidate_impact":
        decision = "defer_candidate_impact_review"
        status = "deferred_holdout"
        note = "Candidate-impact rows require medchem score/rank review before approval."
        next_action = "Resolve sandbox score-delta and candidate-impact review."
    elif action_bucket == "source_owner_review":
        decision = "defer_source_owner_review"
        status = "deferred_holdout"
        note = "Source owner review required before this row can become a positive prior."
        next_action = "Route to source owner and keep row out of promotion."
    else:
        decision = "defer_quality_holdout"
        status = "deferred_holdout"
        note = "Quality or policy holdout remains in place."
        next_action = "Close quality ledger and rerun selective approval."
    return {
        "workbench_id": row.get("workbench_id", ""),
        "approval_id": row.get("approval_id", ""),
        "replacement_id": row.get("replacement_id", ""),
        "source_dataset": row.get("source_dataset", ""),
        "replacement_class": row.get("replacement_class", ""),
        "action_bucket": action_bucket,
        "impact_bucket": row.get("impact_bucket", ""),
        "workbench_decision": decision,
        "decision_status": status,
        "production_promotion_allowed": False,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "decision_note": note,
        "next_action": next_action,
    }


def build_rgroup_approval_workbench_decisions(
    *,
    root: str | Path = ".",
    reviewer: str = "local_approval_workbench",
) -> dict[str, Any]:
    root_path = Path(root)
    workbench = _read_json(root_path / "data/substituents/rgroup_approval_workbench.json")
    reviewed_at = datetime.now(timezone.utc).isoformat()
    rows = [_decision_for_row(row, reviewer=reviewer, reviewed_at=reviewed_at) for row in workbench.get("rows") or []]
    status_counts = Counter(str(row.get("decision_status") or "") for row in rows)
    decision_counts = Counter(str(row.get("workbench_decision") or "") for row in rows)
    return {
        "created_at": reviewed_at,
        "status": "decision_recorded" if rows else "awaiting_workbench",
        "mode": "rgroup_approval_workbench_decisions",
        "source_workbench_status": workbench.get("status", ""),
        "row_count": len(rows),
        "approved_rehearsal_count": status_counts.get("approved_rehearsal", 0),
        "deferred_holdout_count": status_counts.get("deferred_holdout", 0),
        "decision_status_counts": dict(status_counts.most_common()),
        "workbench_decision_counts": dict(decision_counts.most_common()),
        "production_scoring_affected": False,
        "production_promotion_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Use approved_rehearsal rows only for rollback-backed promotion rehearsal.",
            "Keep deferred_holdout rows out of production scoring until their workbench action bucket changes.",
        ],
    }


def render_rgroup_approval_workbench_decisions_markdown(report: dict) -> str:
    lines = [
        "# R-group Approval Workbench Decisions",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        f"- Approved rehearsal / deferred: `{report.get('approved_rehearsal_count')}` / `{report.get('deferred_holdout_count')}`",
        "",
        "| Workbench | Approval | Replacement | Action Bucket | Decision | Status | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("workbench_id") or ""),
                    str(row.get("approval_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("action_bucket") or ""),
                    str(row.get("workbench_decision") or ""),
                    str(row.get("decision_status") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_approval_workbench_decisions(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_DECISIONS_JSON,
    csv_path: str | Path | None = DEFAULT_DECISIONS_CSV,
    markdown_path: str | Path | None = DEFAULT_DECISIONS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "workbench_id",
        "approval_id",
        "replacement_id",
        "source_dataset",
        "replacement_class",
        "action_bucket",
        "impact_bucket",
        "workbench_decision",
        "decision_status",
        "production_promotion_allowed",
        "reviewer",
        "reviewed_at",
        "decision_note",
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
        md_file.write_text(render_rgroup_approval_workbench_decisions_markdown(report), encoding="utf-8")
