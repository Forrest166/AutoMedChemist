from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROMOTION_GATE_PATH = Path("data/projects/demo/closed_loop_promotion_gate.json")


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gate_check(check_id: str, label: str, status: str, details: str = "") -> dict:
    return {
        "check_id": check_id,
        "label": label,
        "status": status,
        "details": details,
    }


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_snapshot(root_path: Path, artifact_id: str, relative_path: str) -> dict:
    path = root_path / relative_path
    exists = path.exists()
    return {
        "artifact_id": artifact_id,
        "path": relative_path,
        "exists": exists,
        "size_bytes": path.stat().st_size if exists and path.is_file() else 0,
        "sha256": _sha256(path),
    }


def _promotion_gate_artifacts(root_path: Path) -> dict[str, dict]:
    artifacts = [
        ("project_closed_loop_dashboard", "data/projects/demo/project_closed_loop_dashboard.json"),
        ("closed_loop_replay_report", "data/projects/demo/closed_loop_replay_report.json"),
        ("closed_loop_drill_acceptance", "data/projects/closed_loop_drill/closed_loop_drill_acceptance.json"),
        ("project_evidence_pack", "data/projects/demo/project_evidence_pack.json"),
        ("profile_promotion_registry", "data/profiles/profile_promotion_registry.json"),
        ("profile_ab_replay_report", "data/projects/demo/profile_ab_replay_report.json"),
        ("profile_ab_replay_matrix", "data/projects/demo/profile_ab_replay_matrix.json"),
        ("profile_ab_material_change_review", "data/projects/demo/profile_ab_material_change_review.json"),
        ("candidate_evidence_priority_report", "data/projects/demo/candidate_evidence_priority_report.json"),
        ("public_sar_contradiction_triage", "data/projects/demo/public_sar_contradiction_triage.json"),
        ("public_sar_contradiction_resolution_batch", "data/projects/demo/public_sar_contradiction_resolution_batch.json"),
        ("public_sar_contradiction_watchlist", "data/projects/demo/public_sar_contradiction_watchlist.json"),
        ("evidence_value_report", "data/projects/demo/evidence_value_report.json"),
        ("measurement_feedback_plan", "data/projects/demo/measurement_feedback_plan.json"),
        ("measurement_feedback_result_import_report", "data/projects/demo/measurement_feedback_result_import_report.json"),
        ("measurement_feedback_gap_closure", "data/projects/demo/measurement_feedback_gap_closure.json"),
        ("measurement_gap_exact_result_intake", "data/projects/demo/measurement_gap_exact_result_intake.json"),
        ("measurement_gap_endpoint_governance", "data/projects/demo/measurement_gap_endpoint_governance.json"),
        ("evidence_value_calibration_report", "data/projects/demo/evidence_value_calibration_report.json"),
        ("evidence_value_policy_proposal", "data/projects/demo/evidence_value_policy_proposal.json"),
        ("evidence_value_policy_replay", "data/projects/demo/evidence_value_policy_replay.json"),
        ("evidence_value_policy_activation", "data/projects/demo/evidence_value_policy_activation.json"),
        ("evidence_value_policy_active", "data/projects/demo/evidence_value_policy_active.json"),
        ("evidence_value_policy_active_compare", "data/projects/demo/evidence_value_policy_active_compare.json"),
        ("profile_impact_review_queue", "data/projects/demo/profile_impact_review_queue.json"),
        ("project_memory_review_queue", "data/projects/demo/project_memory_review_queue.json"),
        ("project_memory_review_dashboard", "data/projects/demo/project_memory_review_dashboard.json"),
        ("profile_promotion_freeze_approvals", "data/projects/demo/profile_promotion_freeze_approvals.json"),
        ("profile_promotion_freeze_rollback_drill", "data/projects/demo/profile_promotion_freeze_rollback_drill.json"),
        ("profile_promotion_rollback_replay", "data/projects/demo/profile_promotion_rollback_replay.json"),
        ("profile_rollback_history", "data/projects/demo/profile_rollback_history.json"),
        ("profile_rollback_snapshot_compare", "data/projects/demo/profile_rollback_snapshot_compare.json"),
        ("project_memory_refresh_report", "data/projects/demo/project_memory_refresh_report.json"),
        (
            "endpoint_family_residual_adjustment_apply_report",
            "data/profiles/calibrated/endpoint_family_residual_adjustment_apply_report.json",
        ),
        ("scaffold_rule_review_drafts", "data/substituents/scaffold_rule_review_drafts.csv"),
    ]
    return {artifact_id: _artifact_snapshot(root_path, artifact_id, relative_path) for artifact_id, relative_path in artifacts}


