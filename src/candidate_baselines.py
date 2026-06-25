from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .governance_diff import COMPARE_FIELDS, _candidate_key, _float, _policy_fingerprints, _read_csv_rows
from .manifest import file_sha256


DEFAULT_BASELINE_REGISTRY_JSON = Path("data/projects/demo/candidate_baseline_registry.json")
DEFAULT_BASELINE_REGISTRY_CSV = Path("data/projects/demo/candidate_baseline_registry.csv")
DEFAULT_BASELINE_COMPARE_JSON = Path("data/projects/demo/candidate_baseline_compare.json")
DEFAULT_BASELINE_COMPARE_CSV = Path("data/projects/demo/candidate_baseline_compare.csv")
DEFAULT_BASELINE_COMPARE_MD = Path("docs/candidate_baseline_compare.md")


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _safe_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in str(value or ""))
    return safe.strip("._-") or datetime.now(timezone.utc).strftime("baseline_%Y%m%dT%H%M%SZ")


def _registry_path(root: Path, project_name: str, registry_path: str | Path | None = None) -> Path:
    return _resolve(root, registry_path or Path("data/projects") / project_name / "candidate_baseline_registry.json")


def _registry_csv_path(root: Path, project_name: str, csv_path: str | Path | None = None) -> Path:
    return _resolve(root, csv_path or Path("data/projects") / project_name / "candidate_baseline_registry.csv")


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_registry(report: dict, json_path: Path, csv_path: Path | None = None) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_path:
        return
    fields = ["baseline_id", "status", "created_at", "project_name", "candidate_count", "source_sha256", "baseline_path", "note", "archived_at", "archive_note"]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report.get("baselines") or []:
            writer.writerow({field: row.get(field, "") for field in fields})


def load_candidate_baseline_registry(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    path = _registry_path(root_path, project_name, registry_path)
    report = _read_json(path)
    if report:
        return report
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "empty",
        "project_name": project_name,
        "baseline_count": 0,
        "baselines": [],
    }


