from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_ROOT = Path(".")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _artifact_exists(root_path: Path, value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    path = Path(text)
    if not path.is_absolute():
        path = root_path / path
    return path.exists()


def build_release_smoke_checklist(root: str | Path = DEFAULT_ROOT, *, production_mode: bool = False) -> dict:
    root_path = Path(root)
    quality = _read_json(root_path / "data/substituents/data_quality_hardening_report.json") or _read_json(root_path / "data/substituents/data_quality_report.json")
    foundation = _read_json(root_path / "data/substituents/data_foundation_report.json")
    maintenance = _read_json(root_path / "data/substituents/daily_maintenance_report.json")
    alert = _read_json(root_path / "data/substituents/daily_maintenance_alert.json")
    gate = _read_json(root_path / "data/substituents/data_foundation_gate.json") or (foundation.get("ci_gate") or {})
    ring_status = _read_json(root_path / "data/substituents/ring_import_status.json") or ((maintenance.get("ring_import_status") or {}))
    manifest_diff = _read_json(root_path / "data/releases/manifest_diff_latest.json")
    closed_loop_acceptance = _read_json(root_path / "data/projects/closed_loop_drill/closed_loop_drill_acceptance.json")
    promotion_gate = _read_json(root_path / "data/projects/demo/closed_loop_promotion_gate.json")
    profile_ab_matrix = _read_json(root_path / "data/projects/demo/profile_ab_replay_matrix.json")
    public_sar_validation = _read_json(root_path / "data/projects/demo/public_sar_validation_report.json")
    assay_triage = _read_json(root_path / "data/projects/demo/assay_event_triage_report.json")
    rollback_drill = _read_json(root_path / "data/projects/demo/profile_promotion_freeze_rollback_drill.json")
    candidate_priority = _read_json(root_path / "data/projects/demo/candidate_evidence_priority_report.json")
    rollback_replay = _read_json(root_path / "data/projects/demo/profile_promotion_rollback_replay.json")
    contradiction_triage = _read_json(root_path / "data/projects/demo/public_sar_contradiction_triage.json")
    sar_resolution_batch = _read_json(root_path / "data/projects/demo/public_sar_contradiction_resolution_batch.json")
    sar_watchlist = _read_json(root_path / "data/projects/demo/public_sar_contradiction_watchlist.json")
    evidence_value = _read_json(root_path / "data/projects/demo/evidence_value_report.json")
    measurement_feedback = _read_json(root_path / "data/projects/demo/measurement_feedback_plan.json")
    measurement_feedback_import = _read_json(root_path / "data/projects/demo/measurement_feedback_result_import_report.json")
    measurement_gap_closure = _read_json(root_path / "data/projects/demo/measurement_feedback_gap_closure.json")
    measurement_gap_exact_intake = _read_json(root_path / "data/projects/demo/measurement_gap_exact_result_intake.json")
    measurement_gap_endpoint_governance = _read_json(root_path / "data/projects/demo/measurement_gap_endpoint_governance.json")
    site_class_policy_pack = _read_json(root_path / "data/projects/demo/site_class_policy_pack.json")
    evidence_value_calibration = _read_json(root_path / "data/projects/demo/evidence_value_calibration_report.json")
    evidence_value_policy_proposal = _read_json(root_path / "data/projects/demo/evidence_value_policy_proposal.json")
    evidence_value_policy_replay = _read_json(root_path / "data/projects/demo/evidence_value_policy_replay.json")
    evidence_value_policy_activation = _read_json(root_path / "data/projects/demo/evidence_value_policy_activation.json")
    evidence_value_policy_active = _read_json(root_path / "data/projects/demo/evidence_value_policy_active.json")
    evidence_value_policy_active_compare = _read_json(root_path / "data/projects/demo/evidence_value_policy_active_compare.json")
    profile_impact_review = _read_json(root_path / "data/projects/demo/profile_impact_review_queue.json")
    project_memory_review_queue = _read_json(root_path / "data/projects/demo/project_memory_review_queue.json")
    project_memory_review_dashboard = _read_json(root_path / "data/projects/demo/project_memory_review_dashboard.json")
    promotion_readiness_packet = _read_json(root_path / "data/projects/demo/promotion_readiness_packet.json")
    rollback_history = _read_json(root_path / "data/projects/demo/profile_rollback_history.json")
    rollback_snapshot_compare = _read_json(root_path / "data/projects/demo/profile_rollback_snapshot_compare.json")
    project_memory_refresh = _read_json(root_path / "data/projects/demo/project_memory_refresh_report.json")
    native_ui_quality = _read_json(root_path / "data/releases/native_ui_quality_report.json")
    local_db_health = _read_json(root_path / "data/releases/local_db_health_report.json")
    local_db_maintenance = _read_json(root_path / "data/releases/local_db_maintenance_report.json")
    local_db_maintenance_release_gate = _read_json(root_path / "data/releases/local_db_maintenance_release_gate.json")
    local_db_maintenance_trend = _read_json(root_path / "data/releases/local_db_maintenance_trend_history.json")
    native_ui_regression = _read_json(root_path / "data/releases/native_ui_regression_snapshot.json")
    native_portable_package = _read_json(root_path / "data/releases/native_portable_package_manifest.json")
    candidate_visual_compare = _read_json(root_path / "data/projects/demo/candidate_visual_compare.json")
    candidate_review_packet = _read_json(root_path / "data/projects/demo/candidate_review_packet.json")
    candidate_review_board = _read_json(root_path / "data/projects/demo/candidate_review_board.json")
    candidate_review_analytics = _read_json(root_path / "data/projects/demo/candidate_review_analytics.json")
    candidate_drilldown_packet = _read_json(root_path / "data/projects/demo/candidate_drilldown_packet.json")
    local_governance_diff = _read_json(root_path / "data/projects/demo/local_governance_diff_report.json")
    governance_baselines = _read_json(root_path / "data/projects/demo/governance_baselines/baseline_registry.json")
    candidate_baseline_compare = _read_json(root_path / "data/projects/demo/candidate_baseline_compare.json")
    candidate_decision_packet = _read_json(root_path / "data/projects/demo/candidate_decision_packet.json")
    candidate_evidence_drawer = _read_json(root_path / "data/projects/demo/candidate_evidence_drawer.json")
    candidate_explanation_panel = _read_json(root_path / "data/projects/demo/candidate_explanation_panel.json")
    candidate_explanation_compare = _read_json(root_path / "data/projects/demo/candidate_explanation_compare.json")
    candidate_explanation_drilldown = _read_json(root_path / "data/projects/demo/candidate_explanation_drilldown.json")
    candidate_explanation_matrix = _read_json(root_path / "data/projects/demo/candidate_explanation_matrix.json")
    staged_feed_sandbox_scoring = _read_json(root_path / "data/projects/demo/staged_feed_sandbox_scoring.json")
    sandbox_score_delta_review = _read_json(root_path / "data/projects/demo/sandbox_score_delta_review_packet.json")
    sandbox_score_delta_signoff = _read_json(root_path / "data/projects/demo/sandbox_score_delta_signoff_ledger.json")
    staging_sandbox_filter_views = _read_json(root_path / "data/projects/demo/staging_sandbox_filter_views.json")
    native_drilldown_actions = _read_json(root_path / "data/projects/demo/native_drilldown_actions.json")
    site_detection_regression = _read_json(root_path / "data/projects/demo/site_detection_regression_report.json")
    site_detection_confidence = _read_json(root_path / "data/projects/demo/site_detection_confidence.json")
    candidate_decision_qa = _read_json(root_path / "data/projects/demo/candidate_decision_qa.json")
    evidence_quality_scorecard = _read_json(root_path / "data/projects/demo/evidence_quality_scorecard.json")
    candidate_evidence_quality = _read_json(root_path / "data/projects/demo/candidate_evidence_quality.json")
    if not evidence_quality_scorecard:
        evidence_quality_scorecard = candidate_evidence_quality
    if not candidate_evidence_quality:
        candidate_evidence_quality = evidence_quality_scorecard
    candidate_baseline_manager = _read_json(root_path / "data/projects/demo/candidate_baseline_manager.json")
    reviewer_operations = _read_json(root_path / "data/projects/demo/reviewer_operations.json")
    baseline_lineage_compare = _read_json(root_path / "data/projects/demo/baseline_lineage_compare.json")
    candidate_baseline_lineage = _read_json(root_path / "data/projects/demo/candidate_baseline_lineage.json")
    if not baseline_lineage_compare:
        baseline_lineage_compare = candidate_baseline_lineage
    if not candidate_baseline_lineage:
        candidate_baseline_lineage = baseline_lineage_compare
    review_command_center = _read_json(root_path / "data/projects/demo/review_command_center.json")
    review_closure_workbench = _read_json(root_path / "data/projects/demo/review_closure_workbench.json")
    review_closure_filter_views = _read_json(root_path / "data/projects/demo/review_closure_filter_views.json")
    candidate_remediation_queue = _read_json(root_path / "data/projects/demo/candidate_remediation_queue.json")
    candidate_remediation_history = _read_json(root_path / "data/projects/demo/candidate_remediation_queue_history.json")
    review_remediation_queue = candidate_remediation_queue or _read_json(root_path / "data/projects/demo/review_remediation_queue.json")
    candidate_review_ops_console = _read_json(root_path / "data/projects/demo/candidate_review_ops_console.json")
    baseline_history_explorer = _read_json(root_path / "data/projects/demo/baseline_history_explorer.json")
    baseline_scenario_board = _read_json(root_path / "data/projects/demo/baseline_scenario_board.json")
    baseline_whatif_board = _read_json(root_path / "data/projects/demo/baseline_whatif_board.json")
    baseline_lineage_history = baseline_history_explorer or _read_json(root_path / "data/projects/demo/baseline_lineage_history.json")
    baseline_lineage_preview = _read_json(root_path / "data/projects/demo/baseline_lineage_preview.json")
    baseline_lineage_filter_views = _read_json(root_path / "data/projects/demo/baseline_lineage_filter_views.json")
    operator_trend_summary = _read_json(root_path / "data/releases/operator_trend_summary.json")
    operator_trend_charts = _read_json(root_path / "data/releases/operator_trend_charts.json")
    medchem_discussion_handoff = _read_json(root_path / "data/projects/demo/medchem_discussion_handoff.json")
    rgroup_feed_metadata = _read_json(root_path / "data/substituents/rgroup_feed_metadata_report.json")
    rgroup_review_coverage = _read_json(root_path / "data/substituents/rgroup_feed_review_coverage.json")
    rgroup_pair_contradictions = _read_json(root_path / "data/substituents/rgroup_normalized_pair_contradictions.json")
    rgroup_pair_decisions = _read_json(root_path / "data/substituents/rgroup_normalized_pair_contradiction_decisions.json")
    rgroup_pair_owner_packet = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_review_packet.json")
    rgroup_pair_owner_ledger = _read_json(root_path / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json")
    rgroup_feed_onboarding = _read_json(root_path / "data/substituents/rgroup_feed_onboarding_gate.json")
    rgroup_feed_staging = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging.json")
    rgroup_feed_staging_gate = _read_json(root_path / "data/substituents/rgroup_next_feed_drop_staging_gate.json")
    feed_absorption_audit = _read_json(root_path / "data/substituents/feed_absorption_audit.json")
    feed_absorption_diff = _read_json(root_path / "data/substituents/feed_absorption_diff_navigator.json")
    source_expansion_governance = _read_json(root_path / "data/substituents/source_expansion_governance.json")
    feed_promotion_simulator = _read_json(root_path / "data/substituents/feed_promotion_simulator.json")
    staging_quality_budget = _read_json(root_path / "data/substituents/rgroup_staging_quality_budget.json")
    rgroup_feed_digestion_ledger = _read_json(root_path / "data/substituents/rgroup_feed_digestion_ledger.json")
    rgroup_selective_approval_batch = _read_json(root_path / "data/substituents/rgroup_selective_approval_batch.json")
    rgroup_promotion_approval_ledger = _read_json(root_path / "data/substituents/rgroup_promotion_approval_ledger.json")
    rgroup_digestion_quality_metrics = _read_json(root_path / "data/substituents/rgroup_digestion_quality_metrics.json")
    rgroup_digestion_quality_closure_queue = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_queue.json")
    feed_promotion_rollback_audit = _read_json(root_path / "data/substituents/feed_promotion_rollback_audit.json")
    rgroup_approval_workbench = _read_json(root_path / "data/substituents/rgroup_approval_workbench.json")
    rgroup_ring_context_alignment = _read_json(root_path / "data/substituents/rgroup_ring_context_alignment.json")
    rgroup_digestion_quality_closure_ledger = _read_json(root_path / "data/substituents/rgroup_digestion_quality_closure_ledger.json")
    rgroup_approval_workbench_decisions = _read_json(root_path / "data/substituents/rgroup_approval_workbench_decisions.json")
    rgroup_guarded_promotion_rehearsal = _read_json(root_path / "data/substituents/rgroup_guarded_promotion_rehearsal.json")
    ring_rgroup_axis_governance = _read_json(root_path / "data/substituents/ring_rgroup_axis_governance.json")
    rgroup_next_expansion_batch_plan = _read_json(root_path / "data/substituents/rgroup_next_expansion_batch_plan.json")
    rgroup_approval_trend_views = _read_json(root_path / "data/substituents/rgroup_approval_trend_views.json")
    governed_ingestion_batches = _read_json(root_path / "data/substituents/governed_ingestion_batches.json")
    substituent_version_diff_browser = _read_json(root_path / "data/substituents/substituent_version_diff_browser.json")
    ring_overlay_activation = _read_json(root_path / "data/profiles/calibrated/ring_outcome_overlay_activation.json")
    ring_outcome_readiness = _read_json(root_path / "data/projects/demo/ring_outcome_production_readiness.json")
    ring_outcome_result_package = _read_json(root_path / "data/projects/demo/ring_outcome_result_package.json")
    ring_outcome_holdout = _read_json(root_path / "data/projects/demo/ring_outcome_holdout_report.json")
    promotion_status = promotion_gate.get("promotion_status")
    cache_hits = int(profile_ab_matrix.get("cache_hit_count") or 0)
    scenario_count = int(profile_ab_matrix.get("scenario_count") or 0)
    open_issues = sum(int(value or 0) for value in (assay_triage.get("open_issue_counts") or {}).values())
    allowlist_issue_count = int(rgroup_feed_metadata.get("allowlist_issue_count") or 0)
    freshness_issue_count = int(rgroup_feed_metadata.get("freshness_issue_count") or 0)
    low_review_coverage = int(rgroup_review_coverage.get("low_coverage_count") or 0)
    no_review_coverage = int(rgroup_review_coverage.get("no_review_count") or 0)
    pair_blocking_count = int(rgroup_pair_contradictions.get("blocking_count") or 0)
    pair_open_high_count = int(rgroup_pair_decisions.get("open_high_priority_count", rgroup_pair_contradictions.get("open_high_priority_count") or 0) or 0)
    pair_blocking_unresolved_count = int(rgroup_pair_decisions.get("blocking_unresolved_count") or 0)
    pair_deferred_source_review_count = int(rgroup_pair_owner_packet.get("deferred_conflict_count") or 0)
    pair_pending_owner_review_count = int(rgroup_pair_owner_packet.get("pending_owner_review_count", pair_deferred_source_review_count) or 0)
    owner_ledger_pending_count = int(rgroup_pair_owner_ledger.get("pending_owner_review_count") or 0)
    deferred_decision_count = int((rgroup_pair_decisions.get("decision_counts") or {}).get("defer_source_review") or 0)
    owner_ledger_complete = (
        rgroup_pair_owner_ledger.get("status")
        in {"all_kept_deferred", "owner_decisions_applied", "owner_decisions_recorded", "closed_no_deferred_conflicts"}
        and owner_ledger_pending_count == 0
    )
    owner_ledger_needed = bool(deferred_decision_count or pair_deferred_source_review_count)
    feed_staging_ready = rgroup_feed_staging.get("status") == "staged" and int(rgroup_feed_staging.get("template_file_count") or 0) > 0
    feed_staging_gate_ok = rgroup_feed_staging_gate.get("status") in {"awaiting_filled_staging_rows", "ready_for_promotion"}
    ring_result_package_ok = ring_outcome_result_package.get("status") in {"awaiting_result_payload", "ready_for_strict_import"}
    ring_holdout_ok = ring_outcome_holdout.get("status") in {
        "awaiting_production_results",
        "blocked_no_active_nonzero_context",
        "holdout_ready",
    }
    checks = [
        {
            "check_id": "strict_quality",
            "label": "Strict data quality has no errors or must-fix warnings",
            "status": "pass" if quality.get("ok") and not quality.get("error_count") and not quality.get("must_fix_warning_count", 0) else "fail",
            "details": f"errors={quality.get('error_count')}, must_fix={quality.get('must_fix_warning_count', quality.get('warning_count'))}",
        },
        {
            "check_id": "daily_maintenance_alert",
            "label": "Daily maintenance alert is clear",
            "status": "pass" if alert.get("alert_level") in {None, "ok"} else "fail" if alert.get("alert_level") == "error" else "warn",
            "details": alert.get("alert_level") or "missing",
        },
        {
            "check_id": "data_foundation_gate",
            "label": "Data foundation gate passes",
            "status": "pass" if gate.get("passed", True) and gate.get("status") != "error" else "fail",
            "details": gate.get("status", "missing"),
        },
        {
            "check_id": "ring_import_currency",
            "label": "Ring import checkpoint is healthy",
            "status": "pass" if (ring_status.get("checkpoint_integrity") or {}).get("status") in {None, "ok"} else "warn",
            "details": f"offset={ring_status.get('next_offset')}, progress={ring_status.get('progress_percent')}",
        },
        {
            "check_id": "rgroup_feed_freshness",
            "label": "R-group feed metadata is allowlisted and fresh",
            "status": "fail"
            if allowlist_issue_count
            else "warn"
            if not rgroup_feed_metadata or freshness_issue_count
            else "pass",
            "details": (
                f"feeds={rgroup_feed_metadata.get('feed_count')}; rows={rgroup_feed_metadata.get('row_count')}; "
                f"allowlist={allowlist_issue_count}; freshness={freshness_issue_count}; "
                f"sample_review={rgroup_feed_metadata.get('sample_review_count')}"
            ),
        },
        {
            "check_id": "rgroup_feed_review_coverage",
            "label": "R-group feed review coverage has no empty strata",
            "status": "fail"
            if production_mode and (not rgroup_review_coverage or no_review_coverage or low_review_coverage)
            else "warn"
            if not rgroup_review_coverage or no_review_coverage or low_review_coverage
            else "pass",
            "details": (
                f"cells={rgroup_review_coverage.get('coverage_cell_count')}; no_review={no_review_coverage}; "
                f"low={low_review_coverage}; covered={rgroup_review_coverage.get('covered_count')}"
            ),
        },
        {
            "check_id": "rgroup_normalized_pair_contradictions",
            "label": "R-group normalized pair contradictions are queued before scoring",
            "status": "fail"
            if pair_blocking_count or (production_mode and (pair_open_high_count or pair_blocking_unresolved_count))
            else "pass"
            if rgroup_pair_contradictions
            else "warn",
            "details": (
                f"status={rgroup_pair_contradictions.get('status') or 'missing'}; "
                f"rows={rgroup_pair_contradictions.get('row_count')}; "
                f"high={rgroup_pair_contradictions.get('high_priority_count')}; "
                f"blocking={rgroup_pair_contradictions.get('blocking_count')}; "
                f"decisions={rgroup_pair_decisions.get('status') or 'missing'}; "
                f"open_high={pair_open_high_count}"
            ),
        },
        {
            "check_id": "rgroup_pair_conflict_owner_review_packet",
            "label": "Deferred pair conflicts have source-owner review packets",
            "status": "pass"
            if rgroup_pair_owner_packet.get("status") in {"owner_review_required", "owner_review_recorded", "closed"}
            else "fail"
            if production_mode and deferred_decision_count
            else "warn",
            "details": (
                f"status={rgroup_pair_owner_packet.get('status') or 'missing'}; "
                f"deferred={rgroup_pair_owner_packet.get('deferred_conflict_count')}; "
                f"pending_owner={pair_pending_owner_review_count}; "
                f"owners={rgroup_pair_owner_packet.get('owner_count')}"
            ),
        },
        {
            "check_id": "rgroup_pair_conflict_owner_decision_ledger",
            "label": "Deferred pair conflicts have recorded owner decisions or conservative holds",
            "status": "pass"
            if owner_ledger_complete
            else "fail"
            if production_mode and owner_ledger_needed
            else "warn",
            "details": (
                f"status={rgroup_pair_owner_ledger.get('status') or 'missing'}; "
                f"rows={rgroup_pair_owner_ledger.get('row_count')}; "
                f"pending_owner={owner_ledger_pending_count}; "
                f"applied={rgroup_pair_owner_ledger.get('applied_to_pair_review_count')}; "
                f"decisions={rgroup_pair_owner_ledger.get('decision_counts')}"
            ),
        },
        {
            "check_id": "rgroup_feed_onboarding_gate",
            "label": "Next R-group feed drop has an onboarding gate",
            "status": "pass"
            if rgroup_feed_onboarding.get("status")
            in {"ready_for_next_feed_drop", "ready_with_deferred_source_owner_review", "awaiting_new_feed_drop"}
            else "fail"
            if rgroup_feed_onboarding.get("status") == "blocked" or production_mode
            else "warn",
            "details": (
                f"status={rgroup_feed_onboarding.get('status') or 'missing'}; "
                f"feeds={rgroup_feed_onboarding.get('feed_file_count')}; "
                f"unmanifested={rgroup_feed_onboarding.get('unmanifested_file_count')}; "
                f"deferred_owner_review={rgroup_feed_onboarding.get('deferred_source_owner_review_count')}; "
                f"pending_owner_review={rgroup_feed_onboarding.get('pending_source_owner_review_count')}"
            ),
        },
        {
            "check_id": "feed_absorption_audit",
            "label": "Feed absorption audit has no blockers before new rows are absorbed",
            "status": "pass"
            if feed_absorption_audit.get("status") in {"ready", "ready_with_open_staging"}
            and int(feed_absorption_audit.get("blocker_count") or 0) == 0
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={feed_absorption_audit.get('status') or 'missing'}; "
                f"rows={feed_absorption_audit.get('row_count')}; "
                f"blockers={feed_absorption_audit.get('blocker_count')}; "
                f"warnings={feed_absorption_audit.get('warning_count')}"
            ),
        },
        {
            "check_id": "feed_absorption_diff_navigator",
            "label": "Feed absorption diff navigator exposes deltas and duplicate/owner drill-down rows",
            "status": "pass"
            if feed_absorption_diff.get("status") in {"ready", "ready_with_open_staging"}
            and int(feed_absorption_diff.get("blocker_count") or 0) == 0
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={feed_absorption_diff.get('status') or 'missing'}; "
                f"rows={feed_absorption_diff.get('row_count')}; "
                f"deltas={feed_absorption_diff.get('feed_delta_count')}; "
                f"duplicates={feed_absorption_diff.get('duplicate_group_count')}; "
                f"blockers={feed_absorption_diff.get('blocker_count')}"
            ),
        },
        {
            "check_id": "source_expansion_governance",
            "label": "Source expansion is governance-only and explicitly blocks ungated expansion",
            "status": "pass"
            if source_expansion_governance.get("status") == "ready"
            and source_expansion_governance.get("ungated_expansion_allowed") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={source_expansion_governance.get('status') or 'missing'}; "
                f"rows={source_expansion_governance.get('row_count')}; "
                f"blocked={source_expansion_governance.get('blocked_gate_count')}; "
                f"scopes={source_expansion_governance.get('allowed_expansion_scopes')}"
            ),
        },
        {
            "check_id": "feed_promotion_simulator",
            "label": "Feed promotion simulator previews staged-row impact before promotion",
            "status": "pass"
            if feed_promotion_simulator.get("status") in {"awaiting_filled_staging_rows", "ready_with_warnings", "ready_for_promotion"}
            and int(feed_promotion_simulator.get("blocker_count") or 0) == 0
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={feed_promotion_simulator.get('status') or 'missing'}; "
                f"rows={feed_promotion_simulator.get('row_count')}; "
                f"staged={feed_promotion_simulator.get('staged_row_count')}; "
                f"blockers={feed_promotion_simulator.get('blocker_count')}; "
                f"allowed={feed_promotion_simulator.get('promotion_allowed_count')}"
            ),
        },
        {
            "check_id": "governed_ingestion_batches",
            "label": "Governed ingestion batches require source and data-foundation gates",
            "status": "pass"
            if governed_ingestion_batches.get("status") in {"ready", "awaiting_rows", "reviewed_holdout"}
            and int(governed_ingestion_batches.get("blocked_batch_count") or 0) == 0
            and governed_ingestion_batches.get("data_foundation_delta_required") is True
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={governed_ingestion_batches.get('status') or 'missing'}; "
                f"rows={governed_ingestion_batches.get('row_count')}; "
                f"blocked={governed_ingestion_batches.get('blocked_batch_count')}; "
                f"allowed={governed_ingestion_batches.get('allowed_ingestion_batch_count')}; "
                f"delta_required={governed_ingestion_batches.get('data_foundation_delta_required')}"
            ),
        },
        {
            "check_id": "rgroup_staging_quality_budget",
            "label": "R-group staging quality budget blocks low-quality staged rows before sandbox review",
            "status": "pass"
            if staging_quality_budget.get("status") in {"awaiting_rows", "ready_for_sandbox_review"}
            and int(staging_quality_budget.get("blocker_count") or 0) == 0
            and staging_quality_budget.get("promotion_allowed_without_sandbox_review") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={staging_quality_budget.get('status') or 'missing'}; "
                f"sources={staging_quality_budget.get('source_count')}; "
                f"staged={staging_quality_budget.get('staged_row_count')}; "
                f"blockers={staging_quality_budget.get('blocker_count')}; "
                f"signoff_required={staging_quality_budget.get('operator_signoff_required')}"
            ),
        },
        {
            "check_id": "staged_feed_sandbox_scoring",
            "label": "Staged feed sandbox scoring previews impact without production scoring writes",
            "status": "pass"
            if staged_feed_sandbox_scoring.get("status") in {"ready", "awaiting_staged_rows"}
            and staged_feed_sandbox_scoring.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={staged_feed_sandbox_scoring.get('status') or 'missing'}; "
                f"candidates={staged_feed_sandbox_scoring.get('candidate_count')}; "
                f"staged={staged_feed_sandbox_scoring.get('staged_row_count')}; "
                f"matched={staged_feed_sandbox_scoring.get('candidate_with_staged_match_count')}; "
                f"production_affected={staged_feed_sandbox_scoring.get('production_scoring_affected')}"
            ),
        },
        {
            "check_id": "sandbox_score_delta_review_packet",
            "label": "Sandbox score-delta review requires operator signoff before production scoring impact",
            "status": "pass"
            if sandbox_score_delta_review.get("status") in {"awaiting_staged_rows", "review_required", "approved", "reviewed_holdout"}
            and sandbox_score_delta_review.get("production_scoring_affected") is False
            and (
                int(sandbox_score_delta_review.get("staged_row_count") or 0) == 0
                or sandbox_score_delta_review.get("status") == "review_required"
                or sandbox_score_delta_review.get("production_scoring_approved") is True
                or sandbox_score_delta_review.get("operator_signoff_complete") is True
            )
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={sandbox_score_delta_review.get('status') or 'missing'}; "
                f"rows={sandbox_score_delta_review.get('row_count')}; "
                f"signoff_required={sandbox_score_delta_review.get('operator_signoff_required_count')}; "
                f"approved={sandbox_score_delta_review.get('approved_signoff_count')}; "
                f"deferred={sandbox_score_delta_review.get('deferred_signoff_count')}; "
                f"pending={sandbox_score_delta_review.get('pending_signoff_count')}; "
                f"production_approved={sandbox_score_delta_review.get('production_scoring_approved')}; "
                f"production_affected={sandbox_score_delta_review.get('production_scoring_affected')}"
            ),
        },
        {
            "check_id": "sandbox_score_delta_signoff_ledger",
            "label": "Sandbox score-delta signoff ledger records explicit operator decisions",
            "status": "pass"
            if sandbox_score_delta_signoff.get("status") in {"reviewed", "pending_signoff"}
            and int(sandbox_score_delta_signoff.get("invalid_row_count") or 0) == 0
            and int(sandbox_score_delta_signoff.get("missing_packet_row_count") or 0) == 0
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={sandbox_score_delta_signoff.get('status') or 'missing'}; "
                f"required={sandbox_score_delta_signoff.get('required_signoff_count')}; "
                f"completed={sandbox_score_delta_signoff.get('completed_signoff_count')}; "
                f"pending={sandbox_score_delta_signoff.get('pending_signoff_count')}; "
                f"decisions={sandbox_score_delta_signoff.get('decision_counts')}"
            ),
        },
        {
            "check_id": "rgroup_feed_digestion_ledger",
            "label": "R-group feed digestion ledger records staged row outcomes by checksum",
            "status": "pass"
            if rgroup_feed_digestion_ledger.get("status") in {"ready", "awaiting_rows"}
            and rgroup_feed_digestion_ledger.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_feed_digestion_ledger.get('status') or 'missing'}; "
                f"rows={rgroup_feed_digestion_ledger.get('row_count')}; "
                f"accepted={rgroup_feed_digestion_ledger.get('accepted_count')}; "
                f"deferred={rgroup_feed_digestion_ledger.get('deferred_count')}; "
                f"held={rgroup_feed_digestion_ledger.get('held_out_count')}; "
                f"promoted={rgroup_feed_digestion_ledger.get('promoted_count')}"
            ),
        },
        {
            "check_id": "rgroup_promotion_approval_ledger",
            "label": "R-group promotion approval ledger binds staged rows before feed copy",
            "status": "pass"
            if rgroup_promotion_approval_ledger.get("status") in {"approved", "reviewed_holdout", "pending_approval", "partially_approved_holdout"}
            and int(rgroup_promotion_approval_ledger.get("invalid_row_count") or 0) == 0
            and int(rgroup_promotion_approval_ledger.get("missing_candidate_row_count") or 0) == 0
            and int(rgroup_promotion_approval_ledger.get("binding_blocker_count") or 0) == 0
            and int(rgroup_promotion_approval_ledger.get("pending_approval_count") or 0) == 0
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_promotion_approval_ledger.get('status') or 'missing'}; "
                f"required={rgroup_promotion_approval_ledger.get('approval_required_count')}; "
                f"pending={rgroup_promotion_approval_ledger.get('pending_approval_count')}; "
                f"approved={rgroup_promotion_approval_ledger.get('approved_count')}; "
                f"deferred={rgroup_promotion_approval_ledger.get('deferred_count')}; "
                f"allowed={rgroup_promotion_approval_ledger.get('promotion_allowed')}"
            ),
        },
        {
            "check_id": "rgroup_selective_approval_batch",
            "label": "R-group selective approval batch approves only positive-control staged rows",
            "status": "pass"
            if rgroup_selective_approval_batch.get("status") in {"ready", "awaiting_positive_control"}
            and rgroup_selective_approval_batch.get("mode") == "rgroup_selective_approval_batch"
            and rgroup_selective_approval_batch.get("production_promotion_allowed") is False
            and rgroup_selective_approval_batch.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_selective_approval_batch.get('status') or 'missing'}; "
                f"candidates={rgroup_selective_approval_batch.get('candidate_count')}; "
                f"approved={rgroup_selective_approval_batch.get('positive_control_approved_count')}; "
                f"holdout={rgroup_selective_approval_batch.get('holdout_count')}; "
                f"allowed={rgroup_selective_approval_batch.get('production_promotion_allowed')}"
            ),
        },
        {
            "check_id": "rgroup_digestion_quality_metrics",
            "label": "R-group digestion quality metrics expose confidence, duplicate, endpoint, and impact warnings",
            "status": "pass"
            if rgroup_digestion_quality_metrics.get("status") in {"ready", "watch", "awaiting_rows"}
            and rgroup_digestion_quality_metrics.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_digestion_quality_metrics.get('status') or 'missing'}; "
                f"rows={rgroup_digestion_quality_metrics.get('row_count')}; "
                f"digestion_rows={rgroup_digestion_quality_metrics.get('digestion_row_count')}; "
                f"quality={rgroup_digestion_quality_metrics.get('quality_status_counts')}; "
                f"deferred_impact={rgroup_digestion_quality_metrics.get('deferred_candidate_impact_row_count')}"
            ),
        },
        {
            "check_id": "rgroup_digestion_quality_closure_queue",
            "label": "R-group digestion quality closure queue converts watch slices into owner actions",
            "status": "pass"
            if rgroup_digestion_quality_closure_queue.get("status") in {"ready", "awaiting_metrics", "closed_holdout"}
            and rgroup_digestion_quality_closure_queue.get("mode") == "rgroup_digestion_quality_closure_queue"
            and (
                rgroup_digestion_quality_closure_queue.get("status") != "closed_holdout"
                or int(rgroup_digestion_quality_closure_queue.get("open_count") or 0) == 0
            )
            and rgroup_digestion_quality_closure_queue.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_digestion_quality_closure_queue.get('status') or 'missing'}; "
                f"tasks={rgroup_digestion_quality_closure_queue.get('row_count')}; "
                f"open={rgroup_digestion_quality_closure_queue.get('open_count')}; "
                f"issues={rgroup_digestion_quality_closure_queue.get('issue_type_counts')}"
            ),
        },
        {
            "check_id": "feed_promotion_rollback_audit",
            "label": "Feed promotion rollback audit records replay checkpoints for approved rows",
            "status": "pass"
            if feed_promotion_rollback_audit.get("status") in {"ready", "awaiting_rows"}
            and feed_promotion_rollback_audit.get("mode") == "feed_promotion_rollback_audit"
            and int(feed_promotion_rollback_audit.get("blocked_count") or 0) == 0
            and feed_promotion_rollback_audit.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={feed_promotion_rollback_audit.get('status') or 'missing'}; "
                f"approved={feed_promotion_rollback_audit.get('approved_row_count')}; "
                f"ready={feed_promotion_rollback_audit.get('ready_count')}; "
                f"blocked={feed_promotion_rollback_audit.get('blocked_count')}; "
                f"allowed={feed_promotion_rollback_audit.get('promotion_allowed')}"
            ),
        },
        {
            "check_id": "rgroup_approval_workbench",
            "label": "R-group approval workbench exposes native filters for promotion review",
            "status": "pass"
            if rgroup_approval_workbench.get("status") in {"ready", "awaiting_rows"}
            and rgroup_approval_workbench.get("mode") == "rgroup_approval_workbench"
            and rgroup_approval_workbench.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_approval_workbench.get('status') or 'missing'}; "
                f"rows={rgroup_approval_workbench.get('row_count')}; "
                f"actions={rgroup_approval_workbench.get('action_bucket_counts')}; "
                f"quality_open={rgroup_approval_workbench.get('quality_open_count')}"
            ),
        },
        {
            "check_id": "rgroup_ring_context_alignment",
            "label": "R-group ring context alignment separates ring and local R-group axes",
            "status": "pass"
            if rgroup_ring_context_alignment.get("status") in {"ready", "awaiting_rows"}
            and rgroup_ring_context_alignment.get("mode") == "rgroup_ring_context_alignment"
            and rgroup_ring_context_alignment.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_ring_context_alignment.get('status') or 'missing'}; "
                f"rows={rgroup_ring_context_alignment.get('row_count')}; "
                f"ring={rgroup_ring_context_alignment.get('ring_replacement_count')}; "
                f"rgroup={rgroup_ring_context_alignment.get('rgroup_replacement_count')}; "
                f"combined={rgroup_ring_context_alignment.get('combined_review_count')}"
            ),
        },
        {
            "check_id": "rgroup_digestion_quality_closure_ledger",
            "label": "R-group digestion quality closure ledger records conservative task closure",
            "status": "pass"
            if rgroup_digestion_quality_closure_ledger.get("status") in {"closed_holdout", "awaiting_queue"}
            and rgroup_digestion_quality_closure_ledger.get("mode") == "rgroup_digestion_quality_closure_ledger"
            and rgroup_digestion_quality_closure_ledger.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_digestion_quality_closure_ledger.get('status') or 'missing'}; "
                f"tasks={rgroup_digestion_quality_closure_ledger.get('task_count')}; "
                f"closed={rgroup_digestion_quality_closure_ledger.get('closed_count')}; "
                f"open={rgroup_digestion_quality_closure_ledger.get('open_count')}"
            ),
        },
        {
            "check_id": "rgroup_approval_workbench_decisions",
            "label": "R-group approval workbench decisions round-trip through signed local records",
            "status": "pass"
            if rgroup_approval_workbench_decisions.get("status") in {"decision_recorded", "awaiting_workbench"}
            and rgroup_approval_workbench_decisions.get("mode") == "rgroup_approval_workbench_decisions"
            and rgroup_approval_workbench_decisions.get("production_scoring_affected") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_approval_workbench_decisions.get('status') or 'missing'}; "
                f"rows={rgroup_approval_workbench_decisions.get('row_count')}; "
                f"approved_rehearsal={rgroup_approval_workbench_decisions.get('approved_rehearsal_count')}; "
                f"deferred={rgroup_approval_workbench_decisions.get('deferred_holdout_count')}"
            ),
        },
        {
            "check_id": "rgroup_guarded_promotion_rehearsal",
            "label": "R-group guarded promotion rehearsal is rollback-backed and dry-run only",
            "status": "pass"
            if rgroup_guarded_promotion_rehearsal.get("status") in {"ready_for_rehearsal", "awaiting_positive_controls"}
            and rgroup_guarded_promotion_rehearsal.get("mode") == "rgroup_guarded_promotion_rehearsal"
            and rgroup_guarded_promotion_rehearsal.get("production_promotion_allowed") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_guarded_promotion_rehearsal.get('status') or 'missing'}; "
                f"ready={rgroup_guarded_promotion_rehearsal.get('ready_count')}; "
                f"blocked={rgroup_guarded_promotion_rehearsal.get('blocked_count')}; "
                f"allowed={rgroup_guarded_promotion_rehearsal.get('production_promotion_allowed')}"
            ),
        },
        {
            "check_id": "ring_rgroup_axis_governance",
            "label": "Ring/R-group axis governance keeps modification axes first-class",
            "status": "pass"
            if ring_rgroup_axis_governance.get("status") in {"ready", "awaiting_alignment"}
            and ring_rgroup_axis_governance.get("mode") == "ring_rgroup_axis_governance"
            and ring_rgroup_axis_governance.get("production_promotion_allowed") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={ring_rgroup_axis_governance.get('status') or 'missing'}; "
                f"axes={ring_rgroup_axis_governance.get('axis_count')}; "
                f"rows={ring_rgroup_axis_governance.get('row_count')}; "
                f"approved_rehearsal={ring_rgroup_axis_governance.get('approved_rehearsal_count')}"
            ),
        },
        {
            "check_id": "rgroup_next_expansion_batch_plan",
            "label": "R-group next expansion batch is planned through governed analog/literature sources",
            "status": "pass"
            if rgroup_next_expansion_batch_plan.get("status") in {"ready", "awaiting_sources"}
            and rgroup_next_expansion_batch_plan.get("mode") == "rgroup_next_expansion_batch_plan"
            and rgroup_next_expansion_batch_plan.get("production_promotion_allowed") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_next_expansion_batch_plan.get('status') or 'missing'}; "
                f"ready={rgroup_next_expansion_batch_plan.get('ready_count')}; "
                f"blocked={rgroup_next_expansion_batch_plan.get('blocked_count')}; "
                f"cap={rgroup_next_expansion_batch_plan.get('planned_staging_cap_total')}"
            ),
        },
        {
            "check_id": "rgroup_approval_trend_views",
            "label": "R-group approval trend views expose approval growth versus quality debt",
            "status": "pass"
            if rgroup_approval_trend_views.get("status") in {"ready", "ready_with_watch"}
            and rgroup_approval_trend_views.get("mode") == "rgroup_approval_trend_views"
            and rgroup_approval_trend_views.get("production_promotion_allowed") is False
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_approval_trend_views.get('status') or 'missing'}; "
                f"views={rgroup_approval_trend_views.get('row_count')}; "
                f"attention={rgroup_approval_trend_views.get('needs_attention_count')}"
            ),
        },
        {
            "check_id": "staging_sandbox_filter_views",
            "label": "Staging and sandbox filtered views are available for native drilldown",
            "status": "pass"
            if staging_sandbox_filter_views.get("status") in {"ready", "empty"}
            and staging_sandbox_filter_views.get("mode") == "staging_sandbox_filter_views"
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={staging_sandbox_filter_views.get('status') or 'missing'}; "
                f"rows={staging_sandbox_filter_views.get('row_count')}; "
                f"types={staging_sandbox_filter_views.get('view_type_counts')}"
            ),
        },
        {
            "check_id": "rgroup_next_feed_drop_staging",
            "label": "Next R-group feed drop has source-specific staging templates",
            "status": "pass"
            if feed_staging_ready
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={rgroup_feed_staging.get('status') or 'missing'}; "
                f"drop={rgroup_feed_staging.get('drop_label')}; "
                f"templates={rgroup_feed_staging.get('template_file_count')}; "
                f"manifest={rgroup_feed_staging.get('manifest_path')}"
            ),
        },
        {
            "check_id": "rgroup_next_feed_drop_staging_gate",
            "label": "Filled next-feed-drop staging rows validate before promotion",
            "status": "pass"
            if feed_staging_gate_ok
            else "fail"
            if rgroup_feed_staging_gate.get("status") == "blocked" or production_mode
            else "warn",
            "details": (
                f"status={rgroup_feed_staging_gate.get('status') or 'missing'}; "
                f"files={rgroup_feed_staging_gate.get('staged_file_count')}; "
                f"filled_files={rgroup_feed_staging_gate.get('filled_file_count')}; "
                f"rows={rgroup_feed_staging_gate.get('staged_row_count')}; "
                f"blockers={rgroup_feed_staging_gate.get('blocker_count')}; "
                f"warnings={rgroup_feed_staging_gate.get('warning_count')}"
            ),
        },
        {
            "check_id": "ring_outcome_overlay_activation",
            "label": "Ring outcome overlay activation is explicit and replay-gated",
            "status": "pass"
            if ring_overlay_activation.get("status") in {"activated", "blocked_no_active_nonzero_context"}
            else "warn"
            if not ring_overlay_activation or ring_overlay_activation.get("status") == "blocked"
            else "fail",
            "details": (
                f"status={ring_overlay_activation.get('status') or 'missing'}; "
                f"active_nonzero={ring_overlay_activation.get('active_nonzero_context_count')}; "
                f"replay={ring_overlay_activation.get('replay_status')}"
            ),
        },
        {
            "check_id": "ring_outcome_production_readiness",
            "label": "Ring outcome result intake is production-gated",
            "status": "pass"
            if ring_outcome_readiness.get("status") in {"awaiting_production_results", "ready_for_strict_import", "activated"}
            else "fail"
            if ring_outcome_readiness.get("gate_status") == "fail"
            else "warn",
            "details": (
                f"status={ring_outcome_readiness.get('status') or 'missing'}; "
                f"importable={ring_outcome_readiness.get('importable_result_count')}; "
                f"pending={ring_outcome_readiness.get('pending_result_count')}; "
                f"validation_errors={ring_outcome_readiness.get('validation_error_count')}"
            ),
        },
        {
            "check_id": "ring_outcome_result_package",
            "label": "Ring outcome result package is production-named and guarded",
            "status": "pass"
            if ring_result_package_ok
            else "fail"
            if ring_outcome_result_package.get("status") == "blocked_by_validation" or production_mode
            else "warn",
            "details": (
                f"status={ring_outcome_result_package.get('status') or 'missing'}; "
                f"rows={ring_outcome_result_package.get('result_row_count')}; "
                f"pending={ring_outcome_result_package.get('pending_result_count')}; "
                f"importable={ring_outcome_result_package.get('importable_result_count')}; "
                f"validation_errors={ring_outcome_result_package.get('validation_error_count')}"
            ),
        },
        {
            "check_id": "ring_outcome_holdout",
            "label": "Ring outcome overlay activation has endpoint holdout status",
            "status": "pass"
            if ring_holdout_ok
            else "fail"
            if ring_outcome_holdout.get("status") == "holdout_review_required"
            else "warn",
            "details": (
                f"status={ring_outcome_holdout.get('status') or 'missing'}; "
                f"endpoints={ring_outcome_holdout.get('endpoint_count')}; "
                f"holdout_ready={ring_outcome_holdout.get('holdout_ready_endpoint_count')}; "
                f"active_nonzero={ring_outcome_holdout.get('active_nonzero_context_count')}; "
                f"replay={ring_outcome_holdout.get('replay_status')}"
            ),
        },
        {
            "check_id": "release_manifest_drift",
            "label": "Release manifest drift has no removals",
            "status": "pass" if not manifest_diff or not manifest_diff.get("removed_count") else "fail",
            "details": f"added={manifest_diff.get('added_count')}, changed={manifest_diff.get('changed_count')}, removed={manifest_diff.get('removed_count')}",
        },
        {
            "check_id": "closed_loop_acceptance",
            "label": "Closed-loop drill acceptance passes",
            "status": "pass"
            if closed_loop_acceptance.get("passed") and closed_loop_acceptance.get("status") != "fail"
            else "warn"
            if not closed_loop_acceptance
            else "fail",
            "details": closed_loop_acceptance.get("status", "missing"),
        },
        {
            "check_id": "closed_loop_promotion_gate",
            "label": "Closed-loop promotion gate is ready or explicitly reviewable",
            "status": "pass"
            if promotion_status == "ready"
            else "warn"
            if promotion_status in {None, "review_required"}
            else "fail",
            "details": f"promotion={promotion_status or 'missing'}; blocks={promotion_gate.get('block_count')}; reviews={promotion_gate.get('review_count')}",
        },
        {
            "check_id": "profile_ab_matrix_cache",
            "label": "Profile A/B matrix is cached and replayable",
            "status": "pass"
            if profile_ab_matrix.get("status") == "ready" and scenario_count and cache_hits >= scenario_count
            else "warn"
            if profile_ab_matrix.get("status") == "ready"
            else "fail",
            "details": f"status={profile_ab_matrix.get('status') or 'missing'}; scenarios={scenario_count}; cache_hits={cache_hits}; material_changes={profile_ab_matrix.get('material_change_count')}",
        },
        {
            "check_id": "public_sar_candidate_links",
            "label": "Public SAR validation links signals to candidates or analog series",
            "status": "pass"
            if public_sar_validation.get("status") == "ready" and int(public_sar_validation.get("candidate_linked_count") or 0)
            else "warn"
            if public_sar_validation
            else "fail",
            "details": (
                f"status={public_sar_validation.get('status') or 'missing'}; "
                f"candidate_linked={public_sar_validation.get('candidate_linked_count')}; "
                f"contradiction_linked={public_sar_validation.get('contradiction_linked_count')}"
            ),
        },
        {
            "check_id": "assay_triage_lineage",
            "label": "Assay triage has follow-up lineage provenance",
            "status": "pass"
            if assay_triage.get("status") in {"triaged", "empty"} and open_issues == 0 and int(assay_triage.get("lineage_group_count") or 0)
            else "warn"
            if assay_triage.get("status") in {"triaged", "empty"}
            else "fail",
            "details": (
                f"status={assay_triage.get('status') or 'missing'}; "
                f"lineage_groups={assay_triage.get('lineage_group_count')}; "
                f"duplicate_lineage={assay_triage.get('duplicate_lineage_event_count')}; open_issues={open_issues}"
            ),
        },
        {
            "check_id": "candidate_evidence_priority",
            "label": "Candidate evidence priority view is current",
            "status": "pass" if candidate_priority.get("status") == "ready" else "warn" if candidate_priority else "fail",
            "details": (
                f"status={candidate_priority.get('status') or 'missing'}; rows={candidate_priority.get('row_count')}; "
                f"high={candidate_priority.get('high_priority_count')}; material={candidate_priority.get('material_diff_linked_count')}"
            ),
        },
        {
            "check_id": "freeze_rollback_drill",
            "label": "Profile freeze rollback drill passes",
            "status": "pass" if rollback_drill.get("status") == "pass" else "warn" if rollback_drill else "fail",
            "details": f"status={rollback_drill.get('status') or 'missing'}; target={rollback_drill.get('target_freeze_id')}; release={rollback_drill.get('would_release_tag')}",
        },
        {
            "check_id": "profile_rollback_replay",
            "label": "Profile rollback replay is available",
            "status": "pass" if rollback_replay.get("status") in {"ready", "empty"} else "warn" if rollback_replay else "fail",
            "details": (
                f"status={rollback_replay.get('status') or 'missing'}; rows={rollback_replay.get('row_count')}; "
                f"max_score_delta={rollback_replay.get('max_abs_rollback_score_delta')}; max_rank_delta={rollback_replay.get('max_abs_rollback_rank_delta')}"
            ),
        },
        {
            "check_id": "public_sar_contradiction_triage",
            "label": "Public SAR contradictions have a triage worklist",
            "status": "pass" if contradiction_triage.get("status") in {"ready", "empty"} else "warn" if contradiction_triage else "fail",
            "details": (
                f"status={contradiction_triage.get('status') or 'missing'}; rows={contradiction_triage.get('row_count')}; "
                f"candidate_linked={contradiction_triage.get('candidate_linked_count')}; net={contradiction_triage.get('net_contradicted_count')}"
            ),
        },
        {
            "check_id": "public_sar_contradiction_resolution_batch",
            "label": "High-priority public SAR contradictions have first-pass resolution",
            "status": "pass" if sar_resolution_batch.get("status") in {"resolved", "no_open_priority_rows"} else "warn" if sar_resolution_batch else "fail",
            "details": (
                f"status={sar_resolution_batch.get('status') or 'missing'}; "
                f"processed={sar_resolution_batch.get('processed_count')}; "
                f"needs_measurement={sar_resolution_batch.get('candidate_measurement_gated_count')}; "
                f"reference_watch={sar_resolution_batch.get('reference_only_watch_count')}"
            ),
        },
        {
            "check_id": "public_sar_contradiction_watchlist",
            "label": "Remaining SAR contradiction work advances only with project overlap",
            "status": "pass"
            if sar_watchlist.get("status") in {"ready", "no_linked_open_rows", "empty"}
            else "warn"
            if sar_watchlist
            else "fail",
            "details": (
                f"status={sar_watchlist.get('status') or 'missing'}; "
                f"actionable={sar_watchlist.get('actionable_count')}; "
                f"deferred_reference={sar_watchlist.get('deferred_reference_only_count')}"
            ),
        },
        {
            "check_id": "evidence_value_report",
            "label": "Candidate evidence value scoring is current",
            "status": "pass" if evidence_value.get("status") in {"ready", "empty"} else "warn" if evidence_value else "fail",
            "details": (
                f"status={evidence_value.get('status') or 'missing'}; rows={evidence_value.get('row_count')}; "
                f"high_value={evidence_value.get('high_value_count')}; contradiction={evidence_value.get('contradiction_resolution_count')}"
            ),
        },
        {
            "check_id": "measurement_feedback_plan",
            "label": "Measurement feedback plan is available for high-value evidence gaps",
            "status": "pass" if measurement_feedback.get("status") in {"ready", "empty"} else "warn" if measurement_feedback else "fail",
            "details": (
                f"status={measurement_feedback.get('status') or 'missing'}; rows={measurement_feedback.get('row_count')}; "
                f"high={measurement_feedback.get('high_priority_count')}; candidates={measurement_feedback.get('candidate_row_count')}"
            ),
        },
        {
            "check_id": "measurement_feedback_import",
            "label": "Local measurement-evidence intake is traceable",
            "status": "pass"
            if measurement_feedback_import.get("status")
            in {"imported", "imported_with_validation_issues", "imported_uncalibrated_measurements", "needs_real_measurement_feedback"}
            else "fail"
            if measurement_feedback_import.get("status") == "validation_failed" or not measurement_feedback_import
            else "warn",
            "details": (
                f"status={measurement_feedback_import.get('status') or 'missing'}; "
                f"importable={measurement_feedback_import.get('importable_row_count')}; "
                f"calibration_ready={measurement_feedback_import.get('calibration_ready_row_count')}; "
                f"rejected={measurement_feedback_import.get('rejected_row_count')}"
            ),
        },
        {
            "check_id": "measurement_feedback_gap_closure",
            "label": "Unmatched measurement rows are endpoint-safe and manually reviewable",
            "status": "pass"
            if measurement_gap_closure.get("status") in {"manual_review_required", "decision_recorded", "ready_for_exact_import", "no_unmatched_plan_rows"}
            else "warn"
            if measurement_gap_closure
            else "fail",
            "details": (
                f"status={measurement_gap_closure.get('status') or 'missing'}; "
                f"open_gap={measurement_gap_closure.get('open_gap_count')}; "
                f"endpoint_mismatch={measurement_gap_closure.get('endpoint_mismatch_count')}"
            ),
        },
        {
            "check_id": "measurement_gap_exact_result_intake",
            "label": "Exact endpoint measurement gap intake is available",
            "status": "pass"
            if measurement_gap_exact_intake.get("status") in {"awaiting_exact_results", "ready_for_import", "empty"}
            else "warn"
            if measurement_gap_exact_intake
            else "fail",
            "details": (
                f"status={measurement_gap_exact_intake.get('status') or 'missing'}; "
                f"template_rows={measurement_gap_exact_intake.get('template_row_count')}; "
                f"pending_exact={measurement_gap_exact_intake.get('pending_exact_result_count')}; "
                f"importable_exact={measurement_gap_exact_intake.get('importable_exact_result_count')}"
            ),
        },
        {
            "check_id": "measurement_gap_endpoint_governance",
            "label": "Measurement gaps have strict non-experimental endpoint governance",
            "status": "pass"
            if measurement_gap_endpoint_governance.get("status") in {"ready", "attention_required", "empty"}
            and measurement_gap_endpoint_governance.get("real_experiment_feedback_used") is False
            else "warn"
            if measurement_gap_endpoint_governance
            else "fail",
            "details": (
                f"status={measurement_gap_endpoint_governance.get('status') or 'missing'}; "
                f"mode={measurement_gap_endpoint_governance.get('mode') or 'missing'}; "
                f"pending={measurement_gap_endpoint_governance.get('strict_exact_pending_count')}; "
                f"blocked_pairs={measurement_gap_endpoint_governance.get('blocked_cross_endpoint_pair_count')}"
            ),
        },
        {
            "check_id": "site_class_policy_pack",
            "label": "Candidate-facing site-class guidance pack is available",
            "status": "pass"
            if site_class_policy_pack.get("status") == "ready"
            and site_class_policy_pack.get("real_experiment_feedback_used") is False
            and int(site_class_policy_pack.get("row_count") or 0) >= 4
            else "warn"
            if site_class_policy_pack
            else "fail",
            "details": (
                f"status={site_class_policy_pack.get('status') or 'missing'}; "
                f"rows={site_class_policy_pack.get('row_count')}; "
                f"classes={site_class_policy_pack.get('site_classes')}"
            ),
        },
        {
            "check_id": "evidence_value_calibration",
            "label": "Evidence value calibration is present or explicitly awaiting local evidence",
            "status": "pass"
            if evidence_value_calibration.get("status") in {"calibrated", "needs_real_measurement_feedback", "needs_normalized_measurement_scores"}
            else "fail"
            if not evidence_value_calibration
            else "warn",
            "details": (
                f"status={evidence_value_calibration.get('status') or 'missing'}; "
                f"rows={evidence_value_calibration.get('calibration_row_count')}; "
                f"mae={evidence_value_calibration.get('mean_absolute_error')}"
            ),
        },
        {
            "check_id": "evidence_value_policy_proposal",
            "label": "Evidence-value policy proposal is versioned and not auto-activated",
            "status": "pass"
            if evidence_value_policy_proposal.get("status")
            in {"review_required", "approved_not_active", "activated", "hold_current_policy", "insufficient_calibration_data", "blocked_missing_rollback_compare"}
            and evidence_value_policy_proposal.get("activation_status") in {"not_active", "active", None}
            else "fail"
            if not evidence_value_policy_proposal
            else "warn",
            "details": (
                f"status={evidence_value_policy_proposal.get('status') or 'missing'}; "
                f"approval={evidence_value_policy_proposal.get('approval_status')}; "
                f"changes={evidence_value_policy_proposal.get('weight_change_count')}; "
                f"activation={evidence_value_policy_proposal.get('activation_status')}"
            ),
        },
        {
            "check_id": "evidence_value_policy_replay",
            "label": "Evidence-value policy proposal has pre-activation replay",
            "status": "pass"
            if evidence_value_policy_replay.get("status") in {"compared", "empty"}
            and evidence_value_policy_replay.get("activation_status") in {"not_active", "active"}
            and evidence_value_policy_replay.get("activation_gate_status")
            in {"ready_for_manual_activation", "blocked_pending_manual_approval", "blocked_replay_drift_review", "blocked_missing_evidence_rows", "activated"}
            else "warn"
            if evidence_value_policy_replay
            else "fail",
            "details": (
                f"status={evidence_value_policy_replay.get('status') or 'missing'}; "
                f"gate={evidence_value_policy_replay.get('activation_gate_status')}; "
                f"top_n_changes={evidence_value_policy_replay.get('top_n_change_count')}; "
                f"max_score_delta={evidence_value_policy_replay.get('max_abs_score_delta')}"
            ),
        },
        {
            "check_id": "evidence_value_policy_activation",
            "label": "Activated evidence-value policy has an auditable active snapshot",
            "status": "pass"
            if evidence_value_policy_proposal.get("activation_status") != "active"
            or (
                evidence_value_policy_activation.get("status") == "activated"
                and evidence_value_policy_active.get("activation_status") == "active"
                and evidence_value_policy_active.get("source_proposal_id") == evidence_value_policy_proposal.get("proposal_id")
            )
            else "warn"
            if evidence_value_policy_activation or evidence_value_policy_active
            else "fail",
            "details": (
                f"activation_status={evidence_value_policy_activation.get('status') or 'missing'}; "
                f"active_policy={evidence_value_policy_active.get('policy_version') or 'missing'}; "
                f"source_proposal={evidence_value_policy_active.get('source_proposal_id') or 'missing'}"
            ),
        },
        {
            "check_id": "evidence_value_policy_active_compare",
            "label": "Active evidence-value policy has baseline comparison",
            "status": "pass"
            if evidence_value_policy_proposal.get("activation_status") != "active"
            or evidence_value_policy_active_compare.get("status") == "compared"
            else "warn"
            if evidence_value_policy_active_compare
            else "fail",
            "details": (
                f"status={evidence_value_policy_active_compare.get('status') or 'missing'}; "
                f"rows={evidence_value_policy_active_compare.get('row_count')}; "
                f"max_score_delta={evidence_value_policy_active_compare.get('max_abs_score_delta')}; "
                f"profile_flags={evidence_value_policy_active_compare.get('profile_impact_review_count')}"
            ),
        },
        {
            "check_id": "profile_impact_review_queue",
            "label": "Profile-impact flags have a non-experimental reviewer workflow",
            "status": "pass" if profile_impact_review.get("status") in {"review_required", "reviewed", "empty"} else "warn" if profile_impact_review else "fail",
            "details": (
                f"status={profile_impact_review.get('status') or 'missing'}; "
                f"rows={profile_impact_review.get('row_count')}; "
                f"open={profile_impact_review.get('open_review_count')}; "
                f"mode={profile_impact_review.get('mode') or 'missing'}"
            ),
        },
        {
            "check_id": "project_memory_review_queue",
            "label": "Project Memory review queue consolidates policy, measurement, and SAR follow-up",
            "status": "pass" if project_memory_review_queue.get("status") in {"ready", "empty"} else "warn" if project_memory_review_queue else "fail",
            "details": (
                f"status={project_memory_review_queue.get('status') or 'missing'}; rows={project_memory_review_queue.get('row_count')}; "
                f"policy_gate={project_memory_review_queue.get('policy_activation_gate_status')}"
            ),
        },
        {
            "check_id": "project_memory_review_dashboard",
            "label": "Project Memory review dashboard summarizes lanes and assignees",
            "status": "pass" if project_memory_review_dashboard.get("status") in {"ready", "needs_attention", "empty"} else "warn" if project_memory_review_dashboard else "fail",
            "details": (
                f"status={project_memory_review_dashboard.get('status') or 'missing'}; "
                f"rows={project_memory_review_dashboard.get('row_count')}; "
                f"open_like={project_memory_review_dashboard.get('open_like_count')}; "
                f"lanes={project_memory_review_dashboard.get('lane_row_count')}"
            ),
        },
        {
            "check_id": "promotion_readiness_packet",
            "label": "Promotion readiness packet combines policy, profile, endpoint, and Project Memory governance",
            "status": "pass"
            if promotion_readiness_packet.get("status") in {"ready", "review_required"}
            and promotion_readiness_packet.get("mode") == "non_experimental_promotion_readiness_packet"
            else "fail"
            if promotion_readiness_packet.get("status") == "blocked"
            else "warn"
            if promotion_readiness_packet
            else "fail",
            "details": (
                f"status={promotion_readiness_packet.get('status') or 'missing'}; "
                f"score={promotion_readiness_packet.get('readiness_score')}; "
                f"profile_open={promotion_readiness_packet.get('profile_impact_open_count')}; "
                f"endpoint_pending={promotion_readiness_packet.get('strict_exact_pending_count')}; "
                f"project_memory_open={promotion_readiness_packet.get('project_memory_open_like_count')}"
            ),
        },
        {
            "check_id": "native_ui_quality",
            "label": "Native UI quality report confirms browser-free high-DPI shell",
            "status": "pass"
            if native_ui_quality.get("status") == "pass"
            and native_ui_quality.get("browser_required") is False
            else "warn"
            if native_ui_quality
            else "warn",
            "details": (
                f"status={native_ui_quality.get('status') or 'missing'}; "
                f"browser_required={native_ui_quality.get('browser_required')}; "
                f"dpi={native_ui_quality.get('high_dpi')}"
            ),
        },
        {
            "check_id": "local_db_health",
            "label": "Local SQLite health report is available for large DB workflows",
            "status": "pass"
            if local_db_health.get("status") == "healthy"
            else "warn"
            if local_db_health
            else "warn",
            "details": (
                f"status={local_db_health.get('status') or 'missing'}; "
                f"ring_rows={(local_db_health.get('table_rows') or {}).get('ring_system')}; "
                f"ring_indexes={local_db_health.get('ring_index_count')}"
            ),
        },
        {
            "check_id": "local_db_maintenance",
            "label": "Local DB maintenance report covers indexes, cache, and latency budgets",
            "status": "pass"
            if local_db_maintenance.get("status") in {"ready", "attention_required"}
            else "warn"
            if local_db_maintenance
            else "warn",
            "details": (
                f"status={local_db_maintenance.get('status') or 'missing'}; "
                f"rows={local_db_maintenance.get('row_count')}; "
                f"warnings={local_db_maintenance.get('warn_count')}; "
                f"failures={local_db_maintenance.get('fail_count')}"
            ),
        },
        {
            "check_id": "local_db_maintenance_release_gate",
            "label": "Local DB maintenance separates release stops from watch items",
            "status": "pass"
            if local_db_maintenance_release_gate.get("status") in {"pass", "watch"}
            and int(local_db_maintenance_release_gate.get("release_stop_count") or 0) == 0
            else "fail"
            if production_mode
            else "warn",
            "details": (
                f"status={local_db_maintenance_release_gate.get('status') or 'missing'}; "
                f"release_stop={local_db_maintenance_release_gate.get('release_stop_count')}; "
                f"watch={local_db_maintenance_release_gate.get('watch_count')}; "
                f"daily_alert={local_db_maintenance_release_gate.get('daily_alert_level')}"
            ),
        },
        {
            "check_id": "local_db_maintenance_trend",
            "label": "Local DB maintenance trend tracks latency and cache warm status",
            "status": "pass"
            if local_db_maintenance_trend.get("status") == "tracking"
            else "warn"
            if local_db_maintenance_trend
            else "warn",
            "details": (
                f"status={local_db_maintenance_trend.get('status') or 'missing'}; "
                f"rows={local_db_maintenance_trend.get('row_count')}; "
                f"latest={(local_db_maintenance_trend.get('latest') or {}).get('status')}; "
                f"max_latency={(local_db_maintenance_trend.get('latest') or {}).get('max_latency_ms')}"
            ),
        },
        {
            "check_id": "candidate_visual_compare",
            "label": "Candidate visual compare packet has molecule images and evidence deltas",
            "status": "pass"
            if candidate_visual_compare.get("status") == "ready"
            and candidate_visual_compare.get("grid_image_path")
            and candidate_visual_compare.get("alignment_status")
            else "warn"
            if candidate_visual_compare
            else "warn",
            "details": (
                f"status={candidate_visual_compare.get('status') or 'missing'}; "
                f"rows={candidate_visual_compare.get('candidate_count')}; "
                f"alignment={candidate_visual_compare.get('alignment_status')}; "
                f"grid={candidate_visual_compare.get('grid_image_path')}"
            ),
        },
        {
            "check_id": "candidate_review_packet",
            "label": "Candidate review packet groups site-class, evidence, and risk review rows",
            "status": "pass"
            if candidate_review_packet.get("status") == "review_ready"
            and candidate_review_packet.get("mode") == "non_experimental_candidate_review_packet"
            else "warn"
            if candidate_review_packet
            else "warn",
            "details": (
                f"status={candidate_review_packet.get('status') or 'missing'}; "
                f"rows={candidate_review_packet.get('row_count')}; "
                f"pending={candidate_review_packet.get('review_required_count')}"
            ),
        },
        {
            "check_id": "candidate_review_board",
            "label": "Candidate review board preserves local reviewer decisions and focused rows",
            "status": "pass"
            if candidate_review_board.get("status") == "ready"
            and candidate_review_board.get("mode") == "local_candidate_review_board"
            else "warn"
            if candidate_review_board
            else "warn",
            "details": (
                f"status={candidate_review_board.get('status') or 'missing'}; "
                f"rows={candidate_review_board.get('filtered_row_count')}; "
                f"focused={candidate_review_board.get('focused_row_count')}; "
                f"pending={candidate_review_board.get('pending_local_review_count')}"
            ),
        },
        {
            "check_id": "candidate_drilldown_packet",
            "label": "Candidate drill-down packet links image, review, board, and governance evidence",
            "status": "pass"
            if candidate_drilldown_packet.get("status") == "ready"
            and candidate_drilldown_packet.get("mode") == "non_experimental_candidate_drilldown_packet"
            else "warn"
            if candidate_drilldown_packet
            else "warn",
            "details": (
                f"status={candidate_drilldown_packet.get('status') or 'missing'}; "
                f"rows={candidate_drilldown_packet.get('row_count')}; "
                f"visual={candidate_drilldown_packet.get('linked_visual_rows')}; "
                f"board={candidate_drilldown_packet.get('linked_board_rows')}; "
                f"governance={candidate_drilldown_packet.get('linked_governance_rows')}"
            ),
        },
        {
            "check_id": "local_governance_diff",
            "label": "Local governance diff tracks candidate movement across scoring/profile/policy snapshots",
            "status": "pass"
            if local_governance_diff.get("status") in {"compared", "baseline_created"}
            else "warn"
            if local_governance_diff
            else "warn",
            "details": (
                f"status={local_governance_diff.get('status') or 'missing'}; "
                f"changed={local_governance_diff.get('changed_candidate_count')}; "
                f"added={local_governance_diff.get('added_candidate_count')}; "
                f"removed={local_governance_diff.get('removed_candidate_count')}"
            ),
        },
        {
            "check_id": "named_governance_baselines",
            "label": "Named governance baselines are available for local policy/profile diffing",
            "status": "pass"
            if governance_baselines.get("status") == "ready"
            else "warn"
            if governance_baselines
            else "warn",
            "details": (
                f"status={governance_baselines.get('status') or 'missing'}; "
                f"baselines={governance_baselines.get('baseline_count') or len(governance_baselines.get('baselines') or [])}"
            ),
        },
        {
            "check_id": "candidate_baseline_compare",
            "label": "Named candidate-set baseline comparison is available",
            "status": "pass"
            if candidate_baseline_compare.get("status") in {"compared", "baseline_created"}
            else "warn"
            if candidate_baseline_compare
            else "warn",
            "details": (
                f"status={candidate_baseline_compare.get('status') or 'missing'}; "
                f"baseline={candidate_baseline_compare.get('baseline_id')}; "
                f"changed={candidate_baseline_compare.get('changed_candidate_count')}; "
                f"added={candidate_baseline_compare.get('added_candidate_count')}; "
                f"removed={candidate_baseline_compare.get('removed_candidate_count')}"
            ),
        },
        {
            "check_id": "candidate_review_analytics",
            "label": "Candidate review analytics summarize backlog, risk, and reviewer workload",
            "status": "pass"
            if candidate_review_analytics.get("status") == "ready"
            and candidate_review_analytics.get("mode") == "local_candidate_review_analytics"
            else "warn"
            if candidate_review_analytics
            else "warn",
            "details": (
                f"status={candidate_review_analytics.get('status') or 'missing'}; "
                f"pending={candidate_review_analytics.get('pending_backlog_count')}; "
                f"risks={candidate_review_analytics.get('repeated_risk_bucket_count')}; "
                f"reviewers={candidate_review_analytics.get('reviewer_count')}"
            ),
        },
        {
            "check_id": "candidate_decision_packet",
            "label": "Candidate decision packet separates local decisions from execution automation",
            "status": "pass"
            if candidate_decision_packet.get("status") == "ready"
            and candidate_decision_packet.get("mode") == "local_candidate_decision_packet"
            and (candidate_decision_packet.get("export_schema") or {}).get("procurement_allowed") is False
            else "warn"
            if candidate_decision_packet
            else "warn",
            "details": (
                f"status={candidate_decision_packet.get('status') or 'missing'}; "
                f"decisions={candidate_decision_packet.get('decision_count')}; "
                f"counts={candidate_decision_packet.get('decision_counts')}; "
                "external_operational_workflows_blocked=True"
            ),
        },
        {
            "check_id": "candidate_evidence_drawer",
            "label": "Candidate evidence drawer links structure, evidence, review, baseline, and decision context",
            "status": "pass"
            if candidate_evidence_drawer.get("status") == "ready"
            and candidate_evidence_drawer.get("mode") == "native_candidate_evidence_drawer"
            else "warn"
            if candidate_evidence_drawer
            else "warn",
            "details": (
                f"status={candidate_evidence_drawer.get('status') or 'missing'}; "
                f"rows={candidate_evidence_drawer.get('row_count')}; "
                f"decision_links={candidate_evidence_drawer.get('linked_decision_rows')}"
            ),
        },
        {
            "check_id": "candidate_explanation_panel",
            "label": "Candidate explanation panel links score, evidence, baseline, QA, and remediation",
            "status": "pass"
            if candidate_explanation_panel.get("status") == "ready"
            and candidate_explanation_panel.get("mode") == "candidate_explanation_panel"
            else "warn"
            if candidate_explanation_panel
            else "warn",
            "details": (
                f"status={candidate_explanation_panel.get('status') or 'missing'}; "
                f"rows={candidate_explanation_panel.get('row_count')}; "
                f"drawer={candidate_explanation_panel.get('linked_drawer_rows')}; "
                f"qa={candidate_explanation_panel.get('linked_qa_rows')}; "
                f"remediation_linked={candidate_explanation_panel.get('remediation_linked_count')}"
            ),
        },
        {
            "check_id": "candidate_explanation_compare",
            "label": "Candidate explanation compare supports side-by-side local review",
            "status": "pass"
            if candidate_explanation_compare.get("status") == "ready"
            and candidate_explanation_compare.get("mode") == "candidate_explanation_compare"
            else "warn"
            if candidate_explanation_compare
            else "warn",
            "details": (
                f"status={candidate_explanation_compare.get('status') or 'missing'}; "
                f"base={candidate_explanation_compare.get('base_candidate_id')}; "
                f"head={candidate_explanation_compare.get('head_candidate_id')}; "
                f"different={candidate_explanation_compare.get('different_component_count')}; "
                f"stoplist={candidate_explanation_compare.get('stoplist_component_count')}"
            ),
        },
        {
            "check_id": "candidate_explanation_drilldown",
            "label": "Candidate explanation drilldown routes components to evidence, QA, baseline, and remediation",
            "status": "pass"
            if candidate_explanation_drilldown.get("status") == "ready"
            and candidate_explanation_drilldown.get("mode") == "candidate_explanation_drilldown"
            else "warn"
            if candidate_explanation_drilldown
            else "warn",
            "details": (
                f"status={candidate_explanation_drilldown.get('status') or 'missing'}; "
                f"candidates={candidate_explanation_drilldown.get('candidate_count')}; "
                f"rows={candidate_explanation_drilldown.get('row_count')}; "
                f"attention={candidate_explanation_drilldown.get('attention_count')}"
            ),
        },
        {
            "check_id": "candidate_component_structure_highlight",
            "label": "Candidate explanation components carry 2D structure/highlight context",
            "status": "pass"
            if any(
                row.get("structure_image_path")
                and row.get("site_highlight_label") is not None
                and row.get("right_panel_detail")
                for row in candidate_explanation_drilldown.get("rows") or []
            )
            else "warn"
            if candidate_explanation_drilldown
            else "warn",
            "details": (
                f"rows={candidate_explanation_drilldown.get('row_count')}; "
                "fields=structure_image_path/site_highlight_label/right_panel_detail"
            ),
        },
        {
            "check_id": "candidate_explanation_matrix",
            "label": "Candidate explanation matrix supports N-way local review",
            "status": "pass"
            if candidate_explanation_matrix.get("status") == "ready"
            and candidate_explanation_matrix.get("mode") == "candidate_explanation_matrix"
            else "warn",
            "details": (
                f"status={candidate_explanation_matrix.get('status') or 'missing'}; "
                f"candidates={candidate_explanation_matrix.get('candidate_count')}; "
                f"stoplist={candidate_explanation_matrix.get('stoplist_candidate_count')}; "
                f"pairwise={candidate_explanation_matrix.get('pairwise_delta_count')}"
            ),
        },
        {
            "check_id": "site_detection_confidence",
            "label": "Site detection confidence explains rule hits, boundary guards, and false-positive tiers",
            "status": "pass"
            if site_detection_confidence.get("status") in {"ready", "review_required"}
            and site_detection_confidence.get("mode") == "site_detection_confidence"
            and int(site_detection_confidence.get("row_count") or 0) > 0
            else "warn"
            if site_detection_confidence
            else "warn",
            "details": (
                f"status={site_detection_confidence.get('status') or 'missing'}; "
                f"rows={site_detection_confidence.get('row_count')}; "
                f"low={site_detection_confidence.get('low_confidence_count')}; "
                f"classes={site_detection_confidence.get('site_class_count')}"
            ),
        },
        {
            "check_id": "native_drilldown_actions",
            "label": "Native Reports selected-row drilldown actions are indexed",
            "status": "pass"
            if native_drilldown_actions.get("status") in {"ready", "empty"}
            and native_drilldown_actions.get("mode") == "native_drilldown_actions"
            and int(native_drilldown_actions.get("route_supported_count") or 0) >= 0
            and int(native_drilldown_actions.get("direct_action_supported_count") or 0) >= int(native_drilldown_actions.get("route_supported_count") or 0)
            else "warn",
            "details": (
                f"status={native_drilldown_actions.get('status') or 'missing'}; "
                f"rows={native_drilldown_actions.get('row_count')}; "
                f"routes={native_drilldown_actions.get('route_supported_count')}; "
                f"direct={native_drilldown_actions.get('direct_action_supported_count')}; "
                f"types={native_drilldown_actions.get('action_type_counts')}"
            ),
        },
        {
            "check_id": "candidate_explanation_score_breakdown",
            "label": "Candidate explanation score breakdown charts are available",
            "status": "pass"
            if int(candidate_explanation_panel.get("chart_count") or 0) > 0
            and any(_artifact_exists(root_path, row.get("preview_path") or row.get("image_path") or row.get("chart_path")) for row in candidate_explanation_panel.get("chart_rows") or [])
            else "warn"
            if candidate_explanation_panel
            else "warn",
            "details": f"charts={candidate_explanation_panel.get('chart_count')}; rows={len(candidate_explanation_panel.get('chart_rows') or [])}",
        },
        {
            "check_id": "candidate_decision_qa",
            "label": "Candidate decision QA is available before discussion handoff",
            "status": "pass"
            if candidate_decision_qa.get("status") == "ready"
            and candidate_decision_qa.get("mode") == "local_candidate_decision_qa"
            else "warn"
            if candidate_decision_qa
            else "warn",
            "details": (
                f"status={candidate_decision_qa.get('status') or 'missing'}; "
                f"rows={candidate_decision_qa.get('row_count')}; "
                f"attention={candidate_decision_qa.get('attention_count')}"
            ),
        },
        {
            "check_id": "evidence_quality_scorecard",
            "label": "Candidate evidence quality scorecard is available",
            "status": "pass"
            if evidence_quality_scorecard.get("status") == "ready"
            and evidence_quality_scorecard.get("mode") == "candidate_evidence_quality_scorecard"
            else "warn"
            if evidence_quality_scorecard
            else "warn",
            "details": (
                f"status={evidence_quality_scorecard.get('status') or 'missing'}; "
                f"rows={evidence_quality_scorecard.get('row_count')}; "
                f"attention={evidence_quality_scorecard.get('attention_count')}; "
                f"watch={evidence_quality_scorecard.get('watch_count')}"
            ),
        },
        {
            "check_id": "candidate_evidence_quality",
            "label": "Candidate evidence quality scorecard is available",
            "status": "pass"
            if candidate_evidence_quality.get("status") == "ready"
            and candidate_evidence_quality.get("mode") == "candidate_evidence_quality_scorecard"
            else "warn"
            if candidate_evidence_quality
            else "warn",
            "details": (
                f"status={candidate_evidence_quality.get('status') or 'missing'}; "
                f"rows={candidate_evidence_quality.get('row_count')}; "
                f"attention={candidate_evidence_quality.get('attention_count')}"
            ),
        },
        {
            "check_id": "candidate_baseline_manager",
            "label": "Candidate baseline manager lists active and archived local baselines",
            "status": "pass"
            if candidate_baseline_manager.get("status") in {"ready", "empty"}
            and candidate_baseline_manager.get("mode") == "candidate_baseline_manager"
            else "warn"
            if candidate_baseline_manager
            else "warn",
            "details": (
                f"status={candidate_baseline_manager.get('status') or 'missing'}; "
                f"baselines={candidate_baseline_manager.get('baseline_count')}; "
                f"archive_review={candidate_baseline_manager.get('archive_review_count')}"
            ),
        },
        {
            "check_id": "reviewer_operations",
            "label": "Reviewer operations report summarizes SLA, deferrals, and handoff load",
            "status": "pass"
            if reviewer_operations.get("status") == "ready"
            and reviewer_operations.get("mode") == "candidate_reviewer_operations"
            else "warn"
            if reviewer_operations
            else "warn",
            "details": (
                f"status={reviewer_operations.get('status') or 'missing'}; "
                f"overdue={reviewer_operations.get('pending_overdue_count')}; "
                f"repeated_defer={reviewer_operations.get('repeated_defer_reason_count')}; "
                f"workload_pending={reviewer_operations.get('workload_pending_count')}"
            ),
        },
        {
            "check_id": "baseline_lineage_compare",
            "label": "Baseline lineage compare is available",
            "status": "pass"
            if baseline_lineage_compare.get("status") in {"ready", "compared"}
            and baseline_lineage_compare.get("mode") == "candidate_baseline_lineage_compare"
            else "warn"
            if baseline_lineage_compare
            else "warn",
            "details": (
                f"status={baseline_lineage_compare.get('status') or 'missing'}; "
                f"base={baseline_lineage_compare.get('base_baseline_id')}; "
                f"head={baseline_lineage_compare.get('head_baseline_id')}; "
                f"entered={baseline_lineage_compare.get('entered_candidate_count')}; "
                f"exited={baseline_lineage_compare.get('exited_candidate_count')}; "
                f"changed={baseline_lineage_compare.get('changed_candidate_count')}"
            ),
        },
        {
            "check_id": "candidate_baseline_lineage",
            "label": "Candidate baseline lineage compare is available",
            "status": "pass"
            if candidate_baseline_lineage.get("status") in {"ready", "compared"}
            and candidate_baseline_lineage.get("mode") == "candidate_baseline_lineage_compare"
            else "warn"
            if candidate_baseline_lineage
            else "warn",
            "details": (
                f"status={candidate_baseline_lineage.get('status') or 'missing'}; "
                f"mode={candidate_baseline_lineage.get('comparison_mode')}; "
                f"entered={candidate_baseline_lineage.get('entered_count', candidate_baseline_lineage.get('entered_candidate_count'))}; "
                f"exited={candidate_baseline_lineage.get('exited_count', candidate_baseline_lineage.get('exited_candidate_count'))}; "
                f"changed={candidate_baseline_lineage.get('changed_count', candidate_baseline_lineage.get('changed_candidate_count'))}"
            ),
        },
        {
            "check_id": "review_command_center",
            "label": "Review command center links gates to local review artifacts",
            "status": "pass"
            if review_command_center.get("status") == "ready"
            and review_command_center.get("mode") == "review_command_center"
            else "warn"
            if review_command_center
            else "warn",
            "details": (
                f"status={review_command_center.get('status') or 'missing'}; "
                f"rows={review_command_center.get('row_count')}; "
                f"actionable={review_command_center.get('actionable_count')}; "
                f"types={review_command_center.get('row_type_counts')}"
            ),
        },
        {
            "check_id": "candidate_remediation_queue",
            "label": "Candidate remediation queue captures local evidence and reviewer follow-up tasks",
            "status": "pass"
            if candidate_remediation_queue.get("status") in {"ready", "clear"}
            and candidate_remediation_queue.get("mode") == "local_candidate_remediation_queue"
            else "warn"
            if candidate_remediation_queue
            else "warn",
            "details": (
                f"status={candidate_remediation_queue.get('status') or 'missing'}; "
                f"open={candidate_remediation_queue.get('open_count')}; "
                f"high={candidate_remediation_queue.get('high_count', candidate_remediation_queue.get('high_priority_count'))}; "
                f"medium={candidate_remediation_queue.get('medium_count', candidate_remediation_queue.get('medium_priority_count'))}; "
                f"types={candidate_remediation_queue.get('task_type_counts')}"
            ),
        },
        {
            "check_id": "candidate_remediation_history",
            "label": "Candidate remediation queue has a local immutable edit history",
            "status": "pass"
            if candidate_remediation_history.get("mode") == "local_candidate_remediation_queue_history"
            and candidate_remediation_history.get("status") in {"empty", "tracking"}
            else "warn"
            if candidate_remediation_history
            else "warn",
            "details": (
                f"status={candidate_remediation_history.get('status') or 'missing'}; "
                f"events={candidate_remediation_history.get('event_count')}; "
                f"project={candidate_remediation_history.get('project_name')}"
            ),
        },
        {
            "check_id": "candidate_remediation_workbench",
            "label": "Candidate remediation workbench has saved views and trend slices",
            "status": "pass"
            if int(candidate_remediation_queue.get("saved_view_count") or 0) > 0
            and int(candidate_remediation_queue.get("trend_row_count") or 0) > 0
            else "warn"
            if candidate_remediation_queue
            else "warn",
            "details": (
                f"saved_views={candidate_remediation_queue.get('saved_view_count')}; "
                f"trend_rows={candidate_remediation_queue.get('trend_row_count')}"
            ),
        },
        {
            "check_id": "candidate_remediation_batch_actions",
            "label": "Native remediation workbench supports audited batch assign and postpone",
            "status": "pass"
            if native_ui_quality.get("candidate_remediation_batch_assign_supported") is True
            and native_ui_quality.get("candidate_remediation_batch_postpone_supported") is True
            else "warn",
            "details": (
                f"assign={native_ui_quality.get('candidate_remediation_batch_assign_supported')}; "
                f"postpone={native_ui_quality.get('candidate_remediation_batch_postpone_supported')}; "
                f"history={candidate_remediation_history.get('status') or 'missing'}"
            ),
        },
        {
            "check_id": "review_remediation_queue",
            "label": "Review remediation queue captures local evidence, reviewer, decision QA, and lineage follow-up tasks",
            "status": "pass"
            if review_remediation_queue.get("status") in {"ready", "clear"}
            and review_remediation_queue.get("mode") in {"review_remediation_queue", "local_candidate_remediation_queue"}
            else "warn"
            if review_remediation_queue
            else "warn",
            "details": (
                f"status={review_remediation_queue.get('status') or 'missing'}; "
                f"open={review_remediation_queue.get('open_count')}; "
                f"high={review_remediation_queue.get('high_count', review_remediation_queue.get('high_priority_count'))}; "
                f"medium={review_remediation_queue.get('medium_count', review_remediation_queue.get('medium_priority_count'))}; "
                f"types={review_remediation_queue.get('task_type_counts')}"
            ),
        },
        {
            "check_id": "candidate_review_ops_console",
            "label": "Candidate review ops console merges review, risk, owner, and remediation queues",
            "status": "pass"
            if candidate_review_ops_console.get("status") == "ready"
            and candidate_review_ops_console.get("mode") == "candidate_review_ops_console"
            else "warn"
            if candidate_review_ops_console
            else "warn",
            "details": (
                f"status={candidate_review_ops_console.get('status') or 'missing'}; "
                f"rows={candidate_review_ops_console.get('row_count')}; "
                f"open={candidate_review_ops_console.get('open_task_count')}; "
                f"overdue={candidate_review_ops_console.get('overdue_task_count')}; "
                f"lanes={candidate_review_ops_console.get('lane_counts')}"
            ),
        },
        {
            "check_id": "review_closure_workbench",
            "label": "Review closure workbench has batch groups, reason taxonomy, due policy, and filtered audit history",
            "status": "pass"
            if review_closure_workbench.get("status") in {"ready", "empty"}
            and review_closure_workbench.get("mode") == "review_closure_workbench"
            else "warn"
            if review_closure_workbench
            else "warn",
            "details": (
                f"status={review_closure_workbench.get('status') or 'missing'}; "
                f"open={review_closure_workbench.get('open_count')}; "
                f"overdue={review_closure_workbench.get('overdue_count')}; "
                f"reasons={review_closure_workbench.get('reason_taxonomy_count')}; "
                f"audit={review_closure_workbench.get('filtered_audit_event_count')}"
            ),
        },
        {
            "check_id": "review_closure_filter_views",
            "label": "Review closure filter views expose owner/reason/overdue/audit batch navigation",
            "status": "pass"
            if review_closure_filter_views.get("status") in {"ready", "empty"}
            and review_closure_filter_views.get("mode") == "review_closure_filter_views"
            else "warn",
            "details": (
                f"status={review_closure_filter_views.get('status') or 'missing'}; "
                f"views={review_closure_filter_views.get('row_count')}; "
                f"tasks={review_closure_filter_views.get('task_row_count')}; "
                f"filters={review_closure_filter_views.get('available_filters')}"
            ),
        },
        {
            "check_id": "baseline_history_explorer",
            "label": "Baseline history explorer lists saved baselines and recent comparisons",
            "status": "pass"
            if baseline_history_explorer.get("status") == "ready"
            and baseline_history_explorer.get("mode") == "candidate_baseline_history_explorer"
            else "warn"
            if baseline_history_explorer
            else "warn",
            "details": (
                f"status={baseline_history_explorer.get('status') or 'missing'}; "
                f"baselines={baseline_history_explorer.get('baseline_count')}; "
                f"comparisons={baseline_history_explorer.get('comparison_count')}; "
                f"rows={baseline_history_explorer.get('row_count')}"
            ),
        },
        {
            "check_id": "baseline_scenario_board",
            "label": "Baseline scenario board compares active, candidate, and policy/profile movement",
            "status": "pass"
            if baseline_scenario_board.get("status") == "ready"
            and baseline_scenario_board.get("mode") == "baseline_scenario_board"
            else "warn"
            if baseline_scenario_board
            else "warn",
            "details": (
                f"status={baseline_scenario_board.get('status') or 'missing'}; "
                f"rows={baseline_scenario_board.get('row_count')}; "
                f"attention={baseline_scenario_board.get('attention_count')}"
            ),
        },
        {
            "check_id": "baseline_whatif_board",
            "label": "Baseline what-if board exposes per-candidate rank/score movement by scenario",
            "status": "pass"
            if baseline_whatif_board.get("status") == "ready"
            and baseline_whatif_board.get("mode") == "baseline_whatif_board"
            and int(baseline_whatif_board.get("scenario_count") or 0) >= 4
            else "warn"
            if baseline_whatif_board
            else "warn",
            "details": (
                f"status={baseline_whatif_board.get('status') or 'missing'}; "
                f"rows={baseline_whatif_board.get('row_count')}; "
                f"scenarios={baseline_whatif_board.get('scenario_count')}; "
                f"review={baseline_whatif_board.get('review_required_count')}"
            ),
        },
        {
            "check_id": "baseline_history_charts",
            "label": "Baseline history explorer emits native-readable movement charts",
            "status": "pass"
            if int(baseline_history_explorer.get("chart_count") or 0) > 0
            and any(_artifact_exists(root_path, row.get("preview_path") or row.get("image_path") or row.get("chart_path")) for row in baseline_history_explorer.get("chart_rows") or [])
            else "warn"
            if baseline_history_explorer
            else "warn",
            "details": (
                f"charts={baseline_history_explorer.get('chart_count')}; "
                f"rows={len(baseline_history_explorer.get('chart_rows') or [])}"
            ),
        },
        {
            "check_id": "baseline_active_preview",
            "label": "Baseline workflow includes active preview, matrix, and rollback explanation",
            "status": "pass"
            if (baseline_history_explorer.get("active_preview") or {}).get("status") == "ready"
            and int(baseline_history_explorer.get("matrix_row_count") or 0) >= 0
            and "rollback_rows" in baseline_history_explorer
            else "warn"
            if baseline_history_explorer
            else "warn",
            "details": (
                f"active={baseline_history_explorer.get('active_baseline_id')}; "
                f"matrix={baseline_history_explorer.get('matrix_row_count')}; "
                f"rollback={baseline_history_explorer.get('rollback_option_count')}"
            ),
        },
        {
            "check_id": "baseline_lineage_history",
            "label": "Baseline lineage history tracks local baseline comparison movement over time",
            "status": "pass"
            if baseline_lineage_history.get("status") in {"tracking", "ready"}
            and baseline_lineage_history.get("mode") in {"baseline_lineage_history", "candidate_baseline_history_explorer"}
            else "warn"
            if baseline_lineage_history
            else "warn",
            "details": (
                f"status={baseline_lineage_history.get('status') or 'missing'}; "
                f"rows={baseline_lineage_history.get('row_count')}; "
                f"latest_movement={baseline_lineage_history.get('latest_movement_row_count')}"
            ),
        },
        {
            "check_id": "baseline_lineage_preview",
            "label": "Baseline lineage preview renders movement chart and top-mover rows",
            "status": "pass"
            if baseline_lineage_preview.get("status") in {"ready", "empty"}
            and baseline_lineage_preview.get("mode") == "baseline_lineage_preview"
            else "warn"
            if baseline_lineage_preview
            else "warn",
            "details": (
                f"status={baseline_lineage_preview.get('status') or 'missing'}; "
                f"rows={baseline_lineage_preview.get('row_count')}; "
                f"chart_points={baseline_lineage_preview.get('chart_point_count')}; "
                f"pairwise={baseline_lineage_preview.get('pairwise_row_count')}; "
                f"preview={baseline_lineage_preview.get('preview_available')}"
            ),
        },
        {
            "check_id": "baseline_lineage_filter_views",
            "label": "Baseline lineage filter views expose movement drill-down filters",
            "status": "pass"
            if baseline_lineage_filter_views.get("status") in {"ready", "empty"}
            and baseline_lineage_filter_views.get("mode") == "baseline_lineage_filter_views"
            else "warn",
            "details": (
                f"status={baseline_lineage_filter_views.get('status') or 'missing'}; "
                f"views={baseline_lineage_filter_views.get('row_count')}; "
                f"preview_rows={baseline_lineage_filter_views.get('preview_row_count')}; "
                f"filters={baseline_lineage_filter_views.get('available_filters')}"
            ),
        },
        {
            "check_id": "governance_only_source_expansion_guard",
            "label": "Advanced candidate review stays local-only with external operational workflows blocked",
            "status": "pass"
            if {"procurement", "supplier_purchase", "real_experiment_feedback_auto_import"}.issubset(
                set(candidate_remediation_queue.get("blocked_scopes") or [])
                | set(baseline_history_explorer.get("blocked_scopes") or [])
                | set(candidate_explanation_panel.get("blocked_scopes") or [])
                | set(source_expansion_governance.get("blocked_scopes") or [])
                | set(site_detection_confidence.get("blocked_scopes") or [])
                | set(baseline_whatif_board.get("blocked_scopes") or [])
                | set(candidate_review_ops_console.get("blocked_scopes") or [])
                | set(substituent_version_diff_browser.get("blocked_scopes") or [])
            )
            else "warn",
            "details": "external_operational_workflows_blocked=True; local_review_guard=active",
        },
        {
            "check_id": "site_detection_regression",
            "label": "Site detection regression covers soft spots and false-positive guards",
            "status": "pass"
            if site_detection_regression.get("status") == "pass"
            and site_detection_regression.get("mode") == "site_detection_regression"
            and int(site_detection_regression.get("coverage_fail_count") or 0) == 0
            else "warn"
            if site_detection_regression
            else "warn",
            "details": (
                f"rows={site_detection_regression.get('row_count')}; "
                f"failures={site_detection_regression.get('fail_count')}; "
                f"coverage_fail={site_detection_regression.get('coverage_fail_count')}; "
                f"project_samples={site_detection_regression.get('project_sample_count')}; "
                f"classes={site_detection_regression.get('site_classes_under_test')}"
            ),
        },
        {
            "check_id": "substituent_version_diff_browser",
            "label": "Substituent version diff browser links review status and candidate impact",
            "status": "pass"
            if substituent_version_diff_browser.get("status") == "ready"
            and substituent_version_diff_browser.get("mode") == "substituent_version_diff_browser"
            and int(substituent_version_diff_browser.get("row_count") or 0) > 0
            else "warn"
            if substituent_version_diff_browser
            else "warn",
            "details": (
                f"status={substituent_version_diff_browser.get('status') or 'missing'}; "
                f"rows={substituent_version_diff_browser.get('row_count')}; "
                f"linked={substituent_version_diff_browser.get('linked_substituent_count')}; "
                f"attention={substituent_version_diff_browser.get('candidate_attention_substituent_count')}"
            ),
        },
        {
            "check_id": "operator_trend_summary",
            "label": "Operator trend summary rolls up backlog, baseline, DB, and packet movement",
            "status": "pass"
            if operator_trend_summary.get("status") == "ready"
            and operator_trend_summary.get("mode") == "operator_trend_summary"
            else "warn"
            if operator_trend_summary
            else "warn",
            "details": (
                f"status={operator_trend_summary.get('status') or 'missing'}; "
                f"cards={operator_trend_summary.get('card_count')}; "
                f"needs_attention={operator_trend_summary.get('needs_attention_count')}"
            ),
        },
        {
            "check_id": "operator_trend_charts",
            "label": "Operator trend charts are generated for native review",
            "status": "pass"
            if operator_trend_charts.get("status") == "ready"
            and operator_trend_charts.get("mode") == "operator_trend_chart_pack"
            else "warn"
            if operator_trend_charts
            else "warn",
            "details": (
                f"status={operator_trend_charts.get('status') or 'missing'}; "
                f"charts={operator_trend_charts.get('chart_count')}; "
                f"dir={operator_trend_charts.get('chart_dir')}"
            ),
        },
        {
            "check_id": "medchem_discussion_handoff",
            "label": "Medchem discussion handoff stays local-only and separate from external operational workflows",
            "status": "pass"
            if medchem_discussion_handoff.get("status") == "ready"
            and medchem_discussion_handoff.get("mode") == "medchem_discussion_handoff"
            else "warn"
            if medchem_discussion_handoff
            else "warn",
            "details": (
                f"status={medchem_discussion_handoff.get('status') or 'missing'}; "
                f"rows={medchem_discussion_handoff.get('row_count')}; "
                "external_operational_workflows_blocked=True"
            ),
        },
        {
            "check_id": "native_ui_regression_snapshot",
            "label": "Native UI regression snapshot covers quality, schema, package, and DB checks",
            "status": "pass"
            if native_ui_regression.get("status") == "pass"
            else "warn"
            if native_ui_regression
            else "warn",
            "details": (
                f"status={native_ui_regression.get('status') or 'missing'}; "
                f"checks={len(native_ui_regression.get('checks') or [])}; "
                f"project={native_ui_regression.get('project_name')}"
            ),
        },
        {
            "check_id": "native_portable_package",
            "label": "Native portable package manifest is available",
            "status": "pass"
            if native_portable_package.get("status") == "ready"
            and native_portable_package.get("external_python_required_for_pipeline_actions") is True
            else "warn"
            if native_portable_package
            else "warn",
            "details": (
                f"status={native_portable_package.get('status') or 'missing'}; "
                f"files={native_portable_package.get('copied_file_count')}; "
                f"zip_bytes={native_portable_package.get('zip_size_bytes')}"
            ),
        },
        {
            "check_id": "profile_rollback_history",
            "label": "Profile rollback history compares current, freeze, and iteration snapshots",
            "status": "pass" if rollback_history.get("status") in {"ready", "empty"} else "warn" if rollback_history else "fail",
            "details": (
                f"status={rollback_history.get('status') or 'missing'}; snapshots={rollback_history.get('snapshot_count')}; "
                f"candidate_history={rollback_history.get('candidate_history_count')}"
            ),
        },
        {
            "check_id": "profile_rollback_snapshot_compare",
            "label": "Profile rollback snapshot drift comparison is available",
            "status": "pass"
            if rollback_snapshot_compare.get("status") == "compared"
            else "warn"
            if rollback_snapshot_compare.get("status") == "insufficient_snapshots"
            else "fail",
            "details": (
                f"status={rollback_snapshot_compare.get('status') or 'missing'}; "
                f"base={rollback_snapshot_compare.get('base_snapshot_id')}; head={rollback_snapshot_compare.get('head_snapshot_id')}; "
                f"changed={rollback_snapshot_compare.get('changed_candidate_count')}; added={rollback_snapshot_compare.get('added_candidate_count')}; "
                f"removed={rollback_snapshot_compare.get('removed_candidate_count')}"
            ),
        },
        {
            "check_id": "project_memory_refresh",
            "label": "One-command project memory refresh has run",
            "status": "pass" if project_memory_refresh.get("status") == "pass" else "warn",
            "details": (
                f"status={project_memory_refresh.get('status') or 'missing'}; "
                f"passed={project_memory_refresh.get('passed_step_count')}; failed={project_memory_refresh.get('failed_step_count')}"
            ),
        },
    ]
    status = "fail" if any(item["status"] == "fail" for item in checks) else "warn" if any(item["status"] == "warn" for item in checks) else "pass"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "checks": checks,
        "data_currency": {
            "last_maintenance_at": maintenance.get("created_at"),
            "alert_level": alert.get("alert_level"),
            "ring_next_offset": ring_status.get("next_offset"),
            "ring_progress_percent": ring_status.get("progress_percent"),
            "strict_quality_ok": quality.get("ok"),
            "data_foundation_gate": gate.get("status"),
            "closed_loop_acceptance": closed_loop_acceptance.get("status"),
            "closed_loop_promotion_gate": promotion_status,
            "profile_ab_matrix_cache_hits": cache_hits,
            "public_sar_candidate_linked": public_sar_validation.get("candidate_linked_count"),
            "assay_triage_lineage_groups": assay_triage.get("lineage_group_count"),
            "candidate_evidence_priority_status": candidate_priority.get("status"),
            "freeze_rollback_drill": rollback_drill.get("status"),
            "profile_rollback_replay": rollback_replay.get("status"),
            "public_sar_contradiction_triage": contradiction_triage.get("status"),
            "public_sar_contradiction_resolution_batch": sar_resolution_batch.get("status"),
            "public_sar_contradiction_watchlist": sar_watchlist.get("status"),
            "evidence_value_report": evidence_value.get("status"),
            "measurement_feedback_plan": measurement_feedback.get("status"),
            "measurement_feedback_import": measurement_feedback_import.get("status"),
            "measurement_feedback_gap_closure": measurement_gap_closure.get("status"),
            "measurement_gap_exact_result_intake": measurement_gap_exact_intake.get("status"),
            "measurement_gap_endpoint_governance": measurement_gap_endpoint_governance.get("status"),
            "site_class_policy_pack": site_class_policy_pack.get("status"),
            "evidence_value_calibration": evidence_value_calibration.get("status"),
            "evidence_value_policy_proposal": evidence_value_policy_proposal.get("status"),
            "evidence_value_policy_replay": evidence_value_policy_replay.get("status"),
            "evidence_value_policy_activation": evidence_value_policy_activation.get("status"),
            "evidence_value_policy_active": evidence_value_policy_active.get("policy_version"),
            "evidence_value_policy_active_compare": evidence_value_policy_active_compare.get("status"),
            "profile_impact_review_queue": profile_impact_review.get("status"),
            "project_memory_review_queue": project_memory_review_queue.get("status"),
            "project_memory_review_dashboard": project_memory_review_dashboard.get("status"),
            "promotion_readiness_packet": promotion_readiness_packet.get("status"),
            "promotion_readiness_score": promotion_readiness_packet.get("readiness_score"),
            "native_ui_quality": native_ui_quality.get("status"),
            "local_db_health": local_db_health.get("status"),
            "local_db_maintenance": local_db_maintenance.get("status"),
            "local_db_maintenance_release_gate": local_db_maintenance_release_gate.get("status"),
            "local_db_maintenance_release_stop_count": local_db_maintenance_release_gate.get("release_stop_count"),
            "local_db_maintenance_watch_count": local_db_maintenance_release_gate.get("watch_count"),
            "local_db_maintenance_trend": local_db_maintenance_trend.get("status"),
            "local_db_maintenance_trend_rows": local_db_maintenance_trend.get("row_count"),
            "candidate_visual_compare": candidate_visual_compare.get("status"),
            "candidate_visual_compare_rows": candidate_visual_compare.get("candidate_count"),
            "candidate_visual_compare_alignment": candidate_visual_compare.get("alignment_status"),
            "candidate_review_packet": candidate_review_packet.get("status"),
            "candidate_review_pending": candidate_review_packet.get("review_required_count"),
            "candidate_review_board": candidate_review_board.get("status"),
            "candidate_review_board_pending": candidate_review_board.get("pending_local_review_count"),
            "candidate_review_analytics": candidate_review_analytics.get("status"),
            "candidate_review_analytics_pending": candidate_review_analytics.get("pending_backlog_count"),
            "candidate_review_analytics_risks": candidate_review_analytics.get("repeated_risk_bucket_count"),
            "candidate_drilldown_packet": candidate_drilldown_packet.get("status"),
            "candidate_drilldown_rows": candidate_drilldown_packet.get("row_count"),
            "local_governance_diff": local_governance_diff.get("status"),
            "local_governance_diff_changed": local_governance_diff.get("changed_candidate_count"),
            "named_governance_baselines": governance_baselines.get("status"),
            "named_governance_baseline_count": governance_baselines.get("baseline_count") or len(governance_baselines.get("baselines") or []),
            "candidate_baseline_compare": candidate_baseline_compare.get("status"),
            "candidate_baseline_changed": candidate_baseline_compare.get("changed_candidate_count"),
            "candidate_decision_packet": candidate_decision_packet.get("status"),
            "candidate_decision_count": candidate_decision_packet.get("decision_count"),
            "candidate_decision_counts": candidate_decision_packet.get("decision_counts"),
            "candidate_evidence_drawer": candidate_evidence_drawer.get("status"),
            "candidate_evidence_drawer_rows": candidate_evidence_drawer.get("row_count"),
            "candidate_explanation_panel": candidate_explanation_panel.get("status"),
            "candidate_explanation_panel_rows": candidate_explanation_panel.get("row_count"),
            "candidate_explanation_panel_remediation_linked": candidate_explanation_panel.get("remediation_linked_count"),
            "candidate_explanation_compare": candidate_explanation_compare.get("status"),
            "candidate_explanation_compare_stoplist": candidate_explanation_compare.get("stoplist_component_count"),
            "candidate_explanation_drilldown": candidate_explanation_drilldown.get("status"),
            "candidate_explanation_drilldown_attention": candidate_explanation_drilldown.get("attention_count"),
            "candidate_explanation_matrix": candidate_explanation_matrix.get("status"),
            "candidate_explanation_matrix_stoplist": candidate_explanation_matrix.get("stoplist_candidate_count"),
            "site_detection_confidence": site_detection_confidence.get("status"),
            "site_detection_confidence_low": site_detection_confidence.get("low_confidence_count"),
            "staged_feed_sandbox_scoring": staged_feed_sandbox_scoring.get("status"),
            "staged_feed_sandbox_staged_rows": staged_feed_sandbox_scoring.get("staged_row_count"),
            "sandbox_score_delta_review_packet": sandbox_score_delta_review.get("status"),
            "sandbox_score_delta_review_required": sandbox_score_delta_review.get("operator_signoff_required_count"),
            "sandbox_score_delta_signoff_ledger": sandbox_score_delta_signoff.get("status"),
            "sandbox_score_delta_signoff_pending": sandbox_score_delta_signoff.get("pending_signoff_count"),
            "staging_sandbox_filter_views": staging_sandbox_filter_views.get("status"),
            "staging_sandbox_filter_view_rows": staging_sandbox_filter_views.get("row_count"),
            "native_drilldown_actions": native_drilldown_actions.get("status"),
            "native_drilldown_actions_routes": native_drilldown_actions.get("route_supported_count"),
            "native_drilldown_actions_direct": native_drilldown_actions.get("direct_action_supported_count"),
            "candidate_decision_qa": candidate_decision_qa.get("status"),
            "candidate_decision_qa_attention": candidate_decision_qa.get("attention_count"),
            "evidence_quality_scorecard": evidence_quality_scorecard.get("status"),
            "evidence_quality_scorecard_attention": evidence_quality_scorecard.get("attention_count"),
            "candidate_evidence_quality": candidate_evidence_quality.get("status"),
            "candidate_evidence_quality_attention": candidate_evidence_quality.get("attention_count"),
            "candidate_baseline_manager": candidate_baseline_manager.get("status"),
            "candidate_baseline_archive_review": candidate_baseline_manager.get("archive_review_count"),
            "reviewer_operations": reviewer_operations.get("status"),
            "reviewer_operations_overdue": reviewer_operations.get("pending_overdue_count"),
            "baseline_lineage_compare": baseline_lineage_compare.get("status"),
            "baseline_lineage_compare_changed": baseline_lineage_compare.get("changed_candidate_count"),
            "candidate_baseline_lineage": candidate_baseline_lineage.get("status"),
            "candidate_baseline_lineage_changed": candidate_baseline_lineage.get("changed_count", candidate_baseline_lineage.get("changed_candidate_count")),
            "review_command_center": review_command_center.get("status"),
            "review_command_center_actionable": review_command_center.get("actionable_count"),
            "candidate_remediation_queue": candidate_remediation_queue.get("status"),
            "candidate_remediation_open": candidate_remediation_queue.get("open_count"),
            "review_remediation_queue": review_remediation_queue.get("status"),
            "review_remediation_open": review_remediation_queue.get("open_count"),
            "candidate_review_ops_console": candidate_review_ops_console.get("status"),
            "candidate_review_ops_open": candidate_review_ops_console.get("open_task_count"),
            "review_closure_workbench": review_closure_workbench.get("status"),
            "review_closure_workbench_overdue": review_closure_workbench.get("overdue_count"),
            "review_closure_filter_views": review_closure_filter_views.get("status"),
            "review_closure_filter_views_count": review_closure_filter_views.get("row_count"),
            "baseline_history_explorer": baseline_history_explorer.get("status"),
            "baseline_history_comparisons": baseline_history_explorer.get("comparison_count"),
            "baseline_scenario_board": baseline_scenario_board.get("status"),
            "baseline_scenario_attention": baseline_scenario_board.get("attention_count"),
            "baseline_whatif_board": baseline_whatif_board.get("status"),
            "baseline_whatif_review": baseline_whatif_board.get("review_required_count"),
            "baseline_lineage_history": baseline_lineage_history.get("status"),
            "baseline_lineage_history_rows": baseline_lineage_history.get("row_count"),
            "baseline_lineage_preview": baseline_lineage_preview.get("status"),
            "baseline_lineage_preview_pairwise": baseline_lineage_preview.get("pairwise_row_count"),
            "baseline_lineage_filter_views": baseline_lineage_filter_views.get("status"),
            "baseline_lineage_filter_views_count": baseline_lineage_filter_views.get("row_count"),
            "operator_trend_summary": operator_trend_summary.get("status"),
            "operator_trend_needs_attention": operator_trend_summary.get("needs_attention_count"),
            "operator_trend_charts": operator_trend_charts.get("status"),
            "operator_trend_chart_count": operator_trend_charts.get("chart_count"),
            "medchem_discussion_handoff": medchem_discussion_handoff.get("status"),
            "medchem_discussion_handoff_rows": medchem_discussion_handoff.get("row_count"),
            "native_ui_regression_snapshot": native_ui_regression.get("status"),
            "native_portable_package": native_portable_package.get("status"),
            "profile_rollback_history": rollback_history.get("status"),
            "profile_rollback_snapshot_compare": rollback_snapshot_compare.get("status"),
            "project_memory_refresh": project_memory_refresh.get("status"),
            "rgroup_feed_created_at": rgroup_feed_metadata.get("created_at"),
            "rgroup_feed_count": rgroup_feed_metadata.get("feed_count"),
            "rgroup_feed_row_count": rgroup_feed_metadata.get("row_count"),
            "rgroup_feed_freshness_issues": freshness_issue_count,
            "rgroup_feed_allowlist_issues": allowlist_issue_count,
            "rgroup_review_coverage_cells": rgroup_review_coverage.get("coverage_cell_count"),
            "rgroup_review_no_review_cells": no_review_coverage,
            "rgroup_review_low_coverage_cells": low_review_coverage,
            "feed_absorption_audit": feed_absorption_audit.get("status"),
            "feed_absorption_audit_blockers": feed_absorption_audit.get("blocker_count"),
            "feed_absorption_audit_warnings": feed_absorption_audit.get("warning_count"),
            "feed_absorption_diff_navigator": feed_absorption_diff.get("status"),
            "feed_absorption_diff_navigator_blockers": feed_absorption_diff.get("blocker_count"),
            "source_expansion_governance": source_expansion_governance.get("status"),
            "source_expansion_governance_blocked": source_expansion_governance.get("blocked_gate_count"),
            "feed_promotion_simulator": feed_promotion_simulator.get("status"),
            "feed_promotion_simulator_blockers": feed_promotion_simulator.get("blocker_count"),
            "rgroup_staging_quality_budget": staging_quality_budget.get("status"),
            "rgroup_staging_quality_budget_blockers": staging_quality_budget.get("blocker_count"),
            "rgroup_feed_digestion_ledger": rgroup_feed_digestion_ledger.get("status"),
            "rgroup_feed_digestion_rows": rgroup_feed_digestion_ledger.get("row_count"),
            "rgroup_promotion_approval_ledger": rgroup_promotion_approval_ledger.get("status"),
            "rgroup_promotion_approval_pending": rgroup_promotion_approval_ledger.get("pending_approval_count"),
            "rgroup_promotion_allowed": rgroup_promotion_approval_ledger.get("promotion_allowed"),
            "rgroup_selective_approval_batch": rgroup_selective_approval_batch.get("status"),
            "rgroup_selective_approval_approved": rgroup_selective_approval_batch.get("positive_control_approved_count"),
            "rgroup_selective_approval_holdout": rgroup_selective_approval_batch.get("holdout_count"),
            "rgroup_digestion_quality_metrics": rgroup_digestion_quality_metrics.get("status"),
            "rgroup_digestion_quality_watch": (rgroup_digestion_quality_metrics.get("quality_status_counts") or {}).get("watch"),
            "rgroup_digestion_quality_closure_queue": rgroup_digestion_quality_closure_queue.get("status"),
            "rgroup_digestion_quality_closure_open": rgroup_digestion_quality_closure_queue.get("open_count"),
            "feed_promotion_rollback_audit": feed_promotion_rollback_audit.get("status"),
            "feed_promotion_rollback_ready": feed_promotion_rollback_audit.get("ready_count"),
            "rgroup_approval_workbench": rgroup_approval_workbench.get("status"),
            "rgroup_approval_workbench_rows": rgroup_approval_workbench.get("row_count"),
            "rgroup_ring_context_alignment": rgroup_ring_context_alignment.get("status"),
            "rgroup_ring_context_ring_rows": rgroup_ring_context_alignment.get("ring_replacement_count"),
            "rgroup_digestion_quality_closure_ledger": rgroup_digestion_quality_closure_ledger.get("status"),
            "rgroup_digestion_quality_closure_closed": rgroup_digestion_quality_closure_ledger.get("closed_count"),
            "rgroup_approval_workbench_decisions": rgroup_approval_workbench_decisions.get("status"),
            "rgroup_approval_workbench_decisions_approved": rgroup_approval_workbench_decisions.get("approved_rehearsal_count"),
            "rgroup_guarded_promotion_rehearsal": rgroup_guarded_promotion_rehearsal.get("status"),
            "rgroup_guarded_promotion_rehearsal_ready": rgroup_guarded_promotion_rehearsal.get("ready_count"),
            "ring_rgroup_axis_governance": ring_rgroup_axis_governance.get("status"),
            "ring_rgroup_axis_governance_axes": ring_rgroup_axis_governance.get("axis_count"),
            "rgroup_next_expansion_batch_plan": rgroup_next_expansion_batch_plan.get("status"),
            "rgroup_next_expansion_batch_plan_cap": rgroup_next_expansion_batch_plan.get("planned_staging_cap_total"),
            "rgroup_approval_trend_views": rgroup_approval_trend_views.get("status"),
            "rgroup_approval_trend_views_attention": rgroup_approval_trend_views.get("needs_attention_count"),
            "governed_ingestion_batches": governed_ingestion_batches.get("status"),
            "governed_ingestion_batches_blocked": governed_ingestion_batches.get("blocked_batch_count"),
            "substituent_version_diff_browser": substituent_version_diff_browser.get("status"),
            "substituent_version_diff_linked": substituent_version_diff_browser.get("linked_substituent_count"),
            "rgroup_pair_contradictions": rgroup_pair_contradictions.get("status"),
            "rgroup_pair_contradiction_rows": rgroup_pair_contradictions.get("row_count"),
            "rgroup_pair_contradiction_high_priority": rgroup_pair_contradictions.get("high_priority_count"),
            "rgroup_pair_contradiction_decisions": rgroup_pair_decisions.get("status"),
            "rgroup_pair_contradiction_open_high": pair_open_high_count,
            "rgroup_pair_deferred_source_review": pair_deferred_source_review_count,
            "rgroup_pair_pending_owner_review": pair_pending_owner_review_count,
            "rgroup_pair_owner_decision_ledger": rgroup_pair_owner_ledger.get("status"),
            "rgroup_pair_owner_decision_pending": owner_ledger_pending_count,
            "rgroup_feed_onboarding_gate": rgroup_feed_onboarding.get("status"),
            "rgroup_feed_onboarding_unmanifested": rgroup_feed_onboarding.get("unmanifested_file_count"),
            "rgroup_next_feed_drop_staging": rgroup_feed_staging.get("status"),
            "rgroup_next_feed_drop_templates": rgroup_feed_staging.get("template_file_count"),
            "rgroup_next_feed_drop_staging_gate": rgroup_feed_staging_gate.get("status"),
            "rgroup_next_feed_drop_staged_rows": rgroup_feed_staging_gate.get("staged_row_count"),
            "ring_outcome_overlay_activation": ring_overlay_activation.get("status"),
            "ring_outcome_overlay_active_nonzero": ring_overlay_activation.get("active_nonzero_context_count"),
            "ring_outcome_production_readiness": ring_outcome_readiness.get("status"),
            "ring_outcome_importable_results": ring_outcome_readiness.get("importable_result_count"),
            "ring_outcome_result_package": ring_outcome_result_package.get("status"),
            "ring_outcome_result_package_rows": ring_outcome_result_package.get("result_row_count"),
            "ring_outcome_holdout": ring_outcome_holdout.get("status"),
            "production_mode": production_mode,
        },
    }


