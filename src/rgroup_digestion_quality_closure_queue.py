from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_QUEUE_JSON = Path("data/substituents/rgroup_digestion_quality_closure_queue.json")
DEFAULT_QUEUE_CSV = Path("data/substituents/rgroup_digestion_quality_closure_queue.csv")
DEFAULT_QUEUE_MD = Path("docs/rgroup_digestion_quality_closure_queue.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _primary_issue(metric: dict[str, Any]) -> tuple[str, str, str, str]:
    if int(metric.get("provenance_missing_count") or 0):
        return (
            "provenance_missing",
            "high",
            "source_owner_review",
            "Fill provenance level, source reference, and review status before any promotion approval.",
        )
    if int(metric.get("license_missing_count") or 0):
        return (
            "license_missing",
            "high",
            "data_steward",
            "Add source license before ingesting this slice into the governed library.",
        )
    if int(metric.get("low_confidence_count") or 0):
        return (
            "low_confidence",
            "medium",
            "source_owner_review",
            "Re-check source confidence or keep the slice deferred.",
        )
    if int(metric.get("endpoint_unassigned_count") or 0):
        return (
            "endpoint_unassigned",
            "medium",
            "endpoint_curator",
            "Assign endpoint group or explicitly mark endpoint-independent before approval.",
        )
    if int(metric.get("duplicate_pressure_count") or 0):
        return (
            "duplicate_pressure",
            "medium",
            "data_steward",
            "Collapse duplicate rows or document why repeated replacements should remain separate.",
        )
    impact_counts = metric.get("candidate_impact_counts") or {}
    if int(impact_counts.get("deferred_candidate_impact") or 0):
        return (
            "deferred_candidate_impact",
            "medium",
            "medchem_review",
            "Resolve candidate impact or keep the affected rows out of promotion.",
        )
    if int(metric.get("candidate_impacted_row_count") or 0):
        return (
            "candidate_impact_review",
            "low",
            "medchem_review",
            "Confirm reviewed candidate impact remains compatible with staged promotion.",
        )
    return (
        "quality_watch",
        "low",
        "data_steward",
        "Review this watch slice and close it once the metric returns to ready.",
    )


def build_rgroup_digestion_quality_closure_queue(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    metrics = _read_json(root_path / "data/substituents/rgroup_digestion_quality_metrics.json")
    approval = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    closure_ledger = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_ledger.json")
    closure_by_task = {str(row.get("task_id") or ""): row for row in closure_ledger.get("rows") or []}
    rows: list[dict[str, Any]] = []
    for metric in metrics.get("rows") or []:
        quality_status = str(metric.get("quality_status") or "")
        if quality_status not in {"watch", "blocked"}:
            continue
        issue_type, severity, owner_role, next_action = _primary_issue(metric)
        task_id = f"RGQC-{len(rows) + 1:04d}"
        closure = closure_by_task.get(task_id, {})
        closure_status = closure.get("closure_status") or "open"
        rows.append(
            {
                "task_id": task_id,
                "metric_id": metric.get("metric_id", ""),
                "metric_type": metric.get("metric_type", ""),
                "group_key": metric.get("group_key", ""),
                "quality_status": quality_status,
                "issue_type": issue_type,
                "severity": severity,
                "owner_role": owner_role,
                "status": closure_status,
                "closure_decision": closure.get("closure_decision", ""),
                "resolved_for_promotion": closure.get("resolved_for_promotion", False),
                "closure_note": closure.get("closure_note", ""),
                "row_count": metric.get("row_count", 0),
                "low_confidence_count": metric.get("low_confidence_count", 0),
                "provenance_missing_count": metric.get("provenance_missing_count", 0),
                "license_missing_count": metric.get("license_missing_count", 0),
                "endpoint_unassigned_count": metric.get("endpoint_unassigned_count", 0),
                "duplicate_pressure_count": metric.get("duplicate_pressure_count", 0),
                "candidate_impacted_row_count": metric.get("candidate_impacted_row_count", 0),
                "promotion_approval_status": approval.get("status", ""),
                "promotion_allowed": approval.get("promotion_allowed", False),
                "next_action": next_action,
            }
        )
    severity_counts = Counter(str(row.get("severity") or "") for row in rows)
    issue_counts = Counter(str(row.get("issue_type") or "") for row in rows)
    owner_counts = Counter(str(row.get("owner_role") or "") for row in rows)
    status_counts = Counter(str(row.get("status") or "") for row in rows)
    open_count = sum(1 for row in rows if not str(row.get("status") or "").startswith("closed"))
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "closed_holdout" if rows and open_count == 0 else "ready" if metrics else "awaiting_metrics",
        "mode": "rgroup_digestion_quality_closure_queue",
        "metric_row_count": metrics.get("row_count", 0),
        "watch_metric_count": (metrics.get("quality_status_counts") or {}).get("watch", 0),
        "blocked_metric_count": (metrics.get("quality_status_counts") or {}).get("blocked", 0),
        "row_count": len(rows),
        "open_count": open_count,
        "closed_count": len(rows) - open_count,
        "high_count": severity_counts.get("high", 0),
        "medium_count": severity_counts.get("medium", 0),
        "low_count": severity_counts.get("low", 0),
        "issue_type_counts": dict(issue_counts.most_common()),
        "owner_role_counts": dict(owner_counts.most_common()),
        "status_counts": dict(status_counts.most_common()),
        "closure_ledger_status": closure_ledger.get("status", ""),
        "production_scoring_affected": False,
        "promotion_allowed": approval.get("promotion_allowed", False),
        "rows": rows,
        "recommended_next_actions": [
            "Work high-severity provenance and license tasks first.",
            "Use medium-severity endpoint, confidence, duplicate, and candidate-impact tasks to decide which holdout rows can be promoted later.",
        ],
    }


def render_rgroup_digestion_quality_closure_queue_markdown(report: dict) -> str:
    lines = [
        "# R-group Digestion Quality Closure Queue",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Open tasks: `{report.get('open_count')}`",
        "",
        "| Task | Metric | Type | Group | Severity | Issue | Owner | Rows | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("task_id") or ""),
                    str(row.get("metric_id") or ""),
                    str(row.get("metric_type") or ""),
                    str(row.get("group_key") or ""),
                    str(row.get("severity") or ""),
                    str(row.get("issue_type") or ""),
                    str(row.get("owner_role") or ""),
                    str(row.get("row_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_digestion_quality_closure_queue(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_QUEUE_JSON,
    csv_path: str | Path | None = DEFAULT_QUEUE_CSV,
    markdown_path: str | Path | None = DEFAULT_QUEUE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "task_id",
        "metric_id",
        "metric_type",
        "group_key",
        "quality_status",
        "issue_type",
        "severity",
        "owner_role",
        "status",
        "closure_decision",
        "resolved_for_promotion",
        "closure_note",
        "row_count",
        "low_confidence_count",
        "provenance_missing_count",
        "license_missing_count",
        "endpoint_unassigned_count",
        "duplicate_pressure_count",
        "candidate_impacted_row_count",
        "promotion_approval_status",
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
        md_file.write_text(render_rgroup_digestion_quality_closure_queue_markdown(report), encoding="utf-8")
