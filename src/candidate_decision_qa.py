from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DECISION_QA_JSON = Path("data/projects/demo/candidate_decision_qa.json")
DEFAULT_DECISION_QA_CSV = Path("data/projects/demo/candidate_decision_qa.csv")
DEFAULT_DECISION_QA_MD = Path("docs/candidate_decision_qa.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _by_candidate(report: dict) -> dict[str, dict]:
    rows = {}
    for row in report.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            rows[candidate_id] = dict(row)
    return rows


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


def _qa_bucket(decision: dict, board: dict, ledger_row: dict, now: datetime) -> tuple[str, str]:
    local_decision = str(decision.get("local_decision") or "").strip()
    confidence = int(float(decision.get("decision_confidence") or 0))
    risk = str(decision.get("risk_bucket") or board.get("risk_bucket") or "").strip()
    board_status = str(board.get("local_review_status") or decision.get("board_status") or "").strip()
    history_count = len(ledger_row.get("history") or [])
    pending_age = _age_days(board.get("reviewed_at") or ledger_row.get("reviewed_at") or decision.get("packet_created_at"), now)
    if local_decision in {"reject", "watch", "needs_measurement"}:
        return "attention_required", f"decision={local_decision}"
    if local_decision == "accept" and board_status not in {"reviewed", "evidence_supported"}:
        return "accept_without_review", f"board_status={board_status or '-'}"
    if confidence < 70:
        return "low_confidence", f"confidence={confidence}"
    if risk and risk != "clear":
        return "risk_review", f"risk={risk}"
    if history_count > 1:
        return "decision_changed", f"history_count={history_count}"
    if pending_age >= 7 and board_status in {"pending_review", "unreviewed", "needs_follow_up"}:
        return "stale_pending", f"pending_age_days={pending_age}"
    return "clear", "local decision has matching review context"


def build_candidate_decision_qa(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    decision = _read_json(project_dir / "candidate_decision_packet.json")
    board = _read_json(project_dir / "candidate_review_board.json")
    ledger = _read_json(project_dir / "candidate_review_status_ledger.json")
    drawer = _read_json(project_dir / "candidate_evidence_drawer.json")
    board_by_id = _by_candidate(board)
    drawer_by_id = _by_candidate(drawer)
    ledger_rows = ledger.get("decisions") or {}
    now = datetime.now(timezone.utc)
    rows = []
    for decision_row in decision.get("rows") or []:
        candidate_id = str(decision_row.get("candidate_id") or "").strip()
        board_row = board_by_id.get(candidate_id, {})
        ledger_row = dict(ledger_rows.get(candidate_id) or {})
        drawer_row = drawer_by_id.get(candidate_id, {})
        qa_bucket, qa_reason = _qa_bucket(decision_row, board_row, ledger_row, now)
        rows.append(
            {
                "candidate_id": candidate_id,
                "local_decision": decision_row.get("local_decision", ""),
                "decision_confidence": decision_row.get("decision_confidence", ""),
                "qa_bucket": qa_bucket,
                "qa_reason": qa_reason,
                "site_class": decision_row.get("site_class") or board_row.get("site_class", ""),
                "risk_bucket": decision_row.get("risk_bucket") or board_row.get("risk_bucket", ""),
                "board_status": board_row.get("local_review_status") or decision_row.get("board_status", ""),
                "reviewer": board_row.get("reviewer") or ledger_row.get("reviewer", ""),
                "reviewed_at": board_row.get("reviewed_at") or ledger_row.get("reviewed_at", ""),
                "pending_age_days": _age_days(board_row.get("reviewed_at") or ledger_row.get("reviewed_at") or decision.get("created_at"), now),
                "history_count": len(ledger_row.get("history") or []),
                "decision_change_history": ";".join(
                    str(item.get("reviewer_decision") or item.get("local_review_status") or "")
                    for item in ledger_row.get("history") or []
                ),
                "baseline_movement": decision_row.get("baseline_movement", ""),
                "evidence_depth_score": decision_row.get("evidence_depth_score") or drawer_row.get("evidence_depth_score", ""),
                "next_action": "Review QA bucket before discussion handoff." if qa_bucket != "clear" else "No QA action required.",
            }
        )
    qa_counts = Counter(str(row.get("qa_bucket") or "") for row in rows)
    decision_counts = Counter(str(row.get("local_decision") or "") for row in rows)
    site_counts = Counter(str(row.get("site_class") or "unknown") for row in rows)
    attention_count = sum(count for bucket, count in qa_counts.items() if bucket != "clear")
    return {
        "created_at": now.isoformat(),
        "status": "ready" if decision.get("status") == "ready" else "missing_decision_packet",
        "mode": "local_candidate_decision_qa",
        "project_name": project_name,
        "row_count": len(rows),
        "attention_count": attention_count,
        "qa_counts": dict(qa_counts.most_common()),
        "decision_counts": dict(decision_counts.most_common()),
        "site_class_counts": dict(site_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Review non-clear QA buckets before using discussion handoffs.",
            "Treat QA findings as local review prompts only.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_decision_qa_markdown(report: dict) -> str:
    lines = [
        "# Candidate Decision QA",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Attention rows: `{report.get('attention_count')}`",
        "",
        "| ID | Decision | QA | Reason | Site | Age | Next Action |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("local_decision") or ""),
                    str(row.get("qa_bucket") or ""),
                    str(row.get("qa_reason") or "").replace("|", "/"),
                    str(row.get("site_class") or ""),
                    str(row.get("pending_age_days") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_decision_qa(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_DECISION_QA_JSON,
    csv_path: str | Path | None = DEFAULT_DECISION_QA_CSV,
    markdown_path: str | Path | None = DEFAULT_DECISION_QA_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "local_decision",
        "decision_confidence",
        "qa_bucket",
        "qa_reason",
        "site_class",
        "risk_bucket",
        "board_status",
        "reviewer",
        "reviewed_at",
        "pending_age_days",
        "history_count",
        "decision_change_history",
        "baseline_movement",
        "evidence_depth_score",
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
        md_file.write_text(render_candidate_decision_qa_markdown(report), encoding="utf-8")
