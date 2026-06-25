from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SAMPLE_REVIEW_PATH = Path("data/substituents/rgroup_feed_sample_review_queue.csv")
DEFAULT_SAMPLE_REVIEW_COVERAGE_PATH = Path("data/substituents/rgroup_feed_review_coverage.json")
DEFAULT_SAMPLE_REVIEW_COVERAGE_CSV_PATH = Path("data/substituents/rgroup_feed_review_coverage.csv")
REVIEW_DECISIONS = {"accepted", "deferred", "rejected", "retired"}
DEFAULT_COVERAGE_FIELDS = ["source_dataset", "replacement_class", "endpoint_group"]


def _read_rows(path: str | Path) -> tuple[list[dict], list[str]]:
    source = Path(path)
    if not source.exists():
        return [], []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _write_rows(path: str | Path, rows: list[dict], fieldnames: list[str]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(fieldnames)
    for field in ["review_decision", "reviewer", "reviewed_at", "review_notes"]:
        if field not in fields:
            fields.append(field)
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _decision(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def triage_sample_review_decision(row: dict) -> tuple[str, str]:
    """Return a conservative first-pass decision and note for governed feed rows."""
    current = _decision(row.get("review_decision"))
    if current in REVIEW_DECISIONS:
        return current, str(row.get("review_notes") or "").strip()
    status = _decision(row.get("provenance_review_status"))
    dataset = str(row.get("source_dataset") or "").strip().lower()
    if status in {"rejected", "retired"}:
        return status, "Preserved source governance exclusion from provenance review status."
    if dataset == "patent_mined_seed" or status in {"provisional_reviewed", "needs_review", "deferred_review"}:
        return "deferred", "Coverage triage retained provisional source row for later chemist review."
    if status == "reviewed" and dataset in {"analog_series_seed", "literature_bioisostere_seed"}:
        return "accepted", "Coverage triage accepted reviewed curated source row."
    return "deferred", "Coverage triage could not promote source row beyond provisional review."


def sample_review_row_key(row: dict) -> str:
    for field in ("row_sha256", "replacement_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return "|".join(str(row.get(field) or "") for field in ("source_path", "row_number"))


def load_sample_review_queue(path: str | Path = DEFAULT_SAMPLE_REVIEW_PATH) -> list[dict]:
    rows, _ = _read_rows(path)
    return rows


def summarize_sample_review_queue(rows: list[dict]) -> dict:
    decisions = Counter(_decision(row.get("review_decision")) or "pending" for row in rows)
    return {
        "row_count": len(rows),
        "pending_count": decisions.get("pending", 0),
        "decision_counts": dict(decisions.most_common()),
        "source_dataset_counts": dict(Counter(str(row.get("source_dataset") or "unspecified") for row in rows).most_common()),
        "sample_reason_counts": dict(Counter(str(row.get("sample_reason") or "unspecified") for row in rows).most_common()),
        "sample_strategy_counts": dict(Counter(str(row.get("sample_strategy") or "unspecified") for row in rows).most_common()),
        "sample_stratum_count": len({str(row.get("sample_stratum") or "") for row in rows if row.get("sample_stratum")}),
    }


def _parse_sample_stratum(value: object) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for part in str(value or "").split("|"):
        key, sep, raw = part.partition("=")
        if not sep:
            continue
        key = key.strip()
        if key:
            attrs[key] = raw.strip() or "unspecified"
    return attrs


def _coverage_value(row: dict, attrs: dict[str, str], field: str) -> str:
    value = str(row.get(field) or attrs.get(field) or "").strip()
    return value or "unspecified"


def build_sample_review_coverage(
    rows: list[dict],
    *,
    coverage_fields: list[str] | tuple[str, ...] | None = None,
    min_reviewed_per_stratum: int = 1,
) -> dict:
    """Summarize sample-review coverage across governance strata."""
    fields = list(coverage_fields or DEFAULT_COVERAGE_FIELDS)
    grouped: dict[tuple[str, ...], dict] = {}
    for row in rows:
        attrs = _parse_sample_stratum(row.get("sample_stratum"))
        key = tuple(_coverage_value(row, attrs, field) for field in fields)
        if key not in grouped:
            grouped[key] = {
                **{field: value for field, value in zip(fields, key)},
                "review_row_count": 0,
                "pending_count": 0,
                "reviewed_decision_count": 0,
                "accepted_count": 0,
                "deferred_count": 0,
                "rejected_count": 0,
                "retired_count": 0,
                "sample_reason_counts": Counter(),
                "source_path_counts": Counter(),
            }
        item = grouped[key]
        decision = _decision(row.get("review_decision")) or "pending"
        item["review_row_count"] += 1
        if decision == "pending":
            item["pending_count"] += 1
        elif decision in REVIEW_DECISIONS:
            item["reviewed_decision_count"] += 1
            item[f"{decision}_count"] += 1
        else:
            item["pending_count"] += 1
        item["sample_reason_counts"][str(row.get("sample_reason") or "unspecified")] += 1
        item["source_path_counts"][str(row.get("source_path") or "unspecified")] += 1

    min_reviewed = max(0, int(min_reviewed_per_stratum))
    coverage_rows = []
    for key, item in grouped.items():
        reviewed = int(item["reviewed_decision_count"])
        total = int(item["review_row_count"])
        if reviewed <= 0:
            status = "no_review"
        elif reviewed < min_reviewed:
            status = "low_coverage"
        else:
            status = "covered"
        row = {
            field: item.get(field)
            for field in fields
        }
        row.update(
            {
                "coverage_cell_id": "|".join(f"{field}={value}" for field, value in zip(fields, key)),
                "review_row_count": total,
                "reviewed_decision_count": reviewed,
                "pending_count": int(item["pending_count"]),
                "accepted_count": int(item["accepted_count"]),
                "deferred_count": int(item["deferred_count"]),
                "rejected_count": int(item["rejected_count"]),
                "retired_count": int(item["retired_count"]),
                "review_coverage_fraction": round(reviewed / total, 4) if total else 0.0,
                "coverage_status": status,
                "needs_review_count": max(0, min_reviewed - reviewed),
                "sample_reason_counts": dict(item["sample_reason_counts"].most_common()),
                "source_path_counts": dict(item["source_path_counts"].most_common()),
            }
        )
        coverage_rows.append(row)

    status_rank = {"no_review": 0, "low_coverage": 1, "covered": 2}
    coverage_rows.sort(
        key=lambda item: (
            status_rank.get(str(item.get("coverage_status")), 9),
            -int(item.get("review_row_count") or 0),
            *(str(item.get(field) or "") for field in fields),
        )
    )
    status_counts = Counter(str(row.get("coverage_status") or "unknown") for row in coverage_rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "review_row_count": len(rows),
        "coverage_fields": fields,
        "min_reviewed_per_stratum": min_reviewed,
        "coverage_cell_count": len(coverage_rows),
        "no_review_count": status_counts.get("no_review", 0),
        "low_coverage_count": status_counts.get("low_coverage", 0),
        "covered_count": status_counts.get("covered", 0),
        "coverage_status_counts": dict(status_counts.most_common()),
        "rows": coverage_rows,
    }


def write_sample_review_coverage_report(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_SAMPLE_REVIEW_COVERAGE_PATH,
    csv_path: str | Path | None = DEFAULT_SAMPLE_REVIEW_COVERAGE_CSV_PATH,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = report.get("rows") or []
    fields = list(report.get("coverage_fields") or DEFAULT_COVERAGE_FIELDS)
    preferred = [
        *fields,
        "coverage_status",
        "review_row_count",
        "reviewed_decision_count",
        "pending_count",
        "accepted_count",
        "deferred_count",
        "rejected_count",
        "retired_count",
        "review_coverage_fraction",
        "needs_review_count",
        "coverage_cell_id",
    ]
    extras = sorted({key for row in rows for key in row if key not in preferred})
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    with csv_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=preferred + extras)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in preferred + extras})


def filter_sample_review_queue(
    rows: list[dict],
    *,
    source_dataset: str | None = None,
    review_decision: str | None = None,
    sample_reason_contains: str | None = None,
    sample_stratum_contains: str | None = None,
    source_path_contains: str | None = None,
) -> list[dict]:
    wanted_decision = _decision(review_decision)
    reason_text = str(sample_reason_contains or "").strip().lower()
    stratum_text = str(sample_stratum_contains or "").strip().lower()
    source_path_text = str(source_path_contains or "").strip().lower()
    filtered = []
    for row in rows:
        if source_dataset and str(row.get("source_dataset") or "") != source_dataset:
            continue
        row_decision = _decision(row.get("review_decision")) or "pending"
        if wanted_decision and row_decision != wanted_decision:
            continue
        if reason_text and reason_text not in str(row.get("sample_reason") or "").lower():
            continue
        if stratum_text and stratum_text not in str(row.get("sample_stratum") or "").lower():
            continue
        if source_path_text and source_path_text not in str(row.get("source_path") or "").lower():
            continue
        filtered.append(dict(row))
    return filtered


def bulk_update_sample_review_queue(
    path: str | Path = DEFAULT_SAMPLE_REVIEW_PATH,
    *,
    row_keys: list[str] | set[str] | tuple[str, ...],
    review_decision: str,
    reviewer: str = "",
    review_notes: str = "",
    reviewed_at: str | None = None,
    write: bool = True,
) -> dict:
    decision = _decision(review_decision)
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"review_decision must be one of {sorted(REVIEW_DECISIONS)}")
    wanted = {str(key) for key in row_keys if str(key)}
    rows, fieldnames = _read_rows(path)
    reviewed_at = reviewed_at or datetime.now(timezone.utc).isoformat()
    updated = []
    for row in rows:
        item = dict(row)
        key = sample_review_row_key(item)
        if key in wanted:
            item["review_decision"] = decision
            item["reviewer"] = reviewer or item.get("reviewer") or ""
            item["reviewed_at"] = reviewed_at
            item["review_notes"] = review_notes or item.get("review_notes") or ""
            updated.append(key)
        row.update(item)
    if write and updated:
        _write_rows(path, rows, fieldnames)
    return {
        "queue_path": str(Path(path).resolve()),
        "input_key_count": len(wanted),
        "updated_count": len(updated),
        "missing_key_count": len(wanted.difference(updated)),
        "review_decision": decision,
        "reviewer": reviewer,
        "write": bool(write),
    }


