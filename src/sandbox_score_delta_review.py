from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SANDBOX_SCORE_DELTA_REVIEW_JSON = Path("data/projects/demo/sandbox_score_delta_review_packet.json")
DEFAULT_SANDBOX_SCORE_DELTA_REVIEW_CSV = Path("data/projects/demo/sandbox_score_delta_review_packet.csv")
DEFAULT_SANDBOX_SCORE_DELTA_REVIEW_MD = Path("docs/sandbox_score_delta_review_packet.md")
DEFAULT_SANDBOX_SCORE_DELTA_SIGNOFF_LEDGER_JSON = Path("data/projects/demo/sandbox_score_delta_signoff_ledger.json")
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


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _risk_bucket(delta: float, rank_delta: float, matches: int, staged_rows: int) -> str:
    if staged_rows <= 0:
        return "awaiting_staged_rows"
    if abs(delta) >= 2.0 or abs(rank_delta) >= 3 or matches >= 5:
        return "material_delta_review"
    if abs(delta) >= 0.5 or matches:
        return "minor_delta_review"
    return "no_material_delta"


def _ledger_by_review_id(ledger: dict) -> dict[str, dict[str, Any]]:
    rows = {}
    for row in ledger.get("rows") or []:
        review_id = str(row.get("review_id") or "").strip()
        if review_id:
            rows[review_id] = row
    return rows


def _review_status(staged_rows: int, signoff_required: bool, decision: str) -> str:
    if staged_rows <= 0:
        return "awaiting_staged_rows"
    if not signoff_required:
        return "no_signoff_required"
    if decision == "approved":
        return "approved"
    if decision in {"deferred", "rejected"}:
        return f"{decision}_holdout"
    return "pending_operator_signoff"


