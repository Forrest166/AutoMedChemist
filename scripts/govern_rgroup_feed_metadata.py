from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_expansion import (  # noqa: E402
    ADDITIONAL_SOURCE_KEYS,
    SOURCE_PROVENANCE_FIELDS,
    _provenance_defaults,
    _row_sha256,
    _source_dataset_for_path,
)

GOVERNANCE_FIELDS = [
    "source_owner",
    "source_license",
    "provenance_level",
    "provenance_review_status",
    "provenance_note",
    "row_sha256",
]
SOURCE_REVIEW_FIELDS = [
    "source_confidence_tier",
    "source_confidence_score",
    "source_confidence_basis",
    "source_review_decision",
    "source_reviewed_by",
    "source_reviewed_at",
    "source_review_note",
]

DEFAULT_FEED_MANIFEST_PATH = ROOT / "data" / "replacements" / "feed_source_manifest.yaml"
DEFAULT_SAMPLE_REVIEW_PATH = ROOT / "data" / "substituents" / "rgroup_feed_sample_review_queue.csv"
DEFAULT_SAMPLE_REVIEW_APPLY_REPORT_PATH = ROOT / "data" / "substituents" / "rgroup_feed_sample_review_apply_report.json"
DEFAULT_SAMPLE_STRATA_FIELDS = [
    "source_dataset",
    "provenance_review_status",
    "replacement_class",
    "endpoint_group",
]
SAMPLE_KEY_EXCLUDED_FIELDS = set(GOVERNANCE_FIELDS + SOURCE_REVIEW_FIELDS)


def _read_table(path: Path) -> tuple[list[dict], list[str], str]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [dict(row) for row in reader], list(reader.fieldnames or []), delimiter


def _write_table(path: Path, rows: list[dict], fieldnames: list[str], delimiter: str) -> None:
    out_fields = list(fieldnames)
    for field in GOVERNANCE_FIELDS + SOURCE_REVIEW_FIELDS:
        if field not in out_fields:
            out_fields.append(field)
    for row in rows:
        for field in row:
            if field not in out_fields:
                out_fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields, delimiter=delimiter)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in out_fields})


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def load_feed_manifest(path: str | Path | None) -> dict:
    if not path:
        return {}
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {}
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    return _apply_policy_templates(manifest)


def _apply_policy_templates(manifest: dict) -> dict:
    manifest = dict(manifest or {})
    templates = manifest.get("policy_templates") or {}
    sources = {}
    for source_id, source_entry in (manifest.get("sources") or {}).items():
        entry = dict(source_entry or {})
        template_id = entry.get("policy_template")
        template = dict(templates.get(template_id) or {}) if template_id else {}
        merged = {**template, **entry}
        if template_id:
            merged["policy_template"] = template_id
        sources[source_id] = merged
    manifest["sources"] = sources
    return manifest


def _manifest_source_id(path: Path, row: dict, manifest: dict) -> str:
    explicit = row.get("source_dataset") or row.get("dataset") or row.get("source_type")
    if explicit:
        return str(explicit)
    file_manifest = (manifest.get("file_manifests") or {}).get(path.name)
    if isinstance(file_manifest, dict) and file_manifest.get("source_dataset"):
        return str(file_manifest["source_dataset"])
    file_sources = manifest.get("files") or {}
    source_id = file_sources.get(path.name)
    if source_id:
        return str(source_id)
    return _source_dataset_for_path(path, row)


def _manifest_source_entry(path: Path, row: dict, manifest: dict) -> tuple[str, dict | None]:
    source_id = _manifest_source_id(path, row, manifest)
    sources = manifest.get("sources") or {}
    entry = dict(sources.get(source_id) or {})
    file_manifest = (manifest.get("file_manifests") or {}).get(path.name)
    if isinstance(file_manifest, dict):
        entry.update({key: value for key, value in file_manifest.items() if key != "source_dataset"})
    if not entry:
        entry = None
    return source_id, dict(entry) if isinstance(entry, dict) else None