def render_release_smoke_markdown(report: dict) -> str:
    lines = [
        "# LocalMedChem Release Smoke Checklist",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Overall status: `{report.get('status')}`",
        "",
        "## Data Currency",
        "",
    ]
    for key, value in (report.get("data_currency") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Checks", "", "| Check | Status | Details |", "| --- | --- | --- |"])
    for item in report.get("checks") or []:
        lines.append(f"| {item.get('label')} | `{item.get('status')}` | {item.get('details')} |")
    lines.extend(
        [
            "",
            "## Manual Smoke Steps",
            "",
            "1. Start the native shell with `python run_native_ui.py` or `AutoMedChemist.exe` and confirm the desktop window opens.",
            "2. Detect sites for `COc1ccc(Cl)cc1` and confirm the high-DPI molecule preview renders crisply.",
            "3. Generate candidates with `increase_polarity`, then confirm filter, score sort, row detail, score columns, site-class guidance, and CSV/SDF exports render.",
            "4. Open Project Memory and confirm lane dashboard, batch assign/close/defer actions, and reviewer history load.",
            "5. Open Governance/Readiness and verify endpoint site-class governance, promotion readiness packet, drill-down, and freeze package actions are visible.",
            "6. Keep Streamlit only as a legacy/developer path; the user-facing smoke path is the native shell.",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def write_release_smoke_checklist(report: dict, *, json_path: str | Path, markdown_path: str | Path) -> None:
    json_file = Path(json_path)
    md_file = Path(markdown_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_file.write_text(render_release_smoke_markdown(report), encoding="utf-8")
