from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_LINEAGE_HISTORY_JSON = Path("data/projects/demo/baseline_lineage_history.json")
DEFAULT_BASELINE_LINEAGE_HISTORY_CSV = Path("data/projects/demo/baseline_lineage_history.csv")
DEFAULT_BASELINE_LINEAGE_PAIRWISE_CSV = Path("data/projects/demo/baseline_lineage_history_pairwise.csv")
DEFAULT_BASELINE_LINEAGE_CHART_CSV = Path("data/projects/demo/baseline_lineage_history_chart.csv")
DEFAULT_BASELINE_LINEAGE_HISTORY_MD = Path("docs/baseline_lineage_history.md")
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


def _history_row(compare: dict, created_at: str) -> dict[str, Any]:
    return {
        "created_at": created_at,
        "status": compare.get("status") or "missing",
        "base_baseline_id": compare.get("base_baseline_id"),
        "head_baseline_id": compare.get("head_baseline_id"),
        "row_count": compare.get("row_count", 0),
        "entered_candidate_count": compare.get("entered_candidate_count", 0),
        "exited_candidate_count": compare.get("exited_candidate_count", 0),
        "changed_candidate_count": compare.get("changed_candidate_count", 0),
        "unchanged_candidate_count": compare.get("unchanged_candidate_count", 0),
        "max_abs_score_delta": compare.get("max_abs_score_delta", 0),
        "max_abs_rank_delta": compare.get("max_abs_rank_delta", 0),
        "base_path": compare.get("base_path", ""),
        "head_path": compare.get("head_path", ""),
    }


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _pairwise_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for index, (prev, curr) in enumerate(zip(rows, rows[1:]), start=1):
        entered_delta = int(_number(curr.get("entered_candidate_count")) - _number(prev.get("entered_candidate_count")))
        exited_delta = int(_number(curr.get("exited_candidate_count")) - _number(prev.get("exited_candidate_count")))
        changed_delta = int(_number(curr.get("changed_candidate_count")) - _number(prev.get("changed_candidate_count")))
        score_delta = _number(curr.get("max_abs_score_delta")) - _number(prev.get("max_abs_score_delta"))
        rank_delta = _number(curr.get("max_abs_rank_delta")) - _number(prev.get("max_abs_rank_delta"))
        movement_total = abs(entered_delta) + abs(exited_delta) + abs(changed_delta)
        if movement_total == 0 and abs(score_delta) < 1e-9 and abs(rank_delta) < 1e-9:
            signal = "stable"
        elif entered_delta + exited_delta + changed_delta > 0 or score_delta > 0 or rank_delta > 0:
            signal = "increased_movement"
        else:
            signal = "reduced_movement"
        pairs.append(
            {
                "pair_id": f"BLH-{index:04d}",
                "from_created_at": prev.get("created_at", ""),
                "to_created_at": curr.get("created_at", ""),
                "from_base_baseline_id": prev.get("base_baseline_id", ""),
                "to_head_baseline_id": curr.get("head_baseline_id", ""),
                "row_count_delta": int(_number(curr.get("row_count")) - _number(prev.get("row_count"))),
                "entered_delta": entered_delta,
                "exited_delta": exited_delta,
                "changed_delta": changed_delta,
                "max_abs_score_delta_change": round(score_delta, 6),
                "max_abs_rank_delta_change": round(rank_delta, 6),
                "movement_signal": signal,
            }
        )
    return pairs


def _chart_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chart: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        chart.append(
            {
                "snapshot_index": index,
                "created_at": row.get("created_at", ""),
                "entered_candidate_count": row.get("entered_candidate_count", 0),
                "exited_candidate_count": row.get("exited_candidate_count", 0),
                "changed_candidate_count": row.get("changed_candidate_count", 0),
                "unchanged_candidate_count": row.get("unchanged_candidate_count", 0),
                "max_abs_score_delta": row.get("max_abs_score_delta", 0),
                "max_abs_rank_delta": row.get("max_abs_rank_delta", 0),
                "movement_total": int(_number(row.get("entered_candidate_count")) + _number(row.get("exited_candidate_count")) + _number(row.get("changed_candidate_count"))),
            }
        )
    return chart