def _file_freshness_issues(path: Path, entry: dict | None) -> list[dict]:
    if not entry or not entry.get("freshness_sla_days"):
        return []
    try:
        freshness_sla_days = float(entry.get("freshness_sla_days") or 0)
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return [{"path": str(path), "issue_type": "freshness_check_failed"}]
    age_days = (datetime.now(timezone.utc) - modified_at).total_seconds() / 86400
    if freshness_sla_days > 0 and age_days > freshness_sla_days:
        return [
            {
                "path": str(path),
                "issue_type": "source_file_stale",
                "age_days": round(age_days, 3),
                "freshness_sla_days": freshness_sla_days,
                "modified_at": modified_at.isoformat(),
            }
        ]
    return []


def _allowlist_issues(path: Path, row: dict, row_number: int, manifest: dict) -> list[dict]:
    if not manifest:
        return []
    source_id, entry = _manifest_source_entry(path, row, manifest)
    base = {
        "path": str(path),
        "row_number": row_number,
        "replacement_id": row.get("replacement_id"),
        "source_dataset": source_id,
        "row_sha256": row.get("row_sha256"),
    }
    if entry is None:
        return [{**base, "issue_type": "source_not_allowlisted", "field": "source_dataset", "value": source_id}]
    issues = []
    expected_owner = entry.get("source_owner")
    if expected_owner and str(row.get("source_owner") or "") != str(expected_owner):
        issues.append({**base, "issue_type": "source_owner_mismatch", "field": "source_owner", "value": row.get("source_owner")})
    checks = [
        ("source_license", "accepted_licenses"),
        ("provenance_level", "accepted_provenance_levels"),
        ("provenance_review_status", "accepted_review_statuses"),
    ]
    for field, manifest_field in checks:
        allowed = {str(item) for item in _as_list(entry.get(manifest_field))}
        value = str(row.get(field) or "")
        if allowed and value not in allowed:
            issues.append({**base, "issue_type": f"{field}_not_allowed", "field": field, "value": value})
    return issues


def _sample_key(row: dict) -> str:
    replacement_id = str(row.get("replacement_id") or "").strip()
    if replacement_id:
        return f"replacement_id:{replacement_id}"
    payload = {key: value for key, value in row.items() if key not in SAMPLE_KEY_EXCLUDED_FIELDS}
    return f"stable_hash:{_row_sha256(payload)}"


def _source_row_hash(row: dict) -> str:
    return str(row.get("row_sha256") or _row_sha256(row))


def _sample_stratum(path: Path, row: dict, fields: list[str]) -> str:
    parts = []
    for field in fields:
        if field == "source_dataset":
            value = _source_dataset_for_path(path, row)
        else:
            value = row.get(field)
        text = str(value or "").strip() or "unspecified"
        parts.append(f"{field}={text}")
    return "|".join(parts)


def _sampled_hashes_for_rows(
    path: Path,
    rows: list[dict],
    *,
    sample_size: int,
    sample_strategy: str,
    strata_fields: list[str],
) -> set[str]:
    if sample_size <= 0:
        return set()
    sorted_rows = sorted(rows, key=_sample_key)
    if sample_strategy != "stratified":
        return {_sample_key(row) for row in sorted_rows[:sample_size]}
    grouped: dict[str, list[dict]] = {}
    for row in sorted_rows:
        grouped.setdefault(_sample_stratum(path, row, strata_fields), []).append(row)
    selected: list[dict] = []
    strata = sorted(grouped.items(), key=lambda item: hashlib.sha256(item[0].encode("utf-8")).hexdigest())
    round_index = 0
    while len(selected) < sample_size:
        added = False
        for _, group_rows in strata:
            if round_index < len(group_rows):
                selected.append(group_rows[round_index])
                added = True
                if len(selected) >= sample_size:
                    break
        if not added:
            break
        round_index += 1
    return {_sample_key(row) for row in selected}


