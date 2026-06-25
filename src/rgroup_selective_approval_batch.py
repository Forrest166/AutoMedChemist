from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .rgroup_promotion_approval_ledger import (
    BLOCKED_SCOPES,
    DEFAULT_DECISION_TEMPLATE_CSV,
    DEFAULT_LEDGER_CSV,
    DEFAULT_LEDGER_JSON,
    DEFAULT_LEDGER_MD,
    PROMOTION_ELIGIBLE_STATUSES,
    build_rgroup_promotion_approval_ledger,
    write_rgroup_promotion_approval_ledger,
)


DEFAULT_BATCH_JSON = Path("data/substituents/rgroup_selective_approval_batch.json")
DEFAULT_BATCH_CSV = Path("data/substituents/rgroup_selective_approval_batch.csv")
DEFAULT_BATCH_MD = Path("docs/rgroup_selective_approval_batch.md")

LOW_TRUST_SOURCE_DATASETS = {"patent_mined_seed"}
LOW_TRUST_TIERS = {"patent_like", "patent", "low"}


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
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _split(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _decision_reason(row: dict[str, Any], *, min_confidence: float) -> tuple[str, str]:
    confidence = _float(row.get("source_confidence_score"))
    source_dataset = str(row.get("source_dataset") or "").strip()
    confidence_tier = str(row.get("source_confidence_tier") or "").strip().lower()
    matched_ids = _split(row.get("matched_candidate_ids"))
    bindings_ok = all(
        row.get(flag) is True
        for flag in [
            "promotion_eligible",
            "checksum_bound",
            "source_owner_bound",
            "promotion_diff_bound",
            "digestion_bound",
        ]
    )
    if row.get("recommended_decision") != "approved":
        return "deferred", "Ledger recommendation is not approved; keep in holdout."
    if str(row.get("digest_status") or "") not in PROMOTION_ELIGIBLE_STATUSES:
        return "deferred", "Digest status is not promotion eligible."
    if not bindings_ok:
        return "deferred", "Checksum, owner, promotion-diff, or digestion binding is incomplete."
    if str(row.get("provenance_review_status") or "") != "accepted":
        return "deferred", "Provenance review is not accepted."
    if confidence < min_confidence:
        return "deferred", "Source confidence is below the positive-control threshold."
    if matched_ids:
        return "deferred", "Current candidate impact exists; defer for explicit chemist review."
    if source_dataset in LOW_TRUST_SOURCE_DATASETS or confidence_tier in LOW_TRUST_TIERS:
        return "deferred", "Low-trust or patent-like source tier is excluded from the positive-control batch."
    return "approved", "Accepted provenance, high confidence, no current candidate impact, and all promotion bindings are present."


def _write_decision_csv(rows: list[dict[str, Any]], path: Path, *, reviewer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    reviewed_at = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "approval_id": row.get("approval_id", ""),
                    "replacement_id": row.get("replacement_id", ""),
                    "row_sha256": row.get("row_sha256", ""),
                    "source_dataset": row.get("source_dataset", ""),
                    "digest_status": row.get("digest_status", ""),
                    "promotion_eligible": row.get("promotion_eligible", ""),
                    "recommended_decision": row.get("recommended_decision", ""),
                    "recommendation_reason": row.get("recommendation_reason", ""),
                    "promotion_approval_decision": row.get("selective_approval_decision", ""),
                    "reviewer": reviewer,
                    "review_note": row.get("selective_approval_reason", ""),
                    "reviewed_at": reviewed_at,
                }
            )


