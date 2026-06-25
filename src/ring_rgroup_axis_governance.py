from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_AXIS_JSON = Path("data/substituents/ring_rgroup_axis_governance.json")
DEFAULT_AXIS_CSV = Path("data/substituents/ring_rgroup_axis_governance.csv")
DEFAULT_AXIS_MD = Path("docs/ring_rgroup_axis_governance.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_ring_rgroup_axis_governance(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    alignment = _read_json(root_path / "data/substituents/rgroup_ring_context_alignment.json")
    workbench_decisions = _read_json(root_path / "data/substituents/rgroup_approval_workbench_decisions.json")
    closure = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_ledger.json")
    decisions_by_approval = {str(row.get("approval_id") or ""): row for row in workbench_decisions.get("rows") or []}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in alignment.get("rows") or []:
        axis = str(row.get("modification_axis") or "rgroup_replacement")
        buckets[axis].append(row)
    rows: list[dict[str, Any]] = []
    for axis, axis_rows in sorted(buckets.items()):
        decision_statuses = Counter(
            str((decisions_by_approval.get(str(row.get("approval_id") or "")) or {}).get("decision_status") or "pending")
            for row in axis_rows
        )
        combined_count = sum(1 for row in axis_rows if str(row.get("review_mode") or "") == "combined_ring_rgroup_review")
        approved = decision_statuses.get("approved_rehearsal", 0)
        total = len(axis_rows)
        holdout = total - approved
        rows.append(
            {
                "axis_id": f"RGRAX-{len(rows) + 1:04d}",
                "modification_axis": axis,
                "row_count": total,
                "approved_rehearsal_count": approved,
                "holdout_count": holdout,
                "combined_review_count": combined_count,
                "closure_open_count": closure.get("open_count", 0),
                "axis_budget_status": "rehearsal_only" if approved else "holdout_only",
                "next_batch_cap": max(1, min(4, total)),
                "production_promotion_allowed": False,
                "governance_rule": (
                    "Route through ring-system benchmark and ring replacement review before R-group expansion."
                    if axis == "ring_replacement"
                    else "Route through local R-group replacement governance and attach ring context as compatibility metadata."
                ),
                "next_action": (
                    "Use approved rows for dry-run rehearsal only; keep full axis budget disabled."
                    if approved
                    else "Keep axis in holdout until approval workbench records a positive-control decision."
                ),
            }
        )
    if not rows:
        rows.append(
            {
                "axis_id": "RGRAX-0001",
                "modification_axis": "rgroup_replacement",
                "row_count": 0,
                "approved_rehearsal_count": 0,
                "holdout_count": 0,
                "combined_review_count": 0,
                "closure_open_count": closure.get("open_count", 0),
                "axis_budget_status": "awaiting_alignment",
                "next_batch_cap": 0,
                "production_promotion_allowed": False,
                "governance_rule": "Build ring/R-group context alignment before assigning axis budgets.",
                "next_action": "Rebuild rgroup_ring_context_alignment.",
            }
        )
    axis_counts = Counter(str(row.get("modification_axis") or "") for row in alignment.get("rows") or [])
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if alignment.get("rows") else "awaiting_alignment",
        "mode": "ring_rgroup_axis_governance",
        "axis_count": len(rows),
        "row_count": sum(int(row.get("row_count") or 0) for row in rows),
        "approved_rehearsal_count": sum(int(row.get("approved_rehearsal_count") or 0) for row in rows),
        "holdout_count": sum(int(row.get("holdout_count") or 0) for row in rows),
        "combined_review_count": sum(int(row.get("combined_review_count") or 0) for row in rows),
        "closure_open_count": closure.get("open_count", 0),
        "axis_counts": dict(axis_counts.most_common()),
        "production_scoring_affected": False,
        "production_promotion_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Use modification_axis as a first-class filter in generation, scoring explanations, and native review.",
            "Keep ring and R-group approval budgets separate until combined-review rows are explicitly signed.",
        ],
    }


def render_ring_rgroup_axis_governance_markdown(report: dict) -> str:
    lines = [
        "# Ring + R-group Axis Governance",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Axes: `{report.get('axis_count')}`",
        "",
        "| Axis | Rows | Approved Rehearsal | Holdout | Combined | Budget | Next Batch Cap | Rule |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("modification_axis") or ""),
                    str(row.get("row_count") or 0),
                    str(row.get("approved_rehearsal_count") or 0),
                    str(row.get("holdout_count") or 0),
                    str(row.get("combined_review_count") or 0),
                    str(row.get("axis_budget_status") or ""),
                    str(row.get("next_batch_cap") or 0),
                    str(row.get("governance_rule") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_ring_rgroup_axis_governance(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_AXIS_JSON,
    csv_path: str | Path | None = DEFAULT_AXIS_CSV,
    markdown_path: str | Path | None = DEFAULT_AXIS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "axis_id",
        "modification_axis",
        "row_count",
        "approved_rehearsal_count",
        "holdout_count",
        "combined_review_count",
        "closure_open_count",
        "axis_budget_status",
        "next_batch_cap",
        "production_promotion_allowed",
        "governance_rule",
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
        md_file.write_text(render_ring_rgroup_axis_governance_markdown(report), encoding="utf-8")