def pin_candidate_baseline(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    baseline_id: str,
    candidates_csv: str | Path | None = None,
    note: str = "",
    overwrite: bool = False,
    registry_path: str | Path | None = None,
    registry_csv_path: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    safe_id = _safe_id(baseline_id)
    source = _resolve(root_path, candidates_csv or Path("data/projects") / project_name / "candidates.csv")
    if not source.exists():
        raise FileNotFoundError(f"Candidate CSV not found: {source}")
    baseline_dir = root_path / "data" / "projects" / project_name / "candidate_baselines" / safe_id
    target = baseline_dir / "candidates.csv"
    manifest_path = baseline_dir / "manifest.json"
    if target.exists() and not overwrite:
        manifest = _read_json(manifest_path)
        return {"status": "exists", "baseline_id": safe_id, "manifest": manifest}
    baseline_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    rows = _read_csv_rows(target)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pinned",
        "project_name": project_name,
        "baseline_id": safe_id,
        "candidate_count": len(rows),
        "source_candidates_csv": str(source),
        "baseline_path": str(target),
        "source_sha256": file_sha256(source),
        "baseline_sha256": file_sha256(target),
        "policy_fingerprints": _policy_fingerprints(root_path),
        "note": note,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    registry_file = _registry_path(root_path, project_name, registry_path)
    registry_csv = _registry_csv_path(root_path, project_name, registry_csv_path)
    registry = load_candidate_baseline_registry(root=root_path, project_name=project_name, registry_path=registry_file)
    rows_by_id = {str(row.get("baseline_id") or ""): dict(row) for row in registry.get("baselines") or []}
    rows_by_id[safe_id] = {
        "baseline_id": safe_id,
        "status": "active",
        "created_at": manifest["created_at"],
        "project_name": project_name,
        "candidate_count": len(rows),
        "source_sha256": manifest["source_sha256"],
        "baseline_path": str(target),
        "manifest_path": str(manifest_path),
        "note": note,
    }
    registry["status"] = "ready"
    registry["updated_at"] = datetime.now(timezone.utc).isoformat()
    registry["project_name"] = project_name
    registry["baseline_count"] = len(rows_by_id)
    registry["baselines"] = sorted(rows_by_id.values(), key=lambda row: str(row.get("created_at") or ""))
    _write_registry(registry, registry_file, registry_csv)
    return {"status": "pinned", "baseline_id": safe_id, "manifest": manifest, "registry": registry}


def archive_candidate_baseline(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    baseline_id: str,
    note: str = "",
    registry_path: str | Path | None = None,
    registry_csv_path: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    safe_id = _safe_id(baseline_id)
    registry_file = _registry_path(root_path, project_name, registry_path)
    registry_csv = _registry_csv_path(root_path, project_name, registry_csv_path)
    registry = load_candidate_baseline_registry(root=root_path, project_name=project_name, registry_path=registry_file)
    rows = []
    matched = False
    stamp = datetime.now(timezone.utc).isoformat()
    for row in registry.get("baselines") or []:
        item = dict(row)
        if str(item.get("baseline_id") or "") == safe_id:
            item["status"] = "archived"
            item["archived_at"] = stamp
            item["archive_note"] = note
            matched = True
        else:
            item.setdefault("status", "active")
        rows.append(item)
    if not matched:
        return {
            "created_at": stamp,
            "status": "missing_baseline",
            "project_name": project_name,
            "baseline_id": safe_id,
            "recommended_next_actions": ["Select an existing candidate baseline before archiving."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    registry.update(
        {
            "status": "ready",
            "updated_at": stamp,
            "project_name": project_name,
            "baseline_count": len(rows),
            "active_baseline_count": sum(1 for row in rows if row.get("status", "active") != "archived"),
            "archived_baseline_count": sum(1 for row in rows if row.get("status") == "archived"),
            "baselines": rows,
        }
    )
    _write_registry(registry, registry_file, registry_csv)
    return {
        "created_at": stamp,
        "status": "archived",
        "project_name": project_name,
        "baseline_id": safe_id,
        "baseline_registry_path": str(registry_file),
        "archive_note": note,
        "registry": registry,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def compare_candidate_baseline(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    baseline_id: str,
    candidates_csv: str | Path | None = None,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    root_path = Path(root)
    safe_id = _safe_id(baseline_id)
    source = _resolve(root_path, candidates_csv or Path("data/projects") / project_name / "candidates.csv")
    baseline_dir = root_path / "data" / "projects" / project_name / "candidate_baselines" / safe_id
    baseline_csv = baseline_dir / "candidates.csv"
    manifest_path = baseline_dir / "manifest.json"
    if not baseline_csv.exists():
        if create_if_missing:
            pinned = pin_candidate_baseline(root=root_path, project_name=project_name, baseline_id=safe_id, candidates_csv=source, note="Created as first local named candidate baseline.")
            return {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "baseline_created",
                "project_name": project_name,
                "baseline_id": safe_id,
                "baseline_manifest": pinned.get("manifest"),
                "row_count": 0,
                "changed_candidate_count": 0,
                "added_candidate_count": 0,
                "removed_candidate_count": 0,
                "unchanged_candidate_count": 0,
                "max_abs_score_delta": 0.0,
                "max_abs_rank_delta": 0.0,
                "rows": [],
                "recommended_next_actions": ["Run compare again after scoring/profile/rule changes."],
                "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
            }
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_baseline",
            "project_name": project_name,
            "baseline_id": safe_id,
            "row_count": 0,
            "rows": [],
            "recommended_next_actions": ["Pin a named candidate baseline before comparing."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    base_rows = _read_csv_rows(baseline_csv)
    head_rows = _read_csv_rows(source)
    base_by_key = {_candidate_key(row): row for row in base_rows}
    head_by_key = {_candidate_key(row): row for row in head_rows}
    rows = []
    for key in sorted(set(base_by_key) | set(head_by_key)):
        base = base_by_key.get(key) or {}
        head = head_by_key.get(key) or {}
        if base and head:
            changed_fields = [field for field in COMPARE_FIELDS if str(base.get(field) or "") != str(head.get(field) or "")]
            status = "changed" if changed_fields else "unchanged"
        elif head:
            changed_fields = []
            status = "added"
        else:
            changed_fields = []
            status = "removed"
        rows.append(
            {
                "candidate_key": key,
                "status": status,
                "candidate_id": head.get("candidate_id") or base.get("candidate_id"),
                "smiles": head.get("smiles") or base.get("smiles"),
                "base_rank": base.get("rank", ""),
                "head_rank": head.get("rank", ""),
                "rank_delta": round(_float(head.get("rank")) - _float(base.get("rank")), 4) if base and head else "",
                "base_score": base.get("score", ""),
                "head_score": head.get("score", ""),
                "score_delta": round(_float(head.get("score")) - _float(base.get("score")), 4) if base and head else "",
                "changed_fields": ";".join(changed_fields),
                "base_why_review": base.get("why_review", ""),
                "head_why_review": head.get("why_review", ""),
            }
        )
    counts = Counter(str(row.get("status") or "") for row in rows)
    changed = [row for row in rows if row.get("status") == "changed"]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "compared",
        "mode": "non_experimental_candidate_baseline_compare",
        "project_name": project_name,
        "baseline_id": safe_id,
        "baseline_manifest": _read_json(manifest_path),
        "baseline_path": str(baseline_csv),
        "head_candidates_csv": str(source),
        "row_count": len(rows),
        "changed_candidate_count": counts.get("changed", 0),
        "added_candidate_count": counts.get("added", 0),
        "removed_candidate_count": counts.get("removed", 0),
        "unchanged_candidate_count": counts.get("unchanged", 0),
        "status_counts": dict(counts.most_common()),
        "max_abs_score_delta": max([abs(_float(row.get("score_delta"))) for row in changed] or [0.0]),
        "max_abs_rank_delta": max([abs(_float(row.get("rank_delta"))) for row in changed] or [0.0]),
        "head_policy_fingerprints": _policy_fingerprints(root_path),
        "rows": rows,
        "recommended_next_actions": [
            "Review changed, added, or removed candidates before accepting local scoring/profile/rule movement.",
            "Pin a new named baseline only after the movement is understood.",
            "Keep comparisons local and non-experimental.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_candidate_baseline_compare_markdown(report: dict) -> str:
    lines = [
        "# Candidate Baseline Compare",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Baseline: `{report.get('baseline_id')}`",
        f"- Changed: `{report.get('changed_candidate_count')}`",
        f"- Added / removed: `{report.get('added_candidate_count')}` / `{report.get('removed_candidate_count')}`",
        "",
        "| ID | Status | Base Score | Head Score | Score Delta | Rank Delta | Changed Fields |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:80]:
        if row.get("status") == "unchanged":
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("status") or ""),
                    str(row.get("base_score") or ""),
                    str(row.get("head_score") or ""),
                    str(row.get("score_delta") or ""),
                    str(row.get("rank_delta") or ""),
                    str(row.get("changed_fields") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_baseline_compare(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_BASELINE_COMPARE_JSON,
    csv_path: str | Path | None = DEFAULT_BASELINE_COMPARE_CSV,
    markdown_path: str | Path | None = DEFAULT_BASELINE_COMPARE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        fields = [
            "candidate_key",
            "status",
            "candidate_id",
            "smiles",
            "base_rank",
            "head_rank",
            "rank_delta",
            "base_score",
            "head_score",
            "score_delta",
            "changed_fields",
            "base_why_review",
            "head_why_review",
        ]
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
        md_file.write_text(render_candidate_baseline_compare_markdown(report), encoding="utf-8")
