from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_PATH = Path("data/projects/demo/evidence_value_policy_active_compare.json")
DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_CSV_PATH = Path("data/projects/demo/evidence_value_policy_active_compare.csv")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve(root_path: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root_path / item


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


def _identity_keys(row: dict) -> set[str]:
    keys = set()
    for field in ["queue_id", "candidate_id", "smiles"]:
        value = str(row.get(field) or "").strip()
        if value:
            keys.add(f"{field}:{value}")
    return keys


def _lookup_by_identity(rows: list[dict]) -> dict[str, dict]:
    lookup = {}
    for row in rows:
        for key in _identity_keys(row):
            lookup[key] = dict(row)
    return lookup


def _linked(row: dict, lookup: dict[str, dict]) -> dict:
    for key in _identity_keys(row):
        if key in lookup:
            return lookup[key]
    return {}


def build_evidence_value_policy_active_compare(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    proposal_path: str | Path = "data/projects/demo/evidence_value_policy_proposal.json",
    replay_path: str | Path = "data/projects/demo/evidence_value_policy_replay.json",
    active_policy_path: str | Path = "data/projects/demo/evidence_value_policy_active.json",
    evidence_value_path: str | Path = "data/projects/demo/evidence_value_report.json",
    rollback_replay_path: str | Path = "data/projects/demo/profile_promotion_rollback_replay.json",
    top_n: int = 12,
    profile_score_delta_review_threshold: float = 6.0,
    profile_rank_delta_review_threshold: float = 10.0,
) -> dict:
    root_path = Path(root)
    proposal = _read_json(_resolve(root_path, proposal_path))
    replay = _read_json(_resolve(root_path, replay_path))
    active_policy = _read_json(_resolve(root_path, active_policy_path))
    evidence = _read_json(_resolve(root_path, evidence_value_path))
    rollback = _read_json(_resolve(root_path, rollback_replay_path))
    rollback_lookup = _lookup_by_identity([dict(row) for row in rollback.get("rows") or []])
    evidence_lookup = _lookup_by_identity([dict(row) for row in evidence.get("rows") or []])
    rows = []
    for raw in replay.get("rows") or []:
        row = dict(raw)
        evidence_row = _linked(row, evidence_lookup)
        rollback_row = _linked(row, rollback_lookup)
        rollback_score_delta = rollback_row.get("rollback_score_delta") if rollback_row else None
        rollback_rank_delta = rollback_row.get("rollback_rank_delta") if rollback_row else None
        profile_score_delta = _float(rollback_score_delta)
        profile_rank_delta = _float(rollback_rank_delta)
        profile_review_flag = (
            abs(profile_score_delta) >= float(profile_score_delta_review_threshold)
            or abs(profile_rank_delta) >= float(profile_rank_delta_review_threshold)
        )
        rows.append(
            {
                "evidence_value_id": row.get("evidence_value_id"),
                "queue_id": row.get("queue_id"),
                "candidate_id": row.get("candidate_id"),
                "smiles": row.get("smiles"),
                "endpoint_group": row.get("endpoint_group"),
                "value_driver_flags": row.get("value_driver_flags"),
                "baseline_rank": row.get("current_rank"),
                "active_rank": row.get("proposed_rank"),
                "rank_delta": row.get("rank_delta"),
                "baseline_score": row.get("current_recomputed_score") or row.get("current_evidence_value_score"),
                "active_score": row.get("proposed_evidence_value_score") or evidence_row.get("evidence_value_score"),
                "score_delta": row.get("score_delta"),
                "baseline_tier": row.get("current_tier"),
                "active_tier": row.get("proposed_tier") or evidence_row.get("evidence_value_tier"),
                "tier_changed": row.get("tier_changed"),
                "next_evidence_action": row.get("next_evidence_action") or evidence_row.get("next_evidence_action"),
                "profile_rollback_action": rollback_row.get("rollback_action", ""),
                "profile_rollback_score_delta": rollback_score_delta,
                "profile_rollback_rank_delta": rollback_rank_delta,
                "profile_impact_review_flag": profile_review_flag,
            }
        )
    rows.sort(
        key=lambda row: (
            _int(row.get("active_rank"), 9999),
            -_float(row.get("active_score")),
            str(row.get("candidate_id") or ""),
        )
    )
    top_n = max(1, int(top_n))
    top_rows = rows[:top_n]
    profile_review_count = sum(1 for row in rows if row.get("profile_impact_review_flag"))
    tier_counts = Counter(str(row.get("active_tier") or "unknown") for row in rows)
    active = active_policy.get("activation_status") == "active"
    status = "compared" if active and rows else "empty" if active else "blocked_no_active_policy"
    baseline_policy_version = proposal.get("base_policy_version") or replay.get("base_policy_version")
    active_policy_version = active_policy.get("policy_version") or active_policy.get("version") or replay.get("proposed_policy_version")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "proposal_id": proposal.get("proposal_id") or replay.get("proposal_id"),
        "baseline_policy_version": baseline_policy_version,
        "active_policy_version": active_policy_version,
        "activation_status": active_policy.get("activation_status") or "missing",
        "row_count": len(rows),
        "top_n": top_n,
        "top_n_rows": top_rows,
        "tier_counts": dict(tier_counts.most_common()),
        "max_abs_score_delta": max((abs(_float(row.get("score_delta"))) for row in rows), default=0.0),
        "max_abs_rank_delta": max((abs(_int(row.get("rank_delta"))) for row in rows), default=0),
        "tier_changed_count": sum(1 for row in rows if row.get("tier_changed")),
        "profile_impact_review_count": profile_review_count,
        "rollback_available": bool(baseline_policy_version and active_policy_version and baseline_policy_version != active_policy_version),
        "rollback_target_policy_version": baseline_policy_version,
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Use this active-vs-baseline view before accepting future policy changes.",
            "If profile impact flags rise after new assay feedback, rollback to the baseline policy version and replay.",
            "Keep active policy comparison attached to Project Memory and promotion gate artifacts.",
        ],
    }


def write_evidence_value_policy_active_compare(
    report: dict,
    output_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "evidence_value_id",
        "queue_id",
        "candidate_id",
        "endpoint_group",
        "value_driver_flags",
        "baseline_rank",
        "active_rank",
        "rank_delta",
        "baseline_score",
        "active_score",
        "score_delta",
        "baseline_tier",
        "active_tier",
        "tier_changed",
        "next_evidence_action",
        "profile_rollback_action",
        "profile_rollback_score_delta",
        "profile_rollback_rank_delta",
        "profile_impact_review_flag",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
