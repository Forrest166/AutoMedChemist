from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REHEARSAL_JSON = Path("data/substituents/rgroup_guarded_promotion_rehearsal.json")
DEFAULT_REHEARSAL_CSV = Path("data/substituents/rgroup_guarded_promotion_rehearsal.csv")
DEFAULT_REHEARSAL_MD = Path("docs/rgroup_guarded_promotion_rehearsal.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(row.get(key) or ""): row for row in rows if row.get(key)}


def build_rgroup_guarded_promotion_rehearsal(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    selective = _read_json(root_path / "data/substituents/rgroup_selective_approval_batch.json")
    rollback = _read_json(root_path / "data/substituents/feed_promotion_rollback_audit.json")
    closure = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_ledger.json")
    workbench_decisions = _read_json(root_path / "data/substituents/rgroup_approval_workbench_decisions.json")
    admission = _read_json(root_path / "data/substituents/rgroup_staging_admission_scorecard.json")
    owner_ledger = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json")
    promotion_diff = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    rollback_by_approval = _index(rollback.get("rows") or [], "approval_id")
    decision_by_approval = _index(workbench_decisions.get("rows") or [], "approval_id")
    diff_by_source = _index(promotion_diff.get("rows") or [], "source_dataset")
    rows: list[dict[str, Any]] = []
    for row in selective.get("rows") or []:
        if row.get("selective_approval_decision") != "approved":
            continue
        approval_id = str(row.get("approval_id") or "")
        rb = rollback_by_approval.get(approval_id, {})
        decision = decision_by_approval.get(approval_id, {})
        diff = diff_by_source.get(str(row.get("source_dataset") or ""), {})
        blockers: list[str] = []
        if rb.get("audit_status") != "ready":
            blockers.append("rollback_not_ready")
        if decision.get("decision_status") != "approved_rehearsal":
            blockers.append("workbench_rehearsal_decision_missing")
        if int(closure.get("open_count") or 0):
            blockers.append("quality_closure_open")
        if admission.get("status") != "ready":
            blockers.append("admission_not_ready")
        if owner_ledger.get("pending_owner_review_count") not in {0, None}:
            blockers.append("owner_review_pending")
        if diff.get("diff_status") != "ready_to_promote":
            blockers.append("promotion_diff_not_ready")
        rehearsal_status = "ready_for_rehearsal" if not blockers else "blocked"
        rows.append(
            {
                "rehearsal_id": f"RGREH-{len(rows) + 1:04d}",
                "approval_id": approval_id,
                "replacement_id": row.get("replacement_id", ""),
                "source_dataset": row.get("source_dataset", ""),
                "replacement_class": row.get("replacement_class", ""),
                "row_sha256": row.get("row_sha256", ""),
                "rollback_audit_id": rb.get("audit_id", ""),
                "rollback_status": rb.get("audit_status", ""),
                "workbench_decision": decision.get("workbench_decision", ""),
                "decision_status": decision.get("decision_status", ""),
                "promotion_diff_status": diff.get("diff_status", ""),
                "closure_open_count": closure.get("open_count", 0),
                "admission_status": admission.get("status", ""),
                "owner_ledger_status": owner_ledger.get("status", ""),
                "blocker_count": len(blockers),
                "blockers": ";".join(blockers),
                "rehearsal_status": rehearsal_status,
                "dry_run_command": "python scripts/promote_rgroup_feed_drop_from_staging.py --dry-run",
                "rollback_replay_command": rb.get("rollback_replay_command", "python scripts/build_feed_promotion_rollback_audit.py --dry-run"),
                "production_promotion_allowed": False,
                "next_action": (
                    "Use this row for dry-run rehearsal only; do not copy feeds without a separate production approval."
                    if not blockers
                    else "Resolve blockers before rehearsal."
                ),
            }
        )
    status_counts = Counter(str(row.get("rehearsal_status") or "") for row in rows)
    blocked_count = status_counts.get("blocked", 0)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready_for_rehearsal" if rows and blocked_count == 0 else "blocked" if rows else "awaiting_positive_controls",
        "mode": "rgroup_guarded_promotion_rehearsal",
        "row_count": len(rows),
        "ready_count": status_counts.get("ready_for_rehearsal", 0),
        "blocked_count": blocked_count,
        "closure_open_count": closure.get("open_count", 0),
        "rollback_ready_count": rollback.get("ready_count", 0),
        "workbench_approved_rehearsal_count": workbench_decisions.get("approved_rehearsal_count", 0),
        "production_scoring_affected": False,
        "production_promotion_allowed": False,
        "status_counts": dict(status_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Run only the listed dry-run commands during rehearsal.",
            "Keep production_promotion_allowed false until a separate whole-drop approval is intentionally recorded.",
        ],
    }


def render_rgroup_guarded_promotion_rehearsal_markdown(report: dict) -> str:
    lines = [
        "# R-group Guarded Promotion Rehearsal",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Ready / blocked: `{report.get('ready_count')}` / `{report.get('blocked_count')}`",
        f"- Production promotion allowed: `{report.get('production_promotion_allowed')}`",
        "",
        "| Rehearsal | Approval | Replacement | Source | Status | Blockers | Dry Run | Rollback |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("rehearsal_id") or ""),
                    str(row.get("approval_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("rehearsal_status") or ""),
                    str(row.get("blockers") or ""),
                    str(row.get("dry_run_command") or "").replace("|", "/"),
                    str(row.get("rollback_replay_command") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_guarded_promotion_rehearsal(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REHEARSAL_JSON,
    csv_path: str | Path | None = DEFAULT_REHEARSAL_CSV,
    markdown_path: str | Path | None = DEFAULT_REHEARSAL_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "rehearsal_id",
        "approval_id",
        "replacement_id",
        "source_dataset",
        "replacement_class",
        "row_sha256",
        "rollback_audit_id",
        "rollback_status",
        "workbench_decision",
        "decision_status",
        "promotion_diff_status",
        "closure_open_count",
        "admission_status",
        "owner_ledger_status",
        "blocker_count",
        "blockers",
        "rehearsal_status",
        "dry_run_command",
        "rollback_replay_command",
        "production_promotion_allowed",
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
        md_file.write_text(render_rgroup_guarded_promotion_rehearsal_markdown(report), encoding="utf-8")
