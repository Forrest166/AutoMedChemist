from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_MANAGER_JSON = Path("data/projects/demo/candidate_baseline_manager.json")
DEFAULT_BASELINE_MANAGER_CSV = Path("data/projects/demo/candidate_baseline_manager.csv")
DEFAULT_BASELINE_MANAGER_MD = Path("docs/candidate_baseline_manager.md")
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


def _write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_days(value: object, now: datetime) -> int:
    stamp = _parse_time(value)
    if stamp is None:
        return 0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, int((now - stamp).total_seconds() // 86400))


def _is_archived(row: dict) -> bool:
    return bool(row.get("archived")) or str(row.get("status") or "").lower() == "archived"


def _registry_paths(root_path: Path, project_name: str) -> tuple[Path, Path]:
    project_dir = root_path / "data" / "projects" / project_name
    return project_dir / "candidate_baseline_registry.json", project_dir / "candidate_baseline_registry.csv"


def archive_candidate_baseline(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    baseline_id: str,
    reviewer: str = "local_reviewer",
    note: str = "",
) -> dict[str, Any]:
    root_path = Path(root)
    registry_path, csv_path = _registry_paths(root_path, project_name)
    registry = _read_json(registry_path)
    rows = [dict(row) for row in registry.get("baselines") or []]
    stamp = datetime.now(timezone.utc).isoformat()
    updated = False
    for row in rows:
        if str(row.get("baseline_id") or "") == str(baseline_id):
            row["status"] = "archived"
            row["archived"] = True
            row["archived_at"] = stamp
            row["archived_by"] = reviewer
            row["archive_note"] = note
            updated = True
    registry.update(
        {
            "status": "ready" if rows else "empty",
            "updated_at": stamp,
            "project_name": project_name,
            "baseline_count": len(rows),
            "active_baseline_count": sum(1 for row in rows if not _is_archived(row)),
            "archived_baseline_count": sum(1 for row in rows if _is_archived(row)),
            "baselines": rows,
        }
    )
    _write_json(registry_path, registry)
    _write_registry_csv(registry, csv_path)
    return {
        "created_at": stamp,
        "status": "archived" if updated else "missing_baseline",
        "project_name": project_name,
        "baseline_id": baseline_id,
        "registry_path": str(registry_path),
        "blocked_scopes": BLOCKED_SCOPES,
    }


def build_candidate_baseline_manager(*, root: str | Path = ".", project_name: str = "demo", stale_days: int = 30) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    registry = _read_json(project_dir / "candidate_baseline_registry.json")
    compare = _read_json(project_dir / "candidate_baseline_compare.json")
    now = datetime.now(timezone.utc)
    rows = []
    for row in registry.get("baselines") or []:
        baseline_id = str(row.get("baseline_id") or "")
        age = _age_days(row.get("created_at"), now)
        archived = _is_archived(row)
        is_compared = baseline_id == str(compare.get("baseline_id") or "")
        archive_recommendation = "already_archived" if archived else "archive_review" if age >= stale_days and not is_compared else "keep_active"
        rows.append(
            {
                "baseline_id": baseline_id,
                "status": "archived" if archived else str(row.get("status") or "active"),
                "created_at": row.get("created_at", ""),
                "age_days": age,
                "project_name": row.get("project_name") or project_name,
                "candidate_count": row.get("candidate_count", ""),
                "source_sha256": row.get("source_sha256", ""),
                "baseline_path": row.get("baseline_path", ""),
                "note": row.get("note", ""),
                "archived": archived,
                "archived_at": row.get("archived_at", ""),
                "archive_note": row.get("archive_note", ""),
                "current_compare": is_compared,
                "compare_status": compare.get("status") if is_compared else "",
                "changed_candidate_count": compare.get("changed_candidate_count") if is_compared else "",
                "added_candidate_count": compare.get("added_candidate_count") if is_compared else "",
                "removed_candidate_count": compare.get("removed_candidate_count") if is_compared else "",
                "archive_recommendation": archive_recommendation,
                "next_action": "Inspect current compare before archiving." if archive_recommendation == "archive_review" else "Keep as available comparison baseline.",
            }
        )
    return {
        "created_at": now.isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "candidate_baseline_manager",
        "project_name": project_name,
        "baseline_count": len(rows),
        "active_baseline_count": sum(1 for row in rows if not row["archived"]),
        "archived_baseline_count": sum(1 for row in rows if row["archived"]),
        "archive_review_count": sum(1 for row in rows if row["archive_recommendation"] == "archive_review"),
        "rows": rows,
        "recommended_next_actions": [
            "Compare current candidates against a baseline before archiving or pinning a new one.",
            "Archive only hides stale baselines in the manager; it does not delete baseline files.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def _write_registry_csv(registry: dict, csv_path: Path) -> None:
    fields = [
        "baseline_id",
        "status",
        "created_at",
        "project_name",
        "candidate_count",
        "source_sha256",
        "baseline_path",
        "note",
        "archived",
        "archived_at",
        "archived_by",
        "archive_note",
    ]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in registry.get("baselines") or []:
            writer.writerow({field: row.get(field, "") for field in fields})


def render_candidate_baseline_manager_markdown(report: dict) -> str:
    lines = [
        "# Candidate Baseline Manager",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Active / archived: `{report.get('active_baseline_count')}` / `{report.get('archived_baseline_count')}`",
        "",
        "| Baseline | Active | Age | Compare | Changed | Archive | Next Action |",
        "| --- | --- | ---: | --- | ---: | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("baseline_id") or ""),
                    "no" if row.get("archived") else "yes",
                    str(row.get("age_days") or ""),
                    str(row.get("compare_status") or ""),
                    str(row.get("changed_candidate_count") or ""),
                    str(row.get("archive_recommendation") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_baseline_manager(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_MANAGER_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_MANAGER_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_MANAGER_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "baseline_id",
        "status",
        "created_at",
        "age_days",
        "project_name",
        "candidate_count",
        "source_sha256",
        "baseline_path",
        "note",
        "archived",
        "archived_at",
        "archive_note",
        "current_compare",
        "compare_status",
        "changed_candidate_count",
        "added_candidate_count",
        "removed_candidate_count",
        "archive_recommendation",
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
        md_file.write_text(render_candidate_baseline_manager_markdown(report), encoding="utf-8")
