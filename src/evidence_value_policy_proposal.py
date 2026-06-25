from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .evidence_value_scoring import DEFAULT_EVIDENCE_VALUE_ACTIVE_POLICY_PATH, EVIDENCE_VALUE_POLICY


DEFAULT_EVIDENCE_VALUE_POLICY_PROPOSAL_PATH = Path("data/projects/demo/evidence_value_policy_proposal.json")
DEFAULT_EVIDENCE_VALUE_POLICY_PROPOSAL_CSV_PATH = Path("data/projects/demo/evidence_value_policy_proposal.csv")
DEFAULT_EVIDENCE_VALUE_POLICY_REPLAY_PATH = Path("data/projects/demo/evidence_value_policy_replay.json")
DEFAULT_EVIDENCE_VALUE_POLICY_REPLAY_CSV_PATH = Path("data/projects/demo/evidence_value_policy_replay.csv")
DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVATION_PATH = Path("data/projects/demo/evidence_value_policy_activation.json")
DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVATION_CSV_PATH = Path("data/projects/demo/evidence_value_policy_activation.csv")

EVIDENCE_VALUE_POLICY_PROPOSAL_DECISIONS = {"pending_review", "approved", "rejected", "deferred"}


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(data: dict, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _proposal_id(*parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"EVPOL-{digest}"


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


def _proposal_version(base_version: str, created_at: str) -> str:
    compact = created_at.replace("-", "").replace(":", "").split(".")[0]
    return f"{base_version}-proposal-{compact}"


def _changed_weights(calibration: dict) -> list[dict]:
    current = dict((calibration.get("policy") or EVIDENCE_VALUE_POLICY).get("weights") or EVIDENCE_VALUE_POLICY["weights"])
    changes = []
    for item in calibration.get("recommended_weight_adjustments") or []:
        weight = str(item.get("weight") or "")
        direction = str(item.get("direction") or "")
        if weight not in current or direction not in {"increase", "decrease"}:
            continue
        old = float(current[weight])
        factor = 1.1 if direction == "increase" else 0.9
        new = round(max(0.0, old * factor), 4)
        changes.append(
            {
                "weight": weight,
                "direction": direction,
                "current_weight": old,
                "proposed_weight": new,
                "delta": round(new - old, 4),
                "basis": item.get("basis") or "",
                "observed_mean_signed_error": item.get("observed_mean_signed_error"),
            }
        )
    return changes


def _apply_changes(current_weights: dict, changes: list[dict]) -> dict:
    proposed = dict(current_weights)
    for change in changes:
        proposed[str(change.get("weight"))] = change.get("proposed_weight")
    return proposed


def _sufficiency_gap_factor(row: dict) -> float:
    status = str(row.get("evidence_sufficiency_status") or "")
    if status == "conflict_review":
        return 1.0
    if status.startswith("needs"):
        return 0.8
    if status and status != "sufficient":
        return 0.45
    return 0.0


def _tier(score: float) -> str:
    if score >= 36:
        return "high_value"
    if score >= 22:
        return "medium_value"
    return "watch"


def _score_with_weights(row: dict, weights: dict) -> float:
    sar_links = _int(row.get("public_sar_link_count"))
    contradiction_units = _int(row.get("public_sar_contradiction_count")) + _int(row.get("linked_contradiction_triage_count"))
    material_units = _int(row.get("material_ab_diff_count"))
    rollback_impact = abs(_float(row.get("rollback_score_delta"))) + abs(_float(row.get("rollback_rank_delta"))) * 0.18
    value_score = (
        _float(row.get("candidate_evidence_priority_score")) * _float(weights.get("candidate_priority"))
        + min(12.0, sar_links * _float(weights.get("sar_link")))
        + min(20.0, contradiction_units * _float(weights.get("contradiction")))
        + _sufficiency_gap_factor(row) * _float(weights.get("sufficiency_gap"))
        + min(12.0, material_units * _float(weights.get("material_ab")))
        + min(18.0, rollback_impact * _float(weights.get("rollback_impact")))
    )
    return round(max(0.0, min(100.0, value_score)), 2)


def build_evidence_value_policy_proposal(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    calibration_path: str | Path = "data/projects/demo/evidence_value_calibration_report.json",
    rollback_compare_path: str | Path = "data/projects/demo/profile_rollback_snapshot_compare.json",
    min_calibration_rows: int = 3,
) -> dict:
    root_path = Path(root)
    calibration_file = Path(calibration_path)
    if not calibration_file.is_absolute():
        calibration_file = root_path / calibration_file
    rollback_file = Path(rollback_compare_path)
    if not rollback_file.is_absolute():
        rollback_file = root_path / rollback_file
    calibration = _read_json(calibration_file)
    rollback_compare = _read_json(rollback_file)
    now = datetime.now(timezone.utc).isoformat()
    base_policy = calibration.get("policy") or EVIDENCE_VALUE_POLICY
    base_version = str(base_policy.get("version") or EVIDENCE_VALUE_POLICY["version"])
    current_weights = dict(base_policy.get("weights") or EVIDENCE_VALUE_POLICY["weights"])
    calibration_rows = int(calibration.get("calibration_row_count") or 0)
    changes = _changed_weights(calibration)
    rollback_ready = rollback_compare.get("status") == "compared"
    status = "review_required"
    approval_status = "pending_review"
    if calibration.get("status") != "calibrated" or calibration_rows < int(min_calibration_rows):
        status = "insufficient_calibration_data"
        approval_status = "not_requested"
    elif not rollback_ready:
        status = "blocked_missing_rollback_compare"
        approval_status = "not_requested"
    elif not changes:
        status = "hold_current_policy"
        approval_status = "not_required"
    proposal_version = _proposal_version(base_version, now)
    proposed_weights = _apply_changes(current_weights, changes)
    return {
        "created_at": now,
        "status": status,
        "proposal_id": _proposal_id(project_name, base_version, proposal_version, calibration.get("created_at")),
        "project_name": project_name,
        "base_policy_version": base_version,
        "proposed_policy_version": proposal_version,
        "approval_status": approval_status,
        "activation_status": "not_active",
        "min_calibration_rows": int(min_calibration_rows),
        "calibration_status": calibration.get("status") or "missing",
        "calibration_created_at": calibration.get("created_at"),
        "calibration_row_count": calibration_rows,
        "mean_absolute_error": calibration.get("mean_absolute_error"),
        "mean_signed_error": calibration.get("mean_signed_error"),
        "rank_alignment_rate": calibration.get("rank_alignment_rate"),
        "value_driver_error_summary": calibration.get("value_driver_error_summary") or [],
        "priority_driver_weight_adjustments": calibration.get("priority_driver_weight_adjustments") or [],
        "rollback_compare_status": rollback_compare.get("status") or "missing",
        "rollback_compare_id": f"{rollback_compare.get('base_snapshot_id') or ''}->{rollback_compare.get('head_snapshot_id') or ''}",
        "current_weights": current_weights,
        "proposed_weights": proposed_weights,
        "weight_change_count": len(changes),
        "weight_changes": changes,
        "decision_history": [],
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Review the proposed weight changes before activation; this report does not auto-change scoring.",
            "Require rollback snapshot comparison before approving evidence-value policy changes.",
            "Rebuild evidence value and measurement feedback reports after any approved policy update.",
        ],
    }


def review_evidence_value_policy_proposal(
    *,
    proposal_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
    decision: str,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    if decision not in EVIDENCE_VALUE_POLICY_PROPOSAL_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(EVIDENCE_VALUE_POLICY_PROPOSAL_DECISIONS)}")
    path = Path(proposal_path)
    proposal = _read_json(path)
    now = datetime.now(timezone.utc).isoformat()
    history = list(proposal.get("decision_history") or [])
    event = {
        "decided_at": now,
        "decision": decision,
        "reviewer": reviewer or "",
        "note": note or "",
    }
    history.append(event)
    proposal["approval_status"] = decision
    proposal["decision_history"] = history
    proposal["updated_at"] = now
    if decision == "approved":
        proposal["status"] = "approved_not_active"
    elif decision in {"rejected", "deferred"}:
        proposal["status"] = decision
    elif proposal.get("weight_change_count"):
        proposal["status"] = "review_required"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proposal, indent=2, sort_keys=True), encoding="utf-8")
    return proposal


