from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SIGNOFF_JSON = Path("data/substituents/rgroup_staging_curator_signoff.json")
DEFAULT_SIGNOFF_CSV = Path("data/substituents/rgroup_staging_curator_signoff.csv")
DEFAULT_SIGNOFF_MD = Path("docs/rgroup_staging_curator_signoff.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import", "production_scoring_write"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _queue_rows(root_path: Path) -> list[dict[str, Any]]:
    budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    rows = list(budget.get("manual_review_queue_rows") or [])
    if rows:
        return [dict(row) for row in rows]
    return [dict(row) for row in budget.get("rows") or []]


def _wanted(row: dict, queue_ids: set[str], sources: set[str]) -> bool:
    queue_id = str(row.get("review_queue_id") or row.get("budget_id") or "").strip()
    source = str(row.get("source_dataset") or "").strip()
    if not queue_ids and not sources:
        return True
    return bool(queue_id and queue_id in queue_ids) or bool(source and source in sources)


def build_rgroup_staging_curator_signoff(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    report = _read_json(root_path / DEFAULT_SIGNOFF_JSON)
    rows = [dict(row) for row in report.get("rows") or []]
    decision_counts = Counter(str(row.get("curator_decision") or "unknown") for row in rows)
    approved_count = sum(1 for row in rows if str(row.get("curator_decision") or "") in {"ready_for_sandbox_review", "accepted_for_sandbox", "reviewed"})
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "rgroup_staging_curator_signoff",
        "row_count": len(rows),
        "approved_for_sandbox_count": approved_count,
        "decision_counts": dict(decision_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use curator signoff only to clear the manual staging review queue before sandbox score-delta review.",
            "Keep promotion and production scoring disabled until separate governed promotion gates pass.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def record_rgroup_staging_curator_signoff(
    *,
    root: str | Path = ".",
    review_queue_ids: list[str] | None = None,
    source_datasets: list[str] | None = None,
    curator_decision: str = "ready_for_sandbox_review",
    curator: str = "local_curator",
    curator_note: str = "",
    version_change_note: str = "",
) -> dict[str, Any]:
    root_path = Path(root)
    existing = build_rgroup_staging_curator_signoff(root_path)
    existing_rows = [dict(row) for row in existing.get("rows") or []]
    queue_ids = {str(item).strip() for item in review_queue_ids or [] if str(item).strip()}
    sources = {str(item).strip() for item in source_datasets or [] if str(item).strip()}
    now = datetime.now(timezone.utc).isoformat()
    queue = [row for row in _queue_rows(root_path) if _wanted(row, queue_ids, sources)]
    new_rows: list[dict[str, Any]] = []
    for row in queue:
        queue_id = str(row.get("review_queue_id") or row.get("budget_id") or "").strip()
        source = str(row.get("source_dataset") or "").strip()
        new_rows.append(
            {
                "signoff_id": f"RSCUR-{now.replace(':', '').replace('-', '')}-{queue_id or source}",
                "review_queue_id": queue_id,
                "source_dataset": source,
                "manual_review_status": row.get("manual_review_status") or row.get("budget_status") or "",
                "curator_decision": curator_decision,
                "curator": curator,
                "curator_note": curator_note,
                "version_change_note": version_change_note or row.get("version_change_log") or "",
                "applicable_contexts": row.get("applicable_contexts") or "",
                "disabled_contexts": row.get("disabled_contexts") or ";".join(BLOCKED_SCOPES),
                "review_status_policy": row.get("review_status_policy") or "",
                "row_count": row.get("row_count") or 0,
                "blocker_count": row.get("blocker_count") or 0,
                "warning_count": row.get("warning_count") or 0,
                "staging_path": row.get("staging_path") or "",
                "signed_at": now,
                "production_scoring_write_allowed": False,
                "promotion_allowed": False,
                "next_action": "Run sandbox score-delta review only after this source is curated; production promotion remains separately gated.",
            }
        )
    rows = existing_rows + new_rows
    payload = {
        "created_at": now,
        "status": "ready" if rows else "empty",
        "mode": "rgroup_staging_curator_signoff",
        "updated_count": len(new_rows),
        "row_count": len(rows),
        "decision_counts": dict(Counter(str(row.get("curator_decision") or "unknown") for row in rows).most_common()),
        "rows": rows,
        "blocked_scopes": BLOCKED_SCOPES,
    }
    return payload


def render_rgroup_staging_curator_signoff_markdown(report: dict) -> str:
    lines = [
        "# R-group Staging Curator Signoff",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "| Queue | Source | Decision | Curator | Rows | Blockers | Version Note |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("review_queue_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("curator_decision") or ""),
                    str(row.get("curator") or ""),
                    str(row.get("row_count") or 0),
                    str(row.get("blocker_count") or 0),
                    str(row.get("version_change_note") or "").replace("|", "/")[:220],
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_staging_curator_signoff(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_SIGNOFF_JSON,
    csv_path: str | Path | None = DEFAULT_SIGNOFF_CSV,
    markdown_path: str | Path | None = DEFAULT_SIGNOFF_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "signoff_id",
        "review_queue_id",
        "source_dataset",
        "manual_review_status",
        "curator_decision",
        "curator",
        "curator_note",
        "version_change_note",
        "applicable_contexts",
        "disabled_contexts",
        "review_status_policy",
        "row_count",
        "blocker_count",
        "warning_count",
        "staging_path",
        "signed_at",
        "production_scoring_write_allowed",
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
        md_file.write_text(render_rgroup_staging_curator_signoff_markdown(report), encoding="utf-8")