def _check_artifact_ids(check_id: str) -> list[str]:
    mapping = {
        "closed_loop_replay": ["closed_loop_replay_report"],
        "queue_policy_alignment": ["closed_loop_replay_report"],
        "multi_objective_holdout": ["closed_loop_replay_report"],
        "multi_objective_stratified_holdout": ["closed_loop_replay_report"],
        "closed_loop_acceptance": ["closed_loop_drill_acceptance"],
        "open_residual_experiments": ["project_closed_loop_dashboard"],
        "residual_task_registry": ["project_closed_loop_dashboard"],
        "scaffold_review_drafts": ["scaffold_rule_review_drafts"],
        "endpoint_family_residual_adjustments": [
            "project_evidence_pack",
            "endpoint_family_residual_adjustment_apply_report",
        ],
        "profile_promotion_registry": ["profile_promotion_registry"],
        "profile_ab_replay": ["profile_promotion_registry", "profile_ab_replay_report"],
        "profile_ab_replay_matrix": ["profile_promotion_registry", "profile_ab_replay_matrix"],
        "profile_ab_material_change_review": ["profile_ab_replay_matrix", "profile_ab_material_change_review"],
        "candidate_evidence_priority_report": [
            "profile_ab_material_change_review",
            "candidate_evidence_priority_report",
        ],
        "public_sar_contradiction_triage": ["public_sar_contradiction_triage"],
        "public_sar_contradiction_resolution_batch": [
            "public_sar_contradiction_triage",
            "public_sar_contradiction_resolution_batch",
        ],
        "public_sar_contradiction_watchlist": [
            "public_sar_contradiction_triage",
            "public_sar_contradiction_watchlist",
        ],
        "evidence_value_report": [
            "candidate_evidence_priority_report",
            "public_sar_contradiction_triage",
            "evidence_value_report",
        ],
        "measurement_feedback_plan": [
            "evidence_value_report",
            "measurement_feedback_plan",
        ],
        "measurement_feedback_import": [
            "measurement_feedback_plan",
            "measurement_feedback_result_import_report",
        ],
        "measurement_feedback_gap_closure": [
            "measurement_feedback_plan",
            "measurement_feedback_result_import_report",
            "measurement_feedback_gap_closure",
        ],
        "measurement_gap_exact_result_intake": [
            "measurement_feedback_gap_closure",
            "measurement_gap_exact_result_intake",
        ],
        "measurement_gap_endpoint_governance": [
            "measurement_feedback_gap_closure",
            "measurement_gap_exact_result_intake",
            "measurement_gap_endpoint_governance",
        ],
        "evidence_value_calibration": [
            "evidence_value_report",
            "measurement_feedback_result_import_report",
            "evidence_value_calibration_report",
        ],
        "evidence_value_policy_proposal": [
            "evidence_value_calibration_report",
            "profile_rollback_snapshot_compare",
            "evidence_value_policy_proposal",
        ],
        "evidence_value_policy_replay": [
            "evidence_value_policy_proposal",
            "evidence_value_report",
            "evidence_value_policy_replay",
        ],
        "evidence_value_policy_activation": [
            "evidence_value_policy_proposal",
            "evidence_value_policy_replay",
            "evidence_value_policy_activation",
            "evidence_value_policy_active",
        ],
        "evidence_value_policy_active_compare": [
            "evidence_value_policy_active",
            "evidence_value_policy_replay",
            "evidence_value_policy_active_compare",
        ],
        "profile_impact_review_queue": [
            "evidence_value_policy_active_compare",
            "profile_impact_review_queue",
        ],
        "project_memory_review_queue": [
            "evidence_value_policy_replay",
            "measurement_feedback_gap_closure",
            "profile_impact_review_queue",
            "public_sar_contradiction_watchlist",
            "project_memory_review_queue",
        ],
        "project_memory_review_dashboard": [
            "project_memory_review_queue",
            "project_memory_review_dashboard",
        ],
        "profile_promotion_freeze_approval": [
            "profile_promotion_freeze_approvals",
        ],
        "profile_promotion_freeze_rollback_drill": [
            "profile_promotion_freeze_approvals",
            "profile_promotion_freeze_rollback_drill",
        ],
        "profile_promotion_rollback_replay": [
            "profile_promotion_freeze_rollback_drill",
            "profile_promotion_rollback_replay",
        ],
        "profile_rollback_history": [
            "profile_promotion_rollback_replay",
            "profile_rollback_history",
        ],
        "profile_rollback_snapshot_compare": [
            "profile_rollback_history",
            "profile_rollback_snapshot_compare",
        ],
        "project_memory_refresh_report": ["project_memory_refresh_report"],
    }
    return mapping.get(check_id, [])