def triage_sample_review_queue(
    path: str | Path = DEFAULT_SAMPLE_REVIEW_PATH,
    *,
    reviewer: str = "coverage_triage",
    reviewed_at: str | None = None,
    write: bool = True,
) -> dict:
    rows, fieldnames = _read_rows(path)
    reviewed_at = reviewed_at or datetime.now(timezone.utc).isoformat()
    decision_counts: Counter = Counter()
    updated_count = 0
    for row in rows:
        before = _decision(row.get("review_decision"))
        decision, note = triage_sample_review_decision(row)
        if decision not in REVIEW_DECISIONS:
            continue
        decision_counts[decision] += 1
        if before == decision and str(row.get("reviewer") or "").strip():
            continue
        row["review_decision"] = decision
        row["reviewer"] = row.get("reviewer") or reviewer
        row["reviewed_at"] = row.get("reviewed_at") or reviewed_at
        row["review_notes"] = row.get("review_notes") or note
        updated_count += 1
    if write and updated_count:
        _write_rows(path, rows, fieldnames)
    return {
        "queue_path": str(Path(path).resolve()),
        "row_count": len(rows),
        "updated_count": updated_count,
        "decision_counts": dict(decision_counts.most_common()),
        "reviewer": reviewer,
        "write": bool(write),
    }