def build_sandbox_score_delta_review_packet(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    sandbox = _read_json(project_dir / "staged_feed_sandbox_scoring.json")
    budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    ledger = _read_json(root_path / "data" / "projects" / project_name / DEFAULT_SANDBOX_SCORE_DELTA_SIGNOFF_LEDGER_JSON.name)
    ledger_rows = _ledger_by_review_id(ledger)
    staged_rows = _int(sandbox.get("staged_row_count"))
    budget_blockers = _int(budget.get("blocker_count")) or _int(budget.get("blocked_source_count"))
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(sandbox.get("rows") or [], start=1):
        review_id = f"SSDR-{index:04d}"
        delta = _float(source.get("sandbox_score_delta_preview"))
        rank_delta = _float(source.get("sandbox_rank_delta_preview"))
        matches = _int(source.get("matching_staged_rule_count"))
        risk = _risk_bucket(delta, rank_delta, matches, staged_rows)
        signoff_required = staged_rows > 0 and risk in {"material_delta_review", "minor_delta_review", "no_material_delta"}
        decision_row = ledger_rows.get(review_id, {})
        decision = str(decision_row.get("operator_decision") or "").strip().lower()
        if decision not in {"approved", "deferred", "rejected"}:
            decision = ""
        review_status = _review_status(staged_rows, signoff_required, decision)
        rows.append(
            {
                "review_id": review_id,
                "candidate_id": source.get("candidate_id", ""),
                "review_status": review_status,
                "risk_bucket": risk,
                "base_score": source.get("base_score", 0),
                "sandbox_score_preview": source.get("sandbox_score_preview", 0),
                "score_delta": delta,
                "base_rank": source.get("base_rank", ""),
                "sandbox_rank_preview": source.get("sandbox_rank_preview", ""),
                "rank_delta": rank_delta,
                "matching_staged_rule_count": matches,
                "matched_replacement_ids": source.get("matched_replacement_ids", ""),
                "matrix_bucket": source.get("matrix_bucket", ""),
                "qa_bucket": source.get("qa_bucket", ""),
                "baseline_lineage_status": source.get("baseline_lineage_status", ""),
                "operator_signoff_required": signoff_required,
                "operator_decision": decision,
                "operator": decision_row.get("operator", ""),
                "operator_note": decision_row.get("operator_note", ""),
                "operator_reviewed_at": decision_row.get("reviewed_at", ""),
                "production_scoring_approved": decision == "approved",
                "production_scoring_affected": False,
                "next_action": (
                    "Fill governed staged rows before score-delta signoff."
                    if staged_rows <= 0
                    else "Operator approved this sandbox score delta for promotion review."
                    if decision == "approved"
                    else "Operator signed off as holdout; keep staged data out of production scoring."
                    if decision in {"deferred", "rejected"}
                    else "Operator must approve, defer, or reject this sandbox score delta before production smoke passes."
                ),
            }
        )
    risk_counts = Counter(str(row.get("risk_bucket") or "") for row in rows)
    signoff_required_count = sum(1 for row in rows if row.get("operator_signoff_required") is True)
    approved_count = sum(1 for row in rows if str(row.get("operator_decision") or "").lower() == "approved")
    deferred_count = sum(1 for row in rows if str(row.get("operator_decision") or "").lower() == "deferred")
    rejected_count = sum(1 for row in rows if str(row.get("operator_decision") or "").lower() == "rejected")
    completed_count = approved_count + deferred_count + rejected_count
    pending_count = max(0, signoff_required_count - completed_count)
    if budget_blockers:
        status = "blocked"
    elif staged_rows <= 0:
        status = "awaiting_staged_rows"
    elif pending_count:
        status = "review_required"
    elif approved_count == signoff_required_count and signoff_required_count > 0:
        status = "approved"
    else:
        status = "reviewed_holdout"
    production_scoring_approved = bool(staged_rows > 0 and signoff_required_count > 0 and approved_count == signoff_required_count and not budget_blockers)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "sandbox_score_delta_review_packet",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_count": len(rows),
        "staged_row_count": staged_rows,
        "budget_status": budget.get("status") or "missing",
        "budget_blocker_count": budget_blockers,
        "operator_signoff_required_count": signoff_required_count,
        "completed_signoff_count": completed_count,
        "approved_signoff_count": approved_count,
        "deferred_signoff_count": deferred_count,
        "rejected_signoff_count": rejected_count,
        "pending_signoff_count": pending_count,
        "operator_signoff_complete": bool(signoff_required_count == 0 or pending_count == 0),
        "signoff_ledger_status": ledger.get("status") or "missing",
        "material_delta_count": risk_counts.get("material_delta_review", 0),
        "minor_delta_count": risk_counts.get("minor_delta_review", 0),
        "risk_bucket_counts": dict(risk_counts.most_common()),
        "max_abs_score_delta": max([abs(_float(row.get("score_delta"))) for row in rows] or [0.0]),
        "max_abs_rank_delta": max([abs(_float(row.get("rank_delta"))) for row in rows] or [0.0]),
        "production_scoring_approved": production_scoring_approved,
        "production_scoring_affected": False,
        "allowed_to_promote": production_scoring_approved,
        "rows": rows,
        "recommended_next_actions": [
            "Use this packet for operator review before staged feed rows are promoted into rank-affecting data.",
            "Keep production scoring unchanged until staged rows pass quality budget and all required score deltas are approved.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_sandbox_score_delta_review_markdown(report: dict) -> str:
    lines = [
        "# Sandbox Score Delta Review Packet",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Staged rows: `{report.get('staged_row_count')}`",
        f"- Production scoring approved: `{report.get('production_scoring_approved')}`",
        "",
        "| Review | Candidate | Status | Risk | Base | Sandbox | Delta | Rank Delta | Matches | Next Action |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("review_id") or ""),
                    str(row.get("candidate_id") or ""),
                    str(row.get("review_status") or ""),
                    str(row.get("risk_bucket") or ""),
                    str(row.get("base_score") or 0),
                    str(row.get("sandbox_score_preview") or 0),
                    str(row.get("score_delta") or 0),
                    str(row.get("rank_delta") or 0),
                    str(row.get("matching_staged_rule_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_sandbox_score_delta_review_packet(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_SANDBOX_SCORE_DELTA_REVIEW_JSON,
    csv_path: str | Path | None = DEFAULT_SANDBOX_SCORE_DELTA_REVIEW_CSV,
    markdown_path: str | Path | None = DEFAULT_SANDBOX_SCORE_DELTA_REVIEW_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "review_id",
        "candidate_id",
        "review_status",
        "risk_bucket",
        "base_score",
        "sandbox_score_preview",
        "score_delta",
        "base_rank",
        "sandbox_rank_preview",
        "rank_delta",
        "matching_staged_rule_count",
        "matched_replacement_ids",
        "matrix_bucket",
        "qa_bucket",
        "baseline_lineage_status",
        "operator_signoff_required",
        "operator_decision",
        "operator",
        "operator_note",
        "operator_reviewed_at",
        "production_scoring_approved",
        "production_scoring_affected",
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
        md_file.write_text(render_sandbox_score_delta_review_markdown(report), encoding="utf-8")
