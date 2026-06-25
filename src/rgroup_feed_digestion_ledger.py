from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LEDGER_JSON = Path("data/substituents/rgroup_feed_digestion_ledger.json")
DEFAULT_LEDGER_CSV = Path("data/substituents/rgroup_feed_digestion_ledger.csv")
DEFAULT_LEDGER_MD = Path("docs/rgroup_feed_digestion_ledger.md")
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


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _staged_rows(staging_gate: dict) -> list[dict[str, Any]]:
    rows = []
    for gate_row in staging_gate.get("rows") or []:
        path = Path(str(gate_row.get("template_path") or gate_row.get("path") or ""))
        for csv_row in _read_csv(path):
            item = dict(csv_row)
            item["staging_path"] = str(path)
            item["staging_source_dataset"] = gate_row.get("source_dataset") or item.get("source_dataset") or ""
            rows.append(item)
    return rows


def _split_ids(value: object) -> set[str]:
    return {item.strip() for item in str(value or "").split(";") if item.strip()}


def _budget_by_source(budget: dict) -> dict[str, dict]:
    return {
        str(row.get("source_dataset") or ""): row
        for row in budget.get("rows") or []
        if row.get("source_dataset")
    }


def _promotion_by_source(promotion_diff: dict) -> dict[str, dict]:
    return {
        str(row.get("source_dataset") or ""): row
        for row in promotion_diff.get("rows") or []
        if row.get("source_dataset")
    }


def _candidate_matches_by_replacement(sandbox_review: dict) -> dict[str, list[dict]]:
    matches: dict[str, list[dict]] = defaultdict(list)
    for row in sandbox_review.get("rows") or []:
        for replacement_id in _split_ids(row.get("matched_replacement_ids")):
            matches[replacement_id].append(row)
    return matches


def _candidate_impact_bucket(matched_reviews: list[dict]) -> str:
    if not matched_reviews:
        return "no_current_candidate_match"
    decisions = {str(row.get("operator_decision") or "").strip().lower() for row in matched_reviews if row.get("operator_decision")}
    if "rejected" in decisions:
        return "rejected_candidate_impact"
    if "deferred" in decisions:
        return "deferred_candidate_impact"
    if decisions and decisions <= {"approved"}:
        return "approved_candidate_impact"
    return "pending_candidate_impact"


def _digest_status(budget_row: dict, promotion_row: dict, matched_reviews: list[dict]) -> str:
    if budget_row.get("budget_status") == "blocked" or int(budget_row.get("blocker_count") or 0):
        return "held_out_quality_blocker"
    decisions = {str(row.get("operator_decision") or "").strip().lower() for row in matched_reviews if row.get("operator_decision")}
    if "rejected" in decisions:
        return "rejected"
    if "deferred" in decisions:
        return "deferred"
    if matched_reviews and decisions == {"approved"}:
        return "accepted_for_promotion_review"
    if promotion_row.get("diff_status") == "ready_to_promote":
        return "held_out_pending_score_delta_signoff" if matched_reviews else "accepted_no_current_candidate_match"
    return "held_out_pending_gate"


