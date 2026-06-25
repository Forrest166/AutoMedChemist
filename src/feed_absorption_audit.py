from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FEED_ABSORPTION_AUDIT_JSON = Path("data/substituents/feed_absorption_audit.json")
DEFAULT_FEED_ABSORPTION_AUDIT_CSV = Path("data/substituents/feed_absorption_audit.csv")
DEFAULT_FEED_ABSORPTION_AUDIT_MD = Path("docs/feed_absorption_audit.md")
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


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _row(
    gate_id: str,
    label: str,
    status: str,
    details: str,
    *,
    blocker_count: int = 0,
    warning_count: int = 0,
    artifact_path: str | Path = "",
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "label": label,
        "status": status,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "details": details,
        "artifact_path": str(artifact_path or ""),
        "next_action": next_action,
    }


def build_feed_absorption_audit(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    metadata = _read_json(root_path / "data/substituents/rgroup_feed_metadata_report.json")
    coverage = _read_json(root_path / "data/substituents/rgroup_feed_review_coverage.json")
    onboarding = _read_json(root_path / "data/substituents/rgroup_feed_onboarding_gate.json")
    staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    promotion_diff = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    owner_ledger = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json")
    normalization = _read_json(root_path / "data/substituents/rgroup_normalization_report.json")
    contradiction_decisions = _read_json(root_path / "data/substituents/rgroup_normalized_pair_contradiction_decisions.json")

    allowlist = _int(metadata.get("allowlist_issue_count"))
    freshness = _int(metadata.get("freshness_issue_count"))
    no_review = _int(coverage.get("no_review_count"))
    low_review = _int(coverage.get("low_coverage_count"))
    owner_pending = _int(owner_ledger.get("pending_owner_review_count"))
    staging_blockers = _int(staging_gate.get("blocker_count"))
    promotion_blocked = _int(promotion_diff.get("blocked_file_count"))
    invalid_endpoints = _int(normalization.get("invalid_or_blank_endpoint_count"))
    input_count = _int(normalization.get("input_count"))
    normalized_count = _int(normalization.get("normalized_count"))
    open_high = _int(contradiction_decisions.get("open_high_priority_count"))

    rows = [
        _row(
            "feed_manifest_metadata",
            "Feed manifest metadata",
            "pass" if metadata and allowlist == 0 and freshness == 0 else "fail",
            f"feeds={metadata.get('feed_count')}; rows={metadata.get('row_count')}; allowlist={allowlist}; freshness={freshness}; sample_review={metadata.get('sample_review_count')}",
            blocker_count=allowlist,
            warning_count=freshness,
            artifact_path=root_path / "data/substituents/rgroup_feed_metadata_report.json",
            next_action="Fix manifest allowlist or freshness issues before absorbing feed rows.",
        ),
        _row(
            "feed_review_coverage",
            "Feed review coverage",
            "pass" if coverage and no_review == 0 and low_review == 0 else "warn",
            f"cells={coverage.get('coverage_cell_count')}; covered={coverage.get('covered_count')}; no_review={no_review}; low={low_review}",
            warning_count=no_review + low_review,
            artifact_path=root_path / "data/substituents/rgroup_feed_review_coverage.json",
            next_action="Add sample review decisions for empty or low-coverage source/class/endpoint strata.",
        ),
        _row(
            "source_owner_ledger",
            "Source-owner ledger",
            "pass" if owner_ledger and owner_pending == 0 else "fail",
            f"status={owner_ledger.get('status')}; rows={owner_ledger.get('row_count')}; pending={owner_pending}; decisions={owner_ledger.get('decision_counts')}",
            blocker_count=owner_pending,
            artifact_path=root_path / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json",
            next_action="Record owner decisions or conservative holds for deferred pair conflicts.",
        ),
        _row(
            "normalization_digest",
            "Normalization digest",
            "pass" if normalization and normalized_count >= input_count and invalid_endpoints == 0 else "warn",
            f"input={input_count}; normalized={normalized_count}; deduplicated={normalization.get('deduplicated_count')}; duplicate_groups={normalization.get('duplicate_group_count')}; invalid_endpoints={invalid_endpoints}",
            warning_count=invalid_endpoints,
            artifact_path=root_path / "data/substituents/rgroup_normalization_report.json",
            next_action="Standardize endpoints and review duplicate groups before turning feed rows into priors.",
        ),
        _row(
            "contradiction_decisions",
            "Contradiction decisions",
            "pass" if contradiction_decisions and open_high == 0 else "warn",
            f"status={contradiction_decisions.get('status')}; open_high={open_high}; blocking_unresolved={contradiction_decisions.get('blocking_unresolved_count')}; decisions={contradiction_decisions.get('decision_counts')}",
            warning_count=open_high,
            artifact_path=root_path / "data/substituents/rgroup_normalized_pair_contradiction_decisions.json",
            next_action="Resolve or defer high-priority contradictory normalized pairs before scoring them positively.",
        ),
        _row(
            "staging_gate",
            "Next feed staging gate",
            "pass" if staging_gate and staging_blockers == 0 and staging_gate.get("status") in {"awaiting_filled_staging_rows", "ready_for_promotion"} else "fail",
            f"status={staging_gate.get('status')}; files={staging_gate.get('staged_file_count')}; filled={staging_gate.get('filled_file_count')}; rows={staging_gate.get('staged_row_count')}; blockers={staging_blockers}; warnings={staging_gate.get('warning_count')}",
            blocker_count=staging_blockers,
            warning_count=_int(staging_gate.get("warning_count")),
            artifact_path=root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json",
            next_action="Keep staging templates empty or fully validated; never promote partial rows.",
        ),
        _row(
            "promotion_diff",
            "Promotion diff",
            "pass" if promotion_diff and promotion_blocked == 0 and promotion_diff.get("status") in {"awaiting_filled_staging_rows", "ready_for_promotion", "dry_run_ready"} else "fail",
            f"status={promotion_diff.get('status')}; ready={promotion_diff.get('ready_to_promote_file_count')}; awaiting={promotion_diff.get('awaiting_filled_file_count')}; overwrite_review={promotion_diff.get('overwrite_review_file_count')}; blocked={promotion_blocked}",
            blocker_count=promotion_blocked,
            warning_count=_int(promotion_diff.get("awaiting_filled_file_count")),
            artifact_path=root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json",
            next_action="Review row-count and checksum deltas before allowing a non-dry-run promotion.",
        ),
    ]
    blocker_count = sum(_int(row.get("blocker_count")) for row in rows)
    warning_count = sum(_int(row.get("warning_count")) for row in rows)
    pass_count = sum(1 for row in rows if row.get("status") == "pass")
    status = "blocked" if blocker_count else "ready_with_open_staging" if warning_count else "ready"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "feed_absorption_audit",
        "row_count": len(rows),
        "pass_count": pass_count,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "feed_count": metadata.get("feed_count"),
        "feed_row_count": metadata.get("row_count"),
        "normalized_count": normalized_count,
        "deduplicated_count": normalization.get("deduplicated_count"),
        "rows": rows,
        "recommended_next_actions": [
            "Absorb new feed rows only after manifest, review coverage, owner ledger, normalization, contradiction, staging, and promotion gates are green.",
            "Treat awaiting_filled_staging_rows as safe idle state; promotion remains dry-run until reviewed rows exist.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_feed_absorption_audit_markdown(report: dict) -> str:
    lines = [
        "# Feed Absorption Audit",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Blockers / warnings: `{report.get('blocker_count')}` / `{report.get('warning_count')}`",
        "",
        "| Gate | Status | Blockers | Warnings | Details | Next Action |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("gate_id") or ""),
                    str(row.get("status") or ""),
                    str(row.get("blocker_count") or 0),
                    str(row.get("warning_count") or 0),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_feed_absorption_audit(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_ABSORPTION_AUDIT_JSON,
    csv_path: str | Path | None = DEFAULT_FEED_ABSORPTION_AUDIT_CSV,
    markdown_path: str | Path | None = DEFAULT_FEED_ABSORPTION_AUDIT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = ["gate_id", "label", "status", "blocker_count", "warning_count", "details", "artifact_path", "next_action"]
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
        md_file.write_text(render_feed_absorption_audit_markdown(report), encoding="utf-8")
