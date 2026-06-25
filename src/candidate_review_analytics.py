from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REVIEW_ANALYTICS_JSON = Path("data/projects/demo/candidate_review_analytics.json")
DEFAULT_REVIEW_ANALYTICS_CSV = Path("data/projects/demo/candidate_review_analytics.csv")
DEFAULT_REVIEW_ANALYTICS_MD = Path("docs/candidate_review_analytics.md")


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_hours(start: object, now: datetime) -> float:
    parsed = _parse_dt(start)
    if parsed is None:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return round(max(0.0, (now - parsed).total_seconds() / 3600.0), 2)


def _needs_attention(row: dict) -> bool:
    local_status = str(row.get("local_review_status") or "").strip()
    packet_status = str(row.get("review_status") or "").strip()
    risk = str(row.get("risk_bucket") or "").strip()
    return local_status in {"pending_review", "unreviewed", "needs_follow_up", "blocked"} or packet_status == "pending_review" or risk not in {"", "clear"}


def _pending_reason(row: dict) -> tuple[str, str]:
    existing = str(row.get("pending_reason_cluster") or "").strip()
    existing_detail = str(row.get("pending_reason_detail") or "").strip()
    if existing:
        return existing, existing_detail or existing
    local_status = str(row.get("local_review_status") or "").strip()
    packet_status = str(row.get("review_status") or "").strip()
    risk = str(row.get("risk_bucket") or "").strip()
    blocked_contexts = str(row.get("blocked_contexts") or "").strip()
    mmp_flags = str(row.get("mmp_contradiction_flags") or "").strip()
    review_bucket = str(row.get("review_bucket") or "").strip()
    site_action = str(row.get("site_class_governance_action") or "").strip()
    evidence = str(row.get("evidence_strength") or "").strip().lower()
    reviewer = str(row.get("reviewer") or "").strip()
    if risk == "contradiction" or mmp_flags:
        return "risk_contradiction", f"risk={risk or '-'}; mmp_flags={mmp_flags or '-'}"
    if site_action or review_bucket == "site_class_governance_review":
        return "site_class_governance_review", site_action or "site-class policy requires local review"
    if risk == "blocked_context" or blocked_contexts:
        return "blocked_context", blocked_contexts or "blocked context flagged by review packet"
    if risk == "low_risk_score":
        return "low_risk_score", f"risk_score={row.get('risk_score') or '-'}"
    if "mmp=none" in evidence or ("confidence=" in evidence and any(token in evidence for token in ["confidence=0", "confidence=1", "confidence=2", "confidence=3", "confidence=4"])):
        return "thin_evidence", row.get("evidence_strength") or "thin evidence"
    if local_status in {"blocked", "needs_follow_up"}:
        return f"local_{local_status}", f"local_status={local_status}"
    if local_status in {"pending_review", "unreviewed"}:
        return "local_pending_review", f"local_status={local_status}"
    if packet_status == "pending_review":
        return "packet_pending_review", "packet review status is pending"
    if not reviewer and local_status not in {"", "pending_review", "unreviewed"}:
        return "unassigned_reviewer", "local decision exists without reviewer attribution"
    return "manual_review", "manual review attention"


def _card(card_id: str, label: str, status: str, value: object, details: str, next_action: str) -> dict[str, Any]:
    return {
        "card_id": card_id,
        "label": label,
        "status": status,
        "value": value,
        "details": details,
        "next_action": next_action,
    }


