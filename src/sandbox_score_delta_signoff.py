from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PACKET_JSON = Path("data/projects/demo/sandbox_score_delta_review_packet.json")
DEFAULT_DECISION_TEMPLATE_CSV = Path("data/projects/demo/sandbox_score_delta_review_decisions.csv")
DEFAULT_LEDGER_JSON = Path("data/projects/demo/sandbox_score_delta_signoff_ledger.json")
DEFAULT_LEDGER_CSV = Path("data/projects/demo/sandbox_score_delta_signoff_ledger.csv")
DEFAULT_LEDGER_MD = Path("docs/sandbox_score_delta_signoff_ledger.md")
VALID_DECISIONS = {"approved", "deferred", "rejected"}


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _decision_rows_from_packet(packet: dict, *, decision: str, reviewer: str, note: str) -> list[dict[str, str]]:
    decision_value = decision.strip().lower()
    rows = []
    reviewed_at = datetime.now(timezone.utc).isoformat()
    for row in packet.get("rows") or []:
        if row.get("operator_signoff_required") is not True:
            continue
        rows.append(
            {
                "review_id": str(row.get("review_id") or ""),
                "candidate_id": str(row.get("candidate_id") or ""),
                "risk_bucket": str(row.get("risk_bucket") or ""),
                "score_delta": str(row.get("score_delta") or ""),
                "rank_delta": str(row.get("rank_delta") or ""),
                "operator_decision": decision_value,
                "operator": reviewer,
                "operator_note": note,
                "reviewed_at": reviewed_at,
            }
        )
    return rows


def _template_recommendation(row: dict) -> tuple[bool, str, str]:
    risk = str(row.get("risk_bucket") or "")
    review_status = str(row.get("review_status") or "")
    try:
        score_delta = abs(float(row.get("score_delta") or 0.0))
    except (TypeError, ValueError):
        score_delta = 0.0
    try:
        rank_delta = abs(float(row.get("rank_delta") or 0.0))
    except (TypeError, ValueError):
        rank_delta = 0.0
    eligible = risk in {"no_material_delta", "minor_delta_review"} and score_delta <= 1.0 and rank_delta <= 1.0
    if review_status in {"deferred_holdout", "rejected_holdout"}:
        return False, "deferred", "Existing operator signoff is a holdout; keep deferred unless a reviewer overrides."
    if eligible:
        return True, "approved", "Low score/rank movement; reviewer may approve after checking candidate context."
    return False, "deferred", "Material score/rank movement or review risk; keep deferred until chemist review."


def write_sandbox_score_delta_decision_template(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    csv_path: str | Path = DEFAULT_DECISION_TEMPLATE_CSV,
) -> dict[str, Any]:
    root_path = Path(root)
    packet = _read_json(root_path / "data" / "projects" / project_name / "sandbox_score_delta_review_packet.json")
    rows = []
    for row in packet.get("rows") or []:
        eligible, recommended, reason = _template_recommendation(row)
        rows.append(
            {
                "review_id": row.get("review_id", ""),
                "candidate_id": row.get("candidate_id", ""),
                "risk_bucket": row.get("risk_bucket", ""),
                "score_delta": row.get("score_delta", ""),
                "rank_delta": row.get("rank_delta", ""),
                "production_approval_eligible": eligible,
                "recommended_decision": recommended,
                "recommendation_reason": reason,
                "operator_decision": "",
                "operator": "",
                "operator_note": "",
                "reviewed_at": "",
            }
        )
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "review_id",
        "candidate_id",
        "risk_bucket",
        "score_delta",
        "rank_delta",
        "production_approval_eligible",
        "recommended_decision",
        "recommendation_reason",
        "operator_decision",
        "operator",
        "operator_note",
        "reviewed_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "template_written",
        "mode": "sandbox_score_delta_decision_template",
        "row_count": len(rows),
        "csv_path": str(path),
    }


