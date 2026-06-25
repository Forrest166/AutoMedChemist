from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .rgroup_feed_onboarding import ONBOARDING_TEMPLATE_COLUMNS
from .staging_quality_budget import SOURCE_POLICIES


DEFAULT_STAGING_DIR = Path("data/replacements/feed_drops/next_rgroup_feed_drop")
DEFAULT_REPORT_JSON = Path("data/substituents/rgroup_staging_fill_report.json")
DEFAULT_REPORT_CSV = Path("data/substituents/rgroup_staging_fill_report.csv")
DEFAULT_REPORT_MD = Path("docs/rgroup_staging_fill_report.md")

SOURCE_FEEDS = {
    "analog_series_seed": Path("data/replacements/feeds/analog_series_followup_feed_202605.csv"),
    "literature_bioisostere_seed": Path("data/replacements/feeds/literature_bioisostere_followup_feed_202605.csv"),
    "patent_mined_seed": Path("data/replacements/feeds/patent_mined_followup_feed_202605.csv"),
}

DEFAULT_SOURCE_LIMITS = {
    "analog_series_seed": 2,
    "literature_bioisostere_seed": 3,
    "patent_mined_seed": 3,
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _complete_for_staging(row: dict[str, str], source_dataset: str) -> bool:
    required = [
        "replacement_id",
        "source_smiles",
        "target_smiles",
        "edge_weight",
        "source_name",
        "source_dataset",
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
    if str(row.get("source_dataset") or "").strip() != source_dataset:
        return False
    if any(not str(row.get(field) or "").strip() for field in required):
        return False
    policy = SOURCE_POLICIES.get(source_dataset, {})
    min_confidence = _float(policy.get("minimum_confidence_score"))
    if _float(row.get("source_confidence_score")) < min_confidence:
        return False
    allowed = {str(item).lower() for item in policy.get("required_review_statuses", set())}
    review_values = {
        str(row.get("provenance_review_status") or "").strip().lower(),
        str(row.get("source_review_decision") or "").strip().lower(),
    }
    return bool(allowed & review_values)


def _to_staging_row(row: dict[str, str], source_dataset: str) -> dict[str, str]:
    mapped = {
        "replacement_id": row.get("replacement_id", ""),
        "source_smiles": row.get("source_smiles", ""),
        "target_smiles": row.get("target_smiles", ""),
        "edge_weight": row.get("edge_weight", ""),
        "source_name": row.get("source_name", ""),
        "replacement_class": row.get("replacement_class", ""),
        "endpoint_group": row.get("endpoint_group", ""),
        "direction": row.get("direction", ""),
        "source_record_id": row.get("source_record_id", ""),
        "notes": row.get("notes") or row.get("evidence_note") or row.get("provenance_note", ""),
        "source_dataset": source_dataset,
        "source_owner": row.get("source_owner", ""),
        "source_license": row.get("source_license", ""),
        "provenance_level": row.get("provenance_level", ""),
        "provenance_review_status": row.get("source_review_decision") or row.get("provenance_review_status", ""),
        "provenance_note": row.get("provenance_note") or row.get("evidence_note", ""),
        "source_reference": row.get("source_reference", ""),
        "source_confidence_tier": row.get("source_confidence_tier", ""),
        "source_confidence_score": row.get("source_confidence_score", ""),
        "source_confidence_basis": row.get("source_confidence_basis", ""),
        "row_sha256": row.get("row_sha256", ""),
    }
    return {field: str(mapped.get(field, "")) for field in ONBOARDING_TEMPLATE_COLUMNS}


def fill_rgroup_staging_from_reviewed_sources(
    *,
    root: str | Path = ".",
    staging_dir: str | Path = DEFAULT_STAGING_DIR,
    source_limits: dict[str, int] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    root_path = Path(root)
    staging_root = root_path / staging_dir
    limits = dict(DEFAULT_SOURCE_LIMITS)
    limits.update(source_limits or {})
    rows: list[dict[str, Any]] = []
    total_written = 0
    status_counts: Counter[str] = Counter()

    for source_dataset, relative_feed_path in SOURCE_FEEDS.items():
        feed_path = root_path / relative_feed_path
        destination = staging_root / f"next_rgroup_feed_drop_{source_dataset}.csv"
        source_rows = _read_csv(feed_path)
        complete_rows = [row for row in source_rows if _complete_for_staging(row, source_dataset)]
        selected = complete_rows[: max(0, int(limits.get(source_dataset, 0)))]
        existing_rows = _read_csv(destination)
        if existing_rows and not overwrite:
            write_status = "preserved_existing_staging_rows"
            selected_to_write: list[dict[str, str]] = []
        elif not selected:
            write_status = "no_complete_source_rows"
            selected_to_write = []
        else:
            write_status = "staged"
            selected_to_write = [_to_staging_row(row, source_dataset) for row in selected]
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=ONBOARDING_TEMPLATE_COLUMNS)
                writer.writeheader()
                writer.writerows(selected_to_write)
        observed_staged_count = len(existing_rows) if write_status == "preserved_existing_staging_rows" else len(selected_to_write)
        total_written += observed_staged_count
        status_counts[write_status] += 1
        rows.append(
            {
                "source_dataset": source_dataset,
                "source_feed_path": str(feed_path),
                "staging_path": str(destination),
                "source_row_count": len(source_rows),
                "complete_source_row_count": len(complete_rows),
                "selected_row_count": observed_staged_count,
                "existing_staging_row_count": len(existing_rows),
                "write_status": write_status,
                "selected_replacement_ids": ";".join(row.get("replacement_id", "") for row in selected[: len(selected_to_write)]),
                "next_action": (
                    "Run staging validation and sandbox score-delta review."
                    if write_status in {"staged", "preserved_existing_staging_rows"}
                    else "Use --overwrite only after reviewing existing staged rows."
                    if write_status == "skipped_existing_staging_rows"
                    else "Review source feed completeness before staging."
                ),
            }
        )

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "staged" if total_written else "empty",
        "mode": "rgroup_staging_fill_from_reviewed_sources",
        "row_count": len(rows),
        "staged_row_count": total_written,
        "source_count": len(rows),
        "status_counts": dict(status_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Validate staged files before promotion review.",
            "Treat patent-mined deferred rows as provisional holdout evidence unless a source owner upgrades them.",
        ],
    }


def render_rgroup_staging_fill_markdown(report: dict) -> str:
    lines = [
        "# R-group Staging Fill Report",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Staged rows: `{report.get('staged_row_count')}`",
        "",
        "| Source | Status | Source Rows | Complete | Selected | Next Action |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("source_dataset") or ""),
                    str(row.get("write_status") or ""),
                    str(row.get("source_row_count") or 0),
                    str(row.get("complete_source_row_count") or 0),
                    str(row.get("selected_row_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_staging_fill_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_REPORT_JSON,
    csv_path: str | Path | None = DEFAULT_REPORT_CSV,
    markdown_path: str | Path | None = DEFAULT_REPORT_MD,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "source_dataset",
        "source_feed_path",
        "staging_path",
        "source_row_count",
        "complete_source_row_count",
        "selected_row_count",
        "existing_staging_row_count",
        "write_status",
        "selected_replacement_ids",
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
        md_file.write_text(render_rgroup_staging_fill_markdown(report), encoding="utf-8")
