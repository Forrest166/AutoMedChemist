from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PLAN_JSON = Path("data/substituents/rgroup_next_expansion_batch_plan.json")
DEFAULT_PLAN_CSV = Path("data/substituents/rgroup_next_expansion_batch_plan.csv")
DEFAULT_PLAN_MD = Path("docs/rgroup_next_expansion_batch_plan.md")

SOURCE_PATTERNS = {
    "analog_series_seed": ["analog_series_followup_feed_202605.csv", "expanded_analog_series_feed_202605.csv"],
    "literature_bioisostere_seed": ["literature_bioisostere_followup_feed_202605.csv", "expanded_literature_bioisostere_feed_202605.csv"],
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


def _count_rows(path: Path) -> tuple[int, int, int]:
    if not path.exists():
        return 0, 0, 0
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        row_count = 0
        reviewed = 0
        checksum = 0
        for row in reader:
            row_count += 1
            if str(row.get("provenance_review_status") or row.get("review_status") or "").lower() in {"reviewed", "accepted"}:
                reviewed += 1
            if row.get("row_sha256"):
                checksum += 1
    return row_count, reviewed, checksum


def build_rgroup_next_expansion_batch_plan(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    feed_dir = root_path / "data/replacements/feeds"
    closure = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_ledger.json")
    owner_ledger = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json")
    admission = _read_json(root_path / "data/substituents/rgroup_staging_admission_scorecard.json")
    axis = _read_json(root_path / "data/substituents/ring_rgroup_axis_governance.json")
    rows: list[dict[str, Any]] = []
    for source_dataset, filenames in SOURCE_PATTERNS.items():
        total_rows = reviewed_rows = checksum_rows = file_count = 0
        paths: list[str] = []
        for filename in filenames:
            path = feed_dir / filename
            count, reviewed, checksum = _count_rows(path)
            if count:
                file_count += 1
                total_rows += count
                reviewed_rows += reviewed
                checksum_rows += checksum
                paths.append(str(path))
        blocker_count = 0
        blockers: list[str] = []
        if not total_rows:
            blocker_count += 1
            blockers.append("no_reviewed_source_rows")
        if reviewed_rows < total_rows:
            blocker_count += 1
            blockers.append("review_coverage_incomplete")
        if checksum_rows < total_rows:
            blocker_count += 1
            blockers.append("row_checksum_incomplete")
        if int(closure.get("open_count") or 0):
            blocker_count += 1
            blockers.append("quality_closure_open")
        if int(owner_ledger.get("pending_owner_review_count") or 0):
            blocker_count += 1
            blockers.append("owner_review_pending")
        planned_cap = min(8, max(0, reviewed_rows))
        rows.append(
            {
                "batch_id": f"RGEXP-{len(rows) + 1:04d}",
                "source_dataset": source_dataset,
                "source_file_count": file_count,
                "available_row_count": total_rows,
                "reviewed_row_count": reviewed_rows,
                "checksum_row_count": checksum_rows,
                "planned_staging_cap": planned_cap,
                "axis_policy_status": axis.get("status", ""),
                "admission_status": admission.get("status", ""),
                "closure_status": closure.get("status", ""),
                "owner_ledger_status": owner_ledger.get("status", ""),
                "blocker_count": blocker_count,
                "blockers": ";".join(blockers),
                "batch_status": "ready_for_staging_template" if blocker_count == 0 and planned_cap else "blocked",
                "source_paths": ";".join(paths),
                "production_promotion_allowed": False,
                "next_action": (
                    "Create a Phase 43 staging template capped to reviewed rows; keep promotion disabled."
                    if blocker_count == 0 and planned_cap
                    else "Resolve blockers before staging this source."
                ),
            }
        )
    blocked = sum(1 for row in rows if row.get("batch_status") == "blocked")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows and blocked == 0 else "blocked" if rows else "awaiting_sources",
        "mode": "rgroup_next_expansion_batch_plan",
        "row_count": len(rows),
        "ready_count": len(rows) - blocked,
        "blocked_count": blocked,
        "available_row_count": sum(int(row.get("available_row_count") or 0) for row in rows),
        "planned_staging_cap_total": sum(int(row.get("planned_staging_cap") or 0) for row in rows if row.get("batch_status") != "blocked"),
        "production_scoring_affected": False,
        "production_promotion_allowed": False,
        "rows": rows,
        "recommended_next_actions": [
            "Stage only the capped reviewed analog-series and literature-bioisostere rows in the next feed-drop cycle.",
            "Do not include patent-mined rows in this expansion batch until source-owner evidence is upgraded.",
        ],
    }


def render_rgroup_next_expansion_batch_plan_markdown(report: dict) -> str:
    lines = [
        "# R-group Next Expansion Batch Plan",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Available rows / planned cap: `{report.get('available_row_count')}` / `{report.get('planned_staging_cap_total')}`",
        "",
        "| Batch | Source | Files | Available | Reviewed | Checksummed | Cap | Status | Blockers |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("batch_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("source_file_count") or 0),
                    str(row.get("available_row_count") or 0),
                    str(row.get("reviewed_row_count") or 0),
                    str(row.get("checksum_row_count") or 0),
                    str(row.get("planned_staging_cap") or 0),
                    str(row.get("batch_status") or ""),
                    str(row.get("blockers") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_next_expansion_batch_plan(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_PLAN_JSON,
    csv_path: str | Path | None = DEFAULT_PLAN_CSV,
    markdown_path: str | Path | None = DEFAULT_PLAN_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "batch_id",
        "source_dataset",
        "source_file_count",
        "available_row_count",
        "reviewed_row_count",
        "checksum_row_count",
        "planned_staging_cap",
        "axis_policy_status",
        "admission_status",
        "closure_status",
        "owner_ledger_status",
        "blocker_count",
        "blockers",
        "batch_status",
        "source_paths",
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
        md_file.write_text(render_rgroup_next_expansion_batch_plan_markdown(report), encoding="utf-8")
