from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STAGING_QUALITY_BUDGET_JSON = Path("data/substituents/rgroup_staging_quality_budget.json")
DEFAULT_STAGING_QUALITY_BUDGET_CSV = Path("data/substituents/rgroup_staging_quality_budget.csv")
DEFAULT_STAGING_QUALITY_BUDGET_MD = Path("docs/rgroup_staging_quality_budget.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import", "production_scoring_write"]

SOURCE_POLICIES: dict[str, dict[str, Any]] = {
    "analog_series_seed": {
        "max_new_rows": 250,
        "max_duplicate_row_sha256": 0,
        "max_duplicate_replacement_id": 0,
        "required_review_statuses": {"reviewed", "accepted", "accepted_with_caution", "approved", "deferred"},
        "minimum_confidence_score": 0.5,
    },
    "literature_bioisostere_seed": {
        "max_new_rows": 200,
        "max_duplicate_row_sha256": 0,
        "max_duplicate_replacement_id": 0,
        "required_review_statuses": {"reviewed", "accepted", "accepted_with_caution", "approved", "deferred"},
        "minimum_confidence_score": 0.55,
    },
    "patent_mined_seed": {
        "max_new_rows": 50,
        "max_duplicate_row_sha256": 0,
        "max_duplicate_replacement_id": 0,
        "required_review_statuses": {"deferred", "reviewed", "accepted_with_caution", "owner_reviewed", "keep_deferred"},
        "minimum_confidence_score": 0.4,
    },
}
DEFAULT_POLICY = {
    "max_new_rows": 100,
    "max_duplicate_row_sha256": 0,
    "max_duplicate_replacement_id": 0,
    "required_review_statuses": {"reviewed", "accepted", "accepted_with_caution", "approved", "deferred"},
    "minimum_confidence_score": 0.5,
}

REQUIRED_METADATA_COLUMNS = [
    "source_owner",
    "source_license",
    "provenance_level",
    "provenance_review_status",
    "source_reference",
    "source_confidence_tier",
    "source_confidence_score",
    "source_confidence_basis",
    "row_sha256",
]


def _join_policy_values(values: object) -> str:
    if isinstance(values, set):
        return ";".join(sorted(str(item) for item in values))
    if isinstance(values, (list, tuple)):
        return ";".join(str(item) for item in values)
    return str(values or "")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _missing_count(rows: list[dict[str, str]], field: str) -> int:
    return sum(1 for row in rows if not str(row.get(field) or "").strip())


def _duplicate_count(rows: list[dict[str, str]], field: str) -> int:
    values = [str(row.get(field) or "").strip() for row in rows if str(row.get(field) or "").strip()]
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def _row_status(blockers: int, row_count: int) -> str:
    if blockers:
        return "blocked"
    if row_count <= 0:
        return "awaiting_rows"
    return "ready_for_sandbox_review"


def _policy_for(source_dataset: str) -> dict[str, Any]:
    policy = dict(DEFAULT_POLICY)
    policy.update(SOURCE_POLICIES.get(source_dataset, {}))
    return policy


def _manual_review_status(row_count: int, blockers: int) -> str:
    if row_count <= 0:
        return "awaiting_source_rows"
    if blockers:
        return "blocked_pending_curation"
    return "ready_for_sandbox_review"


def _manual_review_queue_row(
    *,
    index: int,
    source_dataset: str,
    path: Path,
    row_count: int,
    blockers: int,
    warnings: int,
    policy: dict[str, Any],
) -> dict[str, Any]:
    manual_status = _manual_review_status(row_count, blockers)
    return {
        "review_queue_id": f"RSRQ-{index:03d}",
        "source_dataset": source_dataset,
        "manual_review_status": manual_status,
        "row_count": row_count,
        "blocker_count": blockers,
        "warning_count": warnings,
        "review_status_policy": _join_policy_values(policy.get("required_review_statuses", set())),
        "minimum_confidence_score": policy.get("minimum_confidence_score"),
        "applicable_contexts": (
            "local R-group/replacement staging; governed substituent curation; "
            "sandbox-only score-delta review; medchem candidate generation support"
        ),
        "disabled_contexts": ";".join(BLOCKED_SCOPES),
        "version_change_log_required": True,
        "version_change_log": "required before promotion: row source, curator note, policy version, and replacement rationale",
        "operator_signoff_required": row_count > 0,
        "allowed_to_promote": False,
        "production_scoring_write_allowed": False,
        "next_action": (
            "Add provenance-complete reviewed rows and row_sha256 values before sandbox scoring."
            if row_count <= 0
            else "Resolve blockers and capture curator/version-change notes before sandbox review."
            if blockers
            else "Open sandbox score-delta review, then require operator signoff before any promotion."
        ),
        "staging_path": str(path),
    }


