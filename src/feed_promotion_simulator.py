from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FEED_PROMOTION_SIMULATOR_JSON = Path("data/substituents/feed_promotion_simulator.json")
DEFAULT_FEED_PROMOTION_SIMULATOR_CSV = Path("data/substituents/feed_promotion_simulator.csv")
DEFAULT_FEED_PROMOTION_SIMULATOR_MD = Path("docs/feed_promotion_simulator.md")
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


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _status(blockers: int, warnings: int, staged_rows: int) -> str:
    if blockers:
        return "blocked"
    if staged_rows <= 0:
        return "awaiting_filled_staging_rows"
    if warnings:
        return "ready_with_warnings"
    return "ready_for_promotion"


def build_feed_promotion_simulator(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    diff = _read_json(root_path / "data/substituents/feed_absorption_diff_navigator.json")
    staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    promotion_diff = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    source_guard = _read_json(root_path / "data/substituents/source_expansion_governance.json")
    coverage = _read_json(root_path / "data/substituents/rgroup_feed_review_coverage.json")

    source_rows: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "staged_row_count": 0,
        "target_row_count": 0,
        "row_delta": 0,
        "blocker_count": 0,
        "warning_count": 0,
        "duplicate_watch_count": 0,
        "owner_reuse_count": 0,
        "coverage_gap_count": 0,
    })

    for row in diff.get("rows") or []:
        source = str(row.get("source_dataset") or row.get("row_type") or "unknown")
        bucket = source_rows[source]
        bucket["staged_row_count"] += _int(row.get("staged_row_count"))
        bucket["target_row_count"] += _int(row.get("target_row_count"))
        bucket["row_delta"] += _int(row.get("row_delta"))
        bucket["blocker_count"] += _int(row.get("blocker_count"))
        bucket["warning_count"] += _int(row.get("warning_count"))
        if row.get("row_type") == "duplicate_normalized_pair":
            bucket["duplicate_watch_count"] += 1
        if row.get("row_type") == "owner_decision_reuse":
            bucket["owner_reuse_count"] += 1
        if row.get("row_type") == "review_coverage_gap":
            bucket["coverage_gap_count"] += 1

    for row in promotion_diff.get("rows") or []:
        source = str(row.get("source_dataset") or "unknown")
        bucket = source_rows[source]
        bucket["staged_row_count"] = max(bucket["staged_row_count"], _int(row.get("staged_row_count")))
        bucket["target_row_count"] = max(bucket["target_row_count"], _int(row.get("target_row_count")))
        bucket["row_delta"] = bucket["staged_row_count"] - bucket["target_row_count"]

    rows: list[dict[str, Any]] = []
    for index, (source, bucket) in enumerate(sorted(source_rows.items()), start=1):
        blockers = _int(bucket["blocker_count"])
        warnings = _int(bucket["warning_count"]) + _int(bucket["duplicate_watch_count"]) + _int(bucket["coverage_gap_count"])
        staged = _int(bucket["staged_row_count"])
        sim_status = _status(blockers, warnings, staged)
        rows.append(
            {
                "simulation_id": f"FPSIM-{index:03d}",
                "source_dataset": source,
                "simulation_status": sim_status,
                "promotion_allowed": sim_status == "ready_for_promotion" and source_guard.get("status") == "ready",
                "staged_row_count": staged,
                "target_row_count": _int(bucket["target_row_count"]),
                "projected_feed_row_count": _int(bucket["target_row_count"]) + staged,
                "row_delta": _int(bucket["row_delta"]),
                "duplicate_watch_count": _int(bucket["duplicate_watch_count"]),
                "owner_reuse_count": _int(bucket["owner_reuse_count"]),
                "coverage_gap_count": _int(bucket["coverage_gap_count"]),
                "blocker_count": blockers,
                "warning_count": warnings,
                "quality_budget": "max_blockers=0; require_source_guard=ready; require_review_coverage=covered_or_deferred",
                "next_action": "Fill and validate staged rows before promotion." if staged <= 0 else "Review warnings, owner reuse, and duplicate groups before promotion.",
            }
        )

    total_blockers = sum(_int(row.get("blocker_count")) for row in rows) + _int(source_guard.get("blocked_gate_count"))
    total_warnings = sum(_int(row.get("warning_count")) for row in rows)
    staged_rows = sum(_int(row.get("staged_row_count")) for row in rows)
    status = "blocked" if total_blockers else "awaiting_filled_staging_rows" if staged_rows <= 0 else "ready_with_warnings" if total_warnings else "ready_for_promotion"
    coverage_gaps = sum(1 for row in coverage.get("rows") or [] if str(row.get("coverage_status") or "") != "covered")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "feed_promotion_simulator",
        "row_count": len(rows),
        "source_count": len(rows),
        "staged_row_count": staged_rows,
        "projected_total_feed_rows": sum(_int(row.get("projected_feed_row_count")) for row in rows),
        "blocker_count": total_blockers,
        "warning_count": total_warnings,
        "coverage_gap_count": coverage_gaps,
        "promotion_allowed_count": sum(1 for row in rows if row.get("promotion_allowed") is True),
        "source_guard_status": source_guard.get("status") or "missing",
        "staging_gate_status": staging_gate.get("status") or "missing",
        "status_counts": dict(Counter(str(row.get("simulation_status") or "") for row in rows).most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use this simulator before copying staged feeds into governed feed files.",
            "Promotion remains blocked unless source governance is ready and staged rows have zero blockers.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_feed_promotion_simulator_markdown(report: dict) -> str:
    lines = [
        "# Feed Promotion Simulator",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Staged rows: `{report.get('staged_row_count')}`",
        f"- Blockers / warnings: `{report.get('blocker_count')}` / `{report.get('warning_count')}`",
        "",
        "| Source | Status | Allowed | Staged | Target | Projected | Duplicates | Coverage Gaps | Next Action |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("source_dataset") or ""),
                    str(row.get("simulation_status") or ""),
                    str(row.get("promotion_allowed")),
                    str(row.get("staged_row_count") or 0),
                    str(row.get("target_row_count") or 0),
                    str(row.get("projected_feed_row_count") or 0),
                    str(row.get("duplicate_watch_count") or 0),
                    str(row.get("coverage_gap_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_feed_promotion_simulator(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_PROMOTION_SIMULATOR_JSON,
    csv_path: str | Path | None = DEFAULT_FEED_PROMOTION_SIMULATOR_CSV,
    markdown_path: str | Path | None = DEFAULT_FEED_PROMOTION_SIMULATOR_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "simulation_id",
        "source_dataset",
        "simulation_status",
        "promotion_allowed",
        "staged_row_count",
        "target_row_count",
        "projected_feed_row_count",
        "row_delta",
        "duplicate_watch_count",
        "owner_reuse_count",
        "coverage_gap_count",
        "blocker_count",
        "warning_count",
        "quality_budget",
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
        md_file.write_text(render_feed_promotion_simulator_markdown(report), encoding="utf-8")
