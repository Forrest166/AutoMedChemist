from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .database import initialize_database


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_ASSAY_EVENT_TRIAGE_PATH = Path("data/projects/demo/assay_event_triage_report.json")
DEFAULT_ASSAY_EVENT_TRIAGE_CSV_PATH = Path("data/projects/demo/assay_event_triage_report.csv")
ADDRESSED_TRIAGE_STATUSES = {
    "planned_followup",
    "resolved",
    "resolved_by_followup",
    "deferred_with_rationale",
    "superseded",
}


def _lineage_group_id(*parts: object) -> str:
    basis = "|".join(str(part or "") for part in parts)
    return f"AELIN-{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:12].upper()}"


def _event_rows(db_path: str | Path, project_name: str | None = None) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params: tuple = ()
        where = ""
        if project_name:
            where = "WHERE COALESCE(p.project_name, '') = ?"
            params = (project_name,)
        rows = conn.execute(
            f"""
            SELECT
                e.event_id, e.plan_id, e.run_id, e.candidate_id, e.status,
                e.endpoint_group, e.assay_name, e.assay_type, e.value,
                e.normalized_score, e.classification, e.replicate_count, e.replicate_cv,
                e.assay_confidence, e.assay_confidence_score,
                e.stop_go_decision, e.retest_reason, e.recorded_at,
                p.project_name
            FROM project_experiment_event e
            LEFT JOIN project_experiment_plan p ON p.plan_id = e.plan_id
            {where}
            ORDER BY e.recorded_at DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _issue_types(row: dict) -> list[str]:
    issues = []
    if str(row.get("assay_confidence") or "").lower() == "low":
        issues.append("low_confidence_assay")
    if str(row.get("stop_go_decision") or "").lower() == "retest":
        issues.append("open_retest")
    return issues


def _default_action(row: dict) -> str:
    issues = set(_issue_types(row))
    if "open_retest" in issues:
        return "Create or link follow-up result row; keep scoring changes review-gated until retest is resolved."
    if "low_confidence_assay" in issues:
        return "Add replicate depth, confirm variance, or defer this event from calibration-sensitive promotion."
    return "No triage needed."


def _parse_dt(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _has_result_payload(row: dict) -> bool:
    return any(row.get(key) not in {None, ""} for key in ["value", "normalized_score", "classification"])


def _same_followup_context(source: dict, candidate: dict) -> bool:
    source_plan = str(source.get("plan_id") or "")
    candidate_plan = str(candidate.get("plan_id") or "")
    if source_plan and candidate_plan and source_plan == candidate_plan:
        return True
    source_run = str(source.get("run_id") or "")
    source_candidate = str(source.get("candidate_id") or "")
    candidate_run = str(candidate.get("run_id") or "")
    candidate_candidate = str(candidate.get("candidate_id") or "")
    if source_run and source_candidate and source_run == candidate_run and source_candidate == candidate_candidate:
        source_endpoint = str(source.get("endpoint_group") or "")
        candidate_endpoint = str(candidate.get("endpoint_group") or "")
        return not source_endpoint or not candidate_endpoint or source_endpoint == candidate_endpoint
    return False


def _is_resolving_followup(row: dict) -> bool:
    if str(row.get("status") or "").lower() != "completed":
        return False
    if not _has_result_payload(row):
        return False
    return not _issue_types(row)


def _linked_followup_event(event: dict, all_events: list[dict]) -> dict:
    event_time = _parse_dt(event.get("recorded_at"))
    candidates = []
    for candidate in all_events:
        if candidate.get("event_id") == event.get("event_id"):
            continue
        if not _same_followup_context(event, candidate):
            continue
        if not _has_result_payload(candidate):
            continue
        candidate_time = _parse_dt(candidate.get("recorded_at"))
        if event_time and candidate_time and candidate_time <= event_time:
            continue
        candidates.append(candidate)
    candidates.sort(key=lambda row: (0 if _is_resolving_followup(row) else 1, str(row.get("recorded_at") or "")))
    return candidates[0] if candidates else {}


def _triage_status_for_event(event: dict, all_events: list[dict], default_status: str) -> tuple[str, dict]:
    followup = _linked_followup_event(event, all_events)
    if not followup:
        return default_status, {}
    if _is_resolving_followup(followup):
        return "resolved_by_followup", followup
    return "followup_result_needs_review", followup


def _lineage_key(row: dict) -> tuple[str, ...]:
    followup_id = str(row.get("linked_followup_event_id") or "")
    if followup_id:
        return (
            "followup",
            followup_id,
            str(row.get("endpoint_group") or ""),
            str(row.get("issue_types") or ""),
        )
    return (
        "source",
        str(row.get("plan_id") or ""),
        str(row.get("run_id") or ""),
        str(row.get("candidate_id") or ""),
        str(row.get("endpoint_group") or ""),
        str(row.get("issue_types") or ""),
    )


def _attach_lineage_groups(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, ...], list[dict]] = {}
    for row in rows:
        groups.setdefault(_lineage_key(row), []).append(row)
    for key, group_rows in groups.items():
        group_rows.sort(key=lambda row: str(row.get("event_id") or ""))
        group_id = _lineage_group_id(*key)
        group_size = len(group_rows)
        for index, row in enumerate(group_rows, start=1):
            row["lineage_group_id"] = group_id
            row["lineage_group_size"] = group_size
            row["lineage_group_index"] = index
            row["lineage_role"] = "lineage_representative" if index == 1 else "duplicate_lineage_event"
            row["lineage_basis"] = "|".join(key)
    return rows


def build_assay_event_triage_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = "demo_learning",
    default_status: str = "planned_followup",
    reviewer: str = "assay_triage",
) -> dict:
    all_events = _event_rows(db_path, project_name=project_name)
    rows = []
    for event in all_events:
        issues = _issue_types(event)
        if not issues:
            continue
        triage_status, followup = _triage_status_for_event(event, all_events, default_status)
        rows.append(
            {
                "event_id": event.get("event_id"),
                "plan_id": event.get("plan_id"),
                "run_id": event.get("run_id"),
                "candidate_id": event.get("candidate_id"),
                "project_name": event.get("project_name") or project_name,
                "endpoint_group": event.get("endpoint_group"),
                "assay_name": event.get("assay_name"),
                "assay_type": event.get("assay_type"),
                "issue_types": ";".join(issues),
                "triage_status": triage_status,
                "triage_action": "Follow-up result imported; review downstream model/gate updates." if followup else _default_action(event),
                "linked_followup_event_id": followup.get("event_id"),
                "linked_followup_status": followup.get("status"),
                "linked_followup_recorded_at": followup.get("recorded_at"),
                "linked_followup_assay_confidence": followup.get("assay_confidence"),
                "linked_followup_stop_go_decision": followup.get("stop_go_decision"),
                "lineage_group_id": "",
                "lineage_group_size": 1,
                "lineage_group_index": 1,
                "lineage_role": "lineage_representative",
                "lineage_basis": "",
                "reviewed_by": reviewer,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "assay_confidence": event.get("assay_confidence"),
                "assay_confidence_score": event.get("assay_confidence_score"),
                "stop_go_decision": event.get("stop_go_decision"),
                "retest_reason": event.get("retest_reason"),
            }
        )
    rows = _attach_lineage_groups(rows)
    counts = Counter()
    addressed = Counter()
    resolved = Counter()
    planned = Counter()
    needs_review = Counter()
    for row in rows:
        issues = [item for item in str(row.get("issue_types") or "").split(";") if item]
        for issue in issues:
            counts[issue] += 1
            if row.get("triage_status") in ADDRESSED_TRIAGE_STATUSES:
                addressed[issue] += 1
            if row.get("triage_status") == "resolved_by_followup":
                resolved[issue] += 1
            if row.get("triage_status") == "planned_followup":
                planned[issue] += 1
            if row.get("triage_status") == "followup_result_needs_review":
                needs_review[issue] += 1
    planned_followup_count = sum(1 for row in rows if row.get("triage_status") == "planned_followup")
    followup_review_count = sum(1 for row in rows if row.get("triage_status") == "followup_result_needs_review")
    real_followup_resolved_count = sum(1 for row in rows if row.get("triage_status") == "resolved_by_followup")
    lineage_groups = {}
    for row in rows:
        group_id = str(row.get("lineage_group_id") or "")
        if not group_id:
            continue
        item = lineage_groups.setdefault(
            group_id,
            {
                "lineage_group_id": group_id,
                "lineage_basis": row.get("lineage_basis"),
                "lineage_group_size": int(row.get("lineage_group_size") or 0),
                "representative_event_id": row.get("event_id") if row.get("lineage_role") == "lineage_representative" else None,
                "linked_followup_event_id": row.get("linked_followup_event_id"),
                "endpoint_group": row.get("endpoint_group"),
                "issue_types": row.get("issue_types"),
                "triage_status": row.get("triage_status"),
                "source_event_ids": [],
            },
        )
        if row.get("lineage_role") == "lineage_representative":
            item["representative_event_id"] = row.get("event_id")
        if row.get("event_id"):
            item["source_event_ids"].append(row.get("event_id"))
        if row.get("linked_followup_event_id"):
            item["linked_followup_event_id"] = row.get("linked_followup_event_id")
    lineage_group_rows = list(lineage_groups.values())
    duplicate_lineage_event_count = sum(max(int(row.get("lineage_group_size") or 0) - 1, 0) for row in lineage_group_rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "triaged" if rows else "empty",
        "project_name": project_name,
        "triage_status": default_status,
        "event_count": len(rows),
        "planned_followup_count": planned_followup_count,
        "followup_review_count": followup_review_count,
        "real_followup_resolved_count": real_followup_resolved_count,
        "unique_followup_event_count": len({str(row.get("linked_followup_event_id") or "") for row in rows if row.get("linked_followup_event_id")}),
        "lineage_group_count": len(lineage_group_rows),
        "duplicate_lineage_event_count": duplicate_lineage_event_count,
        "lineage_groups": lineage_group_rows,
        "issue_counts": dict(counts.most_common()),
        "addressed_issue_counts": dict(addressed.most_common()),
        "planned_issue_counts": dict(planned.most_common()),
        "real_followup_resolved_issue_counts": dict(resolved.most_common()),
        "followup_review_issue_counts": dict(needs_review.most_common()),
        "open_issue_counts": {key: max(counts[key] - addressed.get(key, 0), 0) for key in counts},
        "rows": rows,
        "recommended_next_actions": [
            "Use planned_followup to acknowledge triage, not to claim measured retest resolution.",
            "Replace planned_followup with resolved only after a real follow-up result is imported.",
            "Use lineage_group_id to review repeated low-confidence/retest rows that are resolved by the same follow-up event.",
            "Keep profile promotion review-gated while important retest or low-confidence rows are still only planned.",
        ],
    }


def write_assay_event_triage_report(
    report: dict,
    output_path: str | Path = DEFAULT_ASSAY_EVENT_TRIAGE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_ASSAY_EVENT_TRIAGE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fieldnames = [
        "event_id",
        "plan_id",
        "run_id",
        "candidate_id",
        "project_name",
        "endpoint_group",
        "assay_name",
        "assay_type",
        "issue_types",
        "triage_status",
        "triage_action",
        "linked_followup_event_id",
        "linked_followup_status",
        "linked_followup_recorded_at",
        "linked_followup_assay_confidence",
        "linked_followup_stop_go_decision",
        "lineage_group_id",
        "lineage_group_size",
        "lineage_group_index",
        "lineage_role",
        "lineage_basis",
        "reviewed_by",
        "reviewed_at",
        "assay_confidence",
        "assay_confidence_score",
        "stop_go_decision",
        "retest_reason",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
