from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROFILE_ROLLBACK_HISTORY_PATH = Path("data/projects/demo/profile_rollback_history.json")
DEFAULT_PROFILE_ROLLBACK_HISTORY_CSV_PATH = Path("data/projects/demo/profile_rollback_history.csv")
DEFAULT_PROFILE_ROLLBACK_CANDIDATE_HISTORY_CSV_PATH = Path("data/projects/demo/profile_rollback_candidate_history.csv")
DEFAULT_PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH = Path("data/projects/demo/profile_rollback_snapshot_compare.json")
DEFAULT_PROFILE_ROLLBACK_SNAPSHOT_COMPARE_CSV_PATH = Path("data/projects/demo/profile_rollback_snapshot_compare.csv")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _asset_path_from_manifest(manifest: dict, asset_id: str) -> Path | None:
    for asset in manifest.get("assets") or []:
        if str(asset.get("asset_id") or "") != asset_id:
            continue
        for field in ["package_path", "source_path"]:
            value = asset.get(field)
            if value and Path(value).exists():
                return Path(value)
        package_dir = Path(manifest.get("package_dir") or "")
        if package_dir.exists() and asset.get("package_path"):
            fallback = package_dir / Path(str(asset.get("package_path"))).name
            if fallback.exists():
                return fallback
    return None


def _snapshot_from_replay(snapshot_id: str, snapshot_type: str, created_at: str | None, replay: dict, *, path: Path | None = None) -> dict:
    action_counts = replay.get("rollback_action_counts") or {}
    return {
        "snapshot_id": snapshot_id,
        "snapshot_type": snapshot_type,
        "created_at": created_at or replay.get("created_at"),
        "status": replay.get("status") or "missing",
        "source_path": str(path) if path else "",
        "active_freeze_id": replay.get("active_freeze_id"),
        "latest_release_tag": replay.get("latest_release_tag"),
        "row_count": int(replay.get("row_count") or 0),
        "queue_linked_count": int(replay.get("queue_linked_count") or 0),
        "max_abs_rollback_score_delta": _float(replay.get("max_abs_rollback_score_delta")),
        "max_abs_rollback_rank_delta": _float(replay.get("max_abs_rollback_rank_delta")),
        "rollback_action_counts": action_counts,
        "restore_base_profile_priority_count": int(action_counts.get("restore_base_profile_priority") or 0),
        "remove_candidate_profile_promotion_count": int(action_counts.get("remove_candidate_profile_promotion") or 0),
    }


def _iteration_snapshots(root_path: Path, iteration_root: Path, *, limit: int) -> list[dict]:
    snapshots = []
    if not iteration_root.exists():
        return snapshots
    manifests = []
    for package_dir in iteration_root.iterdir():
        manifest_path = package_dir / "iteration_manifest.json"
        if manifest_path.exists():
            manifest = _read_json(manifest_path)
            if manifest:
                manifests.append((manifest_path.stat().st_mtime, manifest))
    for _, manifest in sorted(manifests, reverse=True)[: int(limit)]:
        replay_path = _asset_path_from_manifest(manifest, "profile_promotion_rollback_replay")
        replay = _read_json(replay_path) if replay_path else {}
        snapshots.append(
            _snapshot_from_replay(
                str(manifest.get("iteration_id") or ""),
                "iteration",
                manifest.get("created_at"),
                replay,
                path=replay_path,
            )
        )
    return snapshots


def _freeze_snapshots(root_path: Path, freeze_root: Path, *, limit: int) -> list[dict]:
    snapshots = []
    if not freeze_root.exists():
        return snapshots
    manifests = []
    for package_dir in freeze_root.iterdir():
        manifest_path = package_dir / "profile_promotion_freeze_manifest.json"
        if manifest_path.exists():
            manifest = _read_json(manifest_path)
            if manifest:
                manifests.append((manifest_path.stat().st_mtime, manifest))
    for _, manifest in sorted(manifests, reverse=True)[: int(limit)]:
        replay_path = _asset_path_from_manifest(manifest, "profile_promotion_rollback_replay")
        replay = _read_json(replay_path) if replay_path else {}
        snapshots.append(
            _snapshot_from_replay(
                str(manifest.get("freeze_id") or ""),
                "freeze",
                manifest.get("created_at"),
                replay,
                path=replay_path,
            )
        )
    return snapshots


