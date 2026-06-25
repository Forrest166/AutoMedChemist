from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROFILE_PROMOTION_ROLLBACK_REPLAY_PATH = Path("data/projects/demo/profile_promotion_rollback_replay.json")
DEFAULT_PROFILE_PROMOTION_ROLLBACK_REPLAY_CSV_PATH = Path("data/projects/demo/profile_promotion_rollback_replay.csv")


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


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _latest_next_design_queue_path(root_path: Path, project_name: str | None) -> Path | None:
    queue_dir = root_path / "data/projects/closed_loop"
    candidates = []
    if project_name:
        candidates.append(queue_dir / f"next_design_queue_{project_name}.json")
    candidates.extend(path for path in queue_dir.glob("next_design_queue*.json") if "decision" not in path.stem)
    existing = [path for path in candidates if path.exists() and path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def _queue_rows(payload: dict) -> list[dict]:
    for key in ["queue", "queue_rows", "rows", "top_rows"]:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _queue_lookup(rows: list[dict]) -> dict[str, dict]:
    lookup = {}
    for row in rows:
        for field in ["queue_id", "candidate_id", "smiles"]:
            value = str(row.get(field) or "")
            if value:
                lookup[f"{field}:{value}"] = row
    return lookup


def _linked_queue_row(diff: dict, lookup: dict[str, dict]) -> dict:
    keys = [
        f"candidate_id:{diff.get('candidate_candidate_id') or ''}",
        f"candidate_id:{diff.get('base_candidate_id') or ''}",
        f"smiles:{diff.get('candidate_key') or ''}",
    ]
    for key in keys:
        if key in lookup:
            return lookup[key]
    return {}


def _rollback_action(diff: dict) -> str:
    membership = str(diff.get("membership") or "")
    if membership == "lost_base_top":
        return "restore_base_profile_priority"
    if membership == "new_candidate_top":
        return "remove_candidate_profile_promotion"
    if abs(_float(diff.get("score_delta"))) >= 5:
        return "restore_base_score_weighting"
    return "rank_shift_only"


def build_profile_promotion_rollback_replay(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    queue_path: str | Path | None = None,
    matrix_path: str | Path = "data/projects/demo/profile_ab_replay_matrix.json",
    material_review_path: str | Path = "data/projects/demo/profile_ab_material_change_review.json",
    freeze_approvals_path: str | Path = "data/projects/demo/profile_promotion_freeze_approvals.json",
    rollback_drill_path: str | Path = "data/projects/demo/profile_promotion_freeze_rollback_drill.json",
) -> dict:
    root_path = Path(root)
    resolved_queue_path = Path(queue_path) if queue_path else _latest_next_design_queue_path(root_path, project_name)
    if resolved_queue_path and not resolved_queue_path.is_absolute():
        resolved_queue_path = root_path / resolved_queue_path
    matrix_file = Path(matrix_path)
    material_file = Path(material_review_path)
    approvals_file = Path(freeze_approvals_path)
    drill_file = Path(rollback_drill_path)
    matrix = _read_json(matrix_file if matrix_file.is_absolute() else root_path / matrix_file)
    material = _read_json(material_file if material_file.is_absolute() else root_path / material_file)
    approvals = _read_json(approvals_file if approvals_file.is_absolute() else root_path / approvals_file)
    drill = _read_json(drill_file if drill_file.is_absolute() else root_path / drill_file)
    queue = _queue_rows(_read_json(resolved_queue_path)) if resolved_queue_path else []
    queue_lookup = _queue_lookup(queue)
    rows = []
    for diff in material.get("candidate_diff_rows") or []:
        queue_row = _linked_queue_row(diff, queue_lookup)
        current_rank = _int(diff.get("candidate_rank"))
        rollback_rank = _int(diff.get("base_rank"))
        current_score = _float(diff.get("candidate_score"))
        rollback_score = _float(diff.get("base_score"))
        rollback_rank_delta = current_rank - rollback_rank if current_rank and rollback_rank else None
        rollback_score_delta = round(rollback_score - current_score, 4)
        rows.append(
            {
                "scenario_id": diff.get("scenario_id"),
                "candidate_id": diff.get("candidate_candidate_id") or diff.get("base_candidate_id"),
                "candidate_key": diff.get("candidate_key"),
                "queue_id": queue_row.get("queue_id"),
                "queue_rank": queue_row.get("queue_rank"),
                "queue_decision": queue_row.get("queue_decision"),
                "current_profile_rank": current_rank or None,
                "rollback_profile_rank": rollback_rank or None,
                "rollback_rank_delta": rollback_rank_delta,
                "current_profile_score": current_score,
                "rollback_profile_score": rollback_score,
                "rollback_score_delta": rollback_score_delta,
                "current_membership": diff.get("membership"),
                "rollback_action": _rollback_action(diff),
                "enumeration_type": diff.get("enumeration_type"),
                "replacement_label": diff.get("replacement_label"),
                "material_acceptance_status": diff.get("acceptance_status"),
            }
        )
    rows.sort(key=lambda row: (abs(_float(row.get("rollback_score_delta"))) + abs(_float(row.get("rollback_rank_delta"))) * 0.25), reverse=True)
    action_counts = Counter(str(row.get("rollback_action") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "project_name": project_name,
        "queue_path": str(resolved_queue_path) if resolved_queue_path else None,
        "active_freeze_id": approvals.get("active_freeze_id"),
        "latest_release_tag": approvals.get("latest_release_tag"),
        "rollback_drill_status": drill.get("status"),
        "would_release_tag": drill.get("would_release_tag"),
        "base_profile_path": matrix.get("base_profile_path"),
        "candidate_profile_path": matrix.get("candidate_profile_path"),
        "material_change_scenario_count": material.get("material_change_scenario_count"),
        "row_count": len(rows),
        "queue_linked_count": sum(1 for row in rows if row.get("queue_id")),
        "max_abs_rollback_score_delta": max((abs(_float(row.get("rollback_score_delta"))) for row in rows), default=0.0),
        "max_abs_rollback_rank_delta": max((abs(_float(row.get("rollback_rank_delta"))) for row in rows), default=0.0),
        "rollback_action_counts": dict(action_counts.most_common()),
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Use this replay before an executed rollback to identify candidates whose profile rank would materially change.",
            "Rebuild the promotion gate after any executed rollback and compare the resulting queue snapshot.",
            "Keep rollback replay tied to profile/ranking behavior only; procurement/vendor actions are out of scope.",
        ],
    }


def write_profile_promotion_rollback_replay(
    report: dict,
    output_path: str | Path = DEFAULT_PROFILE_PROMOTION_ROLLBACK_REPLAY_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROFILE_PROMOTION_ROLLBACK_REPLAY_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fieldnames = [
        "scenario_id",
        "candidate_id",
        "candidate_key",
        "queue_id",
        "queue_rank",
        "queue_decision",
        "current_profile_rank",
        "rollback_profile_rank",
        "rollback_rank_delta",
        "current_profile_score",
        "rollback_profile_score",
        "rollback_score_delta",
        "current_membership",
        "rollback_action",
        "enumeration_type",
        "replacement_label",
        "material_acceptance_status",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