def build_baseline_lineage_history(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    compare_path: str | Path | None = None,
    history_path: str | Path | None = None,
    max_entries: int = 200,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    compare = _read_json(root_path / compare_path) if compare_path else _read_json(project_dir / "baseline_lineage_compare.json")
    created_at = datetime.now(timezone.utc).isoformat()
    history_file = root_path / history_path if history_path else project_dir / "baseline_lineage_history.json"
    existing_rows: list[dict] = []
    if history_file.exists():
        try:
            payload = json.loads(history_file.read_text(encoding="utf-8")) or {}
            if isinstance(payload, dict):
                existing_rows = [dict(row) for row in payload.get("rows") or [] if isinstance(row, dict)]
        except Exception:
            existing_rows = []
    current = _history_row(compare, created_at)
    rows = [*existing_rows, current][-max_entries:] if compare else existing_rows[-max_entries:]
    latest = rows[-1] if rows else {}
    pairwise = _pairwise_rows(rows)
    chart = _chart_rows(rows)
    movement_rows = [
        dict(row)
        for row in compare.get("rows") or []
        if str(row.get("lineage_status") or "") in {"entered", "exited", "changed"}
    ][:120]
    return {
        "created_at": created_at,
        "status": "tracking" if rows else "missing_baseline_lineage_compare",
        "mode": "baseline_lineage_history",
        "project_name": project_name,
        "row_count": len(rows),
        "latest": latest,
        "rows": rows,
        "pairwise_row_count": len(pairwise),
        "pairwise_movement_rows": pairwise[-120:],
        "movement_chart_rows": chart[-200:],
        "latest_movement_row_count": len(movement_rows),
        "latest_movement_rows": movement_rows,
        "real_experiment_feedback_used": False,
        "recommended_next_actions": [
            "Use history rows to compare baseline movement over time before pinning a new release baseline.",
            "Inspect latest_movement_rows when entered, exited, or changed counts rise between snapshots.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_baseline_lineage_history_markdown(report: dict) -> str:
    latest = report.get("latest") or {}
    lines = [
        "# Baseline Lineage History",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- History rows: `{report.get('row_count')}`",
        f"- Pairwise rows: `{report.get('pairwise_row_count')}`",
        f"- Latest base -> head: `{latest.get('base_baseline_id')}` -> `{latest.get('head_baseline_id')}`",
        "",
        "| Created | Base | Head | Entered | Exited | Changed | Max dScore | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[-120:]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("created_at") or ""),
                    str(row.get("base_baseline_id") or ""),
                    str(row.get("head_baseline_id") or ""),
                    str(row.get("entered_candidate_count") or ""),
                    str(row.get("exited_candidate_count") or ""),
                    str(row.get("changed_candidate_count") or ""),
                    str(row.get("max_abs_score_delta") or ""),
                    str(row.get("status") or ""),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Pairwise Movement", "", "| Pair | From | To | Entered d | Exited d | Changed d | Signal |", "| --- | --- | --- | ---: | ---: | ---: | --- |"])
    for row in (report.get("pairwise_movement_rows") or [])[-80:]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("pair_id") or ""),
                    str(row.get("from_created_at") or ""),
                    str(row.get("to_created_at") or ""),
                    str(row.get("entered_delta") or 0),
                    str(row.get("exited_delta") or 0),
                    str(row.get("changed_delta") or 0),
                    str(row.get("movement_signal") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_baseline_lineage_history(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_LINEAGE_HISTORY_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_HISTORY_CSV,
    pairwise_csv_path: str | Path | None = None,
    chart_csv_path: str | Path | None = None,
    markdown_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_HISTORY_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "created_at",
        "status",
        "base_baseline_id",
        "head_baseline_id",
        "row_count",
        "entered_candidate_count",
        "exited_candidate_count",
        "changed_candidate_count",
        "unchanged_candidate_count",
        "max_abs_score_delta",
        "max_abs_rank_delta",
        "base_path",
        "head_path",
    ]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
        pairwise_file = Path(pairwise_csv_path) if pairwise_csv_path else csv_file.with_name(f"{csv_file.stem}_pairwise.csv")
        chart_file = Path(chart_csv_path) if chart_csv_path else csv_file.with_name(f"{csv_file.stem}_chart.csv")
        pairwise_fields = [
            "pair_id",
            "from_created_at",
            "to_created_at",
            "from_base_baseline_id",
            "to_head_baseline_id",
            "row_count_delta",
            "entered_delta",
            "exited_delta",
            "changed_delta",
            "max_abs_score_delta_change",
            "max_abs_rank_delta_change",
            "movement_signal",
        ]
        pairwise_file.parent.mkdir(parents=True, exist_ok=True)
        with pairwise_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=pairwise_fields)
            writer.writeheader()
            for row in report.get("pairwise_movement_rows") or []:
                writer.writerow({field: row.get(field, "") for field in pairwise_fields})
        chart_fields = [
            "snapshot_index",
            "created_at",
            "entered_candidate_count",
            "exited_candidate_count",
            "changed_candidate_count",
            "unchanged_candidate_count",
            "max_abs_score_delta",
            "max_abs_rank_delta",
            "movement_total",
        ]
        chart_file.parent.mkdir(parents=True, exist_ok=True)
        with chart_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=chart_fields)
            writer.writeheader()
            for row in report.get("movement_chart_rows") or []:
                writer.writerow({field: row.get(field, "") for field in chart_fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_baseline_lineage_history_markdown(report), encoding="utf-8")
