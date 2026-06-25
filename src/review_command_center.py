from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_COMMAND_CENTER_JSON = Path("data/projects/demo/review_command_center.json")
DEFAULT_REVIEW_COMMAND_CENTER_CSV = Path("data/projects/demo/review_command_center.csv")
DEFAULT_REVIEW_COMMAND_CENTER_MD = Path("docs/review_command_center.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]

REVIEW_GATE_TARGETS = {
    "candidate_review_packet": "candidate_review",
    "candidate_review_board": "candidate_review",
    "candidate_review_analytics": "candidate_review",
    "candidate_drilldown_packet": "candidate_review",
    "candidate_decision_packet": "reports",
    "candidate_evidence_drawer": "candidate_review",
    "candidate_decision_qa": "reports",
    "evidence_quality_scorecard": "reports",
    "candidate_evidence_quality": "reports",
    "candidate_baseline_compare": "reports",
    "candidate_baseline_manager": "reports",
    "reviewer_operations": "reports",
    "baseline_lineage_compare": "reports",
    "candidate_baseline_lineage": "reports",
    "operator_trend_summary": "reports",
    "operator_trend_charts": "reports",
    "medchem_discussion_handoff": "reports",
    "native_ui_regression": "reports",
}
PASS_LEVELS = {"pass", "ready", "clear", "closed", "fresh", "unchanged"}

SAVED_VIEW_DEFINITIONS = [
    {
        "view_id": "attention_all",
        "label": "All Attention Rows",
        "target_view": "candidate_review",
        "target_filter": "attention=attention",
        "description": "Every non-clear row that can be routed from the command center.",
    },
    {
        "view_id": "production_gates",
        "label": "Production Gates",
        "target_view": "reports",
        "target_filter": "row_type=production_gate_route",
        "description": "Release, dashboard, data-foundation, and native regression gate routes.",
    },
    {
        "view_id": "reviewer_ops",
        "label": "Reviewer Ops",
        "target_view": "candidate_review",
        "target_filter": "row_type=reviewer_operation",
        "description": "Overdue, stale, or workload-oriented review operations rows.",
    },
    {
        "view_id": "baseline_movement",
        "label": "Baseline Movement",
        "target_view": "candidate_review",
        "target_filter": "row_type=baseline_lineage",
        "description": "Candidates that entered, exited, or changed against the active baseline.",
    },
    {
        "view_id": "evidence_quality",
        "label": "Evidence Quality",
        "target_view": "candidate_review",
        "target_filter": "row_type=evidence_quality",
        "description": "Candidates with thin, stale, or conflicting evidence context.",
    },
]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_attention(value: object) -> bool:
    return str(value or "").strip().lower() not in PASS_LEVELS


def _details_value(details: object, key: str) -> str:
    text = str(details or "")
    for part in text.split(";"):
        name, _, value = part.partition("=")
        if name.strip() == key:
            return value.strip()
    return ""


def _target_filter(*, candidate_id: object = "", site_class: object = "", risk_bucket: object = "", reviewer: object = "", attention: bool = False) -> str:
    parts = []
    if candidate_id:
        parts.append(f"candidate_id={candidate_id}")
    if site_class:
        parts.append(f"site_class={site_class}")
    if risk_bucket:
        parts.append(f"risk_bucket={risk_bucket}")
    if reviewer:
        parts.append(f"reviewer={reviewer}")
    if attention:
        parts.append("attention=attention")
    return ";".join(parts)


def _lane_for(row_type: str, target_view: str) -> str:
    if row_type == "production_gate_route":
        return "release_gates"
    if row_type == "evidence_quality":
        return "evidence"
    if row_type == "reviewer_operation":
        return "reviewer_ops"
    if row_type == "baseline_lineage":
        return "baseline"
    if row_type == "operator_trend":
        return "operator_trends"
    return target_view or "reports"


def _command_row(
    *,
    command_id: str,
    row_type: str,
    severity: str,
    target_view: str,
    target_filter: str = "",
    candidate_id: str = "",
    source_artifact: str = "",
    source_csv: str = "",
    label: str = "",
    status: object = "",
    details: object = "",
    next_action: object = "",
) -> dict[str, Any]:
    lane = _lane_for(row_type, target_view)
    return {
        "command_id": command_id,
        "row_type": row_type,
        "lane": lane,
        "severity": severity,
        "target_view": target_view,
        "target_filter": target_filter,
        "candidate_id": candidate_id,
        "source_artifact": source_artifact,
        "source_csv": source_csv,
        "label": label,
        "status": status,
        "details": details,
        "next_action": next_action,
    }


def _saved_views(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    views = []
    for view in SAVED_VIEW_DEFINITIONS:
        filter_text = str(view.get("target_filter") or "")
        row_type = ""
        if filter_text.startswith("row_type="):
            row_type = filter_text.split("=", 1)[1]
        if row_type:
            matched = [row for row in rows if row.get("row_type") == row_type]
        elif filter_text == "attention=attention":
            matched = [row for row in rows if str(row.get("severity") or "") not in {"pass", "ready", "clear"}]
        else:
            matched = list(rows)
        severity_counts = Counter(str(row.get("severity") or "") for row in matched)
        lane_counts = Counter(str(row.get("lane") or "") for row in matched)
        views.append(
            {
                **view,
                "row_count": len(matched),
                "severity_counts": dict(severity_counts.most_common()),
                "lane_counts": dict(lane_counts.most_common()),
            }
        )
    return views


def build_review_command_center(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    dashboard = _read_json(root_path / "data/releases/production_dashboard_snapshot.json")
    evidence_quality = _read_json(project_dir / "evidence_quality_scorecard.json")
    reviewer_operations = _read_json(project_dir / "reviewer_operations.json")
    baseline_lineage = _read_json(project_dir / "baseline_lineage_compare.json")
    operator_trend = _read_json(root_path / "data/releases/operator_trend_summary.json")
    created_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for gate in dashboard.get("rows") or []:
        gate_id = str(gate.get("gate_id") or gate.get("label") or "").strip()
        if not gate_id:
            continue
        target_view = REVIEW_GATE_TARGETS.get(gate_id, "reports")
        if gate_id not in REVIEW_GATE_TARGETS and str(gate.get("level") or "") == "pass":
            continue
        rows.append(
            _command_row(
                command_id=f"gate:{gate_id}",
                row_type="production_gate_route",
                severity=str(gate.get("level") or "warn"),
                target_view=target_view,
                target_filter=f"gate_id={gate_id}",
                source_artifact=str(gate.get("artifact_path") or ""),
                source_csv=str(gate.get("artifact_csv_path") or ""),
                label=str(gate.get("label") or gate_id),
                status=gate.get("status"),
                details=gate.get("details"),
                next_action=gate.get("next_action"),
            )
        )

    for row in evidence_quality.get("rows") or []:
        bucket = str(row.get("quality_bucket") or "").strip()
        if bucket == "clear":
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        rows.append(
            _command_row(
                command_id=f"evidence:{candidate_id or len(rows) + 1}",
                row_type="evidence_quality",
                severity=bucket or "watch",
                target_view="candidate_review",
                target_filter=_target_filter(
                    candidate_id=candidate_id,
                    site_class=row.get("site_class"),
                    risk_bucket=row.get("risk_bucket"),
                    reviewer=row.get("reviewer"),
                    attention=True,
                ),
                candidate_id=candidate_id,
                source_artifact=str(project_dir / "evidence_quality_scorecard.json"),
                source_csv=str(project_dir / "evidence_quality_scorecard.csv"),
                label=f"Evidence quality: {candidate_id}",
                status=row.get("quality_bucket"),
                details=row.get("quality_flags"),
                next_action=row.get("next_action"),
            )
        )

    for row in reviewer_operations.get("rows") or []:
        status = str(row.get("status") or "").strip()
        if not _is_attention(status):
            continue
        row_type = str(row.get("row_type") or "reviewer_operation")
        key = str(row.get("key") or "").strip()
        candidate_id = key if row_type == "candidate_sla" else ""
        reviewer = _details_value(row.get("details"), "reviewer")
        site_class = _details_value(row.get("details"), "site")
        rows.append(
            _command_row(
                command_id=f"reviewer:{row_type}:{key or len(rows) + 1}",
                row_type="reviewer_operation",
                severity=status,
                target_view="candidate_review" if row_type in {"candidate_sla", "reviewer_workload", "site_class_closure"} else "reports",
                target_filter=_target_filter(candidate_id=candidate_id, site_class=site_class, reviewer=reviewer, attention=True),
                candidate_id=candidate_id,
                source_artifact=str(project_dir / "reviewer_operations.json"),
                source_csv=str(project_dir / "reviewer_operations.csv"),
                label=f"Reviewer ops: {key}",
                status=status,
                details=row.get("details"),
                next_action=row.get("next_action"),
            )
        )

    for row in baseline_lineage.get("rows") or []:
        status = str(row.get("lineage_status") or "").strip()
        if status == "unchanged":
            continue
        candidate_id = str(row.get("candidate_id") or row.get("candidate_key") or "").strip()
        rows.append(
            _command_row(
                command_id=f"lineage:{candidate_id or len(rows) + 1}",
                row_type="baseline_lineage",
                severity=status or "changed",
                target_view="candidate_review",
                target_filter=_target_filter(candidate_id=candidate_id, site_class=row.get("site_class")),
                candidate_id=candidate_id,
                source_artifact=str(project_dir / "baseline_lineage_compare.json"),
                source_csv=str(project_dir / "baseline_lineage_compare.csv"),
                label=f"Baseline lineage: {candidate_id}",
                status=status,
                details=row.get("changed_fields"),
                next_action=row.get("rationale"),
            )
        )

    for card in operator_trend.get("cards") or []:
        status = str(card.get("status") or "").strip()
        if status != "needs_attention":
            continue
        card_id = str(card.get("card_id") or card.get("label") or "").strip()
        rows.append(
            _command_row(
                command_id=f"trend:{card_id}",
                row_type="operator_trend",
                severity=status,
                target_view="reports",
                target_filter=f"card_id={card_id}",
                source_artifact=str(root_path / "data/releases/operator_trend_summary.json"),
                source_csv=str(root_path / "data/releases/operator_trend_summary.csv"),
                label=str(card.get("label") or card_id),
                status=status,
                details=card.get("details"),
                next_action=card.get("next_action"),
            )
        )

    counts = Counter(str(row.get("row_type") or "") for row in rows)
    lane_counts = Counter(str(row.get("lane") or "") for row in rows)
    target_view_counts = Counter(str(row.get("target_view") or "") for row in rows)
    severity_counts = Counter(str(row.get("severity") or "") for row in rows)
    actionable_count = sum(1 for row in rows if str(row.get("severity") or "") not in {"pass", "ready", "clear"})
    saved_views = _saved_views(rows)
    return {
        "created_at": created_at,
        "status": "ready" if rows else "missing_review_inputs",
        "mode": "review_command_center",
        "project_name": project_name,
        "row_count": len(rows),
        "actionable_count": actionable_count,
        "gate_route_count": counts.get("production_gate_route", 0),
        "evidence_quality_count": counts.get("evidence_quality", 0),
        "reviewer_operation_count": counts.get("reviewer_operation", 0),
        "baseline_lineage_count": counts.get("baseline_lineage", 0),
        "operator_trend_count": counts.get("operator_trend", 0),
        "row_type_counts": dict(counts.most_common()),
        "lane_counts": dict(lane_counts.most_common()),
        "target_view_counts": dict(target_view_counts.most_common()),
        "severity_counts": dict(severity_counts.most_common()),
        "default_view_id": "attention_all",
        "saved_view_count": len(saved_views),
        "saved_views": saved_views,
        "rows": rows,
        "real_experiment_feedback_used": False,
        "recommended_next_actions": [
            "Use command rows to move from production gates into the native review board or linked local artifacts.",
            "Use target_filter to pre-filter candidate review rows before editing local review status.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_review_command_center_markdown(report: dict) -> str:
    lines = [
        "# Review Command Center",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows / actionable: `{report.get('row_count')}` / `{report.get('actionable_count')}`",
        f"- Saved views: `{report.get('saved_view_count')}`",
        "",
        "## Saved Views",
        "",
        "| View | Target | Filter | Rows |",
        "| --- | --- | --- | ---: |",
    ]
    for view in report.get("saved_views") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(view.get("view_id") or ""),
                    str(view.get("target_view") or ""),
                    str(view.get("target_filter") or "").replace("|", "/"),
                    str(view.get("row_count") or 0),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "| Command | Type | Lane | Severity | Target | Filter | Status | Next Action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in (report.get("rows") or [])[:180]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("command_id") or ""),
                    str(row.get("row_type") or ""),
                    str(row.get("lane") or ""),
                    str(row.get("severity") or ""),
                    str(row.get("target_view") or ""),
                    str(row.get("target_filter") or "").replace("|", "/"),
                    str(row.get("status") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_review_command_center(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_COMMAND_CENTER_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_COMMAND_CENTER_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_COMMAND_CENTER_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "command_id",
        "row_type",
        "lane",
        "severity",
        "target_view",
        "target_filter",
        "candidate_id",
        "source_artifact",
        "source_csv",
        "label",
        "status",
        "details",
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
        md_file.write_text(render_review_command_center_markdown(report), encoding="utf-8")