def build_rgroup_feed_digestion_ledger(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    promotion_diff = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    sandbox_review = _read_json(root_path / "data" / "projects" / project_name / "sandbox_score_delta_review_packet.json")
    budget_map = _budget_by_source(budget)
    promotion_map = _promotion_by_source(promotion_diff)
    candidate_matches = _candidate_matches_by_replacement(sandbox_review)
    rows = []
    for index, staged in enumerate(_staged_rows(staging_gate), start=1):
        replacement_id = str(staged.get("replacement_id") or "")
        source_dataset = str(staged.get("source_dataset") or staged.get("staging_source_dataset") or "")
        matched_reviews = candidate_matches.get(replacement_id, [])
        budget_row = budget_map.get(source_dataset, {})
        promotion_row = promotion_map.get(source_dataset, {})
        digest_status = _digest_status(budget_row, promotion_row, matched_reviews)
        rows.append(
            {
                "ledger_id": f"RGDIG-{index:04d}",
                "replacement_id": replacement_id,
                "source_dataset": source_dataset,
                "source_record_id": staged.get("source_record_id", ""),
                "row_sha256": staged.get("row_sha256", ""),
                "replacement_class": staged.get("replacement_class", ""),
                "endpoint_group": staged.get("endpoint_group", ""),
                "direction": staged.get("direction", ""),
                "source_owner": staged.get("source_owner", ""),
                "source_license": staged.get("source_license", ""),
                "source_confidence_tier": staged.get("source_confidence_tier", ""),
                "source_confidence_score": staged.get("source_confidence_score", ""),
                "provenance_review_status": staged.get("provenance_review_status", ""),
                "source_reference": staged.get("source_reference", ""),
                "budget_status": budget_row.get("budget_status", ""),
                "budget_blocker_count": budget_row.get("blocker_count", 0),
                "promotion_diff_status": promotion_row.get("diff_status", ""),
                "matched_candidate_ids": ";".join(str(row.get("candidate_id") or "") for row in matched_reviews),
                "matched_review_ids": ";".join(str(row.get("review_id") or "") for row in matched_reviews),
                "operator_decisions": ";".join(str(row.get("operator_decision") or "") for row in matched_reviews if row.get("operator_decision")),
                "candidate_impact_bucket": _candidate_impact_bucket(matched_reviews),
                "digest_status": digest_status,
                "promoted": False,
                "production_scoring_affected": False,
                "next_action": (
                    "Eligible for explicit promotion review; still blocked from production scoring until promotion is approved."
                    if digest_status == "accepted_for_promotion_review"
                    else "Keep this staged row as reviewed holdout until a reviewer changes the sandbox signoff."
                    if digest_status in {"deferred", "rejected", "held_out_pending_score_delta_signoff"}
                    else "No current candidate impact; retain row-level checksum and source-confidence trail."
                    if digest_status == "accepted_no_current_candidate_match"
                    else "Clear quality or promotion gates before digestion can advance."
                ),
                "staging_path": staged.get("staging_path", ""),
            }
        )
    status_counts = Counter(str(row.get("digest_status") or "") for row in rows)
    blocked_count = status_counts.get("held_out_quality_blocker", 0)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked" if blocked_count else "ready" if rows else "awaiting_rows",
        "mode": "rgroup_feed_digestion_ledger",
        "project_name": project_name,
        "row_count": len(rows),
        "staged_row_count": len(rows),
        "accepted_count": status_counts.get("accepted_for_promotion_review", 0) + status_counts.get("accepted_no_current_candidate_match", 0),
        "deferred_count": status_counts.get("deferred", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "held_out_count": sum(count for status, count in status_counts.items() if status.startswith("held_out")),
        "promoted_count": 0,
        "status_counts": dict(status_counts.most_common()),
        "production_scoring_affected": False,
        "rows": rows,
        "blocked_scopes": BLOCKED_SCOPES,
        "recommended_next_actions": [
            "Use this ledger as the row-level digestion trail before any feed promotion.",
            "Promoted remains false until an explicit promotion command copies staged rows into governed feeds.",
        ],
    }


def render_rgroup_feed_digestion_ledger_markdown(report: dict) -> str:
    lines = [
        "# R-group Feed Digestion Ledger",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "| Row | Replacement | Source | Digest Status | Decision | Matches | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("ledger_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("digest_status") or ""),
                    str(row.get("operator_decisions") or ""),
                    str(row.get("matched_candidate_ids") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_feed_digestion_ledger(
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
        "replacement_id",
        "source_dataset",
        "source_record_id",
        "row_sha256",
        "replacement_class",
        "endpoint_group",
        "direction",
        "source_owner",
        "source_license",
        "source_confidence_tier",
        "source_confidence_score",
        "provenance_review_status",
        "source_reference",
        "budget_status",
        "budget_blocker_count",
        "promotion_diff_status",
        "matched_candidate_ids",
        "matched_review_ids",
        "operator_decisions",
        "candidate_impact_bucket",
        "digest_status",
        "promoted",
        "production_scoring_affected",
        "next_action",
        "staging_path",
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
        md_file.write_text(render_rgroup_feed_digestion_ledger_markdown(report), encoding="utf-8")