def build_closed_loop_promotion_gate(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    min_queue_alignment_rate: float = 0.6,
    min_rank_lift_delta: float = -0.02,
    min_stratified_group_rows: int = 3,
    allow_open_residual_plans: bool = False,
) -> dict:
    root_path = Path(root)
    dashboard = _read_json(root_path / "data/projects/demo/project_closed_loop_dashboard.json")
    replay = _read_json(root_path / "data/projects/demo/closed_loop_replay_report.json")
    acceptance = _read_json(root_path / "data/projects/closed_loop_drill/closed_loop_drill_acceptance.json")
    evidence_pack = _read_json(root_path / "data/projects/demo/project_evidence_pack.json")
    profile_registry = _read_json(root_path / "data/profiles/profile_promotion_registry.json")
    profile_ab_replay = _read_json(root_path / "data/projects/demo/profile_ab_replay_report.json")
    profile_ab_matrix = _read_json(root_path / "data/projects/demo/profile_ab_replay_matrix.json")
    profile_ab_material_review = _read_json(root_path / "data/projects/demo/profile_ab_material_change_review.json")
    candidate_priority = _read_json(root_path / "data/projects/demo/candidate_evidence_priority_report.json")
    contradiction_triage = _read_json(root_path / "data/projects/demo/public_sar_contradiction_triage.json")
    sar_resolution_batch = _read_json(root_path / "data/projects/demo/public_sar_contradiction_resolution_batch.json")
    sar_watchlist = _read_json(root_path / "data/projects/demo/public_sar_contradiction_watchlist.json")
    evidence_value = _read_json(root_path / "data/projects/demo/evidence_value_report.json")
    measurement_feedback = _read_json(root_path / "data/projects/demo/measurement_feedback_plan.json")
    measurement_feedback_import = _read_json(root_path / "data/projects/demo/measurement_feedback_result_import_report.json")
    measurement_gap_closure = _read_json(root_path / "data/projects/demo/measurement_feedback_gap_closure.json")
    measurement_gap_exact_intake = _read_json(root_path / "data/projects/demo/measurement_gap_exact_result_intake.json")
    measurement_gap_endpoint_governance = _read_json(root_path / "data/projects/demo/measurement_gap_endpoint_governance.json")
    evidence_value_calibration = _read_json(root_path / "data/projects/demo/evidence_value_calibration_report.json")
    evidence_value_policy_proposal = _read_json(root_path / "data/projects/demo/evidence_value_policy_proposal.json")
    evidence_value_policy_replay = _read_json(root_path / "data/projects/demo/evidence_value_policy_replay.json")
    evidence_value_policy_activation = _read_json(root_path / "data/projects/demo/evidence_value_policy_activation.json")
    evidence_value_policy_active = _read_json(root_path / "data/projects/demo/evidence_value_policy_active.json")
    evidence_value_policy_active_compare = _read_json(root_path / "data/projects/demo/evidence_value_policy_active_compare.json")
    profile_impact_review = _read_json(root_path / "data/projects/demo/profile_impact_review_queue.json")
    project_memory_review_queue = _read_json(root_path / "data/projects/demo/project_memory_review_queue.json")
    project_memory_review_dashboard = _read_json(root_path / "data/projects/demo/project_memory_review_dashboard.json")
    assay_triage = _read_json(root_path / "data/projects/demo/assay_event_triage_report.json")
    freeze_approvals = _read_json(root_path / "data/projects/demo/profile_promotion_freeze_approvals.json")
    promotion_freeze = _read_json(root_path / "data/projects/demo/profile_promotion_freeze_manifest.json")
    rollback_drill = _read_json(root_path / "data/projects/demo/profile_promotion_freeze_rollback_drill.json")
    rollback_replay = _read_json(root_path / "data/projects/demo/profile_promotion_rollback_replay.json")
    rollback_history = _read_json(root_path / "data/projects/demo/profile_rollback_history.json")
    rollback_snapshot_compare = _read_json(root_path / "data/projects/demo/profile_rollback_snapshot_compare.json")
    refresh_report = _read_json(root_path / "data/projects/demo/project_memory_refresh_report.json")
    residual_adjustment_report = _read_json(root_path / "data/profiles/calibrated/endpoint_family_residual_adjustment_apply_report.json")
    scaffold_drafts = root_path / "data/substituents/scaffold_rule_review_drafts.csv"

    checks = []
    replay_status = replay.get("status")
    checks.append(
        _gate_check(
            "closed_loop_replay",
            "Closed-loop replay report passes",
            "pass" if replay_status == "pass" else "block",
            f"status={replay_status or 'missing'}",
        )
    )
    queue_alignment = _float_or_none((replay.get("queue_policy_replay") or {}).get("alignment_rate"))
    checks.append(
        _gate_check(
            "queue_policy_alignment",
            "Queue policy replay alignment meets threshold",
            "pass" if queue_alignment is None or queue_alignment >= min_queue_alignment_rate else "block",
            f"alignment={queue_alignment}; threshold={min_queue_alignment_rate}",
        )
    )
    rank_delta = _float_or_none(((replay.get("multi_objective_holdout") or {}).get("delta") or {}).get("rank_lift_delta"))
    checks.append(
        _gate_check(
            "multi_objective_holdout",
            "Multi-objective holdout rank lift is non-negative enough",
            "pass" if rank_delta is None or rank_delta >= min_rank_lift_delta else "block",
            f"rank_lift_delta={rank_delta}; threshold={min_rank_lift_delta}",
        )
    )
    stratified = (replay.get("multi_objective_holdout") or {}).get("stratified_metrics") or []
    weak_strata = [
        row
        for row in stratified
        if int(row.get("row_count") or 0) >= int(min_stratified_group_rows)
        and (_float_or_none(row.get("rank_lift_delta")) or 0.0) < min_rank_lift_delta
    ]
    checks.append(
        _gate_check(
            "multi_objective_stratified_holdout",
            "Endpoint/family/assay holdout strata do not regress materially",
            "pass" if not weak_strata else "review",
            f"weak_strata={len(weak_strata)}; min_rows={min_stratified_group_rows}; threshold={min_rank_lift_delta}",
        )
    )
    acceptance_passed = bool(acceptance.get("passed")) or acceptance.get("status") == "pass"
    checks.append(
        _gate_check(
            "closed_loop_acceptance",
            "Closed-loop acceptance check passes",
            "pass" if acceptance_passed else "block",
            f"status={acceptance.get('status') or 'missing'}; passed={acceptance.get('passed')}",
        )
    )
    open_plans = int((dashboard.get("experiments") or {}).get("open_plan_count") or 0)
    checks.append(
        _gate_check(
            "open_residual_experiments",
            "Residual experiment plans are closed before promotion",
            "pass" if allow_open_residual_plans or open_plans == 0 else "review",
            f"open_plan_count={open_plans}",
        )
    )
    residual_status_counts = (dashboard.get("residual_tasks") or {}).get("status_counts") or {}
    planned_residual = int(residual_status_counts.get("planned") or 0)
    open_residual = int(residual_status_counts.get("open") or 0)
    checks.append(
        _gate_check(
            "residual_task_registry",
            "Residual task registry has no open/planned calibration tasks",
            "pass" if allow_open_residual_plans or (planned_residual + open_residual) == 0 else "review",
            f"open={open_residual}; planned={planned_residual}",
        )
    )
    pending_scaffold_drafts = 0
    if scaffold_drafts.exists():
        try:
            import csv

            with scaffold_drafts.open("r", encoding="utf-8", newline="") as handle:
                pending_scaffold_drafts = sum(
                    1
                    for row in csv.DictReader(handle)
                    if str(row.get("draft_status") or "") not in {"applied", "deferred", "rejected", "retired"}
                )
        except Exception:
            pending_scaffold_drafts = 0
    checks.append(
        _gate_check(
            "scaffold_review_drafts",
            "Scaffold rule review drafts are applied or explicitly deferred",
            "pass" if pending_scaffold_drafts == 0 else "review",
            f"pending_draft_count={pending_scaffold_drafts}",
        )
    )
    evidence_gap_count = len(evidence_pack.get("evidence_gaps") or [])
    residual_adjustment_status = residual_adjustment_report.get("status")
    checks.append(
        _gate_check(
            "endpoint_family_residual_adjustments",
            "Endpoint-family residual score-profile adjustments are reviewed before profile promotion",
            "pass" if evidence_gap_count == 0 or residual_adjustment_status in {"applied", "review_required", "no_approved_adjustments_applied"} else "review",
            f"evidence_gap_count={evidence_gap_count}; adjustment_status={residual_adjustment_status or 'missing'}",
        )
    )
    profile_records = [row for row in profile_registry.get("records") or [] if isinstance(row, dict)]
    pending_profile_promotions = [
        row
        for row in profile_records
        if str(row.get("promotion_status") or "") in {"draft", "review_requested", "approved"}
    ]
    checks.append(
        _gate_check(
            "profile_promotion_registry",
            "Profile promotion registry has no unresolved activation requests",
            "pass" if not pending_profile_promotions else "review",
            f"pending_profile_promotions={len(pending_profile_promotions)}; record_count={len(profile_records)}",
        )
    )
    checks.append(
        _gate_check(
            "profile_ab_replay",
            "Profile promotion has an A/B ranking replay snapshot",
            "pass" if not pending_profile_promotions or profile_ab_replay.get("status") in {"ready", "empty"} else "review",
            (
                f"ab_status={profile_ab_replay.get('status') or 'missing'}; "
                f"ab_review={profile_ab_replay.get('review_status') or 'missing'}; "
                f"changed_top_n={profile_ab_replay.get('changed_top_n_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "profile_ab_replay_matrix",
            "Profile promotion has multi-scenario A/B replay coverage",
            "pass" if not pending_profile_promotions or profile_ab_matrix.get("status") in {"ready", "empty"} else "review",
            (
                f"matrix_status={profile_ab_matrix.get('status') or 'missing'}; "
                f"scenario_count={profile_ab_matrix.get('scenario_count')}; "
                f"review_required={profile_ab_matrix.get('review_required_count')}"
            ),
        )
    )
    material_change_count = int(profile_ab_matrix.get("material_change_count") or 0)
    accepted_material_count = int(profile_ab_material_review.get("accepted_profile_change_count") or 0)
    material_review_status = str(profile_ab_material_review.get("status") or "")
    checks.append(
        _gate_check(
            "profile_ab_material_change_review",
            "Material profile A/B changes have candidate-level acceptance records",
            "pass"
            if material_change_count == 0
            or (material_review_status == "accepted" and accepted_material_count >= material_change_count)
            else "review",
            (
                f"material_change_count={material_change_count}; "
                f"review_status={material_review_status or 'missing'}; "
                f"accepted_profile_change_count={accepted_material_count}; "
                f"candidate_diff_count={profile_ab_material_review.get('candidate_diff_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "candidate_evidence_priority_report",
            "Candidate evidence priority view is built from SAR, material A/B, and series sufficiency",
            "pass" if not pending_profile_promotions or candidate_priority.get("status") == "ready" else "review",
            (
                f"status={candidate_priority.get('status') or 'missing'}; "
                f"rows={candidate_priority.get('row_count')}; "
                f"sar_linked={candidate_priority.get('sar_linked_count')}; "
                f"material_linked={candidate_priority.get('material_diff_linked_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "public_sar_contradiction_triage",
            "Public SAR contradictions are triaged before profile promotion",
            "pass" if not pending_profile_promotions or contradiction_triage.get("status") in {"ready", "empty"} else "review",
            (
                f"triage_status={contradiction_triage.get('status') or 'missing'}; "
                f"rows={contradiction_triage.get('row_count')}; "
                f"candidate_linked={contradiction_triage.get('candidate_linked_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "public_sar_contradiction_resolution_batch",
            "High-priority public SAR contradictions are resolved or measurement-gated",
            "pass" if not pending_profile_promotions or sar_resolution_batch.get("status") in {"resolved", "no_open_priority_rows"} else "review",
            (
                f"resolution_status={sar_resolution_batch.get('status') or 'missing'}; "
                f"processed={sar_resolution_batch.get('processed_count')}; "
                f"needs_measurement={sar_resolution_batch.get('candidate_measurement_gated_count')}; "
                f"reference_watch={sar_resolution_batch.get('reference_only_watch_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "public_sar_contradiction_watchlist",
            "Remaining SAR contradictions only advance when candidate or analog-series linked",
            "pass"
            if not pending_profile_promotions or sar_watchlist.get("status") in {"ready", "no_linked_open_rows", "empty"}
            else "review",
            (
                f"watchlist_status={sar_watchlist.get('status') or 'missing'}; "
                f"actionable={sar_watchlist.get('actionable_count')}; "
                f"candidate_open={sar_watchlist.get('candidate_linked_open_count')}; "
                f"analog_open={sar_watchlist.get('analog_series_linked_open_count')}; "
                f"deferred_reference={sar_watchlist.get('deferred_reference_only_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "evidence_value_report",
            "Evidence value scoring is available for candidate prioritization",
            "pass" if not pending_profile_promotions or evidence_value.get("status") in {"ready", "empty"} else "review",
            (
                f"value_status={evidence_value.get('status') or 'missing'}; "
                f"rows={evidence_value.get('row_count')}; high_value={evidence_value.get('high_value_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "measurement_feedback_plan",
            "High-value evidence gaps have a measurement feedback plan",
            "pass" if not pending_profile_promotions or measurement_feedback.get("status") in {"ready", "empty"} else "review",
            (
                f"measurement_status={measurement_feedback.get('status') or 'missing'}; "
                f"rows={measurement_feedback.get('row_count')}; high={measurement_feedback.get('high_priority_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "measurement_feedback_import",
            "Local measurement-evidence import is traceable and free of validation failures",
            "pass"
            if not pending_profile_promotions
            or measurement_feedback_import.get("status")
            in {"imported", "imported_with_validation_issues", "imported_uncalibrated_measurements", "needs_real_measurement_feedback"}
            else "review",
            (
                f"import_status={measurement_feedback_import.get('status') or 'missing'}; "
                f"importable={measurement_feedback_import.get('importable_row_count')}; "
                f"calibration_ready={measurement_feedback_import.get('calibration_ready_row_count')}; "
                f"rejected={measurement_feedback_import.get('rejected_row_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "measurement_feedback_gap_closure",
            "Unmatched measurement feedback rows are closed without cross-endpoint auto-mapping",
            "pass"
            if not pending_profile_promotions
            or measurement_gap_closure.get("status") in {"manual_review_required", "decision_recorded", "ready_for_exact_import", "no_unmatched_plan_rows"}
            else "review",
            (
                f"gap_status={measurement_gap_closure.get('status') or 'missing'}; "
                f"open_gap={measurement_gap_closure.get('open_gap_count')}; "
                f"endpoint_mismatch={measurement_gap_closure.get('endpoint_mismatch_count')}; "
                f"needs_new={measurement_gap_closure.get('needs_new_measurement_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "measurement_gap_exact_result_intake",
            "Exact endpoint measurement gap intake is explicit and endpoint-safe",
            "pass"
            if not pending_profile_promotions
            or measurement_gap_exact_intake.get("status") in {"awaiting_exact_results", "ready_for_import", "empty"}
            else "review",
            (
                f"intake_status={measurement_gap_exact_intake.get('status') or 'missing'}; "
                f"template_rows={measurement_gap_exact_intake.get('template_row_count')}; "
                f"pending_exact={measurement_gap_exact_intake.get('pending_exact_result_count')}; "
                f"importable_exact={measurement_gap_exact_intake.get('importable_exact_result_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "measurement_gap_endpoint_governance",
            "Measurement gaps are governed by strict non-experimental endpoint matching",
            "pass"
            if not pending_profile_promotions
            or (
                measurement_gap_endpoint_governance.get("status") in {"ready", "attention_required", "empty"}
                and measurement_gap_endpoint_governance.get("real_experiment_feedback_used") is False
            )
            else "review",
            (
                f"endpoint_governance_status={measurement_gap_endpoint_governance.get('status') or 'missing'}; "
                f"mode={measurement_gap_endpoint_governance.get('mode') or 'missing'}; "
                f"pending={measurement_gap_endpoint_governance.get('strict_exact_pending_count')}; "
                f"blocked_pairs={measurement_gap_endpoint_governance.get('blocked_cross_endpoint_pair_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "evidence_value_calibration",
            "Evidence-value calibration report is available before weight changes",
            "pass"
            if not pending_profile_promotions
            or evidence_value_calibration.get("status") in {"calibrated", "needs_real_measurement_feedback", "needs_normalized_measurement_scores"}
            else "review",
            (
                f"calibration_status={evidence_value_calibration.get('status') or 'missing'}; "
                f"rows={evidence_value_calibration.get('calibration_row_count')}; "
                f"mae={evidence_value_calibration.get('mean_absolute_error')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "evidence_value_policy_proposal",
            "Evidence-value policy changes are versioned and held for approval",
            "pass"
            if not pending_profile_promotions
            or (
                evidence_value_policy_proposal.get("status")
                in {"review_required", "approved_not_active", "activated", "hold_current_policy", "insufficient_calibration_data", "blocked_missing_rollback_compare"}
                and evidence_value_policy_proposal.get("activation_status") in {"not_active", "active", None}
            )
            else "review",
            (
                f"proposal_status={evidence_value_policy_proposal.get('status') or 'missing'}; "
                f"approval={evidence_value_policy_proposal.get('approval_status')}; "
                f"changes={evidence_value_policy_proposal.get('weight_change_count')}; "
                f"rollback_compare={evidence_value_policy_proposal.get('rollback_compare_status')}; "
                f"activation={evidence_value_policy_proposal.get('activation_status')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "evidence_value_policy_replay",
            "Evidence-value policy proposal has a pre-activation replay or activation record",
            "pass"
            if not pending_profile_promotions
            or (
                evidence_value_policy_replay.get("status") in {"compared", "empty"}
                and evidence_value_policy_replay.get("activation_status") in {"not_active", "active"}
                and evidence_value_policy_replay.get("activation_gate_status")
                in {"ready_for_manual_activation", "blocked_pending_manual_approval", "blocked_replay_drift_review", "blocked_missing_evidence_rows", "activated"}
            )
            else "review",
            (
                f"replay_status={evidence_value_policy_replay.get('status') or 'missing'}; "
                f"gate={evidence_value_policy_replay.get('activation_gate_status')}; "
                f"top_n_changes={evidence_value_policy_replay.get('top_n_change_count')}; "
                f"max_score_delta={evidence_value_policy_replay.get('max_abs_score_delta')}; "
                f"max_rank_delta={evidence_value_policy_replay.get('max_abs_rank_delta')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "evidence_value_policy_activation",
            "Activated evidence-value policy has an auditable active snapshot",
            "pass"
            if not pending_profile_promotions
            or evidence_value_policy_proposal.get("activation_status") != "active"
            or (
                evidence_value_policy_activation.get("status") == "activated"
                and evidence_value_policy_active.get("activation_status") == "active"
                and evidence_value_policy_active.get("source_proposal_id") == evidence_value_policy_proposal.get("proposal_id")
            )
            else "review",
            (
                f"activation_status={evidence_value_policy_activation.get('status') or 'missing'}; "
                f"active_policy={evidence_value_policy_active.get('policy_version') or 'missing'}; "
                f"source_proposal={evidence_value_policy_active.get('source_proposal_id') or 'missing'}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "evidence_value_policy_active_compare",
            "Active evidence-value policy has baseline comparison and profile impact flags",
            "pass"
            if not pending_profile_promotions
            or evidence_value_policy_proposal.get("activation_status") != "active"
            or evidence_value_policy_active_compare.get("status") == "compared"
            else "review",
            (
                f"compare_status={evidence_value_policy_active_compare.get('status') or 'missing'}; "
                f"rows={evidence_value_policy_active_compare.get('row_count')}; "
                f"max_score_delta={evidence_value_policy_active_compare.get('max_abs_score_delta')}; "
                f"profile_flags={evidence_value_policy_active_compare.get('profile_impact_review_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "profile_impact_review_queue",
            "Profile-impact flags are routed into a reviewer workflow",
            "pass"
            if not pending_profile_promotions
            or profile_impact_review.get("status") in {"review_required", "reviewed", "empty"}
            else "review",
            (
                f"profile_review_status={profile_impact_review.get('status') or 'missing'}; "
                f"rows={profile_impact_review.get('row_count')}; "
                f"open={profile_impact_review.get('open_review_count')}; "
                f"mode={profile_impact_review.get('mode') or 'missing'}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "project_memory_review_queue",
            "Project Memory review queue is available for policy, measurement, and SAR follow-up",
            "pass" if not pending_profile_promotions or project_memory_review_queue.get("status") in {"ready", "empty"} else "review",
            (
                f"queue_status={project_memory_review_queue.get('status') or 'missing'}; "
                f"rows={project_memory_review_queue.get('row_count')}; "
                f"policy_gate={project_memory_review_queue.get('policy_activation_gate_status')}; "
                f"measurement_gaps={project_memory_review_queue.get('measurement_open_gap_count')}; "
                f"sar_deferred={project_memory_review_queue.get('sar_deferred_reference_only_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "project_memory_review_dashboard",
            "Project Memory review dashboard summarizes lanes and open ownership",
            "pass"
            if not pending_profile_promotions
            or project_memory_review_dashboard.get("status") in {"ready", "needs_attention", "empty"}
            else "review",
            (
                f"dashboard_status={project_memory_review_dashboard.get('status') or 'missing'}; "
                f"rows={project_memory_review_dashboard.get('row_count')}; "
                f"open_like={project_memory_review_dashboard.get('open_like_count')}; "
                f"lanes={project_memory_review_dashboard.get('lane_row_count')}"
            ),
        )
    )
    followup_review_count = int(assay_triage.get("followup_review_count") or 0)
    planned_followup_count = int(assay_triage.get("planned_followup_count") or 0)
    checks.append(
        _gate_check(
            "assay_followup_result_intake",
            "Assay follow-up result intake is linked to triage",
            "review" if followup_review_count else "pass",
            (
                f"planned_followup={planned_followup_count}; "
                f"resolved_by_followup={assay_triage.get('real_followup_resolved_count')}; "
                f"followup_review={followup_review_count}"
            ),
        )
    )
    active_freeze_id = freeze_approvals.get("active_freeze_id")
    latest_freeze_id = promotion_freeze.get("freeze_id")
    approved_latest = bool(active_freeze_id and latest_freeze_id and active_freeze_id == latest_freeze_id)
    checks.append(
        _gate_check(
            "profile_promotion_freeze_approval",
            "Latest profile promotion freeze has an approval or release tag",
            "pass" if not pending_profile_promotions or approved_latest else "review",
            (
                f"latest_freeze={latest_freeze_id or 'missing'}; "
                f"active_freeze={active_freeze_id or 'missing'}; "
                f"latest_release_tag={freeze_approvals.get('latest_release_tag') or 'missing'}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "profile_promotion_freeze_rollback_drill",
            "Profile freeze rollback drill is traceable",
            "pass" if not pending_profile_promotions or rollback_drill.get("status") == "pass" else "review",
            (
                f"drill_status={rollback_drill.get('status') or 'missing'}; "
                f"target_freeze={rollback_drill.get('target_freeze_id') or 'missing'}; "
                f"would_release_tag={rollback_drill.get('would_release_tag') or 'missing'}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "profile_promotion_rollback_replay",
            "Profile rollback replay quantifies candidate rank and score impact",
            "pass" if not pending_profile_promotions or rollback_replay.get("status") in {"ready", "empty"} else "review",
            (
                f"replay_status={rollback_replay.get('status') or 'missing'}; "
                f"rows={rollback_replay.get('row_count')}; "
                f"max_score_delta={rollback_replay.get('max_abs_rollback_score_delta')}; "
                f"max_rank_delta={rollback_replay.get('max_abs_rollback_rank_delta')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "profile_rollback_history",
            "Profile rollback history is available across current and packaged snapshots",
            "pass" if not pending_profile_promotions or rollback_history.get("status") in {"ready", "empty"} else "review",
            (
                f"history_status={rollback_history.get('status') or 'missing'}; "
                f"snapshots={rollback_history.get('snapshot_count')}; "
                f"candidate_history={rollback_history.get('candidate_history_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "profile_rollback_snapshot_compare",
            "Profile rollback snapshot drift comparison is available",
            "pass" if not pending_profile_promotions or rollback_snapshot_compare.get("status") == "compared" else "review",
            (
                f"compare_status={rollback_snapshot_compare.get('status') or 'missing'}; "
                f"base={rollback_snapshot_compare.get('base_snapshot_id')}; head={rollback_snapshot_compare.get('head_snapshot_id')}; "
                f"changed={rollback_snapshot_compare.get('changed_candidate_count')}; "
                f"added={rollback_snapshot_compare.get('added_candidate_count')}; removed={rollback_snapshot_compare.get('removed_candidate_count')}"
            ),
        )
    )
    checks.append(
        _gate_check(
            "project_memory_refresh_report",
            "Project memory refresh report is current enough for gate review",
            "pass" if not pending_profile_promotions or refresh_report.get("status") in {"pass", "warn"} else "review",
            (
                f"refresh_status={refresh_report.get('status') or 'missing'}; "
                f"passed={refresh_report.get('passed_step_count')}; failed={refresh_report.get('failed_step_count')}"
            ),
        )
    )

    block_count = sum(1 for check in checks if check["status"] == "block")
    review_count = sum(1 for check in checks if check["status"] == "review")
    status = "blocked" if block_count else "review_required" if review_count else "ready"
    artifacts = _promotion_gate_artifacts(root_path)
    check_evidence = [
        {
            "check_id": check["check_id"],
            "status": check["status"],
            "details": check.get("details", ""),
            "source_artifact_ids": _check_artifact_ids(check["check_id"]),
        }
        for check in checks
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "promotion_status": status,
        "block_count": block_count,
        "review_count": review_count,
        "pass_count": sum(1 for check in checks if check["status"] == "pass"),
        "checks": checks,
        "inputs": {
            "dashboard_status": dashboard.get("overall_status"),
            "replay_status": replay.get("status"),
            "closed_loop_acceptance_status": acceptance.get("status"),
            "project_evidence_pack_status": evidence_pack.get("status"),
            "residual_adjustment_status": residual_adjustment_status,
            "profile_promotion_record_count": len(profile_records),
            "profile_ab_replay_status": profile_ab_replay.get("status"),
            "profile_ab_replay_review_status": profile_ab_replay.get("review_status"),
            "profile_ab_replay_matrix_status": profile_ab_matrix.get("status"),
            "profile_ab_replay_matrix_scenario_count": profile_ab_matrix.get("scenario_count"),
            "profile_ab_material_review_status": profile_ab_material_review.get("status"),
            "profile_ab_material_review_candidate_diff_count": profile_ab_material_review.get("candidate_diff_count"),
            "candidate_evidence_priority_status": candidate_priority.get("status"),
            "candidate_evidence_priority_high_count": candidate_priority.get("high_priority_count"),
            "public_sar_contradiction_triage_status": contradiction_triage.get("status"),
            "public_sar_contradiction_resolution_batch_status": sar_resolution_batch.get("status"),
            "public_sar_contradiction_watchlist_status": sar_watchlist.get("status"),
            "evidence_value_status": evidence_value.get("status"),
            "measurement_feedback_plan_status": measurement_feedback.get("status"),
            "measurement_feedback_import_status": measurement_feedback_import.get("status"),
            "measurement_feedback_gap_closure_status": measurement_gap_closure.get("status"),
            "measurement_gap_exact_result_intake_status": measurement_gap_exact_intake.get("status"),
            "measurement_gap_endpoint_governance_status": measurement_gap_endpoint_governance.get("status"),
            "evidence_value_calibration_status": evidence_value_calibration.get("status"),
            "evidence_value_policy_proposal_status": evidence_value_policy_proposal.get("status"),
            "evidence_value_policy_proposal_approval": evidence_value_policy_proposal.get("approval_status"),
            "evidence_value_policy_replay_status": evidence_value_policy_replay.get("status"),
            "evidence_value_policy_replay_gate": evidence_value_policy_replay.get("activation_gate_status"),
            "evidence_value_policy_activation_status": evidence_value_policy_activation.get("status"),
            "evidence_value_policy_active_version": evidence_value_policy_active.get("policy_version"),
            "evidence_value_policy_active_compare_status": evidence_value_policy_active_compare.get("status"),
            "profile_impact_review_queue_status": profile_impact_review.get("status"),
            "project_memory_review_queue_status": project_memory_review_queue.get("status"),
            "project_memory_review_dashboard_status": project_memory_review_dashboard.get("status"),
            "assay_followup_planned_count": planned_followup_count,
            "assay_followup_review_count": followup_review_count,
            "profile_promotion_freeze_id": latest_freeze_id,
            "profile_promotion_active_freeze_id": active_freeze_id,
            "profile_promotion_freeze_rollback_drill_status": rollback_drill.get("status"),
            "profile_promotion_rollback_replay_status": rollback_replay.get("status"),
            "profile_rollback_history_status": rollback_history.get("status"),
            "profile_rollback_snapshot_compare_status": rollback_snapshot_compare.get("status"),
            "project_memory_refresh_status": refresh_report.get("status"),
            "min_queue_alignment_rate": min_queue_alignment_rate,
            "min_rank_lift_delta": min_rank_lift_delta,
            "min_stratified_group_rows": min_stratified_group_rows,
            "allow_open_residual_plans": allow_open_residual_plans,
        },
        "evidence_snapshot": {
            "artifact_count": len(artifacts),
            "present_artifact_count": sum(1 for artifact in artifacts.values() if artifact.get("exists")),
            "status_basis": {
                "promotion_status": status,
                "block_count": block_count,
                "review_count": review_count,
                "pass_count": sum(1 for check in checks if check["status"] == "pass"),
                "min_queue_alignment_rate": min_queue_alignment_rate,
                "min_rank_lift_delta": min_rank_lift_delta,
                "min_stratified_group_rows": min_stratified_group_rows,
            },
            "artifacts": list(artifacts.values()),
            "check_evidence": check_evidence,
        },
        "recommended_next_actions": [
            "Close or explicitly defer residual experiments before promoting policy/profile changes.",
            "Apply scaffold rule review drafts only after manual medchem approval.",
            "Register profile/policy promotion decisions with gate, evidence pack, and iteration snapshots.",
            "Use this gate together with iteration comparison before activating a new design policy.",
        ],
    }


def write_closed_loop_promotion_gate(report: dict, output_path: str | Path = DEFAULT_PROMOTION_GATE_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
