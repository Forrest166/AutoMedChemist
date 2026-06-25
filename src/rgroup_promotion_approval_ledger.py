from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DECISION_TEMPLATE_CSV = Path("data/substituents/rgroup_promotion_approval_decisions.csv")
DEFAULT_LEDGER_JSON = Path("data/substituents/rgroup_promotion_approval_ledger.json")
DEFAULT_LEDGER_CSV = Path("data/substituents/rgroup_promotion_approval_ledger.csv")
DEFAULT_LEDGER_MD = Path("docs/rgroup_promotion_approval_ledger.md")
VALID_DECISIONS = {"approved", "deferred", "rejected"}
PROMOTION_ELIGIBLE_STATUSES = {"accepted_for_promotion_review", "accepted_no_current_candidate_match"}
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


def _staged_rows(staging_gate: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for gate_row in staging_gate.get("rows") or []:
        path = Path(str(gate_row.get("template_path") or gate_row.get("path") or ""))
        for csv_row in _read_csv(path):
            item = dict(csv_row)
            item["staging_path"] = str(path)
            item["staging_source_dataset"] = str(gate_row.get("source_dataset") or item.get("source_dataset") or "")
            rows.append(item)
    return rows


def _promotion_by_source(promotion_diff: dict) -> dict[str, dict]:
    return {
        str(row.get("source_dataset") or ""): row
        for row in promotion_diff.get("rows") or []
        if row.get("source_dataset")
    }


def _staged_by_key(staging_gate: dict) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in _staged_rows(staging_gate):
        result[(str(row.get("replacement_id") or ""), str(row.get("row_sha256") or ""))] = row
    return result


def _decision_rows_from_ledger(ledger: dict, *, decision: str, reviewer: str, note: str) -> list[dict[str, str]]:
    reviewed_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for row in ledger.get("candidate_rows") or ledger.get("rows") or []:
        rows.append(
            {
                "approval_id": str(row.get("approval_id") or ""),
                "replacement_id": str(row.get("replacement_id") or ""),
                "row_sha256": str(row.get("row_sha256") or ""),
                "source_dataset": str(row.get("source_dataset") or ""),
                "digest_status": str(row.get("digest_status") or ""),
                "promotion_approval_decision": decision.strip().lower(),
                "reviewer": reviewer,
                "review_note": note,
                "reviewed_at": reviewed_at,
            }
        )
    return rows


def _recommended_decision(digest_status: str, provenance_review_status: str, source_confidence_score: object, matched_candidate_ids: str) -> tuple[str, str]:
    try:
        confidence = float(source_confidence_score or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if digest_status not in PROMOTION_ELIGIBLE_STATUSES:
        return "deferred", "Not eligible for promotion while digestion status is held out, deferred, or rejected."
    if provenance_review_status != "accepted":
        return "deferred", "Source provenance has not been accepted by review."
    if matched_candidate_ids:
        return "deferred", "Current candidate impact exists; require explicit chemist review before promotion."
    if confidence < 0.75:
        return "deferred", "Source confidence is below the conservative auto-recommend threshold."
    return "approved", "No current candidate impact, accepted provenance, and high source confidence; reviewer may approve."


def _build_candidate_rows(*, root_path: Path, project_name: str) -> list[dict[str, Any]]:
    staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    promotion_diff = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    digestion = _read_json(root_path / "data/substituents/rgroup_feed_digestion_ledger.json")
    sandbox_signoff = _read_json(root_path / "data" / "projects" / project_name / "sandbox_score_delta_signoff_ledger.json")
    staged_map = _staged_by_key(staging_gate)
    promotion_map = _promotion_by_source(promotion_diff)
    signoff_decisions = Counter(str(row.get("operator_decision") or "") for row in sandbox_signoff.get("rows") or [])

    rows: list[dict[str, Any]] = []
    for index, digest in enumerate(digestion.get("rows") or [], start=1):
        replacement_id = str(digest.get("replacement_id") or "")
        row_sha = str(digest.get("row_sha256") or "")
        staged = staged_map.get((replacement_id, row_sha), {})
        source_dataset = str(digest.get("source_dataset") or staged.get("source_dataset") or staged.get("staging_source_dataset") or "")
        promotion_row = promotion_map.get(source_dataset, {})
        digest_status = str(digest.get("digest_status") or "")
        recommended, reason = _recommended_decision(
            digest_status,
            str(staged.get("provenance_review_status") or digest.get("provenance_review_status") or ""),
            staged.get("source_confidence_score") or digest.get("source_confidence_score"),
            str(digest.get("matched_candidate_ids") or ""),
        )
        promotion_eligible = digest_status in PROMOTION_ELIGIBLE_STATUSES and promotion_row.get("diff_status") == "ready_to_promote"
        rows.append(
            {
                "approval_id": f"RGPROM-{index:04d}",
                "digestion_ledger_id": digest.get("ledger_id", ""),
                "replacement_id": replacement_id,
                "row_sha256": row_sha,
                "source_dataset": source_dataset,
                "source_owner": staged.get("source_owner", ""),
                "source_license": staged.get("source_license", ""),
                "provenance_level": staged.get("provenance_level", ""),
                "provenance_review_status": staged.get("provenance_review_status") or digest.get("provenance_review_status", ""),
                "source_reference": staged.get("source_reference", ""),
                "source_confidence_tier": staged.get("source_confidence_tier") or digest.get("source_confidence_tier", ""),
                "source_confidence_score": staged.get("source_confidence_score") or digest.get("source_confidence_score", ""),
                "replacement_class": staged.get("replacement_class") or digest.get("replacement_class", ""),
                "endpoint_group": staged.get("endpoint_group", ""),
                "direction": staged.get("direction", ""),
                "digest_status": digest_status,
                "promotion_diff_status": promotion_row.get("diff_status", ""),
                "source_path": promotion_row.get("source_path", staged.get("staging_path", "")),
                "target_path": promotion_row.get("target_path", ""),
                "matched_candidate_ids": digest.get("matched_candidate_ids", ""),
                "matched_review_ids": digest.get("matched_review_ids", ""),
                "sandbox_operator_decisions": digest.get("operator_decisions", ""),
                "sandbox_signoff_decision_counts": dict(signoff_decisions.most_common()),
                "promotion_eligible": promotion_eligible,
                "checksum_bound": bool(row_sha and staged.get("row_sha256") == row_sha),
                "source_owner_bound": bool(staged.get("source_owner")),
                "promotion_diff_bound": bool(promotion_row.get("diff_status")),
                "digestion_bound": bool(digest.get("ledger_id")),
                "recommended_decision": recommended,
                "recommendation_reason": reason,
            }
        )
    return rows


def write_rgroup_promotion_approval_decision_template(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    csv_path: str | Path = DEFAULT_DECISION_TEMPLATE_CSV,
) -> dict[str, Any]:
    root_path = Path(root)
    candidate_rows = _build_candidate_rows(root_path=root_path, project_name=project_name)
    fields = [
        "approval_id",
        "replacement_id",
        "row_sha256",
        "source_dataset",
        "digest_status",
        "promotion_eligible",
        "recommended_decision",
        "recommendation_reason",
        "promotion_approval_decision",
        "reviewer",
        "review_note",
        "reviewed_at",
    ]
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in candidate_rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "template_written",
        "mode": "rgroup_promotion_approval_decision_template",
        "row_count": len(candidate_rows),
        "csv_path": str(path),
    }


def build_rgroup_promotion_approval_ledger(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    decisions_csv: str | Path | None = None,
    decision: str | None = None,
    reviewer: str = "",
    note: str = "",
) -> dict[str, Any]:
    root_path = Path(root)
    candidate_rows = _build_candidate_rows(root_path=root_path, project_name=project_name)
    candidate_by_id = {str(row.get("approval_id") or ""): row for row in candidate_rows}
    candidate_by_key = {(str(row.get("replacement_id") or ""), str(row.get("row_sha256") or "")): row for row in candidate_rows}
    if decision:
        raw_rows = _decision_rows_from_ledger({"candidate_rows": candidate_rows}, decision=decision, reviewer=reviewer, note=note)
    else:
        raw_rows = _read_csv(decisions_csv or root_path / DEFAULT_DECISION_TEMPLATE_CSV)

    rows: list[dict[str, Any]] = []
    invalid_rows = 0
    missing_candidate_rows = 0
    for index, raw in enumerate(raw_rows, start=1):
        approval_id = str(raw.get("approval_id") or "").strip()
        candidate = candidate_by_id.get(approval_id)
        if not candidate:
            candidate = candidate_by_key.get((str(raw.get("replacement_id") or ""), str(raw.get("row_sha256") or "")), {})
        decision_value = str(raw.get("promotion_approval_decision") or "").strip().lower()
        valid = decision_value in VALID_DECISIONS
        if not valid:
            invalid_rows += 1
        if not candidate:
            missing_candidate_rows += 1
        approved = bool(candidate and valid and decision_value == "approved" and candidate.get("promotion_eligible"))
        rows.append(
            {
                **candidate,
                "approval_id": approval_id or candidate.get("approval_id") or f"RGPROM-RAW-{index:04d}",
                "promotion_approval_decision": decision_value,
                "reviewer": str(raw.get("reviewer") or reviewer or ""),
                "review_note": str(raw.get("review_note") or note or ""),
                "reviewed_at": str(raw.get("reviewed_at") or datetime.now(timezone.utc).isoformat()),
                "valid_decision": valid,
                "candidate_row_found": bool(candidate),
                "approved_for_promotion": approved,
                "promotion_blocker_count": 0 if approved else 1,
                "next_action": (
                    "Ready for promotion approval ledger gate; still require whole-drop approval before copy."
                    if approved
                    else "Keep staged row out of feed promotion until reviewer explicitly approves this row."
                    if valid and decision_value == "deferred"
                    else "Rejected for this promotion cycle; keep row in holdout."
                    if valid and decision_value == "rejected"
                    else "Fix invalid or stale promotion approval decision row."
                ),
            }
        )

    required_ids = {str(row.get("approval_id") or "") for row in candidate_rows}
    decided_ids = {str(row.get("approval_id") or "") for row in rows if row.get("valid_decision") and row.get("candidate_row_found")}
    pending_ids = sorted(required_ids - decided_ids)
    decision_counts = Counter(str(row.get("promotion_approval_decision") or "") for row in rows if row.get("valid_decision"))
    approved_count = sum(1 for row in rows if row.get("approved_for_promotion") is True)
    eligible_count = sum(1 for row in candidate_rows if row.get("promotion_eligible") is True)
    binding_blocker_count = sum(
        1
        for row in candidate_rows
        if not (row.get("checksum_bound") and row.get("source_owner_bound") and row.get("promotion_diff_bound") and row.get("digestion_bound"))
    )
    pending_count = len(pending_ids)
    rejected_count = decision_counts.get("rejected", 0)
    deferred_count = decision_counts.get("deferred", 0)
    if invalid_rows or missing_candidate_rows or binding_blocker_count:
        status = "blocked"
    elif pending_count:
        status = "pending_approval"
    elif approved_count and approved_count == len(candidate_rows) and eligible_count == len(candidate_rows):
        status = "approved"
    elif approved_count:
        status = "partially_approved_holdout"
    else:
        status = "reviewed_holdout" if rows else "awaiting_rows"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "rgroup_promotion_approval_ledger",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_row_count": len(candidate_rows),
        "approval_required_count": len(candidate_rows),
        "completed_approval_count": len(decided_ids),
        "pending_approval_count": pending_count,
        "eligible_row_count": eligible_count,
        "approved_count": approved_count,
        "deferred_count": deferred_count,
        "rejected_count": rejected_count,
        "invalid_row_count": invalid_rows,
        "missing_candidate_row_count": missing_candidate_rows,
        "binding_blocker_count": binding_blocker_count,
        "decision_counts": dict(decision_counts.most_common()),
        "pending_approval_ids": pending_ids,
        "promotion_allowed": bool(status == "approved" and approved_count == len(candidate_rows) and approved_count > 0),
        "production_scoring_affected": False,
        "rows": rows,
        "blocked_scopes": BLOCKED_SCOPES,
        "recommended_next_actions": [
            "Use the decision template for selective row approval; leave uncertain rows deferred.",
            "Run feed promotion without dry-run only when promotion_allowed is true.",
        ],
    }


