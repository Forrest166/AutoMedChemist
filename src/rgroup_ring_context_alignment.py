from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ALIGNMENT_JSON = Path("data/substituents/rgroup_ring_context_alignment.json")
DEFAULT_ALIGNMENT_CSV = Path("data/substituents/rgroup_ring_context_alignment.csv")
DEFAULT_ALIGNMENT_MD = Path("docs/rgroup_ring_context_alignment.md")


RING_CLASS_HINTS = {"phenyl_to_heteroaryl", "aryl_to_heteroaryl", "heteroaryl_scan", "ring_replacement"}
RGROUP_CLASS_HINTS = {
    "acid_bioisostere",
    "ether_sidechain_scan",
    "fluoroalkyl_scan",
    "polar_group_scan",
    "property_tuning",
    "halogen_to_polar_scan",
}


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


def _axis(row: dict[str, Any]) -> tuple[str, str, str]:
    replacement_class = str(row.get("replacement_class") or "").strip().lower()
    if replacement_class in RING_CLASS_HINTS or "phenyl" in replacement_class or "heteroaryl" in replacement_class or "pyridyl" in replacement_class:
        return (
            "ring_replacement",
            "aryl_ring_context",
            "Map to the ring-system replacement library before expanding around this approval.",
        )
    if replacement_class in RGROUP_CLASS_HINTS:
        return (
            "rgroup_replacement",
            "local_substituent_context",
            "Keep as R-group replacement; use ring context only as a scaffold compatibility annotation.",
        )
    return (
        "rgroup_replacement",
        "unclassified_local_context",
        "Classify replacement axis before production promotion.",
    )


def build_rgroup_ring_context_alignment(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    approval = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    workbench = _read_json(root_path / "data/substituents/rgroup_approval_workbench.json")
    rows: list[dict[str, Any]] = []
    workbench_by_approval = {str(row.get("approval_id") or ""): row for row in workbench.get("rows") or []}
    for row in approval.get("rows") or []:
        axis, context_hint, next_action = _axis(row)
        matched = _split(row.get("matched_candidate_ids"))
        approval_id = str(row.get("approval_id") or "")
        wb = workbench_by_approval.get(approval_id, {})
        review_mode = "combined_ring_rgroup_review" if axis == "ring_replacement" and matched else axis
        rows.append(
            {
                "alignment_id": f"RGRCTX-{len(rows) + 1:04d}",
                "approval_id": approval_id,
                "workbench_id": wb.get("workbench_id", ""),
                "replacement_id": row.get("replacement_id", ""),
                "source_dataset": row.get("source_dataset", ""),
                "replacement_class": row.get("replacement_class", ""),
                "modification_axis": axis,
                "ring_context_hint": context_hint,
                "review_mode": review_mode,
                "matched_candidate_count": len(matched),
                "promotion_approval_decision": row.get("promotion_approval_decision", ""),
                "approved_for_promotion": row.get("approved_for_promotion", False),
                "ring_library_link_required": axis == "ring_replacement",
                "rgroup_library_link_required": True,
                "promotion_allowed": approval.get("promotion_allowed", False),
                "next_action": next_action,
            }
        )
    axis_counts = Counter(str(row.get("modification_axis") or "") for row in rows)
    review_counts = Counter(str(row.get("review_mode") or "") for row in rows)
    ring_rows = axis_counts.get("ring_replacement", 0)
    linked_rows = sum(1 for row in rows if row.get("workbench_id"))
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "awaiting_rows",
        "mode": "rgroup_ring_context_alignment",
        "row_count": len(rows),
        "ring_replacement_count": ring_rows,
        "rgroup_replacement_count": axis_counts.get("rgroup_replacement", 0),
        "combined_review_count": review_counts.get("combined_ring_rgroup_review", 0),
        "workbench_linked_count": linked_rows,
        "axis_counts": dict(axis_counts.most_common()),
        "review_mode_counts": dict(review_counts.most_common()),
        "promotion_allowed": approval.get("promotion_allowed", False),
        "production_scoring_affected": False,
        "rows": rows,
        "recommended_next_actions": [
            "Upgrade the generator to treat ring replacement and R-group replacement as two coordinated axes.",
            "Use ring context hints to bind phenyl-to-heteroaryl rows to ring-system benchmarks before broader expansion.",
        ],
    }


def render_rgroup_ring_context_alignment_markdown(report: dict) -> str:
    lines = [
        "# R-group Ring Context Alignment",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Ring / R-group rows: `{report.get('ring_replacement_count')}` / `{report.get('rgroup_replacement_count')}`",
        "",
        "| Alignment | Approval | Replacement | Class | Axis | Context | Review Mode | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("alignment_id") or ""),
                    str(row.get("approval_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("replacement_class") or ""),
                    str(row.get("modification_axis") or ""),
                    str(row.get("ring_context_hint") or ""),
                    str(row.get("review_mode") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_ring_context_alignment(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_ALIGNMENT_JSON,
    csv_path: str | Path | None = DEFAULT_ALIGNMENT_CSV,
    markdown_path: str | Path | None = DEFAULT_ALIGNMENT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "alignment_id",
        "approval_id",
        "workbench_id",
        "replacement_id",
        "source_dataset",
        "replacement_class",
        "modification_axis",
        "ring_context_hint",
        "review_mode",
        "matched_candidate_count",
        "promotion_approval_decision",
        "approved_for_promotion",
        "ring_library_link_required",
        "rgroup_library_link_required",
        "promotion_allowed",
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
        md_file.write_text(render_rgroup_ring_context_alignment_markdown(report), encoding="utf-8")
