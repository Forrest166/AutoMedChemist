from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SUBSTITUENT_VERSION_DIFF_JSON = Path("data/substituents/substituent_version_diff_browser.json")
DEFAULT_SUBSTITUENT_VERSION_DIFF_CSV = Path("data/substituents/substituent_version_diff_browser.csv")
DEFAULT_SUBSTITUENT_VERSION_DIFF_MD = Path("docs/substituent_version_diff_browser.md")
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


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_yaml(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _join(value: object) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value if item not in {None, ""})
    if isinstance(value, dict):
        return ";".join(f"{key}={item}" for key, item in value.items())
    return str(value or "")


def _latest_history(record: dict) -> dict:
    history = record.get("version_history") or []
    return dict(history[-1]) if history and isinstance(history[-1], dict) else {}


def _record_version(record: dict, csv_row: dict) -> str:
    source = record.get("source") or {}
    return str(csv_row.get("version") or source.get("version") or record.get("version") or "")


def build_substituent_version_diff_browser(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    substituent_dir = root_path / "data" / "substituents"
    project_dir = root_path / "data" / "projects" / project_name
    library = _read_yaml(substituent_dir / "core_substituent_library.yaml")
    records = [dict(row) for row in library.get("substituents") or [] if isinstance(row, dict)]
    common_rows = {str(row.get("substituent_id") or ""): dict(row) for row in _read_csv(substituent_dir / "medchem_common_substituents.csv")}
    review_rows = {str(row.get("substituent_id") or ""): dict(row) for row in _read_csv(substituent_dir / "review_queue.csv")}
    candidates = _read_csv(project_dir / "candidates.csv")
    board_rows = {str(row.get("candidate_id") or ""): dict(row) for row in (_read_json(project_dir / "candidate_review_board.json").get("rows") or [])}
    candidate_by_substituent: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        sid = str(row.get("substituent_id") or "").strip()
        if sid:
            candidate_by_substituent[sid].append(dict(row))
    drilldown = _read_json(project_dir / "candidate_explanation_drilldown.json")
    attention_by_candidate = Counter(
        str(row.get("candidate_id") or "")
        for row in drilldown.get("rows") or []
        if row.get("component_status") in {"attention", "watch"}
    )
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        sid = str(record.get("substituent_id") or "").strip()
        if not sid:
            continue
        seen_ids.add(sid)
        csv_row = common_rows.get(sid, {})
        review_row = review_rows.get(sid, {})
        review = record.get("review") or {}
        risk = record.get("risk") or {}
        latest = _latest_history(record)
        linked_candidates = candidate_by_substituent.get(sid, [])
        linked_candidate_ids = [str(row.get("candidate_id") or "") for row in linked_candidates if row.get("candidate_id")]
        attention_count = sum(attention_by_candidate.get(candidate_id, 0) for candidate_id in linked_candidate_ids)
        version = _record_version(record, csv_row)
        history = record.get("version_history") or []
        rows.append(
            {
                "substituent_id": sid,
                "name": record.get("name") or csv_row.get("name") or "",
                "short_name": record.get("short_name") or csv_row.get("short_name") or "",
                "version": version,
                "review_status": review_row.get("review_status") or csv_row.get("review_status") or review.get("status") or "",
                "default_enabled": risk.get("default_enabled", csv_row.get("default_enabled", "")),
                "applicable_contexts": review_row.get("use_cases") or csv_row.get("use_cases") or _join(review.get("applicable_contexts") or record.get("direction_tags") or []),
                "disabled_contexts": review_row.get("avoid_contexts") or csv_row.get("avoid_contexts") or _join(review.get("disabled_contexts") or risk.get("cautions") or []),
                "version_event_count": len(history),
                "latest_change_type": latest.get("change_type") or latest.get("event_type") or "",
                "latest_changed_at": latest.get("changed_at") or latest.get("timestamp") or csv_row.get("reviewed_at") or "",
                "latest_change_note": latest.get("note") or latest.get("summary") or review_row.get("review_notes") or "",
                "linked_candidate_count": len(linked_candidates),
                "linked_candidate_ids": ";".join(linked_candidate_ids[:12]),
                "candidate_attention_component_count": attention_count,
                "candidate_impact_summary": f"linked_candidates={len(linked_candidates)}; attention_components={attention_count}",
                "next_action": "Review candidate impact before changing review status or enabled context." if linked_candidates or attention_count else "Keep version history available for future candidate impact review.",
                "export_scope": "local_substituent_version_diff_browser",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    for sid, linked_candidates in sorted(candidate_by_substituent.items()):
        if sid in seen_ids:
            continue
        linked_candidate_ids = [str(row.get("candidate_id") or "") for row in linked_candidates if row.get("candidate_id")]
        attention_count = sum(attention_by_candidate.get(candidate_id, 0) for candidate_id in linked_candidate_ids)
        first = linked_candidates[0] if linked_candidates else {}
        board_notes = [board_rows.get(candidate_id, {}).get("why_review") or board_rows.get(candidate_id, {}).get("blocked_contexts") for candidate_id in linked_candidate_ids]
        rows.append(
            {
                "substituent_id": sid,
                "name": first.get("substituent_name") or first.get("replacement_label") or sid,
                "short_name": first.get("replacement_label") or sid,
                "version": first.get("functional_rule_id") or "candidate_rule",
                "review_status": "candidate_rule_review",
                "default_enabled": False,
                "applicable_contexts": f"direction={first.get('direction') or ''}; site_class={first.get('site_class') or first.get('site_type') or ''}; replacement_class={first.get('replacement_class') or ''}",
                "disabled_contexts": " | ".join(str(item) for item in board_notes if item)[:480],
                "version_event_count": 1,
                "latest_change_type": "candidate_rule_link",
                "latest_changed_at": "",
                "latest_change_note": "Candidate-specific functional-group rule is linked to current recommendation explanations.",
                "linked_candidate_count": len(linked_candidates),
                "linked_candidate_ids": ";".join(linked_candidate_ids[:12]),
                "candidate_attention_component_count": attention_count,
                "candidate_impact_summary": f"candidate_rule_linked={len(linked_candidates)}; attention_components={attention_count}",
                "next_action": "Review candidate-linked rule context before changing replacement guidance.",
                "export_scope": "local_substituent_version_diff_browser",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    review_counts = Counter(str(row.get("review_status") or "unknown") for row in rows)
    linked_count = sum(1 for row in rows if int(row.get("linked_candidate_count") or 0) > 0)
    attention_count = sum(1 for row in rows if int(row.get("candidate_attention_component_count") or 0) > 0)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_library",
        "mode": "substituent_version_diff_browser",
        "project_name": project_name,
        "row_count": len(rows),
        "linked_substituent_count": linked_count,
        "candidate_attention_substituent_count": attention_count,
        "review_status_counts": dict(review_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use linked_candidate_count and candidate_attention_component_count to see whether library version changes affect current recommendations.",
            "Keep review status, applicable contexts, disabled contexts, and version history together before enabling a substituent more broadly.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_substituent_version_diff_browser_markdown(report: dict) -> str:
    lines = [
        "# Substituent Version Diff Browser",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows / linked substituents: `{report.get('row_count')}` / `{report.get('linked_substituent_count')}`",
        "",
        "| ID | Name | Version | Review | Enabled | Events | Linked Candidates | Attention | Latest Change |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:180]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("substituent_id") or ""),
                    str(row.get("name") or "").replace("|", "/"),
                    str(row.get("version") or ""),
                    str(row.get("review_status") or ""),
                    str(row.get("default_enabled") or ""),
                    str(row.get("version_event_count") or 0),
                    str(row.get("linked_candidate_count") or 0),
                    str(row.get("candidate_attention_component_count") or 0),
                    str(row.get("latest_change_type") or row.get("latest_change_note") or "").replace("|", "/")[:160],
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_substituent_version_diff_browser(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_SUBSTITUENT_VERSION_DIFF_JSON,
    csv_path: str | Path | None = DEFAULT_SUBSTITUENT_VERSION_DIFF_CSV,
    markdown_path: str | Path | None = DEFAULT_SUBSTITUENT_VERSION_DIFF_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "substituent_id",
        "name",
        "short_name",
        "version",
        "review_status",
        "default_enabled",
        "applicable_contexts",
        "disabled_contexts",
        "version_event_count",
        "latest_change_type",
        "latest_changed_at",
        "latest_change_note",
        "linked_candidate_count",
        "linked_candidate_ids",
        "candidate_attention_component_count",
        "candidate_impact_summary",
        "next_action",
        "export_scope",
        "procurement_allowed",
        "feedback_import_allowed",
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
        md_file.write_text(render_substituent_version_diff_browser_markdown(report), encoding="utf-8")
