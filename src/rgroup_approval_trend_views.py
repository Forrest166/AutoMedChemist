from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TRENDS_JSON = Path("data/substituents/rgroup_approval_trend_views.json")
DEFAULT_TRENDS_CSV = Path("data/substituents/rgroup_approval_trend_views.csv")
DEFAULT_TRENDS_MD = Path("docs/rgroup_approval_trend_views.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _trend_row(view_id: str, label: str, value: object, status: str, next_action: str, *, denominator: object = "", details: str = "") -> dict:
    return {
        "view_id": view_id,
        "label": label,
        "value": value,
        "denominator": denominator,
        "status": status,
        "details": details,
        "next_action": next_action,
    }


def build_rgroup_approval_trend_views(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    selective = _read_json(root_path / "data/substituents/rgroup_selective_approval_batch.json")
    closure = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_ledger.json")
    rollback = _read_json(root_path / "data/substituents/feed_promotion_rollback_audit.json")
    workbench_decisions = _read_json(root_path / "data/substituents/rgroup_approval_workbench_decisions.json")
    axis = _read_json(root_path / "data/substituents/ring_rgroup_axis_governance.json")
    rehearsal = _read_json(root_path / "data/substituents/rgroup_guarded_promotion_rehearsal.json")
    expansion = _read_json(root_path / "data/substituents/rgroup_next_expansion_batch_plan.json")
    approved = int(selective.get("positive_control_approved_count") or 0)
    holdout = int(selective.get("holdout_count") or 0)
    closure_open = int(closure.get("open_count") or 0)
    closure_closed = int(closure.get("closed_count") or 0)
    rollback_ready = int(rollback.get("ready_count") or 0)
    rollback_blocked = int(rollback.get("blocked_count") or 0)
    rows = [
        _trend_row(
            "approval_outcome_mix",
            "Approval outcome mix",
            approved,
            "watch" if holdout else "ready",
            "Review holdout reasons before expanding approved rows.",
            denominator=approved + holdout,
            details=f"approved={approved}; holdout={holdout}",
        ),
        _trend_row(
            "closure_completion",
            "Digestion closure completion",
            closure_closed,
            "ready" if closure_open == 0 and closure_closed else "needs_attention",
            "Keep closure_open at zero before rehearsal.",
            denominator=closure_closed + closure_open,
            details=f"closed={closure_closed}; open={closure_open}",
        ),
        _trend_row(
            "rollback_readiness",
            "Rollback readiness",
            rollback_ready,
            "ready" if rollback_ready and rollback_blocked == 0 else "needs_attention",
            "Every approved rehearsal row must keep rollback ready.",
            denominator=rollback_ready + rollback_blocked,
            details=f"ready={rollback_ready}; blocked={rollback_blocked}",
        ),
        _trend_row(
            "axis_distribution",
            "Ring/R-group axis distribution",
            axis.get("approved_rehearsal_count", 0),
            "ready" if axis.get("status") == "ready" else "needs_attention",
            "Use axis counts to balance the next ring and R-group review batch.",
            denominator=axis.get("row_count", 0),
            details=f"axis_counts={axis.get('axis_counts')}",
        ),
        _trend_row(
            "guarded_rehearsal",
            "Guarded promotion rehearsal",
            rehearsal.get("ready_count", 0),
            "ready" if rehearsal.get("status") == "ready_for_rehearsal" else "needs_attention",
            "Run dry-run rehearsal only while production promotion remains disabled.",
            denominator=rehearsal.get("row_count", 0),
            details=f"blocked={rehearsal.get('blocked_count')}; allowed={rehearsal.get('production_promotion_allowed')}",
        ),
        _trend_row(
            "next_expansion_capacity",
            "Next expansion capacity",
            expansion.get("planned_staging_cap_total", 0),
            "ready" if expansion.get("status") == "ready" else "needs_attention",
            "Stage capped analog/literature rows only after all batch blockers remain zero.",
            denominator=expansion.get("available_row_count", 0),
            details=f"ready={expansion.get('ready_count')}; blocked={expansion.get('blocked_count')}",
        ),
        _trend_row(
            "workbench_decision_roundtrip",
            "Workbench decision roundtrip",
            workbench_decisions.get("row_count", 0),
            "ready" if workbench_decisions.get("status") == "decision_recorded" else "needs_attention",
            "Keep approval decisions signed in CSV/JSON before changing ledgers.",
            denominator=selective.get("candidate_count", 0),
            details=f"approved_rehearsal={workbench_decisions.get('approved_rehearsal_count')}; deferred={workbench_decisions.get('deferred_holdout_count')}",
        ),
    ]
    needs_attention = sum(1 for row in rows if row.get("status") == "needs_attention")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if needs_attention == 0 else "ready_with_watch",
        "mode": "rgroup_approval_trend_views",
        "row_count": len(rows),
        "needs_attention_count": needs_attention,
        "production_scoring_affected": False,
        "production_promotion_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Use trend views to see whether approval growth is reducing quality debt.",
            "Do not increase next expansion capacity when closure, rollback, or workbench roundtrip status needs attention.",
        ],
    }


def render_rgroup_approval_trend_views_markdown(report: dict) -> str:
    lines = [
        "# R-group Approval Trend Views",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Needs attention: `{report.get('needs_attention_count')}`",
        "",
        "| View | Label | Value | Denominator | Status | Details | Next Action |",
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("view_id") or ""),
                    str(row.get("label") or ""),
                    str(row.get("value") or 0),
                    str(row.get("denominator") or ""),
                    str(row.get("status") or ""),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_approval_trend_views(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_TRENDS_JSON,
    csv_path: str | Path | None = DEFAULT_TRENDS_CSV,
    markdown_path: str | Path | None = DEFAULT_TRENDS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["view_id", "label", "value", "denominator", "status", "details", "next_action"]
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
        md_file.write_text(render_rgroup_approval_trend_views_markdown(report), encoding="utf-8")
