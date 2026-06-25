from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FILTER_VIEWS_JSON = Path("data/projects/demo/staging_sandbox_filter_views.json")
DEFAULT_FILTER_VIEWS_CSV = Path("data/projects/demo/staging_sandbox_filter_views.csv")
DEFAULT_FILTER_VIEWS_MD = Path("docs/staging_sandbox_filter_views.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _add_counter_views(
    rows: list[dict[str, Any]],
    *,
    view_type: str,
    source_rows: list[dict],
    field: str,
    artifact_path: str,
    filter_target: str,
    next_action: str,
) -> None:
    counts = Counter(str(row.get(field) or "blank") for row in source_rows)
    for value, count in counts.most_common():
        rows.append(
            {
                "view_id": f"SSFV-{len(rows) + 1:04d}",
                "view_type": view_type,
                "filter_key": field,
                "filter_value": value,
                "filtered_row_count": count,
                "artifact_path": artifact_path,
                "filter_target": filter_target,
                "ui_action": "open_filtered_artifact",
                "next_action": next_action,
            }
        )


def build_staging_sandbox_filter_views(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    staging_budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    sandbox_review = _read_json(project_dir / "sandbox_score_delta_review_packet.json")
    digestion_ledger = _read_json(root_path / "data/substituents/rgroup_feed_digestion_ledger.json")
    promotion_approval = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    digestion_metrics = _read_json(root_path / "data/substituents/rgroup_digestion_quality_metrics.json")
    rows: list[dict[str, Any]] = []

    _add_counter_views(
        rows,
        view_type="staging_budget_source",
        source_rows=staging_budget.get("rows") or [],
        field="source_dataset",
        artifact_path=str(root_path / "data/substituents/rgroup_staging_quality_budget.json"),
        filter_target="rgroup_staging_quality_budget",
        next_action="Open staging quality budget filtered by source dataset.",
    )
    _add_counter_views(
        rows,
        view_type="staging_budget_status",
        source_rows=staging_budget.get("rows") or [],
        field="budget_status",
        artifact_path=str(root_path / "data/substituents/rgroup_staging_quality_budget.json"),
        filter_target="rgroup_staging_quality_budget",
        next_action="Review sources by staging budget status.",
    )
    _add_counter_views(
        rows,
        view_type="sandbox_risk",
        source_rows=sandbox_review.get("rows") or [],
        field="risk_bucket",
        artifact_path=str(project_dir / "sandbox_score_delta_review_packet.json"),
        filter_target="sandbox_score_delta_review_packet",
        next_action="Review sandbox score-delta rows by risk bucket.",
    )
    _add_counter_views(
        rows,
        view_type="sandbox_review_status",
        source_rows=sandbox_review.get("rows") or [],
        field="review_status",
        artifact_path=str(project_dir / "sandbox_score_delta_review_packet.json"),
        filter_target="sandbox_score_delta_review_packet",
        next_action="Review sandbox rows by operator-review status.",
    )
    _add_counter_views(
        rows,
        view_type="sandbox_operator_decision",
        source_rows=sandbox_review.get("rows") or [],
        field="operator_decision",
        artifact_path=str(project_dir / "sandbox_score_delta_review_packet.json"),
        filter_target="sandbox_score_delta_review_packet",
        next_action="Review sandbox rows by operator decision.",
    )
    _add_counter_views(
        rows,
        view_type="digestion_status",
        source_rows=digestion_ledger.get("rows") or [],
        field="digest_status",
        artifact_path=str(root_path / "data/substituents/rgroup_feed_digestion_ledger.json"),
        filter_target="rgroup_feed_digestion_ledger",
        next_action="Review staged rows by digestion status before promotion.",
    )
    for field, view_type, action in [
        ("source_dataset", "digestion_source", "Review staged digestion rows by source dataset."),
        ("replacement_class", "digestion_replacement_class", "Review staged digestion rows by replacement class."),
        ("endpoint_group", "digestion_endpoint_group", "Review staged digestion rows by endpoint group."),
        ("source_confidence_tier", "digestion_confidence_tier", "Review staged digestion rows by source-confidence tier."),
        ("candidate_impact_bucket", "digestion_candidate_impact", "Review staged digestion rows by candidate-impact bucket."),
    ]:
        _add_counter_views(
            rows,
            view_type=view_type,
            source_rows=digestion_ledger.get("rows") or [],
            field=field,
            artifact_path=str(root_path / "data/substituents/rgroup_feed_digestion_ledger.json"),
            filter_target="rgroup_feed_digestion_ledger",
            next_action=action,
        )
    _add_counter_views(
        rows,
        view_type="promotion_approval_decision",
        source_rows=promotion_approval.get("rows") or [],
        field="promotion_approval_decision",
        artifact_path=str(root_path / "data/substituents/rgroup_promotion_approval_ledger.json"),
        filter_target="rgroup_promotion_approval_ledger",
        next_action="Review promotion approval rows by approve/defer/reject decision.",
    )
    _add_counter_views(
        rows,
        view_type="promotion_approval_eligible",
        source_rows=promotion_approval.get("rows") or [],
        field="promotion_eligible",
        artifact_path=str(root_path / "data/substituents/rgroup_promotion_approval_ledger.json"),
        filter_target="rgroup_promotion_approval_ledger",
        next_action="Review which staged rows are structurally eligible but still need explicit approval.",
    )
    _add_counter_views(
        rows,
        view_type="digestion_quality_status",
        source_rows=digestion_metrics.get("rows") or [],
        field="quality_status",
        artifact_path=str(root_path / "data/substituents/rgroup_digestion_quality_metrics.json"),
        filter_target="rgroup_digestion_quality_metrics",
        next_action="Review digestion quality metric groups by ready/watch/blocked status.",
    )
    view_type_counts = Counter(str(row.get("view_type") or "") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "staging_sandbox_filter_views",
        "project_name": project_name,
        "row_count": len(rows),
        "filtered_row_total": sum(int(row.get("filtered_row_count") or 0) for row in rows),
        "available_filters": sorted(view_type_counts),
        "view_type_counts": dict(view_type_counts.most_common()),
        "staging_budget_status": staging_budget.get("status") or "missing",
        "sandbox_review_status": sandbox_review.get("status") or "missing",
        "digestion_ledger_status": digestion_ledger.get("status") or "missing",
        "promotion_approval_status": promotion_approval.get("status") or "missing",
        "digestion_quality_metrics_status": digestion_metrics.get("status") or "missing",
        "rows": rows,
        "recommended_next_actions": [
            "Use these filter rows from Native Reports to jump into budget, sandbox, or digestion artifacts.",
            "Treat deferred/rejected views as reviewed holdouts, not production approvals.",
        ],
    }


def render_staging_sandbox_filter_views_markdown(report: dict) -> str:
    lines = [
        "# Staging Sandbox Filter Views",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "| View | Filter | Value | Rows | Target | Next Action |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("view_type") or ""),
                    str(row.get("filter_key") or ""),
                    str(row.get("filter_value") or ""),
                    str(row.get("filtered_row_count") or 0),
                    str(row.get("filter_target") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_staging_sandbox_filter_views(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FILTER_VIEWS_JSON,
    csv_path: str | Path | None = DEFAULT_FILTER_VIEWS_CSV,
    markdown_path: str | Path | None = DEFAULT_FILTER_VIEWS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "view_id",
        "view_type",
        "filter_key",
        "filter_value",
        "filtered_row_count",
        "artifact_path",
        "filter_target",
        "ui_action",
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
        md_file.write_text(render_staging_sandbox_filter_views_markdown(report), encoding="utf-8")