def render_rgroup_promotion_approval_ledger_markdown(report: dict) -> str:
    lines = [
        "# R-group Promotion Approval Ledger",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Required / completed: `{report.get('approval_required_count')}` / `{report.get('completed_approval_count')}`",
        f"- Approved / deferred / rejected: `{report.get('approved_count')}` / `{report.get('deferred_count')}` / `{report.get('rejected_count')}`",
        f"- Promotion allowed: `{report.get('promotion_allowed')}`",
        "",
        "| Approval | Replacement | Source | Digest | Eligible | Decision | Checksum | Owner | Diff | Next Action |",
        "| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("approval_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("digest_status") or ""),
                    str(row.get("promotion_eligible")),
                    str(row.get("promotion_approval_decision") or ""),
                    str(row.get("checksum_bound")),
                    str(row.get("source_owner_bound")),
                    str(row.get("promotion_diff_bound")),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_promotion_approval_ledger(
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
        "approval_id",
        "digestion_ledger_id",
        "replacement_id",
        "row_sha256",
        "source_dataset",
        "source_owner",
        "source_license",
        "provenance_level",
        "provenance_review_status",
        "source_reference",
        "source_confidence_tier",
        "source_confidence_score",
        "replacement_class",
        "endpoint_group",
        "direction",
        "digest_status",
        "promotion_diff_status",
        "source_path",
        "target_path",
        "matched_candidate_ids",
        "matched_review_ids",
        "sandbox_operator_decisions",
        "promotion_eligible",
        "checksum_bound",
        "source_owner_bound",
        "promotion_diff_bound",
        "digestion_bound",
        "recommended_decision",
        "recommendation_reason",
        "promotion_approval_decision",
        "reviewer",
        "review_note",
        "reviewed_at",
        "valid_decision",
        "candidate_row_found",
        "approved_for_promotion",
        "promotion_blocker_count",
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
        md_file.write_text(render_rgroup_promotion_approval_ledger_markdown(report), encoding="utf-8")
