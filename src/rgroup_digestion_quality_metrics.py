from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_METRICS_JSON = Path("data/substituents/rgroup_digestion_quality_metrics.json")
DEFAULT_METRICS_CSV = Path("data/substituents/rgroup_digestion_quality_metrics.csv")
DEFAULT_METRICS_MD = Path("docs/rgroup_digestion_quality_metrics.md")


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


def _float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _split(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _confidence_bucket(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    if score > 0:
        return "low"
    return "missing"


def _candidate_impact_bucket(row: dict) -> str:
    matched = len(_split(row.get("matched_candidate_ids")))
    decisions = {item.lower() for item in _split(row.get("operator_decisions"))}
    if not matched:
        return "no_current_candidate_match"
    if "approved" in decisions and decisions <= {"approved"}:
        return "approved_candidate_impact"
    if "rejected" in decisions:
        return "rejected_candidate_impact"
    if "deferred" in decisions:
        return "deferred_candidate_impact"
    return "pending_candidate_impact"


def _merge_rows(digestion_rows: list[dict], staged_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    staged_by_key = {(str(row.get("replacement_id") or ""), str(row.get("row_sha256") or "")): row for row in staged_rows}
    merged = []
    for row in digestion_rows:
        staged = staged_by_key.get((str(row.get("replacement_id") or ""), str(row.get("row_sha256") or "")), {})
        score = _float(staged.get("source_confidence_score") or row.get("source_confidence_score"))
        item = {
            **row,
            "source_owner": staged.get("source_owner", ""),
            "source_license": staged.get("source_license", ""),
            "provenance_level": staged.get("provenance_level", ""),
            "provenance_note": staged.get("provenance_note", ""),
            "source_reference": staged.get("source_reference", ""),
            "endpoint_group": staged.get("endpoint_group", ""),
            "direction": staged.get("direction", ""),
            "source_confidence_score_numeric": score,
            "confidence_bucket": _confidence_bucket(score),
            "candidate_impact_bucket": _candidate_impact_bucket(row),
            "provenance_complete": bool(staged.get("provenance_level") and staged.get("provenance_review_status") and staged.get("source_reference")),
            "license_complete": bool(staged.get("source_license")),
            "owner_complete": bool(staged.get("source_owner")),
        }
        merged.append(item)
    return merged


def _group_rows(rows: list[dict[str, Any]], field: str) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = str(row.get(field) or "unassigned")
        groups[value].append(row)
    return sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))


def _metric_row(metric_id: str, metric_type: str, group_key: str, rows: list[dict[str, Any]], *, duplicate_pressure_count: int = 0) -> dict[str, Any]:
    confidences = [_float(row.get("source_confidence_score_numeric")) for row in rows if _float(row.get("source_confidence_score_numeric")) > 0]
    status_counts = Counter(str(row.get("digest_status") or "") for row in rows)
    impact_counts = Counter(str(row.get("candidate_impact_bucket") or "") for row in rows)
    low_confidence = sum(1 for row in rows if row.get("confidence_bucket") in {"low", "missing"})
    provenance_missing = sum(1 for row in rows if not row.get("provenance_complete"))
    license_missing = sum(1 for row in rows if not row.get("license_complete"))
    endpoint_unassigned = sum(1 for row in rows if not row.get("endpoint_group"))
    impacted = sum(1 for row in rows if row.get("candidate_impact_bucket") != "no_current_candidate_match")
    blockers = 0
    warnings = 0
    if provenance_missing or license_missing:
        blockers += provenance_missing + license_missing
    if low_confidence or endpoint_unassigned or duplicate_pressure_count or impact_counts.get("deferred_candidate_impact", 0):
        warnings += low_confidence + endpoint_unassigned + duplicate_pressure_count + impact_counts.get("deferred_candidate_impact", 0)
    quality_status = "blocked" if blockers else "watch" if warnings else "ready"
    return {
        "metric_id": metric_id,
        "metric_type": metric_type,
        "group_key": group_key,
        "row_count": len(rows),
        "quality_status": quality_status,
        "accepted_count": status_counts.get("accepted_for_promotion_review", 0) + status_counts.get("accepted_no_current_candidate_match", 0),
        "deferred_count": status_counts.get("deferred", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "held_out_count": sum(count for key, count in status_counts.items() if key.startswith("held_out")),
        "candidate_impacted_row_count": impacted,
        "candidate_impact_counts": dict(impact_counts.most_common()),
        "confidence_avg": round(mean(confidences), 4) if confidences else 0.0,
        "confidence_min": round(min(confidences), 4) if confidences else 0.0,
        "low_confidence_count": low_confidence,
        "provenance_missing_count": provenance_missing,
        "license_missing_count": license_missing,
        "endpoint_unassigned_count": endpoint_unassigned,
        "duplicate_pressure_count": duplicate_pressure_count,
        "next_action": (
            "Fix missing provenance/license before promotion approval."
            if blockers
            else "Review low-confidence, endpoint, duplicate, or deferred-impact warnings before promotion."
            if warnings
            else "Quality metrics are clean for this group."
        ),
    }


def build_rgroup_digestion_quality_metrics(*, root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    digestion = _read_json(root_path / "data/substituents/rgroup_feed_digestion_ledger.json")
    staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    diff_nav = _read_json(root_path / "data/substituents/feed_absorption_diff_navigator.json")
    rows = _merge_rows(digestion.get("rows") or [], _staged_rows(staging_gate))
    replacement_counts = Counter(str(row.get("replacement_id") or "") for row in rows)
    checksum_counts = Counter(str(row.get("row_sha256") or "") for row in rows)
    duplicate_row_pressure = sum(1 for row in rows if replacement_counts[str(row.get("replacement_id") or "")] > 1 or checksum_counts[str(row.get("row_sha256") or "")] > 1)
    diff_duplicate_pressure = int(diff_nav.get("duplicate_group_count") or 0)

    metric_rows: list[dict[str, Any]] = []
    if rows:
        metric_rows.append(_metric_row("RGDQM-0001", "overall", "all", rows, duplicate_pressure_count=duplicate_row_pressure + diff_duplicate_pressure))
    for field, metric_type in [
        ("source_dataset", "source"),
        ("replacement_class", "replacement_class"),
        ("endpoint_group", "endpoint_group"),
        ("confidence_bucket", "confidence_bucket"),
        ("candidate_impact_bucket", "candidate_impact_bucket"),
    ]:
        for group_key, group_rows in _group_rows(rows, field):
            metric_rows.append(_metric_row(f"RGDQM-{len(metric_rows) + 1:04d}", metric_type, group_key, group_rows))

    status_counts = Counter(str(row.get("quality_status") or "") for row in metric_rows)
    status = "blocked" if status_counts.get("blocked") else "watch" if status_counts.get("watch") else "ready" if metric_rows else "awaiting_rows"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "rgroup_digestion_quality_metrics",
        "row_count": len(metric_rows),
        "digestion_row_count": len(rows),
        "metric_type_counts": dict(Counter(str(row.get("metric_type") or "") for row in metric_rows).most_common()),
        "quality_status_counts": dict(status_counts.most_common()),
        "low_confidence_row_count": sum(1 for row in rows if row.get("confidence_bucket") in {"low", "missing"}),
        "deferred_candidate_impact_row_count": sum(1 for row in rows if row.get("candidate_impact_bucket") == "deferred_candidate_impact"),
        "duplicate_row_pressure_count": duplicate_row_pressure,
        "diff_duplicate_group_count": diff_duplicate_pressure,
        "provenance_missing_row_count": sum(1 for row in rows if not row.get("provenance_complete")),
        "license_missing_row_count": sum(1 for row in rows if not row.get("license_complete")),
        "endpoint_unassigned_row_count": sum(1 for row in rows if not row.get("endpoint_group")),
        "production_scoring_affected": False,
        "rows": metric_rows,
        "recommended_next_actions": [
            "Use source and confidence metrics to choose which staged rows can move from holdout to approval.",
            "Treat duplicate pressure and deferred candidate impact as review warnings, not automatic blockers.",
        ],
    }


def render_rgroup_digestion_quality_metrics_markdown(report: dict) -> str:
    lines = [
        "# R-group Digestion Quality Metrics",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Digestion rows: `{report.get('digestion_row_count')}`",
        "",
        "| Metric | Type | Group | Status | Rows | Low Conf | Missing Prov | Duplicates | Impacted | Next Action |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("metric_id") or ""),
                    str(row.get("metric_type") or ""),
                    str(row.get("group_key") or ""),
                    str(row.get("quality_status") or ""),
                    str(row.get("row_count") or 0),
                    str(row.get("low_confidence_count") or 0),
                    str(row.get("provenance_missing_count") or 0),
                    str(row.get("duplicate_pressure_count") or 0),
                    str(row.get("candidate_impacted_row_count") or 0),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_rgroup_digestion_quality_metrics(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_METRICS_JSON,
    csv_path: str | Path | None = DEFAULT_METRICS_CSV,
    markdown_path: str | Path | None = DEFAULT_METRICS_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "metric_id",
        "metric_type",
        "group_key",
        "row_count",
        "quality_status",
        "accepted_count",
        "deferred_count",
        "rejected_count",
        "held_out_count",
        "candidate_impacted_row_count",
        "candidate_impact_counts",
        "confidence_avg",
        "confidence_min",
        "low_confidence_count",
        "provenance_missing_count",
        "license_missing_count",
        "endpoint_unassigned_count",
        "duplicate_pressure_count",
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
        md_file.write_text(render_rgroup_digestion_quality_metrics_markdown(report), encoding="utf-8")