def _sample_review_rows(
    path: Path,
    rows: list[dict],
    manifest: dict,
    sample_size: int,
    *,
    sample_strategy: str = "stratified",
    strata_fields: list[str] | None = None,
) -> list[dict]:
    if not rows:
        return []
    first = rows[0] if rows else {}
    _, entry = _manifest_source_entry(path, first, manifest) if manifest else ("", None)
    entry_sample_size = int((entry or {}).get("sample_review_size") or sample_size or 0)
    strata_fields = strata_fields or DEFAULT_SAMPLE_STRATA_FIELDS
    sampled_hashes = _sampled_hashes_for_rows(
        path,
        rows,
        sample_size=max(0, entry_sample_size),
        sample_strategy=sample_strategy,
        strata_fields=strata_fields,
    )
    review_rows = []
    for index, row in enumerate(rows, start=1):
        sample_key = _sample_key(row)
        row_hash = _source_row_hash(row)
        status = str(row.get("provenance_review_status") or "")
        reason = ""
        if status not in {"reviewed"}:
            reason = "provisional_or_needs_review"
        if sample_key in sampled_hashes:
            audit_reason = "stratified_sample_audit" if sample_strategy == "stratified" else "sample_audit"
            reason = audit_reason if not reason else f"{reason};{audit_reason}"
        if not reason:
            continue
        review_rows.append(
            {
                "source_path": str(path),
                "row_number": index,
                "replacement_id": row.get("replacement_id"),
                "source_dataset": _source_dataset_for_path(path, row),
                "source_smiles": row.get("source_smiles") or row.get("source_canonical_smiles"),
                "target_smiles": row.get("target_smiles") or row.get("target_canonical_smiles"),
                "source_owner": row.get("source_owner"),
                "source_license": row.get("source_license"),
                "provenance_level": row.get("provenance_level"),
                "provenance_review_status": row.get("provenance_review_status"),
                "row_sha256": row_hash,
                "sample_reason": reason,
                "sample_strategy": sample_strategy,
                "sample_stratum": _sample_stratum(path, row, strata_fields),
                "review_decision": "",
                "reviewer": "",
                "reviewed_at": "",
                "review_notes": "",
            }
        )
    return review_rows


def _govern_row(path: Path, row: dict) -> tuple[dict, list[str]]:
    source_dataset = _source_dataset_for_path(path, row)
    defaults = _provenance_defaults(source_dataset)
    item = dict(row)
    changed = []
    for field, value in defaults.items():
        if not str(item.get(field) or "").strip():
            item[field] = value
            changed.append(field)
    if not str(item.get("provenance_note") or "").strip():
        item["provenance_note"] = item.get("evidence_note") or item.get("source_reference") or ""
        changed.append("provenance_note")
    checksum = _row_sha256(item)
    if item.get("row_sha256") != checksum:
        item["row_sha256"] = checksum
        changed.append("row_sha256")
    return item, changed