def build_staging_quality_budget(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    promotion_diff = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    sandbox = _read_json(root_path / "data/projects/demo/staged_feed_sandbox_scoring.json")
    rows: list[dict[str, Any]] = []
    review_queue_rows: list[dict[str, Any]] = []

    promotion_rows = {
        str(row.get("source_dataset") or ""): row
        for row in promotion_diff.get("rows") or []
        if row.get("source_dataset")
    }

    for index, gate_row in enumerate(staging_gate.get("rows") or [], start=1):
        source_dataset = str(gate_row.get("source_dataset") or "unknown")
        path = Path(str(gate_row.get("path") or gate_row.get("template_path") or ""))
        csv_rows = _read_csv_rows(path)
        policy = _policy_for(source_dataset)
        required_statuses = {str(item).lower() for item in policy.get("required_review_statuses", set())}
        row_count = len(csv_rows)
        duplicate_sha = _duplicate_count(csv_rows, "row_sha256")
        duplicate_replacement = _duplicate_count(csv_rows, "replacement_id")
        missing_metadata = {field: _missing_count(csv_rows, field) for field in REQUIRED_METADATA_COLUMNS}
        missing_metadata_count = sum(missing_metadata.values())
        low_confidence_count = sum(
            1
            for item in csv_rows
            if item.get("source_confidence_score")
            and _float(item.get("source_confidence_score")) < _float(policy.get("minimum_confidence_score"))
        )
        unreviewed_count = sum(
            1
            for item in csv_rows
            if row_count
            and str(item.get("provenance_review_status") or "").strip().lower() not in required_statuses
        )
        over_cap = max(0, row_count - _int(policy.get("max_new_rows")))
        gate_missing_required = len(gate_row.get("missing_required_columns") or [])
        gate_missing_governance = len(gate_row.get("missing_recommended_governance_columns") or [])
        source_mismatch = gate_row.get("source_dataset_match") is False
        blockers = (
            over_cap
            + duplicate_sha
            + duplicate_replacement
            + missing_metadata_count
            + low_confidence_count
            + unreviewed_count
            + gate_missing_required
            + _int(gate_row.get("missing_row_sha256_count"))
            + (1 if source_mismatch else 0)
        )
        warnings = gate_missing_governance
        promotion_row = promotion_rows.get(source_dataset, {})
        status = _row_status(blockers, row_count)
        manual_row = _manual_review_queue_row(
            index=index,
            source_dataset=source_dataset,
            path=path,
            row_count=row_count,
            blockers=blockers,
            warnings=warnings,
            policy=policy,
        )
        review_queue_rows.append(manual_row)
        rows.append(
            {
                "budget_id": f"RSQB-{index:03d}",
                "source_dataset": source_dataset,
                "budget_status": status,
                "manual_review_status": manual_row["manual_review_status"],
                "row_count": row_count,
                "max_new_rows": _int(policy.get("max_new_rows")),
                "over_cap_count": over_cap,
                "duplicate_row_sha256_count": duplicate_sha,
                "duplicate_replacement_id_count": duplicate_replacement,
                "missing_metadata_count": missing_metadata_count,
                "missing_license_count": missing_metadata.get("source_license", 0),
                "missing_provenance_count": missing_metadata.get("provenance_level", 0),
                "missing_review_status_count": missing_metadata.get("provenance_review_status", 0),
                "missing_reference_count": missing_metadata.get("source_reference", 0),
                "missing_confidence_count": missing_metadata.get("source_confidence_score", 0),
                "missing_row_sha256_count": missing_metadata.get("row_sha256", 0) + _int(gate_row.get("missing_row_sha256_count")),
                "low_confidence_count": low_confidence_count,
                "unreviewed_count": unreviewed_count,
                "source_dataset_match": gate_row.get("source_dataset_match"),
                "blocker_count": blockers,
                "warning_count": warnings,
                "promotion_diff_status": promotion_row.get("diff_status") or "missing",
                "sandbox_status": sandbox.get("status") or "missing",
                "operator_signoff_required": row_count > 0,
                "allowed_to_promote": False,
                "production_scoring_write_allowed": False,
                "applicable_contexts": manual_row["applicable_contexts"],
                "disabled_contexts": manual_row["disabled_contexts"],
                "review_status_policy": manual_row["review_status_policy"],
                "version_change_log_required": True,
                "version_change_log": manual_row["version_change_log"],
                "quality_budget": (
                    f"max_new_rows={policy.get('max_new_rows')}; "
                    f"max_duplicate_row_sha256={policy.get('max_duplicate_row_sha256')}; "
                    f"min_confidence={policy.get('minimum_confidence_score')}; "
                    "require_license_provenance_review_reference_confidence_sha=true"
                ),
                "next_action": (
                    "Fill this staged CSV only with real reviewed rows."
                    if row_count <= 0
                    else "Fix budget blockers, rerun sandbox scoring, and collect operator signoff before promotion."
                    if blockers
                    else "Run sandbox score-delta review and require operator signoff before promotion."
                ),
                "staging_path": str(path),
            }
        )

    blocked_count = sum(1 for row in rows if row.get("budget_status") == "blocked")
    awaiting_count = sum(1 for row in rows if row.get("budget_status") == "awaiting_rows")
    ready_count = sum(1 for row in rows if row.get("budget_status") == "ready_for_sandbox_review")
    manual_status_counts = Counter(str(row.get("manual_review_status") or "unknown") for row in review_queue_rows)
    status = "blocked" if blocked_count else "awaiting_rows" if ready_count == 0 else "ready_for_sandbox_review"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "rgroup_staging_quality_budget",
        "row_count": len(rows),
        "source_count": len(rows),
        "manual_review_queue_count": len(review_queue_rows),
        "staging_review_queue_count": len(review_queue_rows),
        "staged_row_count": sum(_int(row.get("row_count")) for row in rows),
        "blocked_source_count": blocked_count,
        "awaiting_source_count": awaiting_count,
        "ready_source_count": ready_count,
        "manual_review_status_counts": dict(manual_status_counts.most_common()),
        "blocker_count": sum(_int(row.get("blocker_count")) for row in rows) + _int(staging_gate.get("blocker_count")),
        "warning_count": sum(_int(row.get("warning_count")) for row in rows) + _int(staging_gate.get("warning_count")),
        "operator_signoff_required": any(row.get("operator_signoff_required") for row in rows),
        "promotion_allowed_without_sandbox_review": False,
        "staging_gate_status": staging_gate.get("status") or "missing",
        "promotion_diff_status": promotion_diff.get("status") or promotion_diff.get("promotion_status") or "missing",
        "sandbox_scoring_status": sandbox.get("status") or "missing",
        "rows": rows,
        "manual_review_queue_rows": review_queue_rows,
        "recommended_next_actions": [
            "Keep empty templates in awaiting_rows until real provenance-complete staged rows are available.",
            "Use the manual review queue to capture applicable contexts, disabled contexts, review status, and version-change notes.",
            "For any nonempty staged source, clear budget blockers and require sandbox score-delta signoff before promotion.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_staging_quality_budget_markdown(report: dict) -> str:
    lines = [
        "# R-group Staging Quality Budget",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Staged rows: `{report.get('staged_row_count')}`",
        f"- Manual review queue rows: `{report.get('manual_review_queue_count')}`",
        f"- Promotion without sandbox review: `{report.get('promotion_allowed_without_sandbox_review')}`",
        "",
        "| Source | Status | Manual Review | Rows | Max | Blockers | Duplicates | Missing Metadata | Low Conf | Unreviewed | Next Action |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("source_dataset") or ""),
                    str(row.get("budget_status") or ""),
                    str(row.get("manual_review_status") or ""),
                    str(row.get("row_count") or 0),
                    str(row.get("max_new_rows") or 0),
                    str(row.get("blocker_count") or 0),
                    str(_int(row.get("duplicate_row_sha256_count")) + _int(row.get("duplicate_replacement_id_count"))),
                    str(row.get("missing_metadata_count") or 0),
                    str(row.get("low_confidence_count") or 0),
                    str(row.get("unreviewed_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Manual Review Queue",
            "",
            "| Queue | Source | Status | Applicable | Disabled | Version Log | Next Action |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.get("manual_review_queue_rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("review_queue_id") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("manual_review_status") or ""),
                    str(row.get("applicable_contexts") or "").replace("|", "/"),
                    str(row.get("disabled_contexts") or "").replace("|", "/"),
                    str(row.get("version_change_log") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_staging_quality_budget(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_STAGING_QUALITY_BUDGET_JSON,
    csv_path: str | Path | None = DEFAULT_STAGING_QUALITY_BUDGET_CSV,
    markdown_path: str | Path | None = DEFAULT_STAGING_QUALITY_BUDGET_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "budget_id",
        "source_dataset",
        "budget_status",
        "manual_review_status",
        "row_count",
        "max_new_rows",
        "over_cap_count",
        "duplicate_row_sha256_count",
        "duplicate_replacement_id_count",
        "missing_metadata_count",
        "missing_license_count",
        "missing_provenance_count",
        "missing_review_status_count",
        "missing_reference_count",
        "missing_confidence_count",
        "missing_row_sha256_count",
        "low_confidence_count",
        "unreviewed_count",
        "source_dataset_match",
        "blocker_count",
        "warning_count",
        "promotion_diff_status",
        "sandbox_status",
        "operator_signoff_required",
        "allowed_to_promote",
        "production_scoring_write_allowed",
        "applicable_contexts",
        "disabled_contexts",
        "review_status_policy",
        "version_change_log_required",
        "version_change_log",
        "quality_budget",
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
        md_file.write_text(render_staging_quality_budget_markdown(report), encoding="utf-8")
