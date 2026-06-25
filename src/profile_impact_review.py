from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROFILE_IMPACT_REVIEW_PATH = Path("data/projects/demo/profile_impact_review_queue.json")
DEFAULT_PROFILE_IMPACT_REVIEW_CSV_PATH = Path("data/projects/demo/profile_impact_review_queue.csv")
PROFILE_IMPACT_REVIEW_STATUSES = {"open", "assigned", "in_review", "accepted", "rollback_requested", "deferred", "closed"}
_REVIEW_FIELDS = ["review_status", "assigned_to", "reviewed_by", "reviewed_at", "review_note", "review_history"]


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve(root_path: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root_path / item


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _review_id(row: dict) -> str:
    identity = row.get("evidence_value_id") or row.get("queue_id") or row.get("candidate_id") or row.get("smiles") or "unknown"
    return f"PIR-{identity}"


def _severity(row: dict) -> str:
    score_delta = abs(_float(row.get("profile_rollback_score_delta")))
    rank_delta = abs(_float(row.get("profile_rollback_rank_delta")))
    if score_delta >= 10 or rank_delta >= 20:
        return "critical"
    if score_delta >= 6 or rank_delta >= 10:
        return "high"
    return "medium"


def _priority_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(severity or ""), 9)


def _existing_review_lookup(path: Path) -> dict[str, dict]:
    report = _read_json(path)
    lookup = {}
    for row in report.get("rows") or []:
        review_id = str(row.get("review_id") or "")
        if not review_id:
            continue
        lookup[review_id] = {field: row.get(field, [] if field == "review_history" else "") for field in _REVIEW_FIELDS}
    return lookup


def build_profile_impact_review_queue(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    active_compare_path: str | Path = "data/projects/demo/evidence_value_policy_active_compare.json",
    existing_review_path: str | Path = DEFAULT_PROFILE_IMPACT_REVIEW_PATH,
) -> dict:
    root_path = Path(root)
    active_file = _resolve(root_path, active_compare_path)
    existing_file = _resolve(root_path, existing_review_path)
    active_compare = _read_json(active_file)
    preserved = _existing_review_lookup(existing_file)
    rows = []
    for raw in active_compare.get("rows") or []:
        if not raw.get("profile_impact_review_flag"):
            continue
        row = dict(raw)
        severity = _severity(row)
        review_id = _review_id(row)
        review_row = {
            "review_id": review_id,
            "severity": severity,
            "source_artifact": "evidence_value_policy_active_compare",
            "evidence_value_id": row.get("evidence_value_id"),
            "queue_id": row.get("queue_id"),
            "candidate_id": row.get("candidate_id"),
            "endpoint_group": row.get("endpoint_group"),
            "active_rank": row.get("active_rank"),
            "baseline_rank": row.get("baseline_rank"),
            "rank_delta": row.get("rank_delta"),
            "active_score": row.get("active_score"),
            "baseline_score": row.get("baseline_score"),
            "score_delta": row.get("score_delta"),
            "profile_rollback_action": row.get("profile_rollback_action"),
            "profile_rollback_score_delta": row.get("profile_rollback_score_delta"),
            "profile_rollback_rank_delta": row.get("profile_rollback_rank_delta"),
            "review_action": (
                "profile_policy_rollback_review"
                if severity in {"critical", "high"}
                else "profile_policy_watch_review"
            ),
            "review_status": "open",
            "assigned_to": "",
            "reviewed_by": "",
            "reviewed_at": "",
            "review_note": "",
            "review_history": [],
        }
        for field in _REVIEW_FIELDS:
            if field == "review_history":
                review_row[field] = list((preserved.get(review_id) or {}).get(field) or [])
            else:
                review_row[field] = (preserved.get(review_id) or {}).get(field) or review_row.get(field) or ""
        rows.append(review_row)
    rows.sort(key=lambda row: (_priority_rank(str(row.get("severity") or "")), int(_float(row.get("active_rank"), 9999))))
    severity_counts = Counter(str(row.get("severity") or "unknown") for row in rows)
    status_counts = Counter(str(row.get("review_status") or "open") for row in rows)
    open_count = sum(1 for row in rows if str(row.get("review_status") or "open") not in {"accepted", "closed", "deferred"})
    status = "empty" if not rows else "review_required" if open_count else "reviewed"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "non_experimental_profile_policy_review",
        "project_name": project_name,
        "active_compare_status": active_compare.get("status") or "missing",
        "row_count": len(rows),
        "open_review_count": open_count,
        "severity_counts": dict(severity_counts.most_common()),
        "review_status_counts": dict(status_counts.most_common()),
        "rollback_target_policy_version": active_compare.get("rollback_target_policy_version"),
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase", "real_experiment_feedback"],
        "recommended_next_actions": [
            "Review high-severity profile impact rows before accepting another active evidence-value policy change.",
            "Use rollback_target_policy_version for policy rollback planning only; do not trigger real experimental feedback.",
            "Close rows after reviewer decision is captured in Project Memory.",
        ],
    }


