from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_NATIVE_DRILLDOWN_ACTIONS_JSON = Path("data/projects/demo/native_drilldown_actions.json")
DEFAULT_NATIVE_DRILLDOWN_ACTIONS_CSV = Path("data/projects/demo/native_drilldown_actions.csv")
DEFAULT_NATIVE_DRILLDOWN_ACTIONS_MD = Path("docs/native_drilldown_actions.md")
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


def _clip(value: object, limit: int = 320) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def build_native_drilldown_actions(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    max_actions_per_source: int = 80,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    closure_filters = _read_json(project_dir / "review_closure_filter_views.json")
    lineage_filters = _read_json(project_dir / "baseline_lineage_filter_views.json")
    explanation_matrix = _read_json(project_dir / "candidate_explanation_matrix.json")
    sandbox_scoring = _read_json(project_dir / "staged_feed_sandbox_scoring.json")
    sandbox_review = _read_json(project_dir / "sandbox_score_delta_review_packet.json")
    staging_filter_views = _read_json(project_dir / "staging_sandbox_filter_views.json")

    rows: list[dict[str, Any]] = []
    sequence = 1

    for source in (closure_filters.get("rows") or [])[:max_actions_per_source]:
        task_ids = str(source.get("task_ids") or "")
        rows.append(
            {
                "action_id": f"NDA-{sequence:04d}",
                "action_type": "closure_filter",
                "source_view_id": source.get("view_id", ""),
                "source_label": f"{source.get('view_type')}={source.get('filter_value')}",
                "target_view": "review_closure_workbench",
                "target_filter": source.get("filter_expression", ""),
                "target_candidate_id": "",
                "target_task_ids": _clip(task_ids, 500),
                "source_artifact": str(project_dir / "review_closure_filter_views.json"),
                "linked_artifact": str(project_dir / "review_closure_workbench.json"),
                "open_artifact_path": str(project_dir / "review_closure_workbench.json"),
                "ui_action": "open_reports_artifact",
                "ui_command": "reports.open_artifact(review_closure_workbench)",
                "filter_target": "review_closure_workbench",
                "filter_key": "task_ids",
                "filter_value": _clip(task_ids, 500),
                "direct_action_supported": True,
                "row_count": source.get("task_count", 0),
                "route_supported": True,
                "next_action": "Route selected closure filter to the closure workbench and inspect task IDs before batch edits.",
            }
        )
        sequence += 1

    for source in (lineage_filters.get("rows") or [])[:max_actions_per_source]:
        rows.append(
            {
                "action_id": f"NDA-{sequence:04d}",
                "action_type": "baseline_lineage_filter",
                "source_view_id": source.get("view_id", ""),
                "source_label": f"{source.get('view_type')}={source.get('filter_value')}",
                "target_view": "baseline_lineage_preview",
                "target_filter": source.get("filter_expression", ""),
                "target_candidate_id": "",
                "target_task_ids": "",
                "source_artifact": str(project_dir / "baseline_lineage_filter_views.json"),
                "linked_artifact": source.get("preview_path") or str(project_dir / "baseline_lineage_preview.json"),
                "open_artifact_path": source.get("preview_path") or str(project_dir / "baseline_lineage_preview.json"),
                "ui_action": "open_reports_artifact",
                "ui_command": "reports.open_artifact(baseline_lineage_preview)",
                "filter_target": "baseline_lineage_preview",
                "filter_key": str(source.get("view_type") or "lineage_filter"),
                "filter_value": str(source.get("filter_value") or ""),
                "direct_action_supported": True,
                "row_count": source.get("row_count", 0),
                "route_supported": True,
                "next_action": "Route selected lineage filter to preview rows before pinning or archiving a baseline.",
            }
        )
        sequence += 1

    for source in (explanation_matrix.get("rows") or [])[:max_actions_per_source]:
        candidate_id = str(source.get("candidate_id") or "")
        rows.append(
            {
                "action_id": f"NDA-{sequence:04d}",
                "action_type": "candidate_matrix_row",
                "source_view_id": candidate_id,
                "source_label": f"candidate={candidate_id}",
                "target_view": "candidate_review",
                "target_filter": f"candidate_id={candidate_id}",
                "target_candidate_id": candidate_id,
                "target_task_ids": "",
                "source_artifact": str(project_dir / "candidate_explanation_matrix.json"),
                "linked_artifact": str(project_dir / "candidate_explanation_drilldown.json"),
                "open_artifact_path": str(project_dir / "candidate_explanation_drilldown.json"),
                "ui_action": "apply_candidate_review_filter",
                "ui_command": f"candidate_review.filter(candidate_id={candidate_id})",
                "filter_target": "candidate_review",
                "filter_key": "candidate_id",
                "filter_value": candidate_id,
                "direct_action_supported": True,
                "row_count": 1,
                "route_supported": True,
                "next_action": "Route selected matrix candidate to Candidate Review and evidence drilldown.",
            }
        )
        sequence += 1

    for source in (sandbox_scoring.get("rows") or [])[:max_actions_per_source]:
        candidate_id = str(source.get("candidate_id") or "")
        rows.append(
            {
                "action_id": f"NDA-{sequence:04d}",
                "action_type": "sandbox_scoring_row",
                "source_view_id": candidate_id,
                "source_label": f"sandbox_candidate={candidate_id}",
                "target_view": "staged_feed_sandbox_scoring",
                "target_filter": f"candidate_id={candidate_id}",
                "target_candidate_id": candidate_id,
                "target_task_ids": "",
                "source_artifact": str(project_dir / "staged_feed_sandbox_scoring.json"),
                "linked_artifact": str(project_dir / "candidate_explanation_matrix.json"),
                "open_artifact_path": str(project_dir / "sandbox_score_delta_review_packet.json")
                if sandbox_review
                else str(project_dir / "staged_feed_sandbox_scoring.json"),
                "ui_action": "open_sandbox_score_delta_review",
                "ui_command": f"reports.open_sandbox_review(candidate_id={candidate_id})",
                "filter_target": "sandbox_score_delta_review_packet",
                "filter_key": "candidate_id",
                "filter_value": candidate_id,
                "direct_action_supported": True,
                "row_count": 1,
                "route_supported": True,
                "next_action": "Review sandbox score preview; production scoring remains unchanged until governed promotion.",
            }
        )
        sequence += 1

    for source in (staging_filter_views.get("rows") or [])[:max_actions_per_source]:
        rows.append(
            {
                "action_id": f"NDA-{sequence:04d}",
                "action_type": "staging_sandbox_filter",
                "source_view_id": source.get("view_id", ""),
                "source_label": f"{source.get('view_type')}={source.get('filter_value')}",
                "target_view": source.get("filter_target", ""),
                "target_filter": f"{source.get('filter_key')}={source.get('filter_value')}",
                "target_candidate_id": "",
                "target_task_ids": "",
                "source_artifact": str(project_dir / "staging_sandbox_filter_views.json"),
                "linked_artifact": source.get("artifact_path", ""),
                "open_artifact_path": source.get("artifact_path", ""),
                "ui_action": "open_filtered_artifact",
                "ui_command": f"reports.open_filtered_artifact({source.get('filter_target')},{source.get('filter_key')}={source.get('filter_value')})",
                "filter_target": source.get("filter_target", ""),
                "filter_key": source.get("filter_key", ""),
                "filter_value": source.get("filter_value", ""),
                "direct_action_supported": True,
                "row_count": source.get("filtered_row_count", 0),
                "route_supported": True,
                "next_action": "Open staging/sandbox filtered view and inspect the exact governance artifact.",
            }
        )
        sequence += 1

    action_counts = Counter(str(row.get("action_type") or "") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "native_drilldown_actions",
        "project_name": project_name,
        "row_count": len(rows),
        "route_supported_count": sum(1 for row in rows if row.get("route_supported") is True),
        "direct_action_supported_count": sum(1 for row in rows if row.get("direct_action_supported") is True),
        "action_type_counts": dict(action_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use these rows as the native selected-row routing index for Reports tables.",
            "Route to local review artifacts only; no procurement or real experiment feedback scopes are enabled.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_native_drilldown_actions_markdown(report: dict) -> str:
    lines = [
        "# Native Drilldown Actions",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "| Action | Type | Source | Target | Filter | Rows | Next Action |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("action_id") or ""),
                    str(row.get("action_type") or ""),
                    str(row.get("source_label") or ""),
                    str(row.get("target_view") or ""),
                    str(row.get("target_filter") or "").replace("|", "/"),
                    str(row.get("row_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_native_drilldown_actions(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_NATIVE_DRILLDOWN_ACTIONS_JSON,
    csv_path: str | Path | None = DEFAULT_NATIVE_DRILLDOWN_ACTIONS_CSV,
    markdown_path: str | Path | None = DEFAULT_NATIVE_DRILLDOWN_ACTIONS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "action_id",
        "action_type",
        "source_view_id",
        "source_label",
        "target_view",
        "target_filter",
        "target_candidate_id",
        "target_task_ids",
        "source_artifact",
        "linked_artifact",
        "open_artifact_path",
        "ui_action",
        "ui_command",
        "filter_target",
        "filter_key",
        "filter_value",
        "direct_action_supported",
        "row_count",
        "route_supported",
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
        md_file.write_text(render_native_drilldown_actions_markdown(report), encoding="utf-8")