def build_candidate_review_analytics(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    board_path: str | Path | None = None,
    ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = Path("data/projects") / project_name
    board = _read_json(_resolve(root_path, board_path or project_dir / "candidate_review_board.json"))
    ledger = _read_json(_resolve(root_path, ledger_path or project_dir / "candidate_review_status_ledger.json"))
    rows = list(board.get("rows") or [])
    now = datetime.now(timezone.utc)
    board_age = _age_hours(board.get("created_at"), now)
    site_counts = Counter(str(row.get("site_class") or "unknown") for row in rows)
    status_counts = Counter(str(row.get("local_review_status") or "unknown") for row in rows)
    risk_counts = Counter(str(row.get("risk_bucket") or "unknown") for row in rows)
    reviewer_counts = Counter(str(row.get("reviewer") or "unassigned") for row in rows if str(row.get("local_review_status") or "") not in {"", "pending_review", "unreviewed"})
    pending_rows = [row for row in rows if _needs_attention(row)]
    site_pending: dict[str, int] = defaultdict(int)
    pending_reason_counts: Counter[str] = Counter()
    pending_reason_sites: dict[str, Counter[str]] = defaultdict(Counter)
    pending_reason_samples: dict[str, list[str]] = defaultdict(list)
    pending_reason_details: dict[str, list[str]] = defaultdict(list)
    for row in pending_rows:
        site = str(row.get("site_class") or "unknown")
        reason, detail = _pending_reason(row)
        site_pending[site] += 1
        pending_reason_counts[reason] += 1
        pending_reason_sites[reason][site] += 1
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id and len(pending_reason_samples[reason]) < 5:
            pending_reason_samples[reason].append(candidate_id)
        if detail and len(pending_reason_details[reason]) < 3:
            pending_reason_details[reason].append(detail)
    analytics_rows = []
    for reason, count in pending_reason_counts.most_common():
        dominant_site = (pending_reason_sites[reason].most_common(1) or [("unknown", 0)])[0][0]
        samples = ",".join(pending_reason_samples[reason]) or "-"
        detail = "; ".join(pending_reason_details[reason]) or reason
        analytics_rows.append(
            {
                "row_type": "pending_reason_cluster",
                "key": reason,
                "status": "needs_attention",
                "value": count,
                "secondary": dominant_site,
                "details": f"rows={count}; site={dominant_site}; samples={samples}; {detail}",
                "filter_type": "pending_reason",
                "filter_value": reason,
            }
        )
    for site, count in sorted(site_counts.items()):
        pending = site_pending.get(site, 0)
        analytics_rows.append(
            {
                "row_type": "site_class_coverage",
                "key": site,
                "status": "needs_attention" if pending else "ready",
                "value": count,
                "secondary": pending,
                "details": f"rows={count}; pending_or_risk={pending}",
                "filter_type": "site_class",
                "filter_value": site,
            }
        )
    for risk, count in sorted(risk_counts.items()):
        analytics_rows.append(
            {
                "row_type": "risk_bucket",
                "key": risk,
                "status": "needs_attention" if risk not in {"clear", "unknown", ""} and count else "ready",
                "value": count,
                "secondary": "",
                "details": f"risk_bucket={risk}; rows={count}",
                "filter_type": "risk_bucket",
                "filter_value": risk,
            }
        )
    for reviewer, count in sorted(reviewer_counts.items()):
        analytics_rows.append(
            {
                "row_type": "reviewer_workload",
                "key": reviewer,
                "status": "ready",
                "value": count,
                "secondary": "",
                "details": f"local reviewed rows={count}",
                "filter_type": "reviewer",
                "filter_value": reviewer,
            }
        )
    pending_count = len(pending_rows)
    repeated_risk_count = sum(count for risk, count in risk_counts.items() if risk not in {"clear", "unknown", ""})
    ledger_decision_count = int(ledger.get("decision_count") or 0)
    cards = [
        _card(
            "pending_backlog",
            "Pending review backlog",
            "needs_attention" if pending_count else "ready",
            pending_count,
            f"focused={board.get('focused_row_count')}; board_age_hours={board_age}",
            "Clear pending, needs-follow-up, blocked, and risk rows in the review board.",
        ),
        _card(
            "pending_reason_clusters",
            "Pending reason clusters",
            "needs_attention" if pending_reason_counts else "ready",
            len(pending_reason_counts),
            f"reason_counts={dict(pending_reason_counts.most_common())}",
            "Pick the largest reason cluster and open its first evidence packet before batch status changes.",
        ),
        _card(
            "site_class_coverage",
            "Site-class coverage",
            "needs_attention" if any(row["secondary"] for row in analytics_rows if row["row_type"] == "site_class_coverage") else "ready",
            len(site_counts),
            f"site_counts={dict(site_counts.most_common())}",
            "Check site classes with pending rows before accepting a local priority list.",
        ),
        _card(
            "repeated_risk_buckets",
            "Repeated risk buckets",
            "needs_attention" if repeated_risk_count else "ready",
            repeated_risk_count,
            f"risk_counts={dict(risk_counts.most_common())}",
            "Review non-clear risk buckets and decide whether to defer, watch, or reject.",
        ),
        _card(
            "reviewer_workload",
            "Reviewer workload",
            "ready",
            sum(reviewer_counts.values()),
            f"reviewers={dict(reviewer_counts.most_common())}; ledger_decisions={ledger_decision_count}",
            "Use this as local review throughput context only.",
        ),
    ]
    cards[0]["filter_type"] = "attention"
    cards[0]["filter_value"] = "attention"
    cards[1]["filter_type"] = "pending_reason"
    cards[1]["filter_value"] = next(iter(pending_reason_counts), "all")
    cards[2]["filter_type"] = "attention" if pending_count else "all"
    cards[2]["filter_value"] = "attention" if pending_count else "all"
    cards[3]["filter_type"] = "risk_bucket"
    cards[3]["filter_value"] = "non_clear"
    cards[4]["filter_type"] = "reviewer"
    cards[4]["filter_value"] = "all"
    return {
        "created_at": now.isoformat(),
        "status": "ready" if rows else "missing_review_board",
        "mode": "local_candidate_review_analytics",
        "project_name": project_name,
        "row_count": len(analytics_rows),
        "candidate_row_count": len(rows),
        "pending_backlog_count": pending_count,
        "repeated_risk_bucket_count": repeated_risk_count,
        "site_class_count": len(site_counts),
        "reviewer_count": len(reviewer_counts),
        "pending_reason_cluster_count": len(pending_reason_counts),
        "ledger_decision_count": ledger_decision_count,
        "board_age_hours": board_age,
        "site_class_counts": dict(site_counts.most_common()),
        "local_status_counts": dict(status_counts.most_common()),
        "risk_bucket_counts": dict(risk_counts.most_common()),
        "pending_reason_counts": dict(pending_reason_counts.most_common()),
        "reviewer_counts": dict(reviewer_counts.most_common()),
        "cards": cards,
        "rows": analytics_rows,
        "recommended_next_actions": [
            "Use analytics to prioritize manual review-board work, not to auto-promote candidates.",
            "Open evidence for the largest pending reason cluster before applying local batch status changes.",
            "Resolve repeated non-clear risk buckets before pinning a new candidate baseline.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_candidate_review_analytics_markdown(report: dict) -> str:
    lines = [
        "# Candidate Review Analytics",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Pending backlog: `{report.get('pending_backlog_count')}`",
        f"- Pending reason clusters: `{report.get('pending_reason_cluster_count')}`",
        "",
        "| Card | Status | Value | Details | Next Action |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in report.get("cards") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("label") or ""),
                    str(row.get("status") or ""),
                    str(row.get("value") or ""),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_review_analytics(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REVIEW_ANALYTICS_JSON,
    csv_path: str | Path | None = DEFAULT_REVIEW_ANALYTICS_CSV,
    markdown_path: str | Path | None = DEFAULT_REVIEW_ANALYTICS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        fields = ["row_type", "key", "status", "value", "secondary", "details", "filter_type", "filter_value"]
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_review_analytics_markdown(report), encoding="utf-8")
