from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_JSON = Path("data/projects/demo/candidate_review_reason_workbench.json")
DEFAULT_CSV = Path("data/projects/demo/candidate_review_reason_workbench.csv")
DEFAULT_AUDIT_JSON = Path("data/projects/demo/candidate_review_reason_workbench_audit.json")
DEFAULT_AUDIT_CSV = Path("data/projects/demo/candidate_review_reason_workbench_audit.csv")
DEFAULT_MD = Path("docs/candidate_review_reason_workbench.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _project_dir(project_name: str) -> Path:
    return Path("data/projects") / project_name


def build_candidate_review_reason_workbench(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = _project_dir(project_name)
    analytics = _read_json(root_path / project_dir / "candidate_review_analytics.json")
    audit = _read_json(root_path / project_dir / "candidate_review_reason_workbench_audit.json")
    clusters = [
        dict(row)
        for row in analytics.get("rows") or []
        if str(row.get("row_type") or "") == "pending_reason_cluster"
    ]
    audit_rows = [dict(row) for row in audit.get("rows") or []]
    closed_counts = Counter(str(row.get("reason_cluster") or "unknown") for row in audit_rows if str(row.get("batch_status") or "") in {"reviewed", "closed", "deferred", "blocked"})
    rows: list[dict[str, Any]] = []
    for idx, cluster in enumerate(clusters, start=1):
        reason = str(cluster.get("filter_value") or cluster.get("key") or "").strip()
        rows.append(
            {
                "workbench_id": f"CRRW-{idx:03d}",
                "reason_cluster": reason,
                "cluster_status": cluster.get("status") or "",
                "cluster_row_count": cluster.get("value") or 0,
                "dominant_site": cluster.get("secondary") or "",
                "closed_batch_count": closed_counts.get(reason, 0),
                "details": cluster.get("details") or "",
                "next_action": "Filter this reason cluster, inspect the first evidence drawer, then batch update only visible rows.",
                "scope_note": "Local candidate review governance only.",
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows or audit_rows else "empty",
        "mode": "candidate_review_reason_workbench",
        "project_name": project_name,
        "row_count": len(rows),
        "audit_event_count": len(audit_rows),
        "closed_cluster_count": sum(1 for row in rows if int(row.get("closed_batch_count") or 0) > 0),
        "rows": rows,
        "audit_rows": audit_rows,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        "scope_note": "Local design/review governance only; external operational workflows are out of scope.",
    }


def record_candidate_review_reason_batch(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    reason_cluster: str,
    candidate_ids: list[str],
    batch_status: str,
    reviewer: str = "local_reviewer",
    note: str = "",
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = _project_dir(project_name)
    audit_path = root_path / project_dir / "candidate_review_reason_workbench_audit.json"
    existing = _read_json(audit_path)
    rows = [dict(row) for row in existing.get("rows") or []]
    now = datetime.now(timezone.utc).isoformat()
    clean_ids = [item.strip() for item in candidate_ids if item.strip()]
    event = {
        "audit_id": f"CRRWA-{now.replace(':', '').replace('-', '')}-{len(rows) + 1:04d}",
        "reason_cluster": reason_cluster,
        "batch_status": batch_status,
        "candidate_ids": ";".join(clean_ids),
        "candidate_count": len(clean_ids),
        "reviewer": reviewer,
        "note": note,
        "created_at": now,
        "audit_scope": "local_candidate_review_reason_batch",
        "production_scoring_write_allowed": False,
        "promotion_allowed": False,
        "next_action": "Use this audit event to replay why visible review rows were batch-updated.",
        "scope_note": "Local candidate review governance only.",
    }
    rows.append(event)
    report = {
        "created_at": now,
        "status": "ready",
        "mode": "candidate_review_reason_workbench_audit",
        "project_name": project_name,
        "updated_count": 1,
        "row_count": len(rows),
        "rows": rows,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        "scope_note": "Local design/review governance only; external operational workflows are out of scope.",
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    audit_csv_path = root_path / project_dir / "candidate_review_reason_workbench_audit.csv"
    audit_fields = [
        "audit_id",
        "reason_cluster",
        "batch_status",
        "candidate_ids",
        "candidate_count",
        "reviewer",
        "note",
        "created_at",
        "audit_scope",
        "production_scoring_write_allowed",
        "promotion_allowed",
        "next_action",
        "scope_note",
    ]
    with audit_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in audit_fields})
    return report


def render_candidate_review_reason_workbench_markdown(report: dict) -> str:
    lines = [
        "# Candidate Review Reason Workbench",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Reason clusters: `{report.get('row_count')}`",
        f"- Audit events: `{report.get('audit_event_count')}`",
        "",
        "| Reason | Rows | Site | Closed Batches | Next Action |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("reason_cluster") or ""),
                    str(row.get("cluster_row_count") or 0),
                    str(row.get("dominant_site") or ""),
                    str(row.get("closed_batch_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    audit_rows = report.get("audit_rows") or []
    if audit_rows:
        lines.extend(
            [
                "",
                "## Audit Replay",
                "",
                "| Reason | Status | Rows | Reviewer | Created | Note |",
                "| --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for row in audit_rows[-20:]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("reason_cluster") or ""),
                        str(row.get("batch_status") or ""),
                        str(row.get("candidate_count") or 0),
                        str(row.get("reviewer") or ""),
                        str(row.get("created_at") or ""),
                        str(row.get("note") or "").replace("|", "/"),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def write_candidate_review_reason_workbench(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_JSON,
    csv_path: str | Path | None = DEFAULT_CSV,
    audit_json_path: str | Path | None = None,
    audit_csv_path: str | Path | None = None,
    markdown_path: str | Path | None = DEFAULT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["workbench_id", "reason_cluster", "cluster_status", "cluster_row_count", "dominant_site", "closed_batch_count", "details", "next_action", "scope_note"]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    audit_rows = report.get("audit_rows") or []
    audit_fields = [
        "audit_id",
        "reason_cluster",
        "batch_status",
        "candidate_ids",
        "candidate_count",
        "reviewer",
        "note",
        "created_at",
        "audit_scope",
        "production_scoring_write_allowed",
        "promotion_allowed",
        "next_action",
        "scope_note",
    ]
    if audit_json_path:
        audit_json = Path(audit_json_path)
        audit_json.parent.mkdir(parents=True, exist_ok=True)
        audit_json.write_text(
            json.dumps(
                {
                    "created_at": report.get("created_at"),
                    "status": "ready" if audit_rows else "empty",
                    "mode": "candidate_review_reason_workbench_audit",
                    "project_name": report.get("project_name"),
                    "row_count": len(audit_rows),
                    "rows": audit_rows,
                    "blocked_scopes": report.get("blocked_scopes") or [],
                    "scope_note": report.get("scope_note") or "Local design/review governance only.",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    if audit_csv_path:
        audit_csv = Path(audit_csv_path)
        audit_csv.parent.mkdir(parents=True, exist_ok=True)
        with audit_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=audit_fields)
            writer.writeheader()
            for row in audit_rows:
                writer.writerow({field: row.get(field, "") for field in audit_fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_review_reason_workbench_markdown(report), encoding="utf-8")
