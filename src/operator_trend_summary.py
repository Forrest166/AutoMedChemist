from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OPERATOR_TREND_JSON = Path("data/releases/operator_trend_summary.json")
DEFAULT_OPERATOR_TREND_CSV = Path("data/releases/operator_trend_summary.csv")
DEFAULT_OPERATOR_TREND_MD = Path("docs/operator_trend_summary.md")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _status_for_attention(value: int) -> str:
    return "needs_attention" if value > 0 else "ready"


def _card(card_id: str, label: str, status: str, value: object, trend: object, details: str, next_action: str) -> dict[str, Any]:
    return {
        "card_id": card_id,
        "label": label,
        "status": status,
        "value": value,
        "trend": trend,
        "details": details,
        "next_action": next_action,
    }


def build_operator_trend_summary(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    dashboard_history = _read_json(root_path / "data/releases/production_dashboard_trend_history.json")
    db_trend = _read_json(root_path / "data/releases/local_db_maintenance_trend_history.json")
    db_release_gate = _read_json(root_path / "data/releases/local_db_maintenance_release_gate.json")
    review_board = _read_json(project_dir / "candidate_review_board.json")
    review_analytics = _read_json(project_dir / "candidate_review_analytics.json")
    visual = _read_json(project_dir / "candidate_visual_compare.json")
    drilldown = _read_json(project_dir / "candidate_drilldown_packet.json")
    baseline = _read_json(project_dir / "candidate_baseline_compare.json")
    decision = _read_json(project_dir / "candidate_decision_packet.json")
    evidence_quality = _read_json(project_dir / "evidence_quality_scorecard.json")
    reviewer_ops = _read_json(project_dir / "reviewer_operations.json")
    baseline_lineage = _read_json(project_dir / "baseline_lineage_compare.json")
    review_command_center = _read_json(project_dir / "review_command_center.json")
    review_remediation = _read_json(project_dir / "candidate_remediation_queue.json") or _read_json(project_dir / "review_remediation_queue.json")
    baseline_history = _read_json(project_dir / "baseline_history_explorer.json") or _read_json(project_dir / "baseline_lineage_history.json")
    latest = dashboard_history.get("latest") or {}
    previous_rows = dashboard_history.get("rows") or []
    previous = previous_rows[-2] if len(previous_rows) >= 2 else {}
    review_pending = _int(review_board.get("pending_local_review_count", latest.get("candidate_review_board_pending_count")))
    previous_pending = _int(previous.get("candidate_review_board_pending_count"), review_pending)
    analytics_pending = _int(review_analytics.get("pending_backlog_count"), review_pending)
    analytics_risk = _int(review_analytics.get("repeated_risk_bucket_count"))
    baseline_changed = _int(baseline.get("changed_candidate_count", latest.get("candidate_baseline_changed_count")))
    previous_baseline_changed = _int(previous.get("candidate_baseline_changed_count"), baseline_changed)
    latest_db = db_trend.get("latest") or {}
    db_warn = _int(latest_db.get("warn_count"))
    db_release_stop = _int(db_release_gate.get("release_stop_count"))
    db_watch = _int(db_release_gate.get("watch_count"), db_warn)
    max_latency = latest_db.get("max_latency_ms", "")
    decision_counts = decision.get("decision_counts") or {}
    needs_decision_attention = _int(decision_counts.get("watch")) + _int(decision_counts.get("needs_measurement")) + _int(decision_counts.get("reject"))
    packet_ready = sum(
        1
        for payload in [visual, drilldown, decision]
        if payload.get("status") == "ready"
    )
    evidence_quality_attention = _int(evidence_quality.get("attention_count")) + _int(evidence_quality.get("watch_count"))
    reviewer_ops_attention = (
        _int(reviewer_ops.get("pending_overdue_count"))
        + _int(reviewer_ops.get("repeated_defer_reason_count"))
        + _int(reviewer_ops.get("low_site_class_closure_count"))
    )
    lineage_movement = (
        _int(baseline_lineage.get("entered_candidate_count"))
        + _int(baseline_lineage.get("exited_candidate_count"))
        + _int(baseline_lineage.get("changed_candidate_count"))
    )
    command_actionable = _int(review_command_center.get("actionable_count"))
    remediation_high = _int(review_remediation.get("high_count", review_remediation.get("high_priority_count")))
    cards = [
        _card(
            "candidate_review_backlog",
            "Candidate review backlog",
            _status_for_attention(analytics_pending),
            analytics_pending,
            analytics_pending - previous_pending,
            f"pending_local={review_pending}; analytics_pending={analytics_pending}; risk_rows={analytics_risk}; focused={review_board.get('focused_row_count')}; rows={review_board.get('filtered_row_count')}",
            "Work focused review-board rows before accepting candidate priority movement.",
        ),
        _card(
            "review_analytics_risk",
            "Review analytics risk",
            _status_for_attention(analytics_risk),
            analytics_risk,
            "",
            f"analytics_status={review_analytics.get('status')}; site_classes={review_analytics.get('site_class_count')}; reviewers={review_analytics.get('reviewer_count')}; board_age_hours={review_analytics.get('board_age_hours')}",
            "Use review analytics to prioritize risk buckets and reviewer workload before pinning baselines.",
        ),
        _card(
            "candidate_decision_mix",
            "Candidate decision mix",
            _status_for_attention(needs_decision_attention),
            decision.get("decision_count", 0),
            needs_decision_attention,
            f"counts={decision_counts}",
            "Clear watch/needs-measurement/reject rows or leave them explicitly documented.",
        ),
        _card(
            "baseline_movement",
            "Baseline movement",
            _status_for_attention(baseline_changed),
            baseline_changed,
            baseline_changed - previous_baseline_changed,
            f"baseline={baseline.get('baseline_id')}; added={baseline.get('added_candidate_count')}; removed={baseline.get('removed_candidate_count')}; max_score_delta={baseline.get('max_abs_score_delta')}",
            "Inspect candidate baseline changes before pinning a new local baseline.",
        ),
        _card(
            "evidence_quality_scorecard",
            "Evidence quality scorecard",
            _status_for_attention(evidence_quality_attention),
            evidence_quality.get("row_count", 0),
            evidence_quality_attention,
            f"status={evidence_quality.get('status')}; attention={evidence_quality.get('attention_count')}; watch={evidence_quality.get('watch_count')}; flags={evidence_quality.get('flag_counts')}",
            "Use attention/watch evidence quality rows to focus manual candidate review.",
        ),
        _card(
            "reviewer_operations",
            "Reviewer operations",
            _status_for_attention(reviewer_ops_attention),
            reviewer_ops.get("candidate_row_count", 0),
            reviewer_ops_attention,
            f"status={reviewer_ops.get('status')}; overdue={reviewer_ops.get('pending_overdue_count')}; repeated_defer={reviewer_ops.get('repeated_defer_reason_count')}; low_closure={reviewer_ops.get('low_site_class_closure_count')}",
            "Route overdue or repeatedly deferred review rows before discussion handoff.",
        ),
        _card(
            "baseline_lineage",
            "Baseline lineage",
            _status_for_attention(lineage_movement),
            lineage_movement,
            baseline_lineage.get("max_abs_score_delta", ""),
            f"status={baseline_lineage.get('status')}; base={baseline_lineage.get('base_baseline_id')}; head={baseline_lineage.get('head_baseline_id')}; counts={baseline_lineage.get('lineage_status_counts')}",
            "Inspect entered, exited, and changed candidates before pinning another baseline.",
        ),
        _card(
            "review_command_center",
            "Review command center",
            _status_for_attention(command_actionable),
            review_command_center.get("row_count", 0),
            command_actionable,
            f"status={review_command_center.get('status')}; actionable={review_command_center.get('actionable_count')}; types={review_command_center.get('row_type_counts')}",
            "Use command rows to jump from production gates into native review filters or linked artifacts.",
        ),
        _card(
            "candidate_remediation_queue",
            "Candidate remediation queue",
            _status_for_attention(remediation_high),
            review_remediation.get("open_count", 0),
            remediation_high,
            f"status={review_remediation.get('status')}; high={review_remediation.get('high_count', review_remediation.get('high_priority_count'))}; medium={review_remediation.get('medium_count', review_remediation.get('medium_priority_count'))}; history_rows={baseline_history.get('row_count')}",
            "Close high-priority local remediation tasks before discussion handoff or baseline pinning.",
        ),
        _card(
            "review_remediation_queue",
            "Review remediation queue",
            _status_for_attention(remediation_high),
            review_remediation.get("open_count", 0),
            remediation_high,
            f"status={review_remediation.get('status')}; high={review_remediation.get('high_count', review_remediation.get('high_priority_count'))}; medium={review_remediation.get('medium_count', review_remediation.get('medium_priority_count'))}; history_rows={baseline_history.get('row_count')}",
            "Close high-priority local remediation tasks before discussion handoff or baseline pinning.",
        ),
        _card(
            "db_latency",
            "Local DB latency",
            _status_for_attention(db_release_stop),
            max_latency,
            db_watch,
            f"trend_rows={db_trend.get('row_count')}; latest={latest_db.get('status')}; release_stop={db_release_stop}; watch={db_watch}; warnings={db_warn}",
            "Fix release-stop DB issues before release; keep latency-only warnings as operator watch items.",
        ),
        _card(
            "packet_coverage",
            "Candidate packet coverage",
            "ready" if packet_ready == 3 else "needs_attention",
            packet_ready,
            "",
            f"visual={visual.get('status')}; drilldown={drilldown.get('status')}; decision={decision.get('status')}",
            "Rebuild visual, drill-down, and decision packets after candidate generation or review updates.",
        ),
        _card(
            "production_gate_trend",
            "Production gate trend",
            "ready" if latest.get("dashboard_status") == "pass" and not _int(latest.get("warn_count")) else "needs_attention",
            latest.get("dashboard_status", "missing"),
            latest.get("warn_count", ""),
            f"history_rows={dashboard_history.get('row_count')}; fail_count={latest.get('fail_count')}; warn_count={latest.get('warn_count')}",
            "Use production dashboard rows as the release-stop list when warnings or failures return.",
        ),
    ]
    attention_count = sum(1 for row in cards if row["status"] == "needs_attention")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "mode": "operator_trend_summary",
        "project_name": project_name,
        "card_count": len(cards),
        "needs_attention_count": attention_count,
        "cards": cards,
        "recommended_next_actions": [
            "Use these compact cards for operator-facing weekly summaries.",
            "Keep detailed provenance in the linked JSON/CSV artifacts, not in the trend cards.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_operator_trend_summary_markdown(report: dict) -> str:
    lines = [
        "# Operator Trend Summary",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Needs attention: `{report.get('needs_attention_count')}`",
        "",
        "| Card | Status | Value | Trend | Details | Next Action |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report.get("cards") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("label") or ""),
                    str(row.get("status") or ""),
                    str(row.get("value") or ""),
                    str(row.get("trend") or ""),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_operator_trend_summary(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_OPERATOR_TREND_JSON,
    csv_path: str | Path | None = DEFAULT_OPERATOR_TREND_CSV,
    markdown_path: str | Path | None = DEFAULT_OPERATOR_TREND_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        fields = ["card_id", "label", "status", "value", "trend", "details", "next_action"]
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("cards") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_operator_trend_summary_markdown(report), encoding="utf-8")
