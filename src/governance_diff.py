from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import file_sha256


DEFAULT_GOVERNANCE_DIFF_JSON = Path("data/projects/demo/local_governance_diff_report.json")
DEFAULT_GOVERNANCE_DIFF_CSV = Path("data/projects/demo/local_governance_diff_report.csv")
DEFAULT_GOVERNANCE_DIFF_MD = Path("docs/local_governance_diff_report.md")
DEFAULT_BASELINE_REGISTRY_JSON = Path("data/projects/demo/governance_baselines/baseline_registry.json")

COMPARE_FIELDS = [
    "rank",
    "score",
    "direction_score",
    "property_score",
    "similarity_score",
    "synthetic_score",
    "risk_score",
    "mmp_precedent_score",
    "sar_neighborhood_score",
    "evidence_consistency_score",
    "evidence_confidence_calibration_score",
    "public_strategy_signal_score",
    "site_class_governance_action",
    "candidate_explanation_summary",
    "why_review",
]

POLICY_ASSETS = [
    "data/rules/direction_rules.yaml",
    "data/rules/functional_group_replacements.yaml",
    "data/rules/scaffold_rule_reviews.yaml",
    "data/rules/transform_priors.yaml",
    "data/projects/demo/site_class_policy_pack.json",
    "data/projects/demo/evidence_value_policy_active.json",
]


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    for row in rows[1:]:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_key(row: dict) -> str:
    for field in ["candidate_id", "smiles"]:
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    return json.dumps(row, sort_keys=True)


def _policy_fingerprints(root: Path) -> list[dict[str, Any]]:
    rows = []
    for rel in POLICY_ASSETS:
        path = root / rel
        rows.append(
            {
                "path": rel,
                "exists": path.exists(),
                "sha256": file_sha256(path) if path.exists() and path.is_file() else "",
                "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
            }
        )
    return rows


def _safe_baseline_name(value: str | None) -> str:
    raw = str(value or "").strip() or datetime.now(timezone.utc).strftime("baseline_%Y%m%dT%H%M%SZ")
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)
    return safe.strip("_") or "baseline"


def _baseline_dir(root: Path, project_name: str, baseline_dir: str | Path | None = None) -> Path:
    return _resolve(root, baseline_dir or Path("data/projects") / project_name / "governance_baselines")