def build_evidence_value_policy_replay(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    proposal_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
    evidence_value_path: str | Path = "data/projects/demo/evidence_value_report.json",
    top_n: int = 10,
    max_allowed_top_n_changes: int = 2,
    max_allowed_score_delta: float = 8.0,
    max_allowed_rank_delta: int = 5,
) -> dict:
    root_path = Path(root)
    proposal_file = Path(proposal_path)
    if not proposal_file.is_absolute():
        proposal_file = root_path / proposal_file
    evidence_file = Path(evidence_value_path)
    if not evidence_file.is_absolute():
        evidence_file = root_path / evidence_file
    proposal = _read_json(proposal_file)
    evidence = _read_json(evidence_file)
    current_weights = proposal.get("current_weights") or (evidence.get("policy") or EVIDENCE_VALUE_POLICY).get("weights") or EVIDENCE_VALUE_POLICY["weights"]
    proposed_weights = proposal.get("proposed_weights") or current_weights
    current_rows = [dict(row) for row in evidence.get("rows") or []]
    current_rank_by_id = {}
    for index, row in enumerate(current_rows, start=1):
        key = str(row.get("evidence_value_id") or row.get("queue_id") or row.get("candidate_id") or index)
        current_rank_by_id[key] = index
        row["_replay_key"] = key
    proposed_rank_rows = []
    for row in current_rows:
        current_score = _score_with_weights(row, current_weights)
        proposed_score = _score_with_weights(row, proposed_weights)
        proposed_rank_rows.append(
            {
                **row,
                "current_recomputed_score": current_score,
                "proposed_evidence_value_score": proposed_score,
                "score_delta": round(proposed_score - current_score, 4),
                "current_tier": row.get("evidence_value_tier") or _tier(current_score),
                "proposed_tier": _tier(proposed_score),
            }
        )
    proposed_rank_rows.sort(
        key=lambda row: (
            -_float(row.get("proposed_evidence_value_score")),
            _int(str(row.get("queue_id") or "").replace("NDQ-", ""), 9999),
            str(row.get("candidate_id") or ""),
        )
    )
    rows = []
    proposed_rank_by_id = {str(row.get("_replay_key")): index for index, row in enumerate(proposed_rank_rows, start=1)}
    for row in proposed_rank_rows:
        key = str(row.get("_replay_key"))
        current_rank = current_rank_by_id.get(key)
        proposed_rank = proposed_rank_by_id.get(key)
        rank_delta = (proposed_rank or 0) - (current_rank or 0)
        rows.append(
            {
                "evidence_value_id": row.get("evidence_value_id"),
                "queue_id": row.get("queue_id"),
                "candidate_id": row.get("candidate_id"),
                "smiles": row.get("smiles"),
                "endpoint_group": row.get("endpoint_group"),
                "value_driver_flags": row.get("value_driver_flags"),
                "current_rank": current_rank,
                "proposed_rank": proposed_rank,
                "rank_delta": rank_delta,
                "current_evidence_value_score": row.get("evidence_value_score"),
                "current_recomputed_score": row.get("current_recomputed_score"),
                "proposed_evidence_value_score": row.get("proposed_evidence_value_score"),
                "score_delta": row.get("score_delta"),
                "current_tier": row.get("current_tier"),
                "proposed_tier": row.get("proposed_tier"),
                "tier_changed": row.get("current_tier") != row.get("proposed_tier"),
                "next_evidence_action": row.get("next_evidence_action"),
            }
        )
    top_n = max(1, int(top_n))
    current_top = {str(row.get("_replay_key")) for row in sorted(current_rows, key=lambda row: current_rank_by_id.get(str(row.get("_replay_key")), 9999))[:top_n]}
    proposed_top = {str(row.get("_replay_key")) for row in proposed_rank_rows[:top_n]}
    top_n_change_count = len(current_top.symmetric_difference(proposed_top))
    max_abs_score_delta = max((abs(_float(row.get("score_delta"))) for row in rows), default=0.0)
    max_abs_rank_delta = max((abs(_int(row.get("rank_delta"))) for row in rows), default=0)
    tier_changed_count = sum(1 for row in rows if row.get("tier_changed"))
    approval = str(proposal.get("approval_status") or "")
    drift_ok = (
        top_n_change_count <= int(max_allowed_top_n_changes)
        and max_abs_score_delta <= float(max_allowed_score_delta)
        and max_abs_rank_delta <= int(max_allowed_rank_delta)
    )
    if not rows:
        activation_gate_status = "blocked_missing_evidence_rows"
    elif approval != "approved":
        activation_gate_status = "blocked_pending_manual_approval"
    elif not drift_ok:
        activation_gate_status = "blocked_replay_drift_review"
    else:
        activation_gate_status = "ready_for_manual_activation"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "compared" if rows else "empty",
        "project_name": project_name,
        "proposal_id": proposal.get("proposal_id"),
        "proposal_status": proposal.get("status") or "missing",
        "approval_status": approval or "missing",
        "activation_status": "not_active",
        "activation_gate_status": activation_gate_status,
        "base_policy_version": proposal.get("base_policy_version") or (evidence.get("policy") or {}).get("version"),
        "proposed_policy_version": proposal.get("proposed_policy_version"),
        "row_count": len(rows),
        "top_n": top_n,
        "top_n_change_count": top_n_change_count,
        "tier_changed_count": tier_changed_count,
        "max_abs_score_delta": round(max_abs_score_delta, 4),
        "max_abs_rank_delta": max_abs_rank_delta,
        "max_allowed_top_n_changes": int(max_allowed_top_n_changes),
        "max_allowed_score_delta": float(max_allowed_score_delta),
        "max_allowed_rank_delta": int(max_allowed_rank_delta),
        "drift_ok": drift_ok,
        "current_weights": current_weights,
        "proposed_weights": proposed_weights,
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Keep proposal activation blocked until a human reviewer approves it.",
            "If replay drift exceeds thresholds, revise the proposal or split the weight change into a smaller version.",
            "After manual activation, rebuild evidence value, measurement feedback, promotion gate, freeze, and iteration packages.",
        ],
    }


