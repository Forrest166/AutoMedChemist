from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_WORKBENCH_JSON = Path("data/substituents/rgroup_approval_workbench.json")
DEFAULT_WORKBENCH_CSV = Path("data/substituents/rgroup_approval_workbench.csv")
DEFAULT_WORKBENCH_MD = Path("docs/rgroup_approval_workbench.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _split(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _impact_bucket(row: dict[str, Any]) -> str:
    matched = _split(row.get("matched_candidate_ids"))
    if not matched:
        return "no_current_candidate_match"
    decisions = {item.lower() for item in _split(row.get("sandbox_operator_decisions"))}
    if "deferred" in decisions:
        return "deferred_candidate_impact"
    if "rejected" in decisions:
        return "rejected_candidate_impact"
    if "approved" in decisions:
        return "approved_candidate_impact"
    return "candidate_impact_review"


def _action_bucket(row: dict[str, Any]) -> str:
    if row.get("approved_for_promotion") is True:
        return "approved_positive_control"
    if row.get("promotion_approval_decision") == "rejected":
        return "closed_rejected"
    if _impact_bucket(row) != "no_current_candidate_match":
        return "review_candidate_impact"
    if str(row.get("source_dataset") or "") == "patent_mined_seed":
        return "source_owner_review"
    if row.get("recommended_decision") == "approved":
        return "eligible_holdout"
    return "quality_or_policy_holdout"


def build_rgroup_approval_workbench(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    approval = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    selective = _read_json(root_path / "data/substituents/rgroup_selective_approval_batch.json")
    closure = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_queue.json")
    rollback = _read_json(root_path / "data/substituents/feed_promotion_rollback_audit.json")
    decisions = _read_json(root_path / "data/substituents/rgroup_approval_workbench_decisions.json")
    decisions_by_approval = {str(row.get("approval_id") or ""): row for row in decisions.get("rows") or []}
    rows: list[dict[str, Any]] = []
    for row in approval.get("rows") or []:
        impact_bucket = _impact_bucket(row)
        action_bucket = _action_bucket(row)
        approval_id = str(row.get("approval_id") or "")
        decision = decisions_by_approval.get(approval_id, {})
        rows.append(
            {
                "workbench_id": f"RGAWB-{len(rows) + 1:04d}",
                "approval_id": approval_id,
                "replacement_id": row.get("replacement_id", ""),
                "source_dataset": row.get("source_dataset", ""),
                "replacement_class": row.get("replacement_class", ""),
                "endpoint_group": row.get("endpoint_group", ""),
                "source_confidence_score": row.get("source_confidence_score", ""),
                "digest_status": row.get("digest_status", ""),
                "recommended_decision": row.get("recommended_decision", ""),
                "promotion_approval_decision": row.get("promotion_approval_decision", ""),
                "approved_for_promotion": row.get("approved_for_promotion", False),
                "promotion_eligible": row.get("promotion_eligible", False),
                "impact_bucket": impact_bucket,
                "action_bucket": action_bucket,
                "matched_candidate_ids": row.get("matched_candidate_ids", ""),
                "reviewer": row.get("reviewer", ""),
                "reviewed_at": row.get("reviewed_at", ""),
                "native_filter_key": "|".join(
                    [
                        str(row.get("source_dataset") or "source"),
                        str(row.get("replacement_class") or "class"),
                        str(row.get("promotion_approval_decision") or "decision"),
                        impact_bucket,
                    ]
                ),
                "editable_decision_supported": True,
                "workbench_decision": decision.get("workbench_decision", ""),
                "decision_status": decision.get("decision_status", "pending_workbench_decision"),
                "decision_note": decision.get("decision_note", ""),
                "next_action": (
                    "Audit positive-control checkpoint and keep whole-drop promotion disabled."
                    if action_bucket == "approved_positive_control"
                    else "Open chemist impact review before approval."
                    if action_bucket == "review_candidate_impact"
                    else "Route to source owner before any promotion."
                    if action_bucket == "source_owner_review"
                    else "Keep row deferred until quality closure queue is resolved."
                    if action_bucket in {"eligible_holdout", "quality_or_policy_holdout"}
                    else "No current approval action."
                ),
            }
        )
    decision_counts = Counter(str(row.get("promotion_approval_decision") or "") for row in rows)
    workbench_decision_counts = Counter(str(row.get("decision_status") or "") for row in rows)
    action_counts = Counter(str(row.get("action_bucket") or "") for row in rows)
    impact_counts = Counter(str(row.get("impact_bucket") or "") for row in rows)
    filters = {
        "source_dataset": sorted({str(row.get("source_dataset") or "") for row in rows if row.get("source_dataset")}),
        "replacement_class": sorted({str(row.get("replacement_class") or "") for row in rows if row.get("replacement_class")}),
        "promotion_approval_decision": sorted({str(row.get("promotion_approval_decision") or "") for row in rows if row.get("promotion_approval_decision")}),
        "impact_bucket": sorted({str(row.get("impact_bucket") or "") for row in rows if row.get("impact_bucket")}),
        "action_bucket": sorted({str(row.get("action_bucket") or "") for row in rows if row.get("action_bucket")}),
    }
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "awaiting_rows",
        "mode": "rgroup_approval_workbench",
        "row_count": len(rows),
        "approved_count": decision_counts.get("approved", 0),
        "deferred_count": decision_counts.get("deferred", 0),
        "rejected_count": decision_counts.get("rejected", 0),
        "positive_control_approved_count": selective.get("positive_control_approved_count", 0),
        "quality_open_count": closure.get("open_count", 0),
        "rollback_ready_count": rollback.get("ready_count", 0),
        "workbench_decision_status": decisions.get("status", "missing"),
        "workbench_decision_count": sum(1 for row in rows if row.get("workbench_decision")),
        "workbench_decision_status_counts": dict(workbench_decision_counts.most_common()),
        "promotion_allowed": approval.get("promotion_allowed", False),
        "decision_counts": dict(decision_counts.most_common()),
        "action_bucket_counts": dict(action_counts.most_common()),
        "impact_bucket_counts": dict(impact_counts.most_common()),
        "available_filters": filters,
        "production_scoring_affected": False,
        "rows": rows,
        "recommended_next_actions": [
            "Use native filters to review approvals by source, replacement class, decision, action bucket, and candidate-impact bucket.",
            "Approve additional rows only after quality closure and rollback checkpoints are green.",
        ],
    }


def render_rgroup_approval_workbench_markdown(report: dict) -> str:
    lines = [
        "# R-group Approval Workbench",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "| Workbench | Approval | Replacement | Source | Class | Decision | Impact | Action | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("workbench_id") or ""),
                    str(row.get("approval_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("replacement_class") or ""),
                    str(row.get("promotion_approval_decision") or ""),
                    str(row.get("impact_bucket") or ""),
                    str(row.get("action_bucket") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_approval_workbench(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_WORKBENCH_JSON,
    csv_path: str | Path | None = DEFAULT_WORKBENCH_CSV,
    markdown_path: str | Path | None = DEFAULT_WORKBENCH_MD,
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
        "endpoint_group",
        "source_confidence_score",
        "digest_status",
        "recommended_decision",
        "promotion_approval_decision",
        "approved_for_promotion",
        "promotion_eligible",
        "impact_bucket",
        "action_bucket",
        "matched_candidate_ids",
        "reviewer",
        "reviewed_at",
        "native_filter_key",
        "editable_decision_supported",
        "workbench_decision",
        "decision_status",
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
        md_file.write_text(render_rgroup_approval_workbench_markdown(report), encoding="utf-8")
