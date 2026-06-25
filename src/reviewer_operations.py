from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEWER_OPS_JSON = Path("data/projects/demo/reviewer_operations.json")
DEFAULT_REVIEWER_OPS_CSV = Path("data/projects/demo/reviewer_operations.csv")
DEFAULT_REVIEWER_OPS_MD = Path("docs/reviewer_operations.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]
PENDING_STATUSES = {"", "pending_review", "unreviewed", "needs_follow_up", "blocked", "deferred"}
CLOSED_STATUSES = {"reviewed", "evidence_supported", "accepted", "accept", "closed"}


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_days(value: object, now: datetime) -> int:
    stamp = _parse_time(value)
    if stamp is None:
        return 0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, int((now - stamp).total_seconds() // 86400))


def _status(row: dict) -> str:
    return str(row.get("local_review_status") or row.get("review_status") or "").strip()


def _is_closed(row: dict) -> bool:
    status = _status(row)
    decision = str(row.get("reviewer_decision") or "").strip()
    return status in CLOSED_STATUSES or decision in CLOSED_STATUSES


def _reason_bucket(row: dict) -> str:
    text = " ".join(
        str(row.get(field) or "")
        for field in ["review_note", "why_review", "review_bucket", "risk_bucket", "proposed_review_action", "site_class_governance_action"]
    ).lower()
    if "contradiction" in text or "conflict" in text:
        return "contradiction"
    if "baseline" in text or "movement" in text:
        return "baseline_context"
    if "thin" in text or "evidence" in text or "mmp" in text or "sar" in text:
        return "evidence_depth"
    if "site" in text or "class" in text or "policy" in text:
        return "site_class_policy"
    if "risk" in text or "blocked" in text:
        return "risk_review"
    return "no_reason_recorded"


def _sla_band(status: str, age_days: int, stale_days: int) -> str:
    if status not in PENDING_STATUSES:
        return "closed"
    if age_days >= stale_days:
        return "overdue"
    if age_days >= max(1, stale_days // 2):
        return "aging"
    return "fresh"


def build_reviewer_operations(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    stale_days: int = 7,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    board = _read_json(project_dir / "candidate_review_board.json")
    ledger = _read_json(project_dir / "candidate_review_status_ledger.json")
    board_rows = [dict(row) for row in board.get("rows") or []]
    ledger_rows = ledger.get("decisions") or {}
    now = datetime.now(timezone.utc)
    candidate_rows: list[dict[str, Any]] = []
    defer_reasons: Counter[str] = Counter()
    reviewer_workload: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "closed": 0, "pending": 0, "ledger_events": 0})
    site_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "closed": 0, "pending": 0})
    for row in board_rows:
        candidate_id = str(row.get("candidate_id") or "").strip()
        status = _status(row)
        age = _age_days(row.get("reviewed_at") or row.get("created_at") or board.get("created_at"), now)
        sla_band = _sla_band(status, age, int(stale_days))
        reviewer = str(row.get("reviewer") or "unassigned").strip() or "unassigned"
        site = str(row.get("site_class") or "unknown").strip() or "unknown"
        closed = _is_closed(row)
        reason = _reason_bucket(row) if status in PENDING_STATUSES or str(row.get("risk_bucket") or "") not in {"", "clear", "unknown"} else ""
        if reason:
            defer_reasons[reason] += 1
        reviewer_workload[reviewer]["total"] += 1
        reviewer_workload[reviewer]["closed"] += 1 if closed else 0
        reviewer_workload[reviewer]["pending"] += 0 if closed else 1
        site_totals[site]["total"] += 1
        site_totals[site]["closed"] += 1 if closed else 0
        site_totals[site]["pending"] += 0 if closed else 1
        candidate_rows.append(
            {
                "candidate_id": candidate_id,
                "site_class": site,
                "reviewer": reviewer,
                "local_review_status": status,
                "reviewer_decision": row.get("reviewer_decision", ""),
                "pending_age_days": age,
                "sla_band": sla_band,
                "defer_reason": reason,
                "risk_bucket": row.get("risk_bucket", ""),
                "next_action": "Refresh or close this pending review row." if sla_band in {"aging", "overdue"} else "No reviewer operation action required.",
            }
        )
    for ledger_row in ledger_rows.values():
        reviewer = str((ledger_row or {}).get("reviewer") or "unassigned").strip() or "unassigned"
        reviewer_workload[reviewer]["ledger_events"] += len((ledger_row or {}).get("history") or [])
    rows: list[dict[str, Any]] = []
    for item in candidate_rows:
        rows.append(
            {
                "row_type": "candidate_sla",
                "key": item["candidate_id"],
                "status": item["sla_band"],
                "value": item["pending_age_days"],
                "secondary": item["local_review_status"],
                "details": f"site={item['site_class']}; reviewer={item['reviewer']}; reason={item['defer_reason'] or '-'}",
                "next_action": item["next_action"],
            }
        )
    for reason, count in sorted(defer_reasons.items()):
        rows.append(
            {
                "row_type": "defer_reason",
                "key": reason,
                "status": "needs_attention" if count > 1 or reason == "no_reason_recorded" else "ready",
                "value": count,
                "secondary": "",
                "details": f"repeat_count={count}",
                "next_action": "Review repeated or unannotated defer reasons before closing the board.",
            }
        )
    for reviewer, counts in sorted(reviewer_workload.items()):
        rows.append(
            {
                "row_type": "reviewer_workload",
                "key": reviewer,
                "status": "needs_attention" if counts["pending"] else "ready",
                "value": counts["closed"],
                "secondary": counts["pending"],
                "details": f"total={counts['total']}; ledger_events={counts['ledger_events']}",
                "next_action": "Balance pending rows across reviewers if one owner accumulates backlog.",
            }
        )
    closure_rates: dict[str, float] = {}
    for site, counts in sorted(site_totals.items()):
        total = counts["total"]
        rate = round(counts["closed"] / total, 3) if total else 0.0
        closure_rates[site] = rate
        rows.append(
            {
                "row_type": "site_class_closure",
                "key": site,
                "status": "ready" if rate >= 0.8 else "needs_attention" if counts["pending"] else "ready",
                "value": rate,
                "secondary": f"{counts['closed']}/{total}",
                "details": f"pending={counts['pending']}",
                "next_action": "Close or explicitly defer site-class rows with low closure rate.",
            }
        )
    pending_overdue = sum(1 for row in candidate_rows if row["sla_band"] == "overdue")
    repeated_defer = sum(1 for reason, count in defer_reasons.items() if count > 1 or reason == "no_reason_recorded")
    workload_pending = sum(counts["pending"] for counts in reviewer_workload.values())
    low_closure = sum(1 for rate in closure_rates.values() if rate < 0.8)
    cards = [
        {
            "card_id": "pending_sla",
            "label": "Pending age SLA",
            "status": "needs_attention" if pending_overdue else "ready",
            "value": pending_overdue,
            "details": f"stale_days={int(stale_days)}; candidate_rows={len(candidate_rows)}",
        },
        {
            "card_id": "repeated_defer_reason",
            "label": "Repeated defer reason",
            "status": "needs_attention" if repeated_defer else "ready",
            "value": repeated_defer,
            "details": f"reasons={dict(defer_reasons.most_common())}",
        },
        {
            "card_id": "reviewer_workload_trend",
            "label": "Reviewer workload trend",
            "status": "needs_attention" if workload_pending else "ready",
            "value": workload_pending,
            "details": f"reviewers={len(reviewer_workload)}; ledger_decisions={len(ledger_rows)}",
        },
        {
            "card_id": "site_class_closure_rate",
            "label": "Site-class closure rate",
            "status": "needs_attention" if low_closure else "ready",
            "value": low_closure,
            "details": f"closure_rates={closure_rates}",
        },
    ]
    return {
        "created_at": now.isoformat(),
        "status": "ready" if board_rows else "missing_review_board",
        "mode": "candidate_reviewer_operations",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_row_count": len(candidate_rows),
        "pending_overdue_count": pending_overdue,
        "stale_count": pending_overdue,
        "repeated_defer_reason_count": repeated_defer,
        "deferral_count": repeated_defer,
        "workload_pending_count": workload_pending,
        "low_site_class_closure_count": low_closure,
        "reviewer_count": len(reviewer_workload),
        "site_class_count": len(site_totals),
        "defer_reason_counts": dict(defer_reasons.most_common()),
        "closure_rates": closure_rates,
        "cards": cards,
        "rows": rows,
        "candidate_rows": candidate_rows,
        "real_experiment_feedback_used": False,
        "recommended_next_actions": [
            "Use reviewer operations to route manual board cleanup.",
            "Keep deferred rows documented instead of converting them into execution or feedback automation.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_reviewer_operations_markdown(report: dict) -> str:
    lines = [
        "# Reviewer Operations",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Overdue pending rows: `{report.get('pending_overdue_count')}`",
        "",
        "| Type | Key | Status | Value | Secondary | Details | Next Action |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:160]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("row_type") or ""),
                    str(row.get("key") or ""),
                    str(row.get("status") or ""),
                    str(row.get("value") or ""),
                    str(row.get("secondary") or ""),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reviewer_operations(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEWER_OPS_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEWER_OPS_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEWER_OPS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["row_type", "key", "status", "value", "secondary", "details", "next_action"]
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
        md_file.write_text(render_reviewer_operations_markdown(report), encoding="utf-8")