def _candidate_history(snapshot: dict, replay: dict) -> list[dict]:
    rows = []
    for row in replay.get("rows") or []:
        rows.append(
            {
                "snapshot_id": snapshot.get("snapshot_id"),
                "snapshot_type": snapshot.get("snapshot_type"),
                "snapshot_created_at": snapshot.get("created_at"),
                "candidate_id": row.get("candidate_id"),
                "candidate_key": row.get("candidate_key"),
                "queue_id": row.get("queue_id"),
                "queue_rank": row.get("queue_rank"),
                "rollback_action": row.get("rollback_action"),
                "rollback_score_delta": row.get("rollback_score_delta"),
                "rollback_rank_delta": row.get("rollback_rank_delta"),
                "current_membership": row.get("current_membership"),
                "material_acceptance_status": row.get("material_acceptance_status"),
            }
        )
    return rows


def _transitions(snapshots: list[dict]) -> list[dict]:
    ordered = [row for row in snapshots if row.get("created_at")]
    ordered.sort(key=lambda row: str(row.get("created_at") or ""))
    transitions = []
    for base, head in zip(ordered, ordered[1:]):
        transitions.append(
            {
                "base_snapshot_id": base.get("snapshot_id"),
                "head_snapshot_id": head.get("snapshot_id"),
                "base_snapshot_type": base.get("snapshot_type"),
                "head_snapshot_type": head.get("snapshot_type"),
                "row_count_delta": int(head.get("row_count") or 0) - int(base.get("row_count") or 0),
                "queue_linked_delta": int(head.get("queue_linked_count") or 0) - int(base.get("queue_linked_count") or 0),
                "max_score_delta_change": round(_float(head.get("max_abs_rollback_score_delta")) - _float(base.get("max_abs_rollback_score_delta")), 4),
                "max_rank_delta_change": round(_float(head.get("max_abs_rollback_rank_delta")) - _float(base.get("max_abs_rollback_rank_delta")), 4),
            }
        )
    return transitions


def _candidate_key(row: dict) -> str:
    for field in ["candidate_id", "candidate_key", "queue_id"]:
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    return json.dumps(row, sort_keys=True)


def _candidate_rows_for_snapshot(history: dict, snapshot_id: str) -> dict[str, dict]:
    rows = {}
    for row in history.get("candidate_history_rows") or []:
        if str(row.get("snapshot_id") or "") != str(snapshot_id):
            continue
        rows[_candidate_key(row)] = dict(row)
    return rows


def _snapshot_by_id(history: dict) -> dict[str, dict]:
    return {str(row.get("snapshot_id") or ""): dict(row) for row in history.get("snapshots") or [] if row.get("snapshot_id")}


def _default_snapshot_pair(history: dict) -> tuple[str | None, str | None]:
    snapshots = [row for row in history.get("snapshots") or [] if row.get("snapshot_id")]
    snapshots.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    if len(snapshots) < 2:
        return None, None
    return str(snapshots[1].get("snapshot_id")), str(snapshots[0].get("snapshot_id"))