def govern_table(
    path: Path,
    *,
    write: bool = False,
    manifest: dict | None = None,
    sample_size: int = 25,
    sample_strategy: str = "stratified",
    sample_strata_fields: list[str] | None = None,
) -> dict:
    rows, fieldnames, delimiter = _read_table(path)
    governed = []
    changed_fields = set()
    rows_changed = 0
    missing_before = 0
    row_level_provenance_count = 0
    allowlist_issues = []
    source_counts = Counter()
    review_status_counts = Counter()
    for index, row in enumerate(rows, start=1):
        if any(not str(row.get(field) or "").strip() for field in SOURCE_PROVENANCE_FIELDS):
            missing_before += 1
        item, changed = _govern_row(path, row)
        governed.append(item)
        allowlist_issues.extend(_allowlist_issues(path, item, index, manifest or {}))
        source_counts[_manifest_source_id(path, item, manifest or {})] += 1
        review_status_counts[str(item.get("provenance_review_status") or "unspecified")] += 1
        if all(str(item.get(field) or "").strip() for field in SOURCE_PROVENANCE_FIELDS):
            row_level_provenance_count += 1
        if changed:
            rows_changed += 1
            changed_fields.update(changed)
    if write:
        out_fields = [field for field in fieldnames if field != "row_sha256"]
        _write_table(path, governed, out_fields, delimiter)
    _, entry = _manifest_source_entry(path, governed[0], manifest or {}) if governed else ("", None)
    freshness_issues = _file_freshness_issues(path, entry)
    return {
        "path": str(path),
        "format": "table",
        "row_count": len(rows),
        "rows_changed": rows_changed,
        "missing_metadata_before": missing_before,
        "row_level_provenance_count": row_level_provenance_count,
        "changed_fields": sorted(changed_fields),
        "allowlist_issue_count": len(allowlist_issues),
        "allowlist_issues": allowlist_issues,
        "freshness_issue_count": len(freshness_issues),
        "freshness_issues": freshness_issues,
        "source_counts": dict(source_counts.most_common()),
        "review_status_counts": dict(review_status_counts.most_common()),
        "sample_review_rows": _sample_review_rows(
            path,
            governed,
            manifest or {},
            sample_size,
            sample_strategy=sample_strategy,
            strata_fields=sample_strata_fields,
        ),
    }


def _structured_rows(payload: object) -> tuple[list[dict], str | None]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)], None
    if isinstance(payload, dict):
        for key in ADDITIONAL_SOURCE_KEYS:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, dict)], key
    return [], None


def _read_structured_payload(path: Path) -> tuple[object, list[dict], str | None, str]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_format = "json"
    else:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        source_format = "yaml"
    rows, row_key = _structured_rows(payload)
    return payload, rows, row_key, source_format


def _write_structured_payload(path: Path, payload: object, rows: list[dict], row_key: str | None, source_format: str) -> None:
    if row_key is None:
        payload = rows
    elif isinstance(payload, dict):
        payload[row_key] = rows
    text = (
        json.dumps(payload, indent=2, sort_keys=True)
        if source_format == "json"
        else yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    )
    path.write_text(text, encoding="utf-8")


def govern_structured(
    path: Path,
    *,
    write: bool = False,
    manifest: dict | None = None,
    sample_size: int = 25,
    sample_strategy: str = "stratified",
    sample_strata_fields: list[str] | None = None,
) -> dict:
    payload, rows, row_key, source_format = _read_structured_payload(path)
    governed = []
    changed_fields = set()
    rows_changed = 0
    missing_before = 0
    row_level_provenance_count = 0
    allowlist_issues = []
    source_counts = Counter()
    review_status_counts = Counter()
    for index, row in enumerate(rows, start=1):
        if any(not str(row.get(field) or "").strip() for field in SOURCE_PROVENANCE_FIELDS):
            missing_before += 1
        item, changed = _govern_row(path, row)
        governed.append(item)
        allowlist_issues.extend(_allowlist_issues(path, item, index, manifest or {}))
        source_counts[_manifest_source_id(path, item, manifest or {})] += 1
        review_status_counts[str(item.get("provenance_review_status") or "unspecified")] += 1
        if all(str(item.get(field) or "").strip() for field in SOURCE_PROVENANCE_FIELDS):
            row_level_provenance_count += 1
        if changed:
            rows_changed += 1
            changed_fields.update(changed)
    if write:
        _write_structured_payload(path, payload, governed, row_key, source_format)
    _, entry = _manifest_source_entry(path, governed[0], manifest or {}) if governed else ("", None)
    freshness_issues = _file_freshness_issues(path, entry)
    return {
        "path": str(path),
        "format": source_format,
        "row_count": len(rows),
        "rows_changed": rows_changed,
        "missing_metadata_before": missing_before,
        "row_level_provenance_count": row_level_provenance_count,
        "changed_fields": sorted(changed_fields),
        "allowlist_issue_count": len(allowlist_issues),
        "allowlist_issues": allowlist_issues,
        "freshness_issue_count": len(freshness_issues),
        "freshness_issues": freshness_issues,
        "source_counts": dict(source_counts.most_common()),
        "review_status_counts": dict(review_status_counts.most_common()),
        "sample_review_rows": _sample_review_rows(
            path,
            governed,
            manifest or {},
            sample_size,
            sample_strategy=sample_strategy,
            strata_fields=sample_strata_fields,
        ),
    }


