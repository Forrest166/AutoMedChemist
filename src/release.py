from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .library import ensure_list, load_yaml_records


TRACKED_FIELDS = [
    "name",
    "smiles",
    "connection_type",
    "allowed_site_types",
    "direction_tags",
    "class",
    "risk.default_enabled",
    "risk.risk_tags",
    "priority.default_rank",
    "review.status",
]


def _field(record: dict, dotted: str):
    value = record
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    return value


def _index(records: list[dict]) -> dict[str, dict]:
    return {record["substituent_id"]: record for record in records}


def compare_libraries(previous_records: list[dict], current_records: list[dict]) -> dict:
    previous = _index(previous_records)
    current = _index(current_records)
    previous_ids = set(previous)
    current_ids = set(current)

    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    changed = []
    status_changes = []
    risk_changes = []

    for sid in sorted(previous_ids.intersection(current_ids)):
        before = previous[sid]
        after = current[sid]
        field_changes = []
        for field in TRACKED_FIELDS:
            old = _field(before, field)
            new = _field(after, field)
            if old != new:
                field_changes.append({"field": field, "from": old, "to": new})
        if field_changes:
            item = {"substituent_id": sid, "name": after.get("name"), "changes": field_changes}
            changed.append(item)
            if any(change["field"] == "review.status" for change in field_changes):
                status_changes.append(item)
            if any(change["field"].startswith("risk.") for change in field_changes):
                risk_changes.append(item)

    by_status = Counter((record.get("review") or {}).get("status", "unknown") for record in current_records)
    by_source = Counter((record.get("source") or {}).get("type", "unknown") for record in current_records)

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "previous_count": len(previous_records),
        "current_count": len(current_records),
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "status_change_count": len(status_changes),
        "risk_change_count": len(risk_changes),
        "review_status_counts": dict(sorted(by_status.items())),
        "source_counts": dict(sorted(by_source.items())),
        "added": [{"substituent_id": sid, "name": current[sid].get("name")} for sid in added],
        "removed": [{"substituent_id": sid, "name": previous[sid].get("name")} for sid in removed],
        "changed": changed,
        "status_changes": status_changes,
        "risk_changes": risk_changes,
    }


def compare_library_files(previous_path: str | Path | None, current_path: str | Path) -> dict:
    current_records = load_yaml_records(current_path)
    previous_records = load_yaml_records(previous_path) if previous_path and Path(previous_path).exists() else []
    return compare_libraries(previous_records, current_records)


def write_release_report(report: dict, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def write_release_markdown(report: dict, output_path: str | Path) -> None:
    lines = [
        "# Library Release Report",
        "",
        f"Created: {report.get('created_at')}",
        "",
        "## Summary",
        "",
        f"- Previous count: {report.get('previous_count')}",
        f"- Current count: {report.get('current_count')}",
        f"- Added: {report.get('added_count')}",
        f"- Removed: {report.get('removed_count')}",
        f"- Changed: {report.get('changed_count')}",
        f"- Review status changes: {report.get('status_change_count')}",
        f"- Risk changes: {report.get('risk_change_count')}",
        "",
        "## Review Status Counts",
        "",
    ]
    for status, count in (report.get("review_status_counts") or {}).items():
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Added", ""])
    for item in report.get("added", [])[:50]:
        lines.append(f"- {item['substituent_id']} {item.get('name')}")
    lines.extend(["", "## Removed", ""])
    for item in report.get("removed", [])[:50]:
        lines.append(f"- {item['substituent_id']} {item.get('name')}")
    lines.extend(["", "## Changed", ""])
    for item in report.get("changed", [])[:50]:
        fields = ", ".join(change["field"] for change in item.get("changes", []))
        lines.append(f"- {item['substituent_id']} {item.get('name')}: {fields}")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