def compare_profile_rollback_snapshots(
    history: dict,
    *,
    base_snapshot_id: str | None = None,
    head_snapshot_id: str | None = None,
    project_name: str | None = "demo_learning",
) -> dict:
    snapshots = _snapshot_by_id(history)
    default_base, default_head = _default_snapshot_pair(history)
    base_id = base_snapshot_id or default_base
    head_id = head_snapshot_id or default_head
    now = datetime.now(timezone.utc).isoformat()
    if not base_id or not head_id or base_id not in snapshots or head_id not in snapshots or base_id == head_id:
        return {
            "created_at": now,
            "status": "insufficient_snapshots",
            "project_name": project_name,
            "base_snapshot_id": base_id,
            "head_snapshot_id": head_id,
            "snapshot_count": len(snapshots),
            "rows": [],
            "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
            "recommended_next_actions": ["Build rollback history with at least two distinct snapshots before comparing drift."],
        }
    base_rows = _candidate_rows_for_snapshot(history, base_id)
    head_rows = _candidate_rows_for_snapshot(history, head_id)
    keys = sorted(set(base_rows) | set(head_rows))
    rows = []
    for key in keys:
        base = base_rows.get(key) or {}
        head = head_rows.get(key) or {}
        if base and head:
            status = "changed" if any(
                str(base.get(field) or "") != str(head.get(field) or "")
                for field in ["rollback_action", "queue_rank", "rollback_score_delta", "rollback_rank_delta", "current_membership", "material_acceptance_status"]
            ) else "unchanged"
        elif head:
            status = "added"
        else:
            status = "removed"
        score_delta_change = round(_float(head.get("rollback_score_delta")) - _float(base.get("rollback_score_delta")), 4) if base and head else ""
        rank_delta_change = round(_float(head.get("rollback_rank_delta")) - _float(base.get("rollback_rank_delta")), 4) if base and head else ""
        queue_rank_change = ""
        if base and head and base.get("queue_rank") not in {None, ""} and head.get("queue_rank") not in {None, ""}:
            queue_rank_change = round(_float(head.get("queue_rank")) - _float(base.get("queue_rank")), 4)
        rows.append(
            {
                "candidate_key": key,
                "status": status,
                "base_snapshot_id": base_id,
                "head_snapshot_id": head_id,
                "candidate_id": head.get("candidate_id") or base.get("candidate_id"),
                "queue_id": head.get("queue_id") or base.get("queue_id"),
                "base_rollback_action": base.get("rollback_action", ""),
                "head_rollback_action": head.get("rollback_action", ""),
                "base_queue_rank": base.get("queue_rank", ""),
                "head_queue_rank": head.get("queue_rank", ""),
                "queue_rank_change": queue_rank_change,
                "base_rollback_score_delta": base.get("rollback_score_delta", ""),
                "head_rollback_score_delta": head.get("rollback_score_delta", ""),
                "rollback_score_delta_change": score_delta_change,
                "base_rollback_rank_delta": base.get("rollback_rank_delta", ""),
                "head_rollback_rank_delta": head.get("rollback_rank_delta", ""),
                "rollback_rank_delta_change": rank_delta_change,
                "base_membership": base.get("current_membership", ""),
                "head_membership": head.get("current_membership", ""),
                "base_material_acceptance_status": base.get("material_acceptance_status", ""),
                "head_material_acceptance_status": head.get("material_acceptance_status", ""),
            }
        )
    status_counts = Counter(row["status"] for row in rows)
    changed_rows = [row for row in rows if row["status"] == "changed"]
    return {
        "created_at": now,
        "status": "compared",
        "project_name": project_name,
        "base_snapshot_id": base_id,
        "head_snapshot_id": head_id,
        "base_snapshot_type": snapshots[base_id].get("snapshot_type"),
        "head_snapshot_type": snapshots[head_id].get("snapshot_type"),
        "base_created_at": snapshots[base_id].get("created_at"),
        "head_created_at": snapshots[head_id].get("created_at"),
        "shared_candidate_count": len(set(base_rows) & set(head_rows)),
        "added_candidate_count": status_counts.get("added", 0),
        "removed_candidate_count": status_counts.get("removed", 0),
        "changed_candidate_count": status_counts.get("changed", 0),
        "unchanged_candidate_count": status_counts.get("unchanged", 0),
        "status_counts": dict(status_counts.most_common()),
        "max_abs_score_delta_change": max([abs(_float(row.get("rollback_score_delta_change"))) for row in changed_rows] or [0.0]),
        "max_abs_rank_delta_change": max([abs(_float(row.get("rollback_rank_delta_change"))) for row in changed_rows] or [0.0]),
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Review changed candidates before profile activation or rollback.",
            "Use added/removed rows to distinguish real candidate movement from snapshot packaging drift.",
            "Keep the comparison scoped to profile, ranking, evidence, and candidate history artifacts.",
        ],
    }