def write_profile_impact_review_queue(
    report: dict,
    output_path: str | Path = DEFAULT_PROFILE_IMPACT_REVIEW_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROFILE_IMPACT_REVIEW_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "review_id",
        "severity",
        "review_status",
        "assigned_to",
        "candidate_id",
        "queue_id",
        "endpoint_group",
        "active_rank",
        "baseline_rank",
        "score_delta",
        "profile_rollback_action",
        "profile_rollback_score_delta",
        "profile_rollback_rank_delta",
        "review_action",
        "reviewed_by",
        "reviewed_at",
        "review_note",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def apply_profile_impact_review_batch(
    *,
    review_path: str | Path = DEFAULT_PROFILE_IMPACT_REVIEW_PATH,
    csv_path: str | Path | None = DEFAULT_PROFILE_IMPACT_REVIEW_CSV_PATH,
    review_ids: list[str] | None = None,
    severity: str | None = None,
    current_review_status: str | None = None,
    review_status: str,
    assigned_to: str | None = None,
    reviewer: str | None = None,
    note: str | None = None,
    limit: int | None = None,
) -> dict:
    status = str(review_status or "").strip().lower()
    if status not in PROFILE_IMPACT_REVIEW_STATUSES:
        raise ValueError(f"Unsupported profile-impact review status: {review_status}")
    selected_ids = {str(item) for item in (review_ids or []) if str(item)}
    path = Path(review_path)
    report = _read_json(path)
    rows = [dict(row) for row in report.get("rows") or []]
    now = datetime.now(timezone.utc).isoformat()
    applied = []
    for row in rows:
        if selected_ids and str(row.get("review_id") or "") not in selected_ids:
            continue
        if severity and str(row.get("severity") or "") != str(severity):
            continue
        if current_review_status and str(row.get("review_status") or "open") != str(current_review_status):
            continue
        if not selected_ids and not severity:
            continue
        if limit is not None and len(applied) >= int(limit):
            continue
        previous = row.get("review_status") or "open"
        row["review_status"] = status
        if assigned_to is not None:
            row["assigned_to"] = assigned_to
        if reviewer is not None:
            row["reviewed_by"] = reviewer
            row["reviewed_at"] = now
        if note is not None:
            row["review_note"] = note
        history = list(row.get("review_history") or [])
        history.append(
            {
                "reviewed_at": now,
                "previous_review_status": previous,
                "review_status": status,
                "assigned_to": assigned_to if assigned_to is not None else row.get("assigned_to", ""),
                "reviewer": reviewer or "",
                "note": note or "",
            }
        )
        row["review_history"] = history
        applied.append(str(row.get("review_id") or ""))
    report["rows"] = rows
    report["review_status_counts"] = dict(Counter(str(row.get("review_status") or "open") for row in rows).most_common())
    report["open_review_count"] = sum(1 for row in rows if str(row.get("review_status") or "open") not in {"accepted", "closed", "deferred"})
    report["status"] = "empty" if not rows else "review_required" if report["open_review_count"] else "reviewed"
    report["updated_at"] = now
    report["last_batch_update"] = {
        "updated_at": now,
        "review_status": status,
        "severity": severity or "",
        "current_review_status": current_review_status or "",
        "applied_count": len(applied),
        "review_ids": applied,
        "reviewer": reviewer or "",
        "note": note or "",
    }
    write_profile_impact_review_queue(report, path, csv_path=csv_path)
    return {
        "status": "updated",
        "applied_count": len(applied),
        "review_status": status,
        "review_ids": applied,
        "open_review_count": report["open_review_count"],
        "queue": report,
    }