def _baseline_registry(root: Path, project_name: str, baseline_dir: str | Path | None = None) -> tuple[Path, dict]:
    directory = _baseline_dir(root, project_name, baseline_dir)
    path = directory / "baseline_registry.json"
    payload = _read_json(path)
    if not payload:
        payload = {
            "status": "ready",
            "project_name": project_name,
            "baselines": [],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    payload.setdefault("baselines", [])
    return path, payload


def create_local_governance_baseline(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    baseline_name: str | None = None,
    candidates_csv: str | Path | None = None,
    baseline_dir: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    csv_path = _resolve(root_path, candidates_csv or Path("data/projects") / project_name / "candidates.csv")
    current_rows = _read_csv_rows(csv_path)
    if not current_rows:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_candidates",
            "project_name": project_name,
            "baseline_name": baseline_name or "",
            "baseline_snapshot_path": "",
            "recommended_next_actions": ["Generate candidates before creating a named governance baseline."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    name = _safe_baseline_name(baseline_name)
    directory = _baseline_dir(root_path, project_name, baseline_dir)
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_path = directory / f"{name}.csv"
    metadata_path = directory / f"{name}.json"
    shutil.copyfile(csv_path, snapshot_path)
    fingerprints = _policy_fingerprints(root_path)
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "project_name": project_name,
        "baseline_name": name,
        "snapshot_path": str(snapshot_path.resolve()),
        "metadata_path": str(metadata_path.resolve()),
        "candidate_count": len(current_rows),
        "policy_fingerprints": fingerprints,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }
    _write_json(metadata_path, metadata)
    registry_path, registry = _baseline_registry(root_path, project_name, baseline_dir)
    baselines = [row for row in registry.get("baselines") or [] if row.get("baseline_name") != name]
    baselines.append(
        {
            "baseline_name": name,
            "created_at": metadata["created_at"],
            "snapshot_path": metadata["snapshot_path"],
            "metadata_path": metadata["metadata_path"],
            "candidate_count": len(current_rows),
        }
    )
    registry.update(
        {
            "updated_at": metadata["created_at"],
            "status": "ready",
            "project_name": project_name,
            "baseline_count": len(baselines),
            "baselines": sorted(baselines, key=lambda row: str(row.get("created_at") or "")),
        }
    )
    _write_json(registry_path, registry)
    return {
        "created_at": metadata["created_at"],
        "status": "named_baseline_created",
        "project_name": project_name,
        "baseline_name": name,
        "baseline_snapshot_path": metadata["snapshot_path"],
        "baseline_metadata_path": metadata["metadata_path"],
        "baseline_registry_path": str(registry_path.resolve()),
        "baseline_count": len(baselines),
        "candidate_count": len(current_rows),
        "policy_fingerprints": fingerprints,
        "recommended_next_actions": [
            "Use this named local baseline as the base side when comparing scoring, profile, or policy movements.",
            "Create a fresh named baseline before major local policy changes.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def _resolve_named_baseline(root: Path, project_name: str, name: str, baseline_dir: str | Path | None = None) -> Path | None:
    _registry_path, registry = _baseline_registry(root, project_name, baseline_dir)
    for row in registry.get("baselines") or []:
        if str(row.get("baseline_name") or "") == name:
            path = Path(str(row.get("snapshot_path") or ""))
            return path if path.exists() else None
    fallback = _baseline_dir(root, project_name, baseline_dir) / f"{_safe_baseline_name(name)}.csv"
    return fallback if fallback.exists() else None


def _latest_snapshot(state_path: Path) -> Path | None:
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    path = Path(str(data.get("latest_snapshot_path") or ""))
    return path if path.exists() else None


def _snapshot_current(csv_path: Path, snapshot_dir: Path) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = snapshot_dir / f"candidates_{stamp}.csv"
    shutil.copyfile(csv_path, target)
    return target


def build_local_governance_diff(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidates_csv: str | Path | None = None,
    snapshot_dir: str | Path | None = None,
    baseline_dir: str | Path | None = None,
    create_baseline: bool = False,
    baseline_name: str | None = None,
    base_baseline: str | None = None,
    update_snapshot: bool = True,
) -> dict[str, Any]:
    root_path = Path(root)
    csv_path = _resolve(root_path, candidates_csv or Path("data/projects") / project_name / "candidates.csv")
    snapshots = _resolve(root_path, snapshot_dir or Path("data/projects") / project_name / "governance_snapshots")
    state_path = snapshots / "latest_snapshot.json"
    current_rows = _read_csv_rows(csv_path)
    policy_rows = _policy_fingerprints(root_path)
    registry_path, registry = _baseline_registry(root_path, project_name, baseline_dir)
    if create_baseline:
        return create_local_governance_baseline(
            root=root_path,
            project_name=project_name,
            baseline_name=baseline_name,
            candidates_csv=csv_path,
            baseline_dir=baseline_dir,
        )
    if not current_rows:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_candidates",
            "project_name": project_name,
            "candidates_csv": str(csv_path),
            "rows": [],
            "policy_fingerprints": policy_rows,
            "baseline_registry_path": str(registry_path),
            "baseline_registry": registry,
            "recommended_next_actions": ["Generate candidates before building governance diff."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    if base_baseline:
        base_path = _resolve_named_baseline(root_path, project_name, _safe_baseline_name(base_baseline), baseline_dir)
        if base_path is None:
            return {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "missing_named_baseline",
                "project_name": project_name,
                "baseline_name": _safe_baseline_name(base_baseline),
                "candidates_csv": str(csv_path),
                "row_count": len(current_rows),
                "rows": [],
                "policy_fingerprints": policy_rows,
                "baseline_registry_path": str(registry_path),
                "baseline_registry": registry,
                "recommended_next_actions": ["Create the named governance baseline before diffing against it."],
                "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
            }
    else:
        base_path = _latest_snapshot(state_path)
    base_rows = _read_csv_rows(base_path) if base_path else []
    current_snapshot_path = _snapshot_current(csv_path, snapshots) if update_snapshot else csv_path
    if update_snapshot:
        state_path.write_text(
            json.dumps(
                {
                    "latest_snapshot_path": str(current_snapshot_path.resolve()),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "project_name": project_name,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    if not base_rows:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "baseline_created",
            "project_name": project_name,
            "candidates_csv": str(csv_path),
            "base_snapshot_path": "",
            "head_snapshot_path": str(current_snapshot_path),
            "base_baseline": _safe_baseline_name(base_baseline) if base_baseline else "",
            "baseline_registry_path": str(registry_path),
            "baseline_count": len(registry.get("baselines") or []),
            "row_count": len(current_rows),
            "added_candidate_count": 0,
            "removed_candidate_count": 0,
            "changed_candidate_count": 0,
            "unchanged_candidate_count": len(current_rows),
            "rows": [],
            "policy_fingerprints": policy_rows,
            "recommended_next_actions": ["Run this report again after scoring/profile/policy changes to compare candidate movement."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    base_by_key = {_candidate_key(row): row for row in base_rows}
    head_by_key = {_candidate_key(row): row for row in current_rows}
    keys = sorted(set(base_by_key) | set(head_by_key))
    rows = []
    for key in keys:
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
                "base_site_class": base.get("site_class", ""),
                "head_site_class": head.get("site_class", ""),
                "changed_fields": ";".join(changed_fields),
                "base_why_review": base.get("why_review", ""),
                "head_why_review": head.get("why_review", ""),
            }
        )
    counts = Counter(row["status"] for row in rows)
    changed = [row for row in rows if row["status"] == "changed"]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "compared",
        "project_name": project_name,
        "candidates_csv": str(csv_path),
        "base_snapshot_path": str(base_path),
        "head_snapshot_path": str(current_snapshot_path),
        "base_baseline": _safe_baseline_name(base_baseline) if base_baseline else "",
        "baseline_registry_path": str(registry_path),
        "baseline_count": len(registry.get("baselines") or []),
        "row_count": len(rows),
        "shared_candidate_count": len(set(base_by_key) & set(head_by_key)),
        "added_candidate_count": counts.get("added", 0),
        "removed_candidate_count": counts.get("removed", 0),
        "changed_candidate_count": counts.get("changed", 0),
        "unchanged_candidate_count": counts.get("unchanged", 0),
        "status_counts": dict(counts.most_common()),
        "max_abs_score_delta": max([abs(_float(row.get("score_delta"))) for row in changed] or [0.0]),
        "max_abs_rank_delta": max([abs(_float(row.get("rank_delta"))) for row in changed] or [0.0]),
        "policy_fingerprints": policy_rows,
        "baseline_registry": registry,
        "rows": rows,
        "recommended_next_actions": [
            "Review changed score/rank/evidence rows before accepting scoring or policy movement.",
            "Use added/removed rows to distinguish enumeration changes from ranking-only drift.",
            "Keep governance diff scoped to local candidate, score, profile, and policy artifacts.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_local_governance_diff_markdown(report: dict) -> str:
    lines = [
        "# Local Governance Diff",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Project: `{report.get('project_name')}`",
        f"- Base baseline: `{report.get('base_baseline') or 'latest_snapshot'}`",
        f"- Named baselines: `{report.get('baseline_count') or 0}`",
        f"- Changed: `{report.get('changed_candidate_count')}`",
        f"- Added / removed: `{report.get('added_candidate_count')}` / `{report.get('removed_candidate_count')}`",
        "",
        "## Candidate Movement",
        "",
        "| ID | Status | Base Score | Head Score | Score Delta | Rank Delta | Changed Fields |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:60]:
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
    lines.extend(["", "## Policy Fingerprints", "", "| Path | Exists | SHA256 |", "| --- | --- | --- |"])
    for row in report.get("policy_fingerprints") or []:
        lines.append(f"| `{row.get('path')}` | `{row.get('exists')}` | `{row.get('sha256')}` |")
    lines.append("")
    return "\n".join(lines)


def write_local_governance_diff(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_GOVERNANCE_DIFF_JSON,
    csv_path: str | Path | None = DEFAULT_GOVERNANCE_DIFF_CSV,
    markdown_path: str | Path | None = DEFAULT_GOVERNANCE_DIFF_MD,
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
            "base_site_class",
            "head_site_class",
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
        md_file.write_text(render_local_governance_diff_markdown(report), encoding="utf-8")