def build_sandbox_score_delta_signoff_ledger(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    decisions_csv: str | Path | None = None,
    decision: str | None = None,
    reviewer: str = "",
    note: str = "",
) -> dict[str, Any]:
    root_path = Path(root)
    packet = _read_json(root_path / "data" / "projects" / project_name / "sandbox_score_delta_review_packet.json")
    if decision:
        raw_rows = _decision_rows_from_packet(packet, decision=decision, reviewer=reviewer, note=note)
    else:
        raw_rows = _read_csv(decisions_csv or root_path / DEFAULT_DECISION_TEMPLATE_CSV)

    packet_rows = {str(row.get("review_id") or ""): row for row in packet.get("rows") or []}
    rows: list[dict[str, Any]] = []
    invalid_rows = 0
    missing_packet_rows = 0
    for index, raw in enumerate(raw_rows, start=1):
        review_id = str(raw.get("review_id") or "").strip()
        packet_row = packet_rows.get(review_id)
        decision_value = str(raw.get("operator_decision") or "").strip().lower()
        valid = decision_value in VALID_DECISIONS
        if not valid:
            invalid_rows += 1
        if not packet_row:
            missing_packet_rows += 1
        rows.append(
            {
                "ledger_id": f"SSDL-{index:04d}",
                "review_id": review_id,
                "candidate_id": str(raw.get("candidate_id") or (packet_row or {}).get("candidate_id") or ""),
                "risk_bucket": str(raw.get("risk_bucket") or (packet_row or {}).get("risk_bucket") or ""),
                "score_delta": raw.get("score_delta") or (packet_row or {}).get("score_delta", ""),
                "rank_delta": raw.get("rank_delta") or (packet_row or {}).get("rank_delta", ""),
                "operator_decision": decision_value,
                "operator": str(raw.get("operator") or reviewer or ""),
                "operator_note": str(raw.get("operator_note") or note or ""),
                "reviewed_at": str(raw.get("reviewed_at") or datetime.now(timezone.utc).isoformat()),
                "valid_decision": valid,
                "packet_row_found": bool(packet_row),
                "production_scoring_approved": valid and decision_value == "approved",
                "production_scoring_affected": False,
            }
        )

    required_ids = {
        str(row.get("review_id") or "")
        for row in packet.get("rows") or []
        if row.get("operator_signoff_required") is True
    }
    decided_ids = {
        str(row.get("review_id") or "")
        for row in rows
        if row.get("valid_decision") and row.get("packet_row_found")
    }
    pending_ids = sorted(required_ids - decided_ids)
    decision_counts = Counter(str(row.get("operator_decision") or "") for row in rows if row.get("valid_decision"))
    status = "blocked" if invalid_rows or missing_packet_rows else "pending_signoff" if pending_ids else "reviewed"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "sandbox_score_delta_signoff_ledger",
        "project_name": project_name,
        "row_count": len(rows),
        "required_signoff_count": len(required_ids),
        "completed_signoff_count": len(decided_ids),
        "pending_signoff_count": len(pending_ids),
        "approved_count": decision_counts.get("approved", 0),
        "deferred_count": decision_counts.get("deferred", 0),
        "rejected_count": decision_counts.get("rejected", 0),
        "invalid_row_count": invalid_rows,
        "missing_packet_row_count": missing_packet_rows,
        "decision_counts": dict(decision_counts.most_common()),
        "pending_review_ids": pending_ids,
        "production_scoring_approved": bool(required_ids and len(required_ids) == decision_counts.get("approved", 0)),
        "production_scoring_affected": False,
        "rows": rows,
        "recommended_next_actions": [
            "Use approved only when a reviewer explicitly accepts staged score/rank impact.",
            "Use deferred or rejected to complete signoff while keeping staged data out of production scoring.",
        ],
    }


def render_sandbox_score_delta_signoff_ledger_markdown(report: dict) -> str:
    lines = [
        "# Sandbox Score Delta Signoff Ledger",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Required / completed: `{report.get('required_signoff_count')}` / `{report.get('completed_signoff_count')}`",
        f"- Production scoring approved: `{report.get('production_scoring_approved')}`",
        "",
        "| Review | Candidate | Decision | Operator | Valid | Note |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("review_id") or ""),
                    str(row.get("candidate_id") or ""),
                    str(row.get("operator_decision") or ""),
                    str(row.get("operator") or ""),
                    str(row.get("valid_decision")),
                    str(row.get("operator_note") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_sandbox_score_delta_signoff_ledger(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_LEDGER_JSON,
    csv_path: str | Path | None = DEFAULT_LEDGER_CSV,
    markdown_path: str | Path | None = DEFAULT_LEDGER_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "ledger_id",
        "review_id",
        "candidate_id",
        "risk_bucket",
        "score_delta",
        "rank_delta",
        "operator_decision",
        "operator",
        "operator_note",
        "reviewed_at",
        "valid_decision",
        "packet_row_found",
        "production_scoring_approved",
        "production_scoring_affected",
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
        md_file.write_text(render_sandbox_score_delta_signoff_ledger_markdown(report), encoding="utf-8")