def build_profile_rollback_history(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    current_replay_path: str | Path = "data/projects/demo/profile_promotion_rollback_replay.json",
    iteration_root: str | Path = "data/projects/iterations",
    freeze_root: str | Path = "data/projects/promotion_freezes",
    limit: int = 8,
) -> dict:
    root_path = Path(root)
    current_file = Path(current_replay_path)
    current_file = current_file if current_file.is_absolute() else root_path / current_file
    iteration_dir = Path(iteration_root)
    iteration_dir = iteration_dir if iteration_dir.is_absolute() else root_path / iteration_dir
    freeze_dir = Path(freeze_root)
    freeze_dir = freeze_dir if freeze_dir.is_absolute() else root_path / freeze_dir
    current_replay = _read_json(current_file)
    snapshots = []
    current_snapshot = _snapshot_from_replay("current", "current", current_replay.get("created_at"), current_replay, path=current_file)
    if current_replay:
        snapshots.append(current_snapshot)
    snapshots.extend(_iteration_snapshots(root_path, iteration_dir, limit=limit))
    snapshots.extend(_freeze_snapshots(root_path, freeze_dir, limit=limit))
    unique = {}
    for snapshot in snapshots:
        key = (snapshot.get("snapshot_type"), snapshot.get("snapshot_id"))
        unique[key] = snapshot
    snapshots = sorted(unique.values(), key=lambda row: str(row.get("created_at") or ""), reverse=True)

    candidate_rows = []
    if current_replay:
        candidate_rows.extend(_candidate_history(current_snapshot, current_replay))
    for snapshot in snapshots:
        if snapshot.get("snapshot_type") == "current":
            continue
        replay = _read_json(snapshot.get("source_path")) if snapshot.get("source_path") else {}
        if replay:
            candidate_rows.extend(_candidate_history(snapshot, replay))
    type_counts = Counter(str(row.get("snapshot_type") or "unknown") for row in snapshots)
    status_counts = Counter(str(row.get("status") or "unknown") for row in snapshots)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if snapshots else "empty",
        "project_name": project_name,
        "snapshot_count": len(snapshots),
        "candidate_history_count": len(candidate_rows),
        "snapshot_type_counts": dict(type_counts.most_common()),
        "snapshot_status_counts": dict(status_counts.most_common()),
        "snapshots": snapshots,
        "candidate_history_rows": candidate_rows,
        "transitions": _transitions(snapshots),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Compare rollback history before activating or rolling back profile changes.",
            "Use candidate_history_rows to identify recurring profile-sensitive candidates across snapshots.",
            "Keep rollback analysis scoped to profile, ranking, and evidence artifacts only.",
        ],
    }


def write_profile_rollback_history(
    report: dict,
    output_path: str | Path = DEFAULT_PROFILE_ROLLBACK_HISTORY_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROFILE_ROLLBACK_HISTORY_CSV_PATH,
    candidate_csv_path: str | Path | None = DEFAULT_PROFILE_ROLLBACK_CANDIDATE_HISTORY_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is not None:
        fieldnames = [
            "snapshot_id",
            "snapshot_type",
            "created_at",
            "status",
            "active_freeze_id",
            "latest_release_tag",
            "row_count",
            "queue_linked_count",
            "max_abs_rollback_score_delta",
            "max_abs_rollback_rank_delta",
            "restore_base_profile_priority_count",
            "remove_candidate_profile_promotion_count",
            "source_path",
        ]
        csv_out = Path(csv_path)
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in report.get("snapshots") or []:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
    if candidate_csv_path is None:
        return
    candidate_fields = [
        "snapshot_id",
        "snapshot_type",
        "snapshot_created_at",
        "candidate_id",
        "candidate_key",
        "queue_id",
        "queue_rank",
        "rollback_action",
        "rollback_score_delta",
        "rollback_rank_delta",
        "current_membership",
        "material_acceptance_status",
    ]
    candidate_out = Path(candidate_csv_path)
    candidate_out.parent.mkdir(parents=True, exist_ok=True)
    with candidate_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields)
        writer.writeheader()
        for row in report.get("candidate_history_rows") or []:
            writer.writerow({field: row.get(field, "") for field in candidate_fields})


def write_profile_rollback_snapshot_compare(
    report: dict,
    output_path: str | Path = DEFAULT_PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROFILE_ROLLBACK_SNAPSHOT_COMPARE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "candidate_key",
        "status",
        "base_snapshot_id",
        "head_snapshot_id",
        "candidate_id",
        "queue_id",
        "base_rollback_action",
        "head_rollback_action",
        "base_queue_rank",
        "head_queue_rank",
        "queue_rank_change",
        "base_rollback_score_delta",
        "head_rollback_score_delta",
        "rollback_score_delta_change",
        "base_rollback_rank_delta",
        "head_rollback_rank_delta",
        "rollback_rank_delta_change",
        "base_membership",
        "head_membership",
        "base_material_acceptance_status",
        "head_material_acceptance_status",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