def activate_evidence_value_policy_proposal(
    *,
    proposal_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
    replay_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_REPLAY_PATH,
    active_policy_path: str | Path = DEFAULT_EVIDENCE_VALUE_ACTIVE_POLICY_PATH,
    activation_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVATION_PATH,
    reviewer: str | None = None,
    note: str | None = None,
    write_back: bool = True,
) -> dict:
    proposal_file = Path(proposal_path)
    replay_file = Path(replay_path)
    active_file = Path(active_policy_path)
    activation_file = Path(activation_path)
    proposal = _read_json(proposal_file)
    replay = _read_json(replay_file)
    now = datetime.now(timezone.utc).isoformat()
    blocked_reasons = []
    if proposal.get("approval_status") != "approved":
        blocked_reasons.append("proposal_not_approved")
    if replay.get("activation_gate_status") != "ready_for_manual_activation" and replay.get("activation_status") != "active":
        blocked_reasons.append("replay_gate_not_ready")
    if not proposal.get("proposed_weights"):
        blocked_reasons.append("missing_proposed_weights")
    if proposal.get("activation_status") == "active":
        blocked_reasons.append("proposal_already_active")

    activation_event = {
        "activated_at": now,
        "reviewer": reviewer or "",
        "note": note or "",
        "proposal_id": proposal.get("proposal_id"),
        "proposed_policy_version": proposal.get("proposed_policy_version"),
    }
    base_report = {
        "created_at": now,
        "status": "blocked" if blocked_reasons else "activated",
        "project_name": proposal.get("project_name") or replay.get("project_name"),
        "proposal_id": proposal.get("proposal_id"),
        "approval_status": proposal.get("approval_status") or "missing",
        "proposal_status": proposal.get("status") or "missing",
        "activation_status": "blocked" if blocked_reasons else "active",
        "activation_gate_status": replay.get("activation_gate_status") or "missing",
        "blocked_reasons": blocked_reasons,
        "base_policy_version": proposal.get("base_policy_version"),
        "activated_policy_version": proposal.get("proposed_policy_version"),
        "active_policy_path": str(active_file),
        "weight_change_count": proposal.get("weight_change_count", 0),
        "top_n_change_count": replay.get("top_n_change_count"),
        "max_abs_score_delta": replay.get("max_abs_score_delta"),
        "max_abs_rank_delta": replay.get("max_abs_rank_delta"),
        "reviewer": reviewer or "",
        "note": note or "",
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
    }
    if blocked_reasons:
        if write_back:
            _write_json(base_report, activation_file)
        return base_report

    active_policy = {
        "created_at": now,
        "activated_at": now,
        "activation_status": "active",
        "status": "active",
        "policy_version": proposal.get("proposed_policy_version"),
        "version": proposal.get("proposed_policy_version"),
        "base_policy_version": proposal.get("base_policy_version"),
        "source_proposal_id": proposal.get("proposal_id"),
        "source_calibration_created_at": proposal.get("calibration_created_at"),
        "weights": proposal.get("proposed_weights") or {},
        "weight_changes": proposal.get("weight_changes") or [],
        "reviewer": reviewer or "",
        "note": note or "",
        "replay_metrics": {
            "top_n_change_count": replay.get("top_n_change_count"),
            "max_abs_score_delta": replay.get("max_abs_score_delta"),
            "max_abs_rank_delta": replay.get("max_abs_rank_delta"),
            "drift_ok": replay.get("drift_ok"),
        },
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
    }
    proposal_history = list(proposal.get("activation_history") or [])
    proposal_history.append(activation_event)
    proposal.update(
        {
            "status": "activated",
            "activation_status": "active",
            "activated_at": now,
            "activated_by": reviewer or "",
            "active_policy_path": str(active_file),
            "activation_history": proposal_history,
            "updated_at": now,
        }
    )
    replay.update(
        {
            "activation_status": "active",
            "activation_gate_status": "activated",
            "activated_at": now,
            "active_policy_path": str(active_file),
        }
    )
    report = {
        **base_report,
        "active_weights": active_policy["weights"],
        "active_policy": active_policy,
        "recommended_next_actions": [
            "Rebuild evidence value scoring so downstream reports carry the active policy version.",
            "Keep activation history attached to promotion gates and iteration packages.",
            "Open a new policy proposal only after new measurement feedback changes calibration evidence.",
        ],
    }
    if write_back:
        _write_json(active_policy, active_file)
        _write_json(proposal, proposal_file)
        _write_json(replay, replay_file)
        _write_json(report, activation_file)
    return report