def govern_path(
    path: Path,
    *,
    write: bool = False,
    manifest: dict | None = None,
    sample_size: int = 25,
    sample_strategy: str = "stratified",
    sample_strata_fields: list[str] | None = None,
) -> dict | None:
    if path.suffix.lower() in {".csv", ".tsv"}:
        return govern_table(
            path,
            write=write,
            manifest=manifest,
            sample_size=sample_size,
            sample_strategy=sample_strategy,
            sample_strata_fields=sample_strata_fields,
        )
    if path.suffix.lower() in {".json", ".yaml", ".yml"}:
        return govern_structured(
            path,
            write=write,
            manifest=manifest,
            sample_size=sample_size,
            sample_strategy=sample_strategy,
            sample_strata_fields=sample_strata_fields,
        )
    return None


def write_sample_review_queue(rows: list[dict], path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_path",
        "row_number",
        "replacement_id",
        "source_dataset",
        "source_smiles",
        "target_smiles",
        "source_owner",
        "source_license",
        "provenance_level",
        "provenance_review_status",
        "row_sha256",
        "sample_reason",
        "sample_strategy",
        "sample_stratum",
        "review_decision",
        "reviewer",
        "reviewed_at",
        "review_notes",
    ]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _review_row_keys(row: dict) -> list[str]:
    keys = []
    for field in ["row_sha256", "replacement_id"]:
        value = str(row.get(field) or "").strip()
        if value:
            keys.append(f"{field}:{value}")
    source_path = str(row.get("source_path") or "").strip()
    row_number = str(row.get("row_number") or "").strip()
    if source_path or row_number:
        keys.append(f"source_row:{source_path}|{row_number}")
    return keys


def _review_row_key(row: dict) -> str:
    keys = _review_row_keys(row)
    return keys[0] if keys else ""


def preserve_sample_review_decisions(rows: list[dict], existing_queue_path: str | Path) -> list[dict]:
    path = Path(existing_queue_path)
    if not path.exists():
        return rows
    try:
        existing_rows, _, _ = _read_table(path)
    except Exception:
        return rows
    decision_lookup = {}
    for row in existing_rows:
        decision = _normalize_review_decision(row.get("review_decision"))
        if not decision:
            continue
        preserved = {
            "review_decision": decision,
            "reviewer": row.get("reviewer") or "",
            "reviewed_at": row.get("reviewed_at") or "",
            "review_notes": row.get("review_notes") or "",
        }
        for key in _review_row_keys(row):
            decision_lookup[key] = preserved
    if not decision_lookup:
        return rows
    preserved = []
    for row in rows:
        item = dict(row)
        previous = None
        for key in _review_row_keys(item):
            previous = decision_lookup.get(key)
            if previous:
                break
        if previous and not _normalize_review_decision(item.get("review_decision")):
            item.update(previous)
        preserved.append(item)
    return preserved


def _normalize_review_decision(value: object) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    aliases = {
        "accept": "accepted",
        "accepted": "accepted",
        "approve": "accepted",
        "approved": "accepted",
        "pass": "accepted",
        "defer": "deferred",
        "deferred": "deferred",
        "needs_followup": "deferred",
        "needs_review": "deferred",
        "reject": "rejected",
        "rejected": "rejected",
        "exclude": "rejected",
        "excluded": "rejected",
        "retire": "retired",
        "retired": "retired",
    }
    return aliases.get(text, "")


