from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FEED_DIFF_NAVIGATOR_JSON = Path("data/substituents/feed_absorption_diff_navigator.json")
DEFAULT_FEED_DIFF_NAVIGATOR_CSV = Path("data/substituents/feed_absorption_diff_navigator.csv")
DEFAULT_FEED_DIFF_NAVIGATOR_MD = Path("docs/feed_absorption_diff_navigator.md")
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


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _join(value: object, limit: int = 180) -> str:
    if isinstance(value, dict):
        text = "; ".join(f"{key}={item}" for key, item in value.items())
    elif isinstance(value, list):
        text = "; ".join(str(item) for item in value)
    else:
        text = str(value or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _status_from_counts(blocker_count: int, warning_count: int) -> str:
    if blocker_count:
        return "blocked"
    if warning_count:
        return "watch"
    return "ready"


def build_feed_absorption_diff_navigator(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    audit = _read_json(root_path / "data/substituents/feed_absorption_audit.json")
    promotion = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_promotion_diff.json")
    staging = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    normalization = _read_json(root_path / "data/substituents/rgroup_normalization_report.json")
    owner_ledger = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json")
    coverage = _read_json(root_path / "data/substituents/rgroup_feed_review_coverage.json")
    rows: list[dict[str, Any]] = []

    for index, row in enumerate(promotion.get("rows") or [], start=1):
        staged = _int(row.get("staged_row_count"))
        target = _int(row.get("target_row_count"))
        missing_columns = row.get("missing_required_columns") or []
        blocker_count = 1 if str(row.get("diff_status") or "").startswith("blocked") or missing_columns else 0
        warning_count = 1 if str(row.get("diff_status") or "") in {"awaiting_filled_rows", "overwrite_review"} else 0
        rows.append(
            {
                "row_id": f"FDIFF-{index:04d}",
                "row_type": "feed_delta",
                "source_dataset": row.get("source_dataset", ""),
                "normalized_pair_key": "",
                "endpoint_group": "",
                "status": _status_from_counts(blocker_count, warning_count),
                "blocker_count": blocker_count,
                "warning_count": warning_count,
                "staged_row_count": staged,
                "target_row_count": target,
                "row_delta": staged - target,
                "duplicate_group_size": "",
                "owner_decision": "",
                "review_coverage_fraction": "",
                "source_path": row.get("source_path", ""),
                "target_path": row.get("target_path", ""),
                "details": f"diff_status={row.get('diff_status')}; action={row.get('action')}; missing_columns={_join(missing_columns)}",
                "next_action": "Review staged-vs-target row delta and checksums before promotion.",
            }
        )

    for index, row in enumerate(staging.get("rows") or [], start=1):
        missing_required = row.get("missing_required_columns") or []
        missing_governance = row.get("missing_recommended_governance_columns") or []
        blocker_count = 1 if missing_required or _int(row.get("missing_row_sha256_count")) else 0
        warning_count = 1 if missing_governance or _int(row.get("row_count")) == 0 else 0
        rows.append(
            {
                "row_id": f"FSTAGE-{index:04d}",
                "row_type": "staging_file",
                "source_dataset": row.get("source_dataset", ""),
                "normalized_pair_key": "",
                "endpoint_group": "",
                "status": _status_from_counts(blocker_count, warning_count),
                "blocker_count": blocker_count,
                "warning_count": warning_count,
                "staged_row_count": _int(row.get("row_count")),
                "target_row_count": "",
                "row_delta": "",
                "duplicate_group_size": "",
                "owner_decision": "",
                "review_coverage_fraction": "",
                "source_path": row.get("path") or row.get("template_path", ""),
                "target_path": "",
                "details": f"manifest={row.get('manifest_status')}; source_dataset_match={row.get('source_dataset_match')}; missing_required={_join(missing_required)}; missing_governance={_join(missing_governance)}",
                "next_action": "Fill only reviewed rows and keep required governance columns complete.",
            }
        )

    for index, row in enumerate(normalization.get("top_duplicate_groups") or [], start=1):
        rows.append(
            {
                "row_id": f"FDUP-{index:04d}",
                "row_type": "duplicate_normalized_pair",
                "source_dataset": _join(row.get("source_dataset") or row.get("source_datasets") or ""),
                "normalized_pair_key": row.get("normalized_pair_key") or row.get("pair_key") or row.get("replacement_key") or "",
                "endpoint_group": row.get("endpoint_group", ""),
                "status": "watch",
                "blocker_count": 0,
                "warning_count": 1,
                "staged_row_count": "",
                "target_row_count": "",
                "row_delta": "",
                "duplicate_group_size": row.get("count") or row.get("duplicate_count") or row.get("row_count") or "",
                "owner_decision": "",
                "review_coverage_fraction": "",
                "source_path": "",
                "target_path": "",
                "details": _join(row),
                "next_action": "Inspect duplicate normalized pair rows before weighting source support.",
            }
        )

    for index, row in enumerate(owner_ledger.get("rows") or [], start=1):
        rows.append(
            {
                "row_id": f"FOWNER-{index:04d}",
                "row_type": "owner_decision_reuse",
                "source_dataset": row.get("source_confidence_tier", ""),
                "normalized_pair_key": row.get("normalized_pair_key", ""),
                "endpoint_group": row.get("endpoint_group", ""),
                "status": "ready" if row.get("owner_decision") else "watch",
                "blocker_count": 0,
                "warning_count": 0 if row.get("owner_decision") else 1,
                "staged_row_count": "",
                "target_row_count": "",
                "row_delta": "",
                "duplicate_group_size": "",
                "owner_decision": row.get("owner_decision", ""),
                "review_coverage_fraction": "",
                "source_path": row.get("source_reference", ""),
                "target_path": "",
                "details": f"owner={row.get('source_owner')}; reviewer={row.get('owner_reviewer')}; apply={row.get('review_apply_status')}",
                "next_action": "Reuse recorded owner decision; keep deferred rows from becoming positive priors.",
            }
        )

    for index, row in enumerate(coverage.get("rows") or [], start=1):
        coverage_status = str(row.get("coverage_status") or "")
        if coverage_status == "covered" and _float(row.get("review_coverage_fraction")) >= 1:
            continue
        rows.append(
            {
                "row_id": f"FCOV-{index:04d}",
                "row_type": "review_coverage_gap",
                "source_dataset": row.get("source_dataset", ""),
                "normalized_pair_key": "",
                "endpoint_group": row.get("endpoint_group", ""),
                "status": "watch",
                "blocker_count": 0,
                "warning_count": 1,
                "staged_row_count": "",
                "target_row_count": "",
                "row_delta": "",
                "duplicate_group_size": "",
                "owner_decision": "",
                "review_coverage_fraction": row.get("review_coverage_fraction", ""),
                "source_path": _join(row.get("source_path_counts", "")),
                "target_path": "",
                "details": f"coverage_status={coverage_status}; reviewed={row.get('reviewed_decision_count')}; pending={row.get('pending_count')}; needs_review={row.get('needs_review_count')}",
                "next_action": "Add sample review decisions for low-coverage strata before absorption.",
            }
        )

    type_counts = Counter(str(row.get("row_type") or "") for row in rows)
    blocker_count = sum(_int(row.get("blocker_count")) for row in rows)
    warning_count = sum(_int(row.get("warning_count")) for row in rows)
    status = "blocked" if blocker_count or audit.get("status") == "blocked" else "ready_with_open_staging" if warning_count else "ready"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "feed_absorption_diff_navigator",
        "row_count": len(rows),
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "feed_delta_count": type_counts.get("feed_delta", 0),
        "staging_file_count": type_counts.get("staging_file", 0),
        "duplicate_group_count": type_counts.get("duplicate_normalized_pair", 0),
        "owner_reuse_count": type_counts.get("owner_decision_reuse", 0),
        "coverage_gap_count": type_counts.get("review_coverage_gap", 0),
        "row_type_counts": dict(type_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use feed_delta rows to inspect staged-vs-target row counts before promotion.",
            "Use duplicate and owner-decision rows to keep repeated or deferred normalized pairs from over-weighting scoring.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_feed_absorption_diff_navigator_markdown(report: dict) -> str:
    lines = [
        "# Feed Absorption Diff Navigator",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        f"- Blockers / warnings: `{report.get('blocker_count')}` / `{report.get('warning_count')}`",
        "",
        "| Row | Type | Source | Status | Staged | Target | Delta | Pair | Details | Next Action |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:180]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("row_id") or ""),
                    str(row.get("row_type") or ""),
                    str(row.get("source_dataset") or ""),
                    str(row.get("status") or ""),
                    str(row.get("staged_row_count") or ""),
                    str(row.get("target_row_count") or ""),
                    str(row.get("row_delta") or ""),
                    str(row.get("normalized_pair_key") or ""),
                    str(row.get("details") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_feed_absorption_diff_navigator(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_FEED_DIFF_NAVIGATOR_JSON,
    csv_path: str | Path | None = DEFAULT_FEED_DIFF_NAVIGATOR_CSV,
    markdown_path: str | Path | None = DEFAULT_FEED_DIFF_NAVIGATOR_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "row_id",
        "row_type",
        "source_dataset",
        "normalized_pair_key",
        "endpoint_group",
        "status",
        "blocker_count",
        "warning_count",
        "staged_row_count",
        "target_row_count",
        "row_delta",
        "duplicate_group_size",
        "owner_decision",
        "review_coverage_fraction",
        "source_path",
        "target_path",
        "details",
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
        md_file.write_text(render_feed_absorption_diff_navigator_markdown(report), encoding="utf-8")