def build_rgroup_selective_approval_batch(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    min_confidence: float = 0.8,
    apply_decisions: bool = False,
    reviewer: str = "selective_positive_control",
    decisions_csv: str | Path = DEFAULT_DECISION_TEMPLATE_CSV,
) -> dict[str, Any]:
    root_path = Path(root)
    seed_ledger = build_rgroup_promotion_approval_ledger(
        root=root_path,
        project_name=project_name,
        decision="deferred",
        reviewer=reviewer,
        note="Seeded for selective positive-control screening.",
    )
    rows: list[dict[str, Any]] = []
    for row in seed_ledger.get("rows") or []:
        decision, reason = _decision_reason(row, min_confidence=min_confidence)
        rows.append(
            {
                **row,
                "selective_approval_decision": decision,
                "selective_approval_reason": reason,
                "candidate_impact_count": len(_split(row.get("matched_candidate_ids"))),
                "positive_control_eligible": decision == "approved",
            }
        )

    decision_counts = Counter(str(row.get("selective_approval_decision") or "") for row in rows)
    source_counts = Counter(str(row.get("source_dataset") or "") for row in rows)
    replacement_class_counts = Counter(str(row.get("replacement_class") or "") for row in rows)
    decisions_path = root_path / decisions_csv
    applied_ledger: dict[str, Any] = {}
    if apply_decisions:
        _write_decision_csv(rows, decisions_path, reviewer=reviewer)
        applied_ledger = build_rgroup_promotion_approval_ledger(
            root=root_path,
            project_name=project_name,
            decisions_csv=decisions_path,
        )
        write_rgroup_promotion_approval_ledger(
            applied_ledger,
            json_path=root_path / DEFAULT_LEDGER_JSON,
            csv_path=root_path / DEFAULT_LEDGER_CSV,
            markdown_path=root_path / DEFAULT_LEDGER_MD,
        )

    approved_count = decision_counts.get("approved", 0)
    holdout_count = decision_counts.get("deferred", 0)
    status = "ready" if rows and approved_count else "awaiting_positive_control"
    if any(not row.get("valid_decision", True) for row in rows):
        status = "blocked"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "rgroup_selective_approval_batch",
        "project_name": project_name,
        "min_confidence": min_confidence,
        "apply_decisions": apply_decisions,
        "candidate_count": len(rows),
        "positive_control_approved_count": approved_count,
        "holdout_count": holdout_count,
        "rejected_count": decision_counts.get("rejected", 0),
        "decision_counts": dict(decision_counts.most_common()),
        "source_counts": dict(source_counts.most_common()),
        "replacement_class_counts": dict(replacement_class_counts.most_common()),
        "decision_csv_path": str(decisions_path),
        "applied_ledger_status": applied_ledger.get("status") if applied_ledger else "",
        "applied_ledger_approved_count": applied_ledger.get("approved_count") if applied_ledger else approved_count,
        "production_promotion_allowed": bool(applied_ledger.get("promotion_allowed")) if applied_ledger else False,
        "production_scoring_affected": False,
        "blocked_scopes": BLOCKED_SCOPES,
        "rows": rows,
        "recommended_next_actions": [
            "Use the approved rows as a tiny positive-control batch only; leave all candidate-impact, low-trust, or patent-like rows deferred.",
            "Do not run non-dry-run feed promotion until the full ledger becomes approved.",
        ],
    }


def render_rgroup_selective_approval_batch_markdown(report: dict) -> str:
    lines = [
        "# R-group Selective Approval Batch",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Positive-control approved / holdout: `{report.get('positive_control_approved_count')}` / `{report.get('holdout_count')}`",
        f"- Production promotion allowed: `{report.get('production_promotion_allowed')}`",
        "",
        "| Approval | Replacement | Source | Class | Decision | Impact | Reason |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("approval_id") or ""),
                    str(row.get("replacement_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("replacement_class") or ""),
                    str(row.get("selective_approval_decision") or ""),
                    str(row.get("candidate_impact_count") or 0),
                    str(row.get("selective_approval_reason") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_selective_approval_batch(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BATCH_JSON,
    csv_path: str | Path | None = DEFAULT_BATCH_CSV,
    markdown_path: str | Path | None = DEFAULT_BATCH_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "approval_id",
        "replacement_id",
        "source_dataset",
        "replacement_class",
        "source_confidence_score",
        "digest_status",
        "promotion_eligible",
        "recommended_decision",
        "selective_approval_decision",
        "positive_control_eligible",
        "candidate_impact_count",
        "selective_approval_reason",
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
        md_file.write_text(render_rgroup_selective_approval_batch_markdown(report), encoding="utf-8")