def _resolve_review_source_path(value: object) -> Path:
    path = Path(str(value or "").strip())
    return path if path.is_absolute() else ROOT / path


def _review_confidence_fields(source_row: dict, review_row: dict, decision: str, reviewed_at: str) -> dict:
    dataset = _source_dataset_for_path(Path(review_row.get("source_path") or ""), source_row)
    reviewer = str(review_row.get("reviewer") or "").strip()
    note = str(review_row.get("review_notes") or "").strip()
    if decision == "accepted":
        confidence_tier = f"{dataset}_sample_reviewed"
        confidence_score = "0.86"
        review_status = "reviewed"
        basis = "Accepted by sample review."
    elif decision == "deferred":
        confidence_tier = f"{dataset}_deferred_review"
        confidence_score = "0.42"
        review_status = "deferred_review"
        basis = "Deferred by sample review; retained only as provisional evidence."
    elif decision == "retired":
        confidence_tier = "source_review_retired"
        confidence_score = "0.00"
        review_status = "retired"
        basis = "Retired by sample review and excluded from downstream expansion."
    else:
        confidence_tier = "source_review_rejected"
        confidence_score = "0.00"
        review_status = "rejected"
        basis = "Rejected by sample review and excluded from downstream expansion."
    if reviewer:
        basis = f"{basis} reviewer={reviewer}."
    if note:
        basis = f"{basis} note={note}"
    return {
        "provenance_review_status": review_status,
        "source_confidence_tier": confidence_tier,
        "source_confidence_score": confidence_score,
        "source_confidence_basis": basis,
        "source_review_decision": decision,
        "source_reviewed_by": reviewer,
        "source_reviewed_at": str(review_row.get("reviewed_at") or "").strip() or reviewed_at,
        "source_review_note": note,
    }


def _load_editable_rows(path: Path) -> tuple[list[dict], dict]:
    if path.suffix.lower() in {".csv", ".tsv"}:
        rows, fieldnames, delimiter = _read_table(path)
        return rows, {"format": "table", "fieldnames": fieldnames, "delimiter": delimiter}
    if path.suffix.lower() in {".json", ".yaml", ".yml"}:
        payload, rows, row_key, source_format = _read_structured_payload(path)
        return rows, {"format": source_format, "payload": payload, "row_key": row_key}
    return [], {"format": "unsupported"}


def _write_editable_rows(path: Path, rows: list[dict], meta: dict) -> None:
    if meta.get("format") == "table":
        _write_table(path, rows, meta.get("fieldnames") or [], meta.get("delimiter") or ",")
    elif meta.get("format") in {"json", "yaml"}:
        _write_structured_payload(path, meta.get("payload"), rows, meta.get("row_key"), meta["format"])


def _match_review_row(rows: list[dict], review_row: dict) -> int | None:
    row_hash = str(review_row.get("row_sha256") or "").strip()
    if row_hash:
        for index, row in enumerate(rows):
            if str(row.get("row_sha256") or _row_sha256(row)) == row_hash:
                return index
    replacement_id = str(review_row.get("replacement_id") or "").strip()
    if replacement_id:
        matches = [index for index, row in enumerate(rows) if str(row.get("replacement_id") or "").strip() == replacement_id]
        if len(matches) == 1:
            return matches[0]
    try:
        row_number = int(float(review_row.get("row_number") or 0))
    except (TypeError, ValueError):
        row_number = 0
    if 1 <= row_number <= len(rows):
        return row_number - 1
    return None


