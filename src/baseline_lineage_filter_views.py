from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_LINEAGE_FILTER_VIEWS_JSON = Path("data/projects/demo/baseline_lineage_filter_views.json")
DEFAULT_BASELINE_LINEAGE_FILTER_VIEWS_CSV = Path("data/projects/demo/baseline_lineage_filter_views.csv")
DEFAULT_BASELINE_LINEAGE_FILTER_VIEWS_MD = Path("docs/baseline_lineage_filter_views.md")
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


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    return int(_number(value))


def _movement_bucket(value: object) -> str:
    score = abs(_number(value))
    if score <= 0:
        return "none"
    if score <= 3:
        return "low"
    if score <= 10:
        return "medium"
    return "high"


def _view_row(view_type: str, value: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    movement_total = sum(_int(row.get("movement_total")) for row in rows)
    return {
        "view_id": f"{view_type}:{value}",
        "view_type": view_type,
        "filter_value": value,
        "row_count": len(rows),
        "candidate_count": len({str(row.get("candidate_id") or "") for row in rows if str(row.get("candidate_id") or "")}),
        "movement_total": movement_total,
        "pairwise_count": sum(1 for row in rows if row.get("row_type") == "pairwise_delta"),
        "top_mover_count": sum(1 for row in rows if row.get("row_type") == "top_mover"),
        "preview_path": next((str(row.get("preview_path") or "") for row in rows if row.get("preview_path")), ""),
        "filter_expression": f"{view_type}={value}",
        "next_action": "Open this view before pinning, archiving, or comparing baselines.",
    }


def build_baseline_lineage_filter_views(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    min_movement_total: int = 0,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    preview = _read_json(project_dir / "baseline_lineage_preview.json")
    preview_rows = [dict(row) for row in preview.get("rows") or []]
    threshold_rows = [row for row in preview_rows if _int(row.get("movement_total")) >= int(min_movement_total)]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in threshold_rows:
        row_type = str(row.get("row_type") or "unknown")
        lineage = str(row.get("lineage_status") or "unknown")
        bucket = _movement_bucket(row.get("movement_total") or row.get("score_delta") or row.get("rank_delta"))
        candidate_state = "candidate_row" if row.get("candidate_id") else "aggregate_row"
        for view_type, value in [
            ("row_type", row_type),
            ("lineage_status", lineage),
            ("movement_bucket", bucket),
            ("candidate_state", candidate_state),
        ]:
            grouped[(view_type, value)].append(row)

    rows = [_view_row(view_type, value, group_rows) for (view_type, value), group_rows in sorted(grouped.items())]
    type_counts = Counter(row["view_type"] for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if preview_rows else "empty",
        "mode": "baseline_lineage_filter_views",
        "project_name": project_name,
        "row_count": len(rows),
        "preview_row_count": len(preview_rows),
        "filtered_preview_row_count": len(threshold_rows),
        "min_movement_total": int(min_movement_total),
        "available_filters": ["row_type", "lineage_status", "movement_bucket", "candidate_state"],
        "view_type_counts": dict(type_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use filter views to focus baseline movement by row type, lineage state, movement size, or candidate rows.",
            "Keep static PNG preview as the release artifact, and use filters for local review navigation.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_baseline_lineage_filter_views_markdown(report: dict) -> str:
    lines = [
        "# Baseline Lineage Filter Views",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Views / preview rows: `{report.get('row_count')}` / `{report.get('preview_row_count')}`",
        "",
        "| View | Value | Rows | Candidates | Movement | Pairwise | Top Movers |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("view_type") or ""),
                    str(row.get("filter_value") or "").replace("|", "/"),
                    str(row.get("row_count") or 0),
                    str(row.get("candidate_count") or 0),
                    str(row.get("movement_total") or 0),
                    str(row.get("pairwise_count") or 0),
                    str(row.get("top_mover_count") or 0),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_baseline_lineage_filter_views(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_LINEAGE_FILTER_VIEWS_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_FILTER_VIEWS_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_LINEAGE_FILTER_VIEWS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "view_id",
        "view_type",
        "filter_value",
        "row_count",
        "candidate_count",
        "movement_total",
        "pairwise_count",
        "top_mover_count",
        "preview_path",
        "filter_expression",
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
        md_file.write_text(render_baseline_lineage_filter_views_markdown(report), encoding="utf-8")