def write_evidence_value_policy_proposal(
    report: dict,
    output_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_VALUE_POLICY_PROPOSAL_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "proposal_id",
        "status",
        "approval_status",
        "activation_status",
        "base_policy_version",
        "proposed_policy_version",
        "weight",
        "direction",
        "current_weight",
        "proposed_weight",
        "delta",
        "basis",
        "observed_mean_signed_error",
        "calibration_row_count",
        "rollback_compare_status",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        rows = report.get("weight_changes") or [{}]
        for change in rows:
            row = {
                "proposal_id": report.get("proposal_id", ""),
                "status": report.get("status", ""),
                "approval_status": report.get("approval_status", ""),
                "activation_status": report.get("activation_status", ""),
                "base_policy_version": report.get("base_policy_version", ""),
                "proposed_policy_version": report.get("proposed_policy_version", ""),
                "calibration_row_count": report.get("calibration_row_count", ""),
                "rollback_compare_status": report.get("rollback_compare_status", ""),
            }
            row.update({field: change.get(field, "") for field in fieldnames if field not in row})
            writer.writerow(
                row
            )


def write_evidence_value_policy_replay(
    report: dict,
    output_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_REPLAY_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_VALUE_POLICY_REPLAY_CSV_PATH,
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
        "current_rank",
        "proposed_rank",
        "rank_delta",
        "current_evidence_value_score",
        "current_recomputed_score",
        "proposed_evidence_value_score",
        "score_delta",
        "current_tier",
        "proposed_tier",
        "tier_changed",
        "next_evidence_action",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_evidence_value_policy_activation(
    report: dict,
    output_path: str | Path = DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVATION_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_VALUE_POLICY_ACTIVATION_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "status",
        "proposal_id",
        "approval_status",
        "activation_status",
        "activation_gate_status",
        "base_policy_version",
        "activated_policy_version",
        "weight_change_count",
        "top_n_change_count",
        "max_abs_score_delta",
        "max_abs_rank_delta",
        "reviewer",
        "note",
        "blocked_reasons",
        "active_policy_path",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    row = {field: report.get(field, "") for field in fieldnames}
    row["blocked_reasons"] = ";".join(report.get("blocked_reasons") or [])
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)