def apply_sample_review_queue(
    queue_path: str | Path = DEFAULT_SAMPLE_REVIEW_PATH,
    *,
    write: bool = False,
    reviewed_at: str | None = None,
) -> dict:
    reviewed_at = reviewed_at or datetime.now(timezone.utc).isoformat()
    queue_rows, _, _ = _read_table(Path(queue_path))
    decisions = []
    skipped = []
    for row_number, row in enumerate(queue_rows, start=1):
        decision = _normalize_review_decision(row.get("review_decision"))
        if not decision:
            skipped.append({"queue_row_number": row_number, "reason": "blank_or_unknown_decision"})
            continue
        if not str(row.get("source_path") or "").strip():
            skipped.append({"queue_row_number": row_number, "reason": "missing_source_path"})
            continue
        decisions.append({**row, "queue_row_number": row_number, "review_decision": decision})

    grouped: dict[Path, list[dict]] = {}
    for row in decisions:
        grouped.setdefault(_resolve_review_source_path(row.get("source_path")), []).append(row)

    source_reports = []
    applied_count = 0
    unmatched = []
    for source_path, review_rows in sorted(grouped.items(), key=lambda item: str(item[0])):
        if not source_path.exists():
            missing = [
                {"queue_row_number": row.get("queue_row_number"), "source_path": str(source_path), "reason": "source_missing"}
                for row in review_rows
            ]
            unmatched.extend(missing)
            source_reports.append({"path": str(source_path), "format": "missing", "applied_count": 0, "unmatched_count": len(missing)})
            continue
        rows, meta = _load_editable_rows(source_path)
        if meta.get("format") == "unsupported":
            unsupported = [
                {
                    "queue_row_number": row.get("queue_row_number"),
                    "source_path": str(source_path),
                    "reason": "unsupported_source_format",
                }
                for row in review_rows
            ]
            unmatched.extend(unsupported)
            source_reports.append({"path": str(source_path), "format": "unsupported", "applied_count": 0, "unmatched_count": len(unsupported)})
            continue

        applied_for_source = 0
        for review_row in review_rows:
            match_index = _match_review_row(rows, review_row)
            if match_index is None:
                unmatched.append(
                    {
                        "queue_row_number": review_row.get("queue_row_number"),
                        "source_path": str(source_path),
                        "replacement_id": review_row.get("replacement_id"),
                        "row_sha256": review_row.get("row_sha256"),
                        "reason": "source_row_not_matched",
                    }
                )
                continue
            updated = dict(rows[match_index])
            updated.update(
                _review_confidence_fields(
                    updated,
                    {**review_row, "source_path": str(source_path)},
                    review_row["review_decision"],
                    reviewed_at,
                )
            )
            updated["row_sha256"] = _row_sha256(updated)
            rows[match_index] = updated
            applied_for_source += 1
        if write and applied_for_source:
            _write_editable_rows(source_path, rows, meta)
        applied_count += applied_for_source
        source_reports.append(
            {
                "path": str(source_path),
                "format": meta.get("format"),
                "input_review_count": len(review_rows),
                "applied_count": applied_for_source,
                "unmatched_count": len(review_rows) - applied_for_source,
                "written": bool(write and applied_for_source),
            }
        )

    return {
        "created_at": reviewed_at,
        "write": bool(write),
        "queue_path": str(Path(queue_path).resolve()),
        "queue_row_count": len(queue_rows),
        "decision_count": len(decisions),
        "applied_count": applied_count,
        "skipped_count": len(skipped),
        "unmatched_count": len(unmatched),
        "source_reports": source_reports,
        "skipped_rows": skipped,
        "unmatched_rows": unmatched,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Add row checksums and provenance fields to governed R-group feed tables.")
    parser.add_argument(
        "--glob",
        action="append",
        default=None,
        help="File glob to govern. May be repeated. Defaults to data/replacements/feeds/*.csv.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--manifest", default=str(DEFAULT_FEED_MANIFEST_PATH))
    parser.add_argument("--require-allowlist", action="store_true")
    parser.add_argument("--require-freshness", action="store_true")
    parser.add_argument("--sample-size", type=int, default=25)
    parser.add_argument("--sample-strategy", choices=["stratified", "deterministic"], default="stratified")
    parser.add_argument(
        "--sample-strata-field",
        action="append",
        default=None,
        help="Field used for stratified sample-review selection. May be repeated.",
    )
    parser.add_argument("--sample-review-out", default=str(DEFAULT_SAMPLE_REVIEW_PATH))
    parser.add_argument("--apply-sample-review", action="store_true", help="Apply accepted/deferred/rejected decisions from the sample review queue.")
    parser.add_argument("--sample-review-in", default=str(DEFAULT_SAMPLE_REVIEW_PATH))
    parser.add_argument("--sample-review-apply-report-out", default=str(DEFAULT_SAMPLE_REVIEW_APPLY_REPORT_PATH))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "rgroup_feed_metadata_report.json"))
    args = parser.parse_args()

    if args.apply_sample_review:
        payload = apply_sample_review_queue(args.sample_review_in, write=args.write)
        out = Path(args.sample_review_apply_report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(
            json.dumps(
                {key: payload[key] for key in ["queue_row_count", "decision_count", "applied_count", "unmatched_count", "write"]},
                indent=2,
            )
        )
        if payload["unmatched_count"]:
            raise SystemExit(1)
        return

    manifest = load_feed_manifest(args.manifest)
    patterns = args.glob or [str(ROOT / "data" / "replacements" / "feeds" / "*.csv")]
    paths = []
    for pattern in patterns:
        paths.extend(Path(item) for item in sorted(glob.glob(pattern)))
    reports = [
        report
        for report in (
            govern_path(
                path,
                write=args.write,
                manifest=manifest,
                sample_size=args.sample_size,
                sample_strategy=args.sample_strategy,
                sample_strata_fields=args.sample_strata_field or DEFAULT_SAMPLE_STRATA_FIELDS,
            )
            for path in paths
        )
        if report is not None
    ]
    sample_review_rows = []
    for report in reports:
        sample_review_rows.extend(report.pop("sample_review_rows", []))
    sample_review_rows = preserve_sample_review_decisions(sample_review_rows, args.sample_review_out)
    write_sample_review_queue(sample_review_rows, args.sample_review_out)
    allowlist_issue_count = sum(int(row.get("allowlist_issue_count") or 0) for row in reports)
    freshness_issue_count = sum(int(row.get("freshness_issue_count") or 0) for row in reports)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "write": bool(args.write),
        "manifest_path": str(Path(args.manifest).resolve()) if args.manifest else None,
        "feed_count": len(reports),
        "row_count": sum(int(row.get("row_count") or 0) for row in reports),
        "rows_changed": sum(int(row.get("rows_changed") or 0) for row in reports),
        "missing_metadata_before": sum(int(row.get("missing_metadata_before") or 0) for row in reports),
        "row_level_provenance_count": sum(int(row.get("row_level_provenance_count") or 0) for row in reports),
        "allowlist_issue_count": allowlist_issue_count,
        "freshness_issue_count": freshness_issue_count,
        "sample_review_count": len(sample_review_rows),
        "sample_strategy": args.sample_strategy,
        "sample_strata_fields": args.sample_strata_field or DEFAULT_SAMPLE_STRATA_FIELDS,
        "sample_review_out": str(Path(args.sample_review_out).resolve()),
        "reports": reports,
        "report_sha256": hashlib.sha256(json.dumps(reports, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    out = Path(args.report_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                key: payload[key]
                for key in [
                    "feed_count",
                    "row_count",
                    "rows_changed",
                    "missing_metadata_before",
                    "allowlist_issue_count",
                    "freshness_issue_count",
                    "sample_review_count",
                ]
            },
            indent=2,
        )
    )
    if args.require_allowlist and allowlist_issue_count:
        raise SystemExit(1)
    if args.require_freshness and freshness_issue_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
