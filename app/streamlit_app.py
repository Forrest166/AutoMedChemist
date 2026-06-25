from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.chemistry import calculate_descriptors, standardize_molecule  # noqa: E402
from localmedchem.analog_series import (  # noqa: E402
    build_analog_series_report,
    build_queue_analog_series_delta,
    calibrate_queue_analog_series_policy,
    load_queue_analog_series_policy_document,
    rollback_queue_analog_series_policy,
    write_analog_series_report,
    write_queue_analog_series_delta_report,
    write_queue_analog_series_policy,
)
from localmedchem.batch_design import build_route_batches, route_batch_summary  # noqa: E402
from localmedchem.calibration import calibrate_project_models, save_calibration_report, write_calibration_profiles  # noqa: E402
from localmedchem.candidate_filters import apply_candidate_filters, candidate_filter_options  # noqa: E402
from localmedchem.data_foundation import build_data_foundation_report, save_data_foundation_report  # noqa: E402
from localmedchem.database import query_ring_systems, record_candidate_promotion, update_candidate_status  # noqa: E402
from localmedchem.assay_learning import build_assay_learning_report  # noqa: E402
from localmedchem.decision_packet import (  # noqa: E402
    PACKET_REVIEW_STATUSES,
    build_decision_packet,
    build_decision_packet_retrospective,
    build_decision_strategy_learning_report,
    compare_decision_packets,
    decision_packet_csv_text,
    decision_packet_markdown,
    list_decision_packets,
    save_decision_packet,
    update_decision_packet_review,
)
from localmedchem.draw import mol_to_svg, smiles_to_svg  # noqa: E402
from localmedchem.experiment_tracking import import_experiment_results_rows, import_residual_experiment_results_rows, summarize_experiment_plans, upsert_experiment_plan_rows, validate_experiment_result_rows  # noqa: E402
from localmedchem.experiment_tracking import read_experiment_plan_csv, write_experiment_result_template  # noqa: E402
from localmedchem.residual_result_intake import build_residual_result_intake_manifest, write_residual_result_intake_manifest  # noqa: E402
from localmedchem.assay_event_triage import build_assay_event_triage_report, write_assay_event_triage_report  # noqa: E402
from localmedchem.assay_followup_results import (  # noqa: E402
    build_assay_followup_result_template,
    import_assay_followup_results_rows,
    write_assay_followup_import_report,
)
from localmedchem.candidate_evidence_priority import build_candidate_evidence_priority_report, write_candidate_evidence_priority_report  # noqa: E402
from localmedchem.evidence_value_scoring import (  # noqa: E402
    build_evidence_value_calibration_report,
    build_evidence_value_report,
    write_evidence_value_calibration_report,
    write_evidence_value_report,
)
from localmedchem.evidence_value_policy_proposal import (  # noqa: E402
    EVIDENCE_VALUE_POLICY_PROPOSAL_DECISIONS,
    activate_evidence_value_policy_proposal,
    build_evidence_value_policy_proposal,
    build_evidence_value_policy_replay,
    review_evidence_value_policy_proposal,
    write_evidence_value_policy_activation,
    write_evidence_value_policy_proposal,
    write_evidence_value_policy_replay,
)
from localmedchem.evidence_value_policy_active_compare import build_evidence_value_policy_active_compare, write_evidence_value_policy_active_compare  # noqa: E402
from localmedchem.export import rows_to_csv_text, rows_to_sdf_text  # noqa: E402
from localmedchem.functional_groups import load_functional_group_rules  # noqa: E402
from localmedchem.feedback import import_feedback_rows, summarize_project_feedback  # noqa: E402
from localmedchem.library import load_yaml_records  # noqa: E402
from localmedchem.pipeline import run_mvp  # noqa: E402
from localmedchem.priority_queue import (  # noqa: E402
    build_bulk_next_design_queue_decisions,
    build_next_design_queue_decision_quality_report,
    list_next_design_queue_decision_events,
    save_next_design_queue_decisions,
    write_next_design_queue_decision_quality_report,
)
from localmedchem.project_dashboard import build_project_closed_loop_dashboard, write_project_closed_loop_dashboard  # noqa: E402
from localmedchem.project_evidence_expansion_plan import (  # noqa: E402
    PROJECT_EVIDENCE_EXPANSION_STATUSES,
    build_project_evidence_expansion_plan,
    load_project_evidence_expansion_plan,
    update_project_evidence_expansion_task_status,
    write_project_evidence_expansion_plan,
)
from localmedchem.project_evidence_execution import execute_project_evidence_expansion_plan, write_project_evidence_execution_report  # noqa: E402
from localmedchem.project_evidence_pack import build_project_evidence_pack, write_project_evidence_pack  # noqa: E402
from localmedchem.profile_ab_replay import build_profile_ab_replay_report, write_profile_ab_replay_report  # noqa: E402
from localmedchem.profile_ab_matrix import build_profile_ab_replay_matrix, write_profile_ab_replay_matrix  # noqa: E402
from localmedchem.profile_ab_review import build_profile_ab_material_change_review, write_profile_ab_material_change_review  # noqa: E402
from localmedchem.profile_promotion_registry import build_profile_promotion_record, load_profile_promotion_registry, register_profile_promotion, update_profile_promotion_status  # noqa: E402
from localmedchem.promotion_freeze_package import build_profile_promotion_freeze_package  # noqa: E402
from localmedchem.promotion_freeze_approval import load_promotion_freeze_approvals, review_profile_promotion_freeze  # noqa: E402
from localmedchem.promotion_freeze_rollback_drill import build_profile_promotion_freeze_rollback_drill, write_profile_promotion_freeze_rollback_drill  # noqa: E402
from localmedchem.profile_rollback_history import (  # noqa: E402
    build_profile_rollback_history,
    compare_profile_rollback_snapshots,
    write_profile_rollback_history,
    write_profile_rollback_snapshot_compare,
)
from localmedchem.profile_promotion_rollback_replay import build_profile_promotion_rollback_replay, write_profile_promotion_rollback_replay  # noqa: E402
from localmedchem.measurement_feedback_plan import (  # noqa: E402
    build_measurement_gap_exact_result_intake,
    build_measurement_feedback_gap_closure,
    import_measurement_feedback_results_rows,
    build_measurement_feedback_plan,
    MEASUREMENT_GAP_DECISIONS,
    review_measurement_feedback_gap_closure,
    validate_measurement_feedback_result_rows,
    write_measurement_feedback_gap_closure,
    write_measurement_gap_exact_result_intake,
    write_measurement_feedback_import_report,
    write_measurement_feedback_plan,
)
from localmedchem.measurement_gap_endpoint_governance import build_measurement_gap_endpoint_governance, write_measurement_gap_endpoint_governance  # noqa: E402
from localmedchem.profile_impact_review import build_profile_impact_review_queue, write_profile_impact_review_queue  # noqa: E402
from localmedchem.project_memory_review_queue import (  # noqa: E402
    PROJECT_MEMORY_OPERATOR_STATUSES,
    apply_project_memory_review_batch,
    build_project_memory_review_dashboard,
    build_project_memory_review_queue,
    update_project_memory_review_item,
    write_project_memory_review_dashboard,
    write_project_memory_review_queue,
)
from localmedchem.project_memory_refresh import refresh_project_memory  # noqa: E402
from localmedchem.public_sar_contradiction_triage import (  # noqa: E402
    SAR_TRIAGE_RESOLUTIONS,
    SAR_TRIAGE_REVIEW_STATUSES,
    apply_public_sar_contradiction_resolution_batch,
    build_public_sar_contradiction_triage,
    build_public_sar_contradiction_watchlist,
    update_public_sar_contradiction_resolution,
    write_public_sar_contradiction_resolution_batch,
    write_public_sar_contradiction_watchlist,
    write_public_sar_contradiction_triage,
)
from localmedchem.public_sar_validation import build_public_sar_validation_report, write_public_sar_validation_report  # noqa: E402
from localmedchem.replay_validation import build_closed_loop_replay_report, write_closed_loop_replay_report  # noqa: E402
from localmedchem.iteration_package import (  # noqa: E402
    build_latest_iteration_comparison,
    build_next_design_iteration_package,
    latest_iteration_manifests,
    write_iteration_comparison_report,
)
from localmedchem.promotion_gate import build_closed_loop_promotion_gate, write_closed_loop_promotion_gate  # noqa: E402
from localmedchem.residual_profile_adjustments import build_residual_adjustment_review_template, write_residual_adjustment_reviews  # noqa: E402
from localmedchem.profiles import list_scoring_profiles  # noqa: E402
from localmedchem.promotion import load_candidate_from_db, promote_candidate_to_seed  # noqa: E402
from localmedchem.project_store import (  # noqa: E402
    DECISION_STATUSES,
    list_project_runs,
    load_project_candidates,
    load_project_route_batches,
    save_project_run,
    update_candidate_decision,
    update_route_batch_decision,
    ROUTE_BATCH_STATUSES,
)
from localmedchem.quality import validate_data_quality  # noqa: E402
from localmedchem.prospective import (  # noqa: E402
    build_experiment_plan,
    build_feedback_control_report,
    save_feedback_control_report,
    write_experiment_plan_csv,
)
from localmedchem.review import REVIEW_STATUSES, default_review_block, update_substituent_review  # noqa: E402
from localmedchem.review_batch import apply_review_backlog_batch, build_review_backlog_batch, write_review_backlog_batch  # noqa: E402
from localmedchem.rgroup_feed_review import (  # noqa: E402
    build_sample_review_coverage,
    bulk_update_sample_review_queue,
    filter_sample_review_queue,
    load_sample_review_queue,
    sample_review_row_key,
    summarize_sample_review_queue,
    write_sample_review_coverage_report,
)
from localmedchem.rgroup_pair_contradictions import (  # noqa: E402
    apply_rgroup_pair_contradiction_first_pass,
    build_rgroup_normalized_pair_contradiction_report,
    build_rgroup_pair_conflict_owner_decision_ledger,
    build_rgroup_pair_conflict_owner_review_packet,
    write_rgroup_normalized_pair_contradiction_report,
    write_rgroup_pair_conflict_owner_decision_ledger,
    write_rgroup_pair_conflict_owner_review_packet,
    write_rgroup_pair_contradiction_decision_summary,
)
from localmedchem.rgroup_feed_onboarding import (  # noqa: E402
    build_rgroup_feed_drop_staging_gate,
    build_rgroup_feed_drop_staging_package,
    build_rgroup_feed_onboarding_gate,
    write_rgroup_feed_drop_staging_gate,
    write_rgroup_feed_drop_staging_report,
    write_rgroup_feed_onboarding_gate,
)
from localmedchem.ring_search import ring_source_summary, search_ring_systems  # noqa: E402
from localmedchem.ring_import_status import build_ring_import_status  # noqa: E402
from localmedchem.ring_outcome_learning import build_ring_outcome_learning_report, write_ring_outcome_learning_report  # noqa: E402
from localmedchem.ring_outcome_overlay import (  # noqa: E402
    DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH,
    build_ring_outcome_overlay_review_template,
    build_ring_outcome_scoring_overlay,
    update_ring_outcome_overlay_review,
    write_ring_outcome_overlay_review_template,
    write_ring_outcome_scoring_overlay,
)
from localmedchem.ring_outcome_replay import build_ring_outcome_overlay_replay, write_ring_outcome_overlay_replay  # noqa: E402
from localmedchem.ring_outcome_holdout import build_ring_outcome_holdout_report, write_ring_outcome_holdout_report  # noqa: E402
from localmedchem.ring_outcome_readiness import (  # noqa: E402
    build_ring_outcome_production_readiness,
    build_ring_outcome_result_package,
    write_ring_outcome_production_readiness,
    write_ring_outcome_result_package,
)
from localmedchem.ring_outcome_tasks import build_ring_outcome_residual_tasks, merge_ring_outcome_tasks_into_registry, write_ring_outcome_residual_tasks  # noqa: E402
from localmedchem.evidence_views import candidate_evidence_examples, candidate_evidence_matrix, evidence_disagreement_summary  # noqa: E402
from localmedchem.evidence_confidence import (  # noqa: E402
    EVIDENCE_RESIDUAL_TASK_STATUSES,
    build_evidence_confidence_report,
    load_evidence_residual_task_registry,
    residual_tasks_to_experiment_plan,
    sync_evidence_residual_task_registry,
    update_evidence_residual_task_status,
    update_residual_tasks_from_experiment_plan,
    write_evidence_confidence_report,
    write_evidence_residual_task_registry,
)
from localmedchem.multi_objective import (  # noqa: E402
    calibrate_multi_objective_profile,
    write_multi_objective_calibration_report,
    write_multi_objective_profile,
)
from localmedchem.scaffold_calibration import (  # noqa: E402
    build_scaffold_calibration_audit_report,
    build_scaffold_rule_review_drafts,
    apply_scaffold_rule_review_drafts,
    bulk_update_scaffold_rule_review_draft_status,
    calibrate_scaffold_rules,
    load_scaffold_calibration_cases,
    load_scaffold_rule_review_drafts,
    load_scaffold_calibration_report,
    update_scaffold_rule_review_draft_status,
    write_scaffold_calibration_audit_report,
    write_scaffold_calibration_report,
    write_scaffold_rule_review_drafts,
)
from localmedchem.scaffold_replacements import load_scaffold_replacements  # noqa: E402
from localmedchem.scaffold_rule_review import (  # noqa: E402
    SCAFFOLD_RULE_RESOLUTION_STATUSES,
    SCAFFOLD_RULE_REVIEW_STATUSES,
    list_scaffold_rule_review_events,
    load_scaffold_rule_reviews,
    scaffold_rule_review_lookup,
    update_scaffold_rule_review,
)
from localmedchem.scoring import load_direction_rules  # noqa: E402
from localmedchem.scaffold_review_workspace import (  # noqa: E402
    append_workspace_examples_to_calibration_set,
    build_scaffold_review_workspace_report,
    write_scaffold_workspace_decision_template,
    write_scaffold_review_workspace_report,
)
from localmedchem.sites import detect_modification_sites  # noqa: E402
from localmedchem.transform_evidence import build_transform_evidence_report  # noqa: E402
from localmedchem.strategy_learning import compare_strategy_policy_effect  # noqa: E402
from localmedchem.data_foundation import data_currency_badge  # noqa: E402


DB_PATH = ROOT / "data" / "localmedchem.sqlite"
LIBRARY_PATH = ROOT / "data" / "substituents" / "core_substituent_library.yaml"
SEED_PATH = ROOT / "data" / "seeds" / "core_substituent_seed.yaml"
SEED_PATHS = [
    ROOT / "data" / "seeds" / "core_substituent_seed.yaml",
    ROOT / "data" / "seeds" / "pubchem_expansion_seed.yaml",
]
DIRECTION_RULES_PATH = ROOT / "data" / "rules" / "direction_rules.yaml"
FUNCTIONAL_RULES_PATH = ROOT / "data" / "rules" / "functional_group_replacements.yaml"
SCAFFOLD_RULES_PATH = ROOT / "data" / "rules" / "scaffold_replacements.yaml"
SCAFFOLD_RULE_REVIEWS_PATH = ROOT / "data" / "rules" / "scaffold_rule_reviews.yaml"
EVIDENCE_CONFIDENCE_REPORT_PATH = ROOT / "data" / "substituents" / "evidence_confidence_report.json"
SCAFFOLD_WORKSPACE_REPORT_PATH = ROOT / "data" / "substituents" / "scaffold_review_workspace_report.json"
ANALOG_SERIES_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "analog_series_report.json"
QUEUE_ANALOG_SERIES_DELTA_PATH = ROOT / "data" / "projects" / "closed_loop" / "queue_analog_series_delta.json"
QUEUE_ANALOG_SERIES_POLICY_PATH = ROOT / "data" / "rules" / "queue_analog_series_policy.yaml"
SCAFFOLD_CALIBRATION_SET_PATH = ROOT / "data" / "rules" / "scaffold_calibration_set.yaml"
SCAFFOLD_CALIBRATION_REPORT_PATH = ROOT / "data" / "substituents" / "scaffold_calibration_report.json"
SCAFFOLD_CALIBRATION_AUDIT_PATH = ROOT / "data" / "substituents" / "scaffold_calibration_audit_report.json"
SCAFFOLD_RULE_REVIEW_DRAFTS_PATH = ROOT / "data" / "substituents" / "scaffold_rule_review_drafts.csv"
EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH = ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"
RESIDUAL_EXPERIMENT_PLAN_PATH = ROOT / "data" / "projects" / "demo" / "residual_experiment_plan.csv"
RESIDUAL_EXPERIMENT_RESULTS_TEMPLATE_PATH = ROOT / "data" / "projects" / "demo" / "residual_experiment_results_template.csv"
RESIDUAL_RESULT_INTAKE_MANIFEST_PATH = ROOT / "data" / "projects" / "demo" / "residual_result_intake_manifest.json"
RESIDUAL_RESULT_INTAKE_MANIFEST_CSV_PATH = ROOT / "data" / "projects" / "demo" / "residual_result_intake_manifest.csv"
MULTI_OBJECTIVE_CALIBRATION_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "multi_objective_calibration_report.json"
MULTI_OBJECTIVE_CALIBRATED_PROFILE_PATH = ROOT / "data" / "profiles" / "calibrated" / "multi_objective_demo_learning.yaml"
TARGET_CONTEXT_PROFILES_PATH = ROOT / "data" / "rules" / "target_context_profiles.yaml"
PROJECT_CLOSED_LOOP_DASHBOARD_PATH = ROOT / "data" / "projects" / "demo" / "project_closed_loop_dashboard.json"
CLOSED_LOOP_REPLAY_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "closed_loop_replay_report.json"
ITERATION_COMPARISON_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "iteration_comparison_report.json"
CLOSED_LOOP_PROMOTION_GATE_PATH = ROOT / "data" / "projects" / "demo" / "closed_loop_promotion_gate.json"
PROJECT_EVIDENCE_PACK_PATH = ROOT / "data" / "projects" / "demo" / "project_evidence_pack.json"
PROJECT_EVIDENCE_PACK_SUMMARY_PATH = ROOT / "data" / "projects" / "demo" / "project_evidence_pack_summary.csv"
PROJECT_EVIDENCE_EXPANSION_PLAN_PATH = ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.json"
PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH = ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.csv"
PROJECT_EVIDENCE_EXECUTION_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "project_evidence_execution_report.json"
PUBLIC_SAR_VALIDATION_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_validation_report.json"
PUBLIC_SAR_VALIDATION_CSV_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_validation_report.csv"
PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.json"
PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.csv"
PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_resolution_batch.json"
PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_CSV_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_resolution_batch.csv"
PUBLIC_SAR_CONTRADICTION_WATCHLIST_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_watchlist.json"
PUBLIC_SAR_CONTRADICTION_WATCHLIST_CSV_PATH = ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_watchlist.csv"
PROJECT_EVIDENCE_GAP_ADJUSTMENT_CANDIDATES_PATH = ROOT / "data" / "profiles" / "calibrated" / "project_evidence_gap_adjustment_candidates.csv"
PROFILE_PROMOTION_REGISTRY_PATH = ROOT / "data" / "profiles" / "profile_promotion_registry.json"
PROFILE_AB_REPLAY_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "profile_ab_replay_report.json"
PROFILE_AB_REPLAY_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_ab_replay_report.csv"
PROFILE_AB_REPLAY_MATRIX_PATH = ROOT / "data" / "projects" / "demo" / "profile_ab_replay_matrix.json"
PROFILE_AB_REPLAY_MATRIX_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_ab_replay_matrix.csv"
PROFILE_AB_MATERIAL_REVIEW_PATH = ROOT / "data" / "projects" / "demo" / "profile_ab_material_change_review.json"
PROFILE_AB_MATERIAL_REVIEW_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_ab_material_change_review.csv"
CANDIDATE_EVIDENCE_PRIORITY_PATH = ROOT / "data" / "projects" / "demo" / "candidate_evidence_priority_report.json"
CANDIDATE_EVIDENCE_PRIORITY_CSV_PATH = ROOT / "data" / "projects" / "demo" / "candidate_evidence_priority_report.csv"
EVIDENCE_VALUE_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_report.json"
EVIDENCE_VALUE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_report.csv"
EVIDENCE_VALUE_CALIBRATION_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_calibration_report.json"
EVIDENCE_VALUE_CALIBRATION_CSV_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_calibration_report.csv"
EVIDENCE_VALUE_POLICY_PROPOSAL_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.json"
EVIDENCE_VALUE_POLICY_PROPOSAL_CSV_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.csv"
EVIDENCE_VALUE_POLICY_REPLAY_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_replay.json"
EVIDENCE_VALUE_POLICY_REPLAY_CSV_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_replay.csv"
EVIDENCE_VALUE_POLICY_ACTIVATION_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_activation.json"
EVIDENCE_VALUE_POLICY_ACTIVATION_CSV_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_activation.csv"
EVIDENCE_VALUE_POLICY_ACTIVE_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_active.json"
EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_active_compare.json"
EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "evidence_value_policy_active_compare.csv"
MEASUREMENT_FEEDBACK_PLAN_PATH = ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.json"
MEASUREMENT_FEEDBACK_PLAN_CSV_PATH = ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.csv"
MEASUREMENT_FEEDBACK_TEMPLATE_PATH = ROOT / "data" / "projects" / "demo" / "measurement_feedback_results_template.csv"
MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.json"
MEASUREMENT_FEEDBACK_IMPORT_CSV_PATH = ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.csv"
MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH = ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.json"
MEASUREMENT_FEEDBACK_GAP_CLOSURE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.csv"
MEASUREMENT_GAP_EXACT_INTAKE_PATH = ROOT / "data" / "projects" / "demo" / "measurement_gap_exact_result_intake.json"
MEASUREMENT_GAP_EXACT_INTAKE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "measurement_gap_exact_result_intake.csv"
MEASUREMENT_GAP_EXACT_TEMPLATE_PATH = ROOT / "data" / "projects" / "demo" / "measurement_gap_exact_results_template.csv"
MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_PATH = ROOT / "data" / "projects" / "demo" / "measurement_gap_endpoint_governance.json"
MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "measurement_gap_endpoint_governance.csv"
PROFILE_IMPACT_REVIEW_PATH = ROOT / "data" / "projects" / "demo" / "profile_impact_review_queue.json"
PROFILE_IMPACT_REVIEW_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_impact_review_queue.csv"
PROJECT_MEMORY_REVIEW_QUEUE_PATH = ROOT / "data" / "projects" / "demo" / "project_memory_review_queue.json"
PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "project_memory_review_queue.csv"
PROJECT_MEMORY_REVIEW_DASHBOARD_PATH = ROOT / "data" / "projects" / "demo" / "project_memory_review_dashboard.json"
PROJECT_MEMORY_REVIEW_DASHBOARD_CSV_PATH = ROOT / "data" / "projects" / "demo" / "project_memory_review_dashboard.csv"
ASSAY_EVENT_TRIAGE_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "assay_event_triage_report.json"
ASSAY_EVENT_TRIAGE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "assay_event_triage_report.csv"
ASSAY_FOLLOWUP_TEMPLATE_PATH = ROOT / "data" / "projects" / "demo" / "assay_followup_results_template.csv"
ASSAY_FOLLOWUP_IMPORT_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "assay_followup_result_import_report.json"
ASSAY_FOLLOWUP_IMPORT_CSV_PATH = ROOT / "data" / "projects" / "demo" / "assay_followup_result_import_report.csv"
PROFILE_PROMOTION_FREEZE_MANIFEST_PATH = ROOT / "data" / "projects" / "demo" / "profile_promotion_freeze_manifest.json"
PROFILE_PROMOTION_FREEZE_APPROVALS_PATH = ROOT / "data" / "projects" / "demo" / "profile_promotion_freeze_approvals.json"
PROFILE_PROMOTION_FREEZE_ROLLBACK_DRILL_PATH = ROOT / "data" / "projects" / "demo" / "profile_promotion_freeze_rollback_drill.json"
PROFILE_PROMOTION_ROLLBACK_REPLAY_PATH = ROOT / "data" / "projects" / "demo" / "profile_promotion_rollback_replay.json"
PROFILE_PROMOTION_ROLLBACK_REPLAY_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_promotion_rollback_replay.csv"
PROFILE_ROLLBACK_HISTORY_PATH = ROOT / "data" / "projects" / "demo" / "profile_rollback_history.json"
PROFILE_ROLLBACK_HISTORY_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_rollback_history.csv"
PROFILE_ROLLBACK_CANDIDATE_HISTORY_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_rollback_candidate_history.csv"
PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH = ROOT / "data" / "projects" / "demo" / "profile_rollback_snapshot_compare.json"
PROFILE_ROLLBACK_SNAPSHOT_COMPARE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "profile_rollback_snapshot_compare.csv"
PROJECT_MEMORY_REFRESH_PATH = ROOT / "data" / "projects" / "demo" / "project_memory_refresh_report.json"
DATA_FOUNDATION_REPORT_PATH = ROOT / "data" / "substituents" / "data_foundation_report.json"
WEEKLY_RELEASE_DIFF_PATH = ROOT / "data" / "releases" / "weekly_release_diff_summary.json"
RGROUP_FEED_METADATA_REPORT_PATH = ROOT / "data" / "substituents" / "rgroup_feed_metadata_report.json"
RGROUP_FEED_SAMPLE_REVIEW_QUEUE_PATH = ROOT / "data" / "substituents" / "rgroup_feed_sample_review_queue.csv"
RGROUP_FEED_SAMPLE_REVIEW_APPLY_REPORT_PATH = ROOT / "data" / "substituents" / "rgroup_feed_sample_review_apply_report.json"
RGROUP_FEED_REVIEW_COVERAGE_PATH = ROOT / "data" / "substituents" / "rgroup_feed_review_coverage.json"
RGROUP_FEED_REVIEW_COVERAGE_CSV_PATH = ROOT / "data" / "substituents" / "rgroup_feed_review_coverage.csv"
RGROUP_PAIR_CONTRADICTION_PATH = ROOT / "data" / "substituents" / "rgroup_normalized_pair_contradictions.json"
RGROUP_PAIR_CONTRADICTION_CSV_PATH = ROOT / "data" / "substituents" / "rgroup_normalized_pair_contradictions.csv"
RGROUP_PAIR_CONTRADICTION_REVIEW_PATH = ROOT / "data" / "substituents" / "rgroup_normalized_pair_contradiction_reviews.csv"
RGROUP_PAIR_CONTRADICTION_DECISION_PATH = ROOT / "data" / "substituents" / "rgroup_normalized_pair_contradiction_decisions.json"
RGROUP_PAIR_OWNER_REVIEW_PACKET_PATH = ROOT / "data" / "substituents" / "rgroup_pair_conflict_owner_review_packet.json"
RGROUP_PAIR_OWNER_REVIEW_PACKET_CSV_PATH = ROOT / "data" / "substituents" / "rgroup_pair_conflict_owner_review_packet.csv"
RGROUP_PAIR_OWNER_DECISION_LEDGER_PATH = ROOT / "data" / "substituents" / "rgroup_pair_conflict_owner_decision_ledger.json"
RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH = ROOT / "data" / "substituents" / "rgroup_pair_conflict_owner_decision_ledger.csv"
RGROUP_FEED_ONBOARDING_GATE_PATH = ROOT / "data" / "substituents" / "rgroup_feed_onboarding_gate.json"
RGROUP_FEED_ONBOARDING_GATE_CSV_PATH = ROOT / "data" / "substituents" / "rgroup_feed_onboarding_gate.csv"
RGROUP_FEED_DROP_STAGING_PATH = ROOT / "data" / "substituents" / "rgroup_next_feed_drop_staging.json"
RGROUP_FEED_DROP_STAGING_CSV_PATH = ROOT / "data" / "substituents" / "rgroup_next_feed_drop_staging.csv"
RGROUP_FEED_DROP_STAGING_GATE_PATH = ROOT / "data" / "substituents" / "rgroup_next_feed_drop_staging_gate.json"
RGROUP_FEED_DROP_STAGING_GATE_CSV_PATH = ROOT / "data" / "substituents" / "rgroup_next_feed_drop_staging_gate.csv"
RGROUP_FEED_DROP_STAGING_DIR = ROOT / "data" / "replacements" / "feed_drops" / "next_rgroup_feed_drop"
RING_OUTCOME_LEARNING_REPORT_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.json"
RING_OUTCOME_LEARNING_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.csv"
RING_OUTCOME_OVERLAY_PATH = ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json"
RING_OUTCOME_OVERLAY_CSV_PATH = ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.csv"
RING_OUTCOME_OVERLAY_REVIEW_PATH = ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_reviews.csv"
RING_OUTCOME_MATURATION_POLICY_PATH = ROOT / DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH
RING_OUTCOME_RESIDUAL_TASKS_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_residual_tasks.json"
RING_OUTCOME_RESIDUAL_TASKS_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_residual_tasks.csv"
RING_OUTCOME_EXPERIMENT_PLAN_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.csv"
RING_OUTCOME_EXPERIMENT_PLAN_JSON_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.json"
RING_OUTCOME_RESULTS_TEMPLATE_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_results_template.csv"
RING_OUTCOME_RESULT_INTAKE_MANIFEST_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_result_intake_manifest.json"
RING_OUTCOME_RESULT_INTAKE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_result_intake_manifest.csv"
RING_OUTCOME_OVERLAY_REPLAY_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.json"
RING_OUTCOME_OVERLAY_REPLAY_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.csv"
RING_OUTCOME_PRODUCTION_READINESS_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_production_readiness.json"
RING_OUTCOME_PRODUCTION_READINESS_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_production_readiness.csv"
RING_OUTCOME_RESULT_PACKAGE_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_result_package.json"
RING_OUTCOME_RESULT_PACKAGE_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_result_package.csv"
RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_result_drops" / "production_ring_outcome_results_pending.csv"
RING_OUTCOME_HOLDOUT_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_holdout_report.json"
RING_OUTCOME_HOLDOUT_CSV_PATH = ROOT / "data" / "projects" / "demo" / "ring_outcome_holdout_report.csv"
ITERATION_PACKAGE_ROOT = ROOT / "data" / "projects" / "iterations"
PROFILE_DIR = ROOT / "data" / "profiles"
DEFAULT_SMILES = "COc1ccc(Cl)cc1"
RING_NOVELTY_BUCKETS = [
    "",
    "approved_drug_precedented",
    "clinical_trial_precedented",
    "ertl_common",
    "ertl_precedented",
    "ertl_expansion",
    "long_tail_or_unranked",
]
RING_CLASS_OPTIONS = [
    "",
    "aromatic_heterocycle",
    "aromatic_carbocycle",
    "saturated_heterocycle",
    "saturated_carbocycle",
    "aliphatic_heterocycle",
    "aliphatic_carbocycle",
    "macrocycle",
    "unclassified",
]
RING_SOURCE_DATASET_OPTIONS = [
    "",
    "approved_drug_ring_systems",
    "clinical_trial_ring_systems",
    "ertl_4m_ring_systems",
]
DEFAULT_DIRECTION_OPTIONS = [
    "increase_polarity",
    "reduce_lipophilicity",
    "improve_solubility",
    "reduce_basicity",
    "metabolism_blocking",
    "linker_replacement",
    "reduce_hydrolysis",
    "ring_contraction",
    "ring_expansion",
    "acid_bioisostere_scan",
    "amide_bioisostere_scan",
    "electronics_scan",
    "heteroaryl_scan",
    "increase_rigidity",
    "increase_size",
    "small_scan",
]


@lru_cache(maxsize=1)
def direction_options() -> list[str]:
    return list(DEFAULT_DIRECTION_OPTIONS)


def site_label(site: dict) -> str:
    state = "ready" if site.get("enumeration_ready") else "rule"
    return f"{site['site_id']} | {site['site_type']} | atom {site['atom_idx']} | {state}"


def compact_candidate_frame(rows: list[dict]) -> pd.DataFrame:
    columns = [
        "rank",
        "candidate_id",
        "enumeration_type",
        "cluster_id",
        "cluster_size",
        "diverse_pick",
        "diverse_rank",
        "decision_status",
        "replacement_label",
        "substituent_name",
        "score",
        "score_without_strategy_prior",
        "strategy_learning_score_delta",
        "queue_analog_series_delta_score_delta",
        "score_after_queue_analog_series_delta",
        "multi_objective_score_delta",
        "multi_objective_profile_id",
        "multi_objective_score",
        "multi_objective_potency_score",
        "multi_objective_stability_score",
        "multi_objective_permeability_score",
        "multi_objective_liability_score",
        "multi_objective_constraint_flags",
        "score_before_strategy_adjustment",
        "score_after_strategy_adjustment",
        "mw",
        "delta_mw",
        "clogp",
        "delta_clogp",
        "tpsa",
        "delta_tpsa",
        "hbd",
        "hba",
        "similarity",
        "transform_prior_score",
        "transform_activity_score",
        "rule_activity_judgment",
        "rule_activity_confidence",
        "rule_activity_uncertainty",
        "transform_evidence_level",
        "transform_mmp_pair_count",
        "transform_confidence",
        "transform_activity_cliff_risk",
        "mmp_precedent_strength",
        "mmp_precedent_score",
        "mmp_contradiction_flags",
        "evidence_consistency_score",
        "evidence_confidence_calibration_score",
        "evidence_confidence_adjustment",
        "evidence_confidence_sources",
        "evidence_confidence_status",
        "evidence_confidence_endpoint",
        "evidence_confidence_target_family",
        "evidence_confidence_assay_type",
        "evidence_confidence_max_abs_residual",
        "evidence_confidence_residual_basis",
        "evidence_conflict_flags",
        "evidence_penalty",
        "evidence_target_family",
        "evidence_target_family_normalized",
        "evidence_target_family_label",
        "evidence_assay_type",
        "evidence_context_match_count",
        "evidence_context_family_weight",
        "evidence_context_judgment",
        "evidence_context_mean_delta_pchembl",
        "mmp_pair_count",
        "mmp_exact_pair_count",
        "mmp_transform_ids",
        "mmp_mean_delta_clogp",
        "mmp_mean_delta_tpsa",
        "sar_neighborhood_strength",
        "sar_neighborhood_score",
        "sar_neighborhood_count",
        "sar_neighbor_ids",
        "ring_frequency_score",
        "ring_novelty_bucket",
        "ring_diversity_bucket",
        "ring_sampling_score",
        "diversity_bucket",
        "scaffold_context_score",
        "scaffold_rule_id",
        "scaffold_rule_review_status",
        "scaffold_rule_review_adjustment",
        "scaffold_local_evidence_strength",
        "scaffold_local_evidence_score",
        "scaffold_local_evidence_count",
        "scaffold_local_evidence_types",
        "scaffold_local_evidence_ids",
        "scaffold_local_target_family_match_count",
        "scaffold_local_target_family_strength",
        "scaffold_local_target_family_score",
        "scaffold_operator_prior_score",
        "scaffold_operator_prior_context_weight",
        "scaffold_operator_prior_basis",
        "scaffold_operator_prior_family_match_count",
        "scaffold_operator_prior_endpoint_match_count",
        "strategy_learning_prior_score",
        "strategy_learning_score_adjustment",
        "strategy_learning_recommendation",
        "strategy_learning_endpoint_policy",
        "strategy_learning_policy_version",
        "strategy_learning_basis",
        "strategy_learning_hit_rate",
        "strategy_learning_observed_candidate_count",
        "queue_analog_series_delta_action",
        "queue_analog_series_policy_version",
        "queue_analog_series_delta_score_adjustment",
        "queue_analog_series_delta_mean_priority_delta",
        "queue_analog_series_delta_mean_observed_feedback",
        "queue_analog_series_delta_basis",
        "public_strategy_signal_score",
        "public_strategy_signal_scope",
        "public_strategy_signal_basis",
        "public_strategy_signal_count",
        "public_strategy_signal_support_count",
        "public_strategy_signal_contradiction_count",
        "novelty_batch_pick",
        "novelty_batch_rank",
        "novelty_batch_tier",
        "novelty_batch_bucket",
        "scaffold_local_mmp_strength",
        "scaffold_local_mmp_score",
        "scaffold_local_mmp_count",
        "scaffold_local_mmp_transform_ids",
        "endpoint_gate_decision",
        "endpoint_gate_reason",
        "endpoint_gate_endpoint",
        "endpoint_gate_go_score",
        "endpoint_gate_stop_score",
        "endpoint_gate_basis",
        "endpoint_gate_source",
        "scaffold_attachment_topology",
        "scaffold_linker_length_delta",
        "scaffold_context_flags",
        "enumeration_sources",
        "duplicate_candidate_ids",
        "vendor_score",
        "availability_tier",
        "lead_time_days",
        "route_confidence",
        "route_score",
        "route_routine_level",
        "route_execution_risk_score",
        "profile_risk_bucket",
        "recommendation_reason",
        "smiles",
    ]
    frame = pd.DataFrame(rows)
    display_columns = list(dict.fromkeys(column for column in columns if column in frame.columns))
    return frame[display_columns]


def rebuild_library_artifacts() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_library.py"), "--preserve-db-ring-tables"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, proc.stdout if proc.returncode == 0 else proc.stderr


def saved_runs_frame(runs: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_id": run.get("run_id"),
                "project_name": run.get("project_name"),
                "parent_smiles": run.get("parent_smiles"),
                "direction": run.get("direction"),
                "site_type": run.get("site_type"),
                "scoring_profile_id": run.get("scoring_profile_id"),
                "calibration_id": run.get("calibration_id"),
                "calibration_endpoint_group": run.get("calibration_endpoint_group"),
                "created_at": run.get("created_at"),
                "note": run.get("note"),
            }
            for run in runs
        ]
    )


def render_molecule_svg(mol, *, width: int, height: int, highlight_atoms: list[int] | None = None) -> None:
    svg = mol_to_svg(mol, width=width, height=height, highlight_atoms=highlight_atoms)
    st.html(f'<div style="min-height:{height + 8}px">{svg}</div>', width="stretch")


def db_table_frame(table: str, limit: int = 200) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(f"SELECT * FROM {table} LIMIT {int(limit)}", conn)
    except sqlite3.OperationalError:
        return pd.DataFrame()
    finally:
        conn.close()


def db_table_count(table: str) -> int:
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def db_distinct_values(table: str, column: str, limit: int = 200) -> list[str]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column} LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [str(row[0]) for row in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


st.set_page_config(page_title="LocalMedChemModifier", layout="wide")
st.title("LocalMedChemModifier")

foundation_badge_path = ROOT / "data" / "substituents" / "data_foundation_report.json"
daily_alert_path = ROOT / "data" / "substituents" / "daily_maintenance_alert.json"
if foundation_badge_path.exists():
    try:
        foundation_badge = json.loads(foundation_badge_path.read_text(encoding="utf-8"))
        daily_alert_badge = json.loads(daily_alert_path.read_text(encoding="utf-8")) if daily_alert_path.exists() else {}
        badge = data_currency_badge(foundation_badge, daily_alert_badge)
        status_method = st.success if badge["status"] == "ok" else st.warning if badge["status"] == "warning" else st.error
        status_method(
            f"{badge['label']} | ring offset {badge.get('ring_next_offset')} | "
            f"quality {badge.get('strict_quality_ok')} | alert {badge.get('alert_level') or 'none'}"
        )
    except Exception:
        pass

design_tab, review_tab, quality_tab, governance_tab, project_tab = st.tabs(
    ["Candidate Design", "Library Review", "Data Quality", "Governance Dashboard", "Project Memory"]
)

with design_tab:
    with st.sidebar:
        smiles = st.text_area("SMILES", value=DEFAULT_SMILES, height=90)
        design_project_name = st.text_input("Project context", value="default", key="design_project_name")
        target_family_context = st.text_input("Target family context", value="", placeholder="optional, e.g. kinase")
        assay_type_context = st.text_input("Assay context", value="", placeholder="optional, e.g. IC50")
        endpoint_context = st.text_input("Endpoint context", value="", placeholder="optional, e.g. potency")
        direction = st.selectbox("Direction", direction_options(), index=0)
        profiles = [{"name": "Default", "_path": None, "profile_id": "default"}] + list_scoring_profiles(PROFILE_DIR)
        selected_profile = st.selectbox(
            "Profile",
            profiles,
            format_func=lambda profile: str(profile.get("name") or profile.get("profile_id") or profile.get("_path") or "Profile"),
        )
        max_candidates = st.slider("Candidates", min_value=10, max_value=200, value=80, step=10)
        max_fragment_mw = st.slider("Max fragment MW", min_value=20, max_value=300, value=180, step=10)
        diverse_top_n = st.slider("Diverse Top N", min_value=5, max_value=50, value=20, step=5)
        per_cluster_limit = st.number_input("Per-cluster cap", min_value=1, max_value=5, value=1, step=1)
        novelty_batch_size = st.slider("Novelty batch", min_value=6, max_value=48, value=24, step=6)
        novelty_bucket_limit = st.number_input("Novelty bucket cap", min_value=1, max_value=6, value=3, step=1)
        enumeration_mode = st.selectbox(
            "Enumeration mode",
            [
                "All modes",
                "Substituent replacement",
                "Functional-group replacement",
                "R-group network replacement",
                "Ring/scaffold replacement",
                "Ring library recommendation",
                "Ring + R-group joint",
            ],
            index=0,
        )
        replacement_source_fragment = ""
        if enumeration_mode in {"All modes", "R-group network replacement"}:
            replacement_source_fragment = st.text_input("Network source fragment", value="", placeholder="optional, e.g. Cl[*:1]")
        ring_library_enabled = enumeration_mode in {"All modes", "Ring library recommendation", "Ring + R-group joint"}
        ring_joint_enabled = enumeration_mode in {"All modes", "Ring + R-group joint"}
        max_ring_library_recommendations = 12
        max_ring_library_source_rank = 5000
        max_ring_library_per_bucket = 2
        max_ring_library_similarity = 0.86
        max_ring_joint_candidates = 8
        ring_cache_ttl_seconds = 86400.0
        if ring_library_enabled:
            with st.expander("Ring library controls"):
                ring_cols = st.columns(3)
                max_ring_library_recommendations = ring_cols[0].number_input("Ring candidates", min_value=1, max_value=100, value=12, step=1)
                max_ring_library_source_rank = ring_cols[1].number_input("Max ring rank", min_value=1, max_value=500000, value=5000, step=500)
                max_ring_library_per_bucket = ring_cols[2].number_input("Per ring bucket", min_value=1, max_value=20, value=2, step=1)
                ring_cols2 = st.columns(3)
                max_ring_library_similarity = ring_cols2[0].slider("Max ring similarity", min_value=0.40, max_value=1.00, value=0.86, step=0.02)
                max_ring_joint_candidates = ring_cols2[1].number_input("Joint candidates", min_value=0, max_value=50, value=8, step=1)
                ring_cache_ttl_seconds = ring_cols2[2].number_input("Cache TTL sec", min_value=0.0, max_value=604800.0, value=86400.0, step=3600.0)
        include_advanced = st.toggle("Advanced groups", value=False)
        include_risky = st.toggle("Disabled/risky groups", value=False)

    try:
        parent = standardize_molecule(smiles)
        parent_props = calculate_descriptors(parent).to_dict()
        sites = [site.to_dict() for site in detect_modification_sites(parent)]
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    left, right = st.columns([0.46, 0.54])
    with left:
        render_molecule_svg(parent, width=560, height=360)

    with right:
        prop_cols = st.columns(4)
        prop_cols[0].metric("MW", f"{parent_props['mw']:.1f}")
        prop_cols[1].metric("cLogP", f"{parent_props['clogp']:.2f}")
        prop_cols[2].metric("TPSA", f"{parent_props['tpsa']:.1f}")
        prop_cols[3].metric("HBD/HBA", f"{parent_props['hbd']}/{parent_props['hba']}")

        site_df = pd.DataFrame(sites)
        st.dataframe(
            site_df[
                [
                    "site_id",
                    "site_type",
                    "atom_idx",
                    "leaving_atom_symbol",
                    "operation_type",
                    "enumeration_ready",
                    "recommended_direction_tags",
                ]
            ],
            hide_index=True,
            width="stretch",
        )

    site_index = st.selectbox("Site", range(len(sites)), format_func=lambda idx: site_label(sites[idx]))
    selected_site = sites[site_index]
    highlight = [selected_site["atom_idx"]]
    if selected_site.get("leaving_atom_idx") is not None:
        highlight.append(selected_site["leaving_atom_idx"])

    preview, controls = st.columns([0.38, 0.62])
    with preview:
        render_molecule_svg(parent, width=420, height=280, highlight_atoms=highlight)
    with controls:
        st.write(selected_site["description"])
        st.caption(selected_site["support_note"])
        generate = st.button("Generate candidates", type="primary", width="stretch")

    if generate:
        filter_state = {
            "max_candidates": max_candidates,
            "max_fragment_mw": float(max_fragment_mw),
            "enumeration_mode": enumeration_mode,
            "include_advanced": include_advanced,
            "include_risky": include_risky,
            "diverse_top_n": diverse_top_n,
            "per_cluster_limit": int(per_cluster_limit),
            "novelty_batch_size": int(novelty_batch_size),
            "novelty_bucket_limit": int(novelty_bucket_limit),
            "ring_library_enabled": ring_library_enabled,
            "ring_joint_enabled": ring_joint_enabled,
            "max_ring_library_recommendations": int(max_ring_library_recommendations),
            "max_ring_library_source_rank": int(max_ring_library_source_rank),
            "max_ring_library_per_bucket": int(max_ring_library_per_bucket),
            "max_ring_library_similarity": float(max_ring_library_similarity),
            "max_ring_joint_candidates": int(max_ring_joint_candidates),
            "ring_cache_ttl_seconds": float(ring_cache_ttl_seconds),
            "scoring_profile": selected_profile.get("profile_id"),
            "target_context": {
                "target_family": target_family_context.strip(),
                "assay_type": assay_type_context.strip(),
                "endpoint_group": endpoint_context.strip(),
            },
        }
        include_substituent_scan = enumeration_mode in {"All modes", "Substituent replacement"}
        include_functional = enumeration_mode in {"All modes", "Functional-group replacement"}
        include_network = enumeration_mode in {"All modes", "R-group network replacement"}
        include_scaffold = enumeration_mode in {"All modes", "Ring/scaffold replacement"}
        result = run_mvp(
            smiles=smiles,
            direction=direction,
            library_path=LIBRARY_PATH,
            direction_rules_path=DIRECTION_RULES_PATH,
            functional_rules_path=FUNCTIONAL_RULES_PATH,
            evidence_confidence_report_path=EVIDENCE_CONFIDENCE_REPORT_PATH,
            queue_analog_series_delta_path=QUEUE_ANALOG_SERIES_DELTA_PATH,
            queue_analog_series_policy_path=QUEUE_ANALOG_SERIES_POLICY_PATH,
            target_context_profiles_path=TARGET_CONTEXT_PROFILES_PATH,
            scoring_profile_path=selected_profile.get("_path"),
            db_path=DB_PATH,
            project_name=design_project_name.strip() or None,
            target_context={
                "target_family": target_family_context.strip(),
                "assay_type": assay_type_context.strip(),
                "endpoint_group": endpoint_context.strip(),
            },
            site_index=site_index,
            max_candidates=max_candidates,
            max_fragment_mw=float(max_fragment_mw),
            include_advanced=include_advanced,
            include_risky=include_risky,
            include_substituent_scan=include_substituent_scan,
            include_functional_replacements=include_functional,
            include_replacement_network=include_network,
            include_scaffold_replacements=include_scaffold,
            include_ring_library_recommendations=ring_library_enabled,
            include_ring_rgroup_joint=ring_joint_enabled,
            replacement_network_source_fragment=replacement_source_fragment.strip() or None,
            max_ring_library_recommendations=int(max_ring_library_recommendations),
            max_ring_library_source_rank=int(max_ring_library_source_rank),
            max_ring_library_per_diversity_bucket=int(max_ring_library_per_bucket),
            max_ring_library_similarity=float(max_ring_library_similarity),
            max_ring_rgroup_joint_candidates=int(max_ring_joint_candidates),
            ring_recommendation_cache_ttl_seconds=float(ring_cache_ttl_seconds) if ring_cache_ttl_seconds else 0,
            diverse_top_n=diverse_top_n,
            per_cluster_limit=int(per_cluster_limit),
            novelty_batch_size=int(novelty_batch_size),
            novelty_batch_per_bucket_limit=int(novelty_bucket_limit),
        )
        rows = result["candidates"]
        if not rows:
            st.info(result.get("status_message", "No candidates generated."))
        else:
            st.session_state["last_rows"] = rows
            st.session_state["last_result"] = result
            st.session_state["last_filters"] = filter_state

    if "last_rows" in st.session_state:
        rows = st.session_state["last_rows"]
        result = st.session_state["last_result"]
        table = compact_candidate_frame(rows)

        candidates_tab, analysis_tab, export_tab = st.tabs(["Candidates", "Analysis", "Export"])
        with candidates_tab:
            options = candidate_filter_options(rows)
            filter_cols = st.columns([0.19, 0.18, 0.15, 0.16, 0.13, 0.12, 0.07])
            evidence_options = ["all", "no_conflicts", "any_conflict"] + options["evidence_flags"]
            evidence_filter = filter_cols[0].selectbox("Evidence conflict", evidence_options, index=0)
            bucket_filter = filter_cols[1].multiselect("Diversity bucket", options["diversity_buckets"], default=[])
            site_filter = filter_cols[2].multiselect("Site type", options["site_types"], default=[])
            enum_filter = filter_cols[3].multiselect("Enumeration", options["enumeration_types"], default=[])
            risk_filter = filter_cols[4].selectbox("Profile risk", ["all", "low", "medium", "high"], index=0)
            endpoint_gate_filter = filter_cols[5].selectbox("Endpoint gate", ["all"] + options.get("endpoint_gates", []), index=0)
            diverse_only_filter = filter_cols[6].checkbox("Diverse", value=False)
            display_rows = apply_candidate_filters(
                rows,
                evidence_conflict=evidence_filter,
                diversity_buckets=bucket_filter,
                site_types=site_filter,
                enumeration_types=enum_filter,
                profile_risk=risk_filter,
                endpoint_gate=endpoint_gate_filter,
                diverse_only=diverse_only_filter,
            )
            st.session_state["last_filtered_rows"] = display_rows
            display_table = compact_candidate_frame(display_rows)
            st.caption(f"{len(display_rows)} / {len(rows)} candidates")
            st.dataframe(display_table, hide_index=True, width="stretch")
            top = display_rows[0] if display_rows else rows[0]
            c1, c2, c3 = st.columns([0.42, 0.29, 0.29])
            with c1:
                render_molecule_svg(standardize_molecule(top["smiles"]), width=420, height=280)
            with c2:
                st.metric("Top score", f"{top['score']:.2f}")
                st.metric("Delta cLogP", f"{top['delta_clogp']:+.2f}")
                st.metric("Delta TPSA", f"{top['delta_tpsa']:+.1f}")
            with c3:
                st.metric("Delta MW", f"{top['delta_mw']:+.1f}")
                st.metric("Similarity", f"{top['similarity']:.2f}")
                st.metric("Candidates", str(len(rows)))
            with st.expander("Evidence disagreement"):
                disagreement = evidence_disagreement_summary(display_rows)
                ecols = st.columns(3)
                ecols[0].metric("Disagreements", disagreement.get("disagreement_count", 0))
                ecols[1].metric("Rate", f"{100 * disagreement.get('disagreement_rate', 0):.1f}%")
                ecols[2].metric("Conflict flags", len(disagreement.get("conflict_flag_counts") or {}))
                if display_rows:
                    selected_evidence_id = st.selectbox(
                        "Candidate evidence matrix",
                        [row["candidate_id"] for row in display_rows],
                        index=0,
                        key="candidate_evidence_matrix_id",
                    )
                    selected_evidence = next(row for row in display_rows if row["candidate_id"] == selected_evidence_id)
                    st.dataframe(pd.DataFrame(candidate_evidence_matrix(selected_evidence)), hide_index=True, width="stretch")
                    analog_examples = candidate_evidence_examples(selected_evidence)
                    if analog_examples:
                        st.caption("Matched analog / replacement structures")
                        st.dataframe(pd.DataFrame(analog_examples), hide_index=True, width="stretch")
                        for idx, example in enumerate(analog_examples[:4], start=1):
                            st.caption(
                                f"{idx}. {example.get('evidence_source')} | {example.get('example_id')} | {example.get('match_type')}"
                            )
                            source_svg = smiles_to_svg(example.get("source_structure_smiles"), width=220, height=150)
                            target_svg = smiles_to_svg(example.get("target_structure_smiles"), width=220, height=150)
                            s_col, t_col = st.columns(2)
                            with s_col:
                                st.caption(example.get("source_structure_smiles") or "")
                                if source_svg:
                                    st.html(f'<div style="min-height:158px">{source_svg}</div>', width="stretch")
                            with t_col:
                                st.caption(example.get("target_structure_smiles") or "")
                                if target_svg:
                                    st.html(f'<div style="min-height:158px">{target_svg}</div>', width="stretch")
                    if disagreement.get("candidates"):
                        st.dataframe(pd.DataFrame(disagreement["candidates"]), hide_index=True, width="stretch")
                else:
                    st.info("No filtered candidates to summarize.")

            with st.expander("Strategy policy comparison"):
                comparison = compare_strategy_policy_effect(display_rows or rows, top_n=min(20, len(display_rows or rows)))
                cm1, cm2, cm3 = st.columns(3)
                cm1.metric("Policy version", comparison.get("policy_version") or "-")
                cm2.metric("Top-N changed", comparison.get("changed_top_n_count", 0))
                cm3.metric("Max score delta", comparison.get("max_score_delta", 0))
                comparison_rows = comparison.get("rows") or []
                if comparison_rows:
                    st.dataframe(pd.DataFrame(comparison_rows), hide_index=True, width="stretch")

        with analysis_tab:
            summary = result.get("analysis", {})
            property_summary = summary.get("property_summary", {})
            metric_cols = st.columns(4)
            metric_cols[0].metric("Clusters", property_summary.get("cluster_count", 0))
            metric_cols[1].metric("MW range", f"{property_summary.get('mw_min', 0)}-{property_summary.get('mw_max', 0)}")
            metric_cols[2].metric("cLogP range", f"{property_summary.get('clogp_min', 0)}-{property_summary.get('clogp_max', 0)}")
            metric_cols[3].metric("TPSA range", f"{property_summary.get('tpsa_min', 0)}-{property_summary.get('tpsa_max', 0)}")

            chart_df = table[["clogp", "tpsa", "score", "cluster_id"]].copy()
            chart_df["cluster_id"] = chart_df["cluster_id"].astype(str)
            st.scatter_chart(chart_df, x="clogp", y="tpsa", color="cluster_id", size="score", width="stretch")

            s1, s2, s3 = st.columns(3)
            s1.dataframe(pd.DataFrame(summary.get("cluster_summary", [])), hide_index=True, width="stretch")
            s2.dataframe(pd.DataFrame(summary.get("enumeration_summary", [])), hide_index=True, width="stretch")
            s3.dataframe(pd.DataFrame(summary.get("site_summary", [])), hide_index=True, width="stretch")
            route_summary = summary.get("route_batch_summary") or route_batch_summary(rows)
            if route_summary.get("batches"):
                st.dataframe(pd.DataFrame(route_summary.get("batches", [])), hide_index=True, width="stretch")
            diverse_rows = summary.get("diverse_top_n", [])
            if diverse_rows:
                st.subheader("Diverse Top N")
                st.dataframe(compact_candidate_frame(diverse_rows), hide_index=True, width="stretch")
            novelty_rows = summary.get("novelty_diversity_batch", [])
            if novelty_rows:
                st.subheader("Novelty-Diversity Batch")
                nb_summary = summary.get("novelty_diversity_batch_summary") or {}
                nb1, nb2, nb3 = st.columns(3)
                nb1.metric("Batch", nb_summary.get("batch_count", len(novelty_rows)))
                nb2.metric("Tiers", len(nb_summary.get("tier_counts") or {}))
                nb3.metric("Top score", nb_summary.get("top_score") if nb_summary.get("top_score") is not None else "-")
                st.dataframe(compact_candidate_frame(novelty_rows), hide_index=True, width="stretch")
                st.download_button(
                    "Download novelty batch",
                    compact_candidate_frame(novelty_rows).to_csv(index=False),
                    file_name="novelty_diversity_batch.csv",
                    mime="text/csv",
                    width="stretch",
                )
            analog_summary = summary.get("analog_series_summary") or {}
            analog_rows = analog_summary.get("series") or []
            if analog_rows:
                st.subheader("Analog Series")
                as1, as2, as3 = st.columns(3)
                as1.metric("Series", analog_summary.get("series_count", len(analog_rows)))
                as2.metric("Observed", analog_summary.get("observed_series_count", 0))
                as3.metric("Candidates", analog_summary.get("candidate_count", len(rows)))
                compact_series = [
                    {key: value for key, value in row.items() if key != "example_candidates"}
                    for row in analog_rows[:50]
                ]
                st.dataframe(pd.DataFrame(compact_series), hide_index=True, width="stretch")
                st.download_button(
                    "Download analog series",
                    json.dumps(analog_summary, indent=2, sort_keys=True),
                    file_name="analog_series_summary.json",
                    mime="application/json",
                    width="stretch",
                )

        with export_tab:
            d1, d2 = st.columns(2)
            export_rows = st.session_state.get("last_filtered_rows") or rows
            d1.download_button(
                "CSV",
                rows_to_csv_text(export_rows),
                file_name="localmedchem_candidates.csv",
                mime="text/csv",
                width="stretch",
            )
            d2.download_button(
                "SDF",
                rows_to_sdf_text(export_rows),
                file_name="localmedchem_candidates.sdf",
                mime="chemical/x-mdl-sdfile",
                width="stretch",
            )
            packet = build_decision_packet(
                export_rows,
                project_name=design_project_name.strip() or None,
                parent_smiles=result.get("parent_smiles"),
                direction=direction,
                site_type=(result.get("selected_site") or {}).get("site_type"),
            )
            p1, p2, p3 = st.columns(3)
            p1.download_button(
                "Decision packet JSON",
                json.dumps(packet, indent=2, sort_keys=True),
                file_name="medchem_decision_packet.json",
                mime="application/json",
                width="stretch",
            )
            p2.download_button(
                "Decision packet CSV",
                decision_packet_csv_text(packet),
                file_name="medchem_decision_packet.csv",
                mime="text/csv",
                width="stretch",
            )
            p3.download_button(
                "Decision packet MD",
                decision_packet_markdown(packet),
                file_name="medchem_decision_packet.md",
                mime="text/markdown",
                width="stretch",
            )
            packet_status_cols = st.columns([0.22, 0.22, 0.36, 0.20])
            packet_status = packet_status_cols[0].selectbox("Packet status", PACKET_REVIEW_STATUSES, index=0, key="new_packet_status")
            packet_reviewer = packet_status_cols[1].text_input("Packet reviewer", value="", key="new_packet_reviewer")
            packet_note = packet_status_cols[2].text_input("Packet note", value="", key="new_packet_note")
            if packet_status_cols[3].button("Save packet", width="stretch"):
                packet_id = save_decision_packet(
                    {**packet, "source_run_id": st.session_state.get("last_saved_run_id")},
                    db_path=DB_PATH,
                    status=packet_status,
                    reviewer=packet_reviewer or None,
                    review_note=packet_note or None,
                )
                st.success(f"Saved decision packet {packet_id}.")
            batches = build_route_batches(export_rows)
            st.download_button(
                "Route batches JSON",
                json.dumps({"batches": [{key: value for key, value in batch.items() if key != "candidates"} for batch in batches]}, indent=2),
                file_name="localmedchem_route_batches.json",
                mime="application/json",
                width="stretch",
            )
            b1, b2 = st.columns(2)
            quick_rows = [candidate for batch in batches if batch["batch_type"] == "quick_purchase" for candidate in batch["candidates"]]
            custom_rows = [candidate for batch in batches if batch["batch_type"] == "custom_synthesis" for candidate in batch["candidates"]]
            b1.download_button("Fast route-class CSV", rows_to_csv_text(quick_rows), file_name="fast_route_class_candidates.csv", mime="text/csv", width="stretch")
            b2.download_button("Synthesis-review CSV", rows_to_csv_text(custom_rows), file_name="synthesis_review_candidates.csv", mime="text/csv", width="stretch")
            st.divider()
            project_name = st.text_input("Project name", value="default", key="save_project_name")
            project_note = st.text_area("Run note", value="", height=90, key="save_project_note")
            if st.button("Save run to project memory", type="primary", width="stretch"):
                run_id = save_project_run(
                    result,
                    db_path=DB_PATH,
                    project_name=project_name or "default",
                    note=project_note or None,
                    filters=st.session_state.get("last_filters", {}),
                )
                st.session_state["last_saved_run_id"] = run_id
                st.success(f"Saved run {run_id}.")

with review_tab:
    seed_records = []
    for seed_path in SEED_PATHS:
        if seed_path.exists():
            for item in load_yaml_records(seed_path):
                item["_seed_path"] = str(seed_path)
                seed_records.append(item)
    review_frame = pd.DataFrame(
        [
            {
                "substituent_id": record["substituent_id"],
                "name": record["name"],
                "review_status": default_review_block(record).get("status"),
                "default_enabled": (record.get("risk") or {}).get("default_enabled", True),
                "default_rank": (record.get("priority") or {}).get("default_rank", 999),
                "seed_file": Path(record["_seed_path"]).name,
            }
            for record in seed_records
        ]
    )
    st.dataframe(review_frame, hide_index=True, width="stretch")
    backlog_count = int((review_frame["review_status"] == "needs_medchem_review").sum()) if not review_frame.empty else 0
    rb1, rb2, rb3 = st.columns([0.22, 0.22, 0.56])
    rb1.metric("Review backlog", backlog_count)
    batch_limit = rb2.number_input("Batch size", min_value=1, max_value=max(len(seed_records), 1), value=min(50, max(len(seed_records), 1)))
    if rb3.button("Build review batch", width="stretch"):
        batch_rows = build_review_backlog_batch(SEED_PATHS, limit=int(batch_limit))
        batch_path = ROOT / "data" / "substituents" / "review_batch_streamlit.csv"
        write_review_backlog_batch(batch_rows, batch_path)
        st.session_state["review_batch_rows"] = batch_rows
        st.session_state["review_batch_path"] = str(batch_path)
    if st.session_state.get("review_batch_rows"):
        st.dataframe(pd.DataFrame(st.session_state["review_batch_rows"]), hide_index=True, width="stretch")
        if st.button("Apply review batch and rebuild", width="stretch"):
            report = apply_review_backlog_batch(st.session_state["review_batch_path"], reviewed_by="streamlit_batch_review")
            ok, output = rebuild_library_artifacts()
            st.session_state["review_batch_apply_report"] = report
            if ok:
                st.success(f"Applied {report['applied_count']} review rows and rebuilt library.")
            else:
                st.error(output)
        if st.session_state.get("review_batch_apply_report"):
            st.json(st.session_state["review_batch_apply_report"])

    selected_id = st.selectbox(
        "Substituent",
        [record["substituent_id"] for record in seed_records],
        format_func=lambda sid: f"{sid} | {next(record['name'] for record in seed_records if record['substituent_id'] == sid)}",
    )
    selected_record = next(record for record in seed_records if record["substituent_id"] == selected_id)
    review = default_review_block(selected_record)
    risk = selected_record.get("risk") or {}
    priority = selected_record.get("priority") or {}

    r1, r2 = st.columns(2)
    with r1:
        status = st.selectbox("Status", REVIEW_STATUSES, index=REVIEW_STATUSES.index(review.get("status", REVIEW_STATUSES[0])))
        reviewer = st.text_input("Reviewer", value=review.get("reviewed_by") or "")
        use_cases = st.text_area("Use cases", value="; ".join(review.get("use_cases") or []), height=120)
        avoid_contexts = st.text_area("Avoid contexts", value="; ".join(review.get("avoid_contexts") or []), height=120)
    with r2:
        default_enabled = st.checkbox("Default enabled", value=bool(risk.get("default_enabled", True)))
        common_medchem = st.checkbox("Common medchem", value=bool(priority.get("common_medchem", False)))
        mvp = st.checkbox("MVP", value=bool(priority.get("mvp", True)))
        default_rank = st.number_input("Default rank", min_value=1, max_value=999, value=int(priority.get("default_rank", 999)))
        note = st.text_area("Review note", height=100)
        change_summary = st.text_input("Change summary", value=f"Review updated to {status}.")

    if st.button("Save review and rebuild library", type="primary", width="stretch"):
        try:
            update_substituent_review(
                selected_record["_seed_path"],
                selected_id,
                status=status,
                reviewed_by=reviewer or None,
                review_note=note or None,
                use_cases=use_cases,
                avoid_contexts=avoid_contexts,
                default_enabled=default_enabled,
                common_medchem=common_medchem,
                mvp=mvp,
                default_rank=int(default_rank),
                change_summary=change_summary,
            )
            ok, output = rebuild_library_artifacts()
            if ok:
                st.success("Review saved and library artifacts rebuilt.")
                st.code(output[-1200:])
            else:
                st.error(output)
        except Exception as exc:
            st.error(str(exc))

with quality_tab:
    if st.button("Run quality checks", type="primary"):
        report = validate_data_quality(ROOT)
        st.session_state["quality_report"] = report

    if "quality_report" in st.session_state:
        report = st.session_state["quality_report"]
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("OK", str(report["ok"]))
        q2.metric("Errors", report["error_count"])
        q3.metric("Warnings", report["warning_count"])
        q4.metric("Rules", report["functional_rule_count"])
        st.dataframe(pd.DataFrame(report["issues"]), hide_index=True, width="stretch")

    st.divider()
    ec_project = st.text_input("Evidence calibration project", value="", key="evidence_confidence_project")
    if st.button("Build evidence confidence report"):
        evidence_report = build_evidence_confidence_report(db_path=DB_PATH, project_name=ec_project or None)
        write_evidence_confidence_report(evidence_report, EVIDENCE_CONFIDENCE_REPORT_PATH)
        residual_registry = sync_evidence_residual_task_registry(
            evidence_report.get("residual_data_tasks") or [],
            existing_registry=load_evidence_residual_task_registry(EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH),
            reviewer="streamlit",
        )
        write_evidence_residual_task_registry(
            residual_registry,
            EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
            csv_path=EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH.with_suffix(".csv"),
        )
        st.session_state["evidence_confidence_report"] = evidence_report
        st.session_state["evidence_residual_task_registry"] = residual_registry
    if "evidence_confidence_report" not in st.session_state and EVIDENCE_CONFIDENCE_REPORT_PATH.exists():
        try:
            st.session_state["evidence_confidence_report"] = json.loads(EVIDENCE_CONFIDENCE_REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    if "evidence_confidence_report" in st.session_state:
        evidence_report = st.session_state["evidence_confidence_report"]
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Observations", evidence_report.get("observation_count", 0))
        ec2.metric("Entries", evidence_report.get("entry_count", 0))
        ec3.metric("Endpoints", len(evidence_report.get("endpoint_counts") or {}))
        ec4.metric("Residual tasks", len(evidence_report.get("residual_data_tasks") or []))
        residual_summary = evidence_report.get("residual_quality_summary") or {}
        if residual_summary:
            rs1, rs2, rs3 = st.columns(3)
            rs1.metric("Actionable residuals", residual_summary.get("actionable_residual_count", 0))
            rs2.metric("Thin-sample residuals", residual_summary.get("thin_sample_residual_count", 0))
            rs3.metric("Max actionable residual", residual_summary.get("max_actionable_abs_residual", 0))
        residual_tasks = evidence_report.get("residual_data_tasks") or []
        if residual_tasks:
            with st.expander("Evidence residual data-strengthening tasks", expanded=True):
                st.dataframe(pd.DataFrame(residual_tasks), hide_index=True, width="stretch")
                st.download_button(
                    "Download residual tasks",
                    pd.DataFrame(residual_tasks).to_csv(index=False),
                    file_name="evidence_residual_tasks.csv",
                    mime="text/csv",
                    width="stretch",
                )
        if "evidence_residual_task_registry" not in st.session_state and EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH.exists():
            st.session_state["evidence_residual_task_registry"] = load_evidence_residual_task_registry(EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH)
        if st.session_state.get("evidence_residual_task_registry"):
            registry = st.session_state["evidence_residual_task_registry"]
            with st.expander("Evidence residual task lifecycle"):
                rt1, rt2, rt3 = st.columns(3)
                rt1.metric("Registry tasks", registry.get("task_count", 0))
                rt2.metric("Active tasks", registry.get("active_task_count", 0))
                rt3.metric("Open tasks", (registry.get("status_counts") or {}).get("open", 0))
                registry_rows = registry.get("tasks") or []
                if registry_rows:
                    st.dataframe(pd.DataFrame(registry_rows).drop(columns=["status_history"], errors="ignore"), hide_index=True, width="stretch")
                    edit_cols = st.columns([0.3, 0.2, 0.2, 0.3])
                    task_ids = [row.get("task_id") for row in registry_rows if row.get("task_id")]
                    selected_task_id = edit_cols[0].selectbox("Residual task", task_ids, key="residual_task_status_id")
                    selected_status = edit_cols[1].selectbox("Status", EVIDENCE_RESIDUAL_TASK_STATUSES, key="residual_task_status")
                    task_reviewer = edit_cols[2].text_input("Reviewer", value="", key="residual_task_reviewer")
                    task_note = edit_cols[3].text_input("Status note", value="", key="residual_task_note")
                    if st.button("Update residual task status", width="stretch"):
                        try:
                            updated_registry = update_evidence_residual_task_status(
                                selected_task_id,
                                status=selected_status,
                                registry_path=EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                                reviewer=task_reviewer or "streamlit",
                                note=task_note or None,
                            )
                            write_evidence_residual_task_registry(
                                updated_registry,
                                EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                                csv_path=EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH.with_suffix(".csv"),
                            )
                            st.session_state["evidence_residual_task_registry"] = updated_registry
                            st.success("Residual task status updated.")
                        except Exception as exc:
                            st.error(str(exc))
                    plan_cols = st.columns([0.25, 0.25, 0.25, 0.25])
                    residual_plan_project = plan_cols[0].text_input("Plan project", value=ec_project or "evidence_residual", key="residual_plan_project")
                    residual_plan_owner = plan_cols[1].text_input("Plan owner", value="", key="residual_plan_owner")
                    residual_plan_size = plan_cols[2].number_input("Plan size", min_value=1, max_value=100, value=24, step=1, key="residual_plan_size")
                    residual_plan_upsert = plan_cols[3].checkbox("Upsert DB", value=True, key="residual_plan_upsert")
                    if st.button("Build residual experiment plan", width="stretch"):
                        try:
                            plan_rows = residual_tasks_to_experiment_plan(
                                registry,
                                project_name=residual_plan_project,
                                owner=residual_plan_owner,
                                batch_size=int(residual_plan_size),
                            )
                            RESIDUAL_EXPERIMENT_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
                            pd.DataFrame(plan_rows).to_csv(RESIDUAL_EXPERIMENT_PLAN_PATH, index=False)
                            upsert_report = upsert_experiment_plan_rows(
                                plan_rows,
                                db_path=DB_PATH,
                                source_path=str(RESIDUAL_EXPERIMENT_PLAN_PATH.resolve()),
                            ) if residual_plan_upsert and plan_rows else {"upserted_count": 0}
                            updated_registry = update_residual_tasks_from_experiment_plan(
                                plan_rows,
                                registry_path=EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                                reviewer="streamlit",
                            ) if plan_rows else registry
                            st.session_state["evidence_residual_task_registry"] = updated_registry
                            st.session_state["residual_experiment_plan_rows"] = plan_rows
                            st.success(f"Residual experiment plan rows: {len(plan_rows)}; upserted: {upsert_report.get('upserted_count', 0)}")
                        except Exception as exc:
                            st.error(str(exc))
                    if st.session_state.get("residual_experiment_plan_rows"):
                        plan_df = pd.DataFrame(st.session_state["residual_experiment_plan_rows"])
                        st.dataframe(plan_df, hide_index=True, width="stretch")
                        if st.button("Build residual result template", width="stretch"):
                            template_rows = write_experiment_result_template(
                                st.session_state["residual_experiment_plan_rows"],
                                RESIDUAL_EXPERIMENT_RESULTS_TEMPLATE_PATH,
                            )
                            st.session_state["residual_result_template_rows"] = template_rows
                            st.success(f"Residual result template rows: {len(template_rows)}")
                        if st.session_state.get("residual_result_template_rows"):
                            template_df = pd.DataFrame(st.session_state["residual_result_template_rows"])
                            st.download_button(
                                "Download residual result template",
                                template_df.to_csv(index=False),
                                file_name="residual_experiment_results_template.csv",
                                mime="text/csv",
                                width="stretch",
                            )
                        st.download_button(
                            "Download residual experiment plan",
                            plan_df.to_csv(index=False),
                            file_name="residual_experiment_plan.csv",
                            mime="text/csv",
                            width="stretch",
                        )
        if (evidence_report.get("residual_trend_delta") or {}).get("status") == "compared":
            with st.expander("Residual trend delta"):
                trend = evidence_report.get("residual_trend_delta") or {}
                st.json({key: trend.get(key) for key in ["changed_count", "new_count", "resolved_count"]})
                changed = trend.get("top_changed_residuals") or []
                if changed:
                    st.dataframe(pd.DataFrame(changed), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(evidence_report.get("entries", [])), hide_index=True, width="stretch")

    st.divider()
    with st.expander("Multi-objective profile calibration"):
        mo_cols = st.columns(4)
        mo_project = mo_cols[0].text_input("Project", value="demo_learning", key="mo_cal_project")
        mo_endpoint = mo_cols[1].text_input("Endpoint", value="", key="mo_cal_endpoint")
        mo_family = mo_cols[2].text_input("Target family", value="", key="mo_cal_family")
        mo_assay = mo_cols[3].text_input("Assay type", value="", key="mo_cal_assay")
        if st.button("Calibrate multi-objective weights", width="stretch"):
            try:
                report = calibrate_multi_objective_profile(
                    db_path=DB_PATH,
                    project_name=mo_project or None,
                    target_context={"endpoint_group": mo_endpoint or None, "target_family": mo_family or None, "assay_type": mo_assay or None},
                    profiles_path=TARGET_CONTEXT_PROFILES_PATH,
                )
                write_multi_objective_calibration_report(report, MULTI_OBJECTIVE_CALIBRATION_REPORT_PATH)
                write_multi_objective_profile(report["calibrated_profile"], MULTI_OBJECTIVE_CALIBRATED_PROFILE_PATH)
                st.session_state["multi_objective_calibration_report"] = report
                st.success(f"Calibration status: {report.get('status')} ({report.get('observation_count')} observations)")
            except Exception as exc:
                st.error(str(exc))
        if "multi_objective_calibration_report" not in st.session_state and MULTI_OBJECTIVE_CALIBRATION_REPORT_PATH.exists():
            try:
                st.session_state["multi_objective_calibration_report"] = json.loads(MULTI_OBJECTIVE_CALIBRATION_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if st.session_state.get("multi_objective_calibration_report"):
            mo_report = st.session_state["multi_objective_calibration_report"]
            mo1, mo2, mo3 = st.columns(3)
            mo1.metric("Status", mo_report.get("status"))
            mo2.metric("Observations", mo_report.get("observation_count", 0))
            mo3.metric("Profile", (mo_report.get("calibrated_profile") or {}).get("profile_id"))
            st.dataframe(pd.DataFrame(mo_report.get("component_diagnostics") or []), hide_index=True, width="stretch")
            st.json((mo_report.get("calibrated_profile") or {}).get("score_weights") or {})

    st.divider()
    if st.button("Build data foundation snapshot"):
        report = build_data_foundation_report(ROOT, db_path=DB_PATH, include_checksums=False)
        save_data_foundation_report(
            report,
            json_path=ROOT / "data" / "substituents" / "data_foundation_report.json",
            markdown_path=ROOT / "data" / "substituents" / "data_foundation_report.md",
            db_path=DB_PATH,
        )
        st.session_state["data_foundation_report"] = report

    foundation_path = ROOT / "data" / "substituents" / "data_foundation_report.json"
    if "data_foundation_report" not in st.session_state and foundation_path.exists():
        try:
            st.session_state["data_foundation_report"] = json.loads(foundation_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if "data_foundation_report" in st.session_state:
        foundation = st.session_state["data_foundation_report"]
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Records", foundation.get("totals", {}).get("record_count", 0))
        f2.metric("Assets", foundation.get("totals", {}).get("asset_count", 0))
        f3.metric("Warnings", foundation.get("totals", {}).get("warning_count", 0))
        f4.metric("Profiles", foundation.get("coverage", {}).get("scoring_profile_count", 0))
        ci_gate = foundation.get("ci_gate") or {}
        if ci_gate:
            g1, g2, g3, g4 = st.columns(4)
            g1.metric("CI gate", ci_gate.get("status", "unknown"))
            g2.metric("Gate passed", str(ci_gate.get("passed")))
            g3.metric("Gate errors", ci_gate.get("error_count", 0))
            g4.metric("Gate warnings", ci_gate.get("warning_count", 0))
            if ci_gate.get("issues"):
                st.dataframe(pd.DataFrame(ci_gate.get("issues", [])), hide_index=True, width="stretch")
        data_drift = foundation.get("data_drift") or {}
        if data_drift:
            dd1, dd2, dd3, dd4 = st.columns(4)
            dd1.metric("Data drift", data_drift.get("status", "unknown"))
            dd2.metric("Drift errors", data_drift.get("error_count", 0))
            dd3.metric("Drift warnings", data_drift.get("warning_count", 0))
            dd4.metric("Accepted drift", data_drift.get("accepted_issue_count", 0))
            if data_drift.get("issues"):
                st.dataframe(pd.DataFrame(data_drift.get("issues", [])), hide_index=True, width="stretch")
            if data_drift.get("accepted_issues"):
                st.dataframe(pd.DataFrame(data_drift.get("accepted_issues", [])), hide_index=True, width="stretch")
            with st.expander("Count drift"):
                st.dataframe(pd.DataFrame(data_drift.get("count_deltas", [])), hide_index=True, width="stretch")
        currency = foundation.get("data_currency") or data_currency_badge(foundation)
        st.caption(
            f"{currency.get('label')} | snapshot {currency.get('last_snapshot_at')} | "
            f"ring offset {currency.get('ring_next_offset')} | drift {currency.get('data_drift')}"
        )
        st.dataframe(pd.DataFrame(foundation.get("assets", [])), hide_index=True, width="stretch")
        drift = foundation.get("release_drift") or {}
        if drift.get("available"):
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Release added", drift.get("added_count", 0))
            d2.metric("Release changed", drift.get("changed_count", 0))
            d3.metric("Release removed", drift.get("removed_count", 0))
            d4.metric("Drift risk", drift.get("risk_level", "unknown"))
        ring_status = ((foundation.get("import_state") or {}).get("ring_import_status") or {})
        if ring_status:
            checkpoint = ring_status.get("checkpoint_integrity") or {}
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Ring import", ring_status.get("status", "unknown"))
            r2.metric("Ring progress", f"{ring_status.get('progress_percent') or 0:.3f}%")
            r3.metric("Next offset", ring_status.get("next_offset", 0))
            r4.metric("Checkpoint", checkpoint.get("status", "unknown"))

with governance_tab:
    st.subheader("Staging and Evidence")
    overview_cols = st.columns(5)
    table_counts = {}
    for table in [
        "candidate_substituent",
        "candidate_promotion",
        "mmp_transform_evidence",
        "transform_mmp_mapping",
        "transform_activity_summary",
        "chembl_activity_evidence",
        "ring_system",
        "literature_substituent",
        "ring_replacement",
        "rgroup_replacement",
        "substituent_vendor_overlay",
        "scaffold_replacement",
        "project_feedback",
        "project_feedback_control",
        "route_batch_status_event",
        "api_health_check",
    ]:
        try:
            table_counts[table] = db_table_count(table)
        except Exception:
            table_counts[table] = 0
    overview_cols[0].metric("Staged candidates", table_counts["candidate_substituent"])
    overview_cols[1].metric("Promotions", table_counts["candidate_promotion"])
    overview_cols[2].metric("MMP evidence", table_counts["mmp_transform_evidence"])
    overview_cols[3].metric("Ring systems", table_counts["ring_system"])
    overview_cols[4].metric("R-group edges", table_counts["rgroup_replacement"])

    g1, g2, g3, g4, g5 = st.tabs(
        ["Candidate Queue", "Source Health", "Transform Evidence", "Ring + R-group", "R-group Feed Review"]
    )
    with g1:
        candidate_frame = db_table_frame("candidate_substituent", limit=300)
        if candidate_frame.empty:
            st.info("No staged candidates found.")
        else:
            st.dataframe(
                candidate_frame[
                    [
                        "candidate_id",
                        "source_name",
                        "name",
                        "canonical_smiles",
                        "candidate_status",
                        "review_tier",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )
            selected_candidate_id = st.selectbox("Review candidate", candidate_frame["candidate_id"].tolist())
            reviewer = st.text_input("Candidate reviewer", value="", key="governance_reviewer")
            review_note = st.text_area("Candidate note", height=80, key="governance_candidate_note")
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("Approve staged candidate", width="stretch"):
                    conn = sqlite3.connect(DB_PATH)
                    try:
                        update_candidate_status(conn, selected_candidate_id, "approved", review_tier="approved")
                    finally:
                        conn.close()
                    st.success(f"Approved {selected_candidate_id}.")
            with a2:
                if st.button("Block staged candidate", width="stretch"):
                    conn = sqlite3.connect(DB_PATH)
                    try:
                        update_candidate_status(conn, selected_candidate_id, "blocked", review_tier="blocked")
                    finally:
                        conn.close()
                    st.success(f"Blocked {selected_candidate_id}.")
            with a3:
                if st.button("Promote and rebuild", type="primary", width="stretch"):
                    candidate = load_candidate_from_db(DB_PATH, selected_candidate_id)
                    if not candidate:
                        st.error("Candidate payload not found.")
                    else:
                        result = promote_candidate_to_seed(
                            candidate,
                            existing_seed_paths=SEED_PATHS,
                            output_seed_path=ROOT / "data" / "seeds" / "pubchem_expansion_seed.yaml",
                            reviewed_by=reviewer or "streamlit",
                            note=review_note or None,
                            source_version="streamlit-promotion-0.1",
                        )
                        ok, output = rebuild_library_artifacts()
                        if ok and result.get("substituent_id"):
                            conn = sqlite3.connect(DB_PATH)
                            try:
                                update_candidate_status(conn, selected_candidate_id, "promoted", review_tier="approved")
                                record_candidate_promotion(
                                    conn,
                                    selected_candidate_id,
                                    result["substituent_id"],
                                    notes=review_note or "Promoted from Governance Dashboard.",
                                )
                            finally:
                                conn.close()
                            st.success(f"Promoted {selected_candidate_id} to {result['substituent_id']}.")
                        elif ok:
                            st.info(f"No new seed appended: {result.get('status')}.")
                        else:
                            st.error(output)
    with g2:
        health_frame = db_table_frame("api_health_check", limit=20)
        if not health_frame.empty:
            st.dataframe(health_frame.sort_values("checked_at", ascending=False), hide_index=True, width="stretch")
        mmp_frame = db_table_frame("mmp_transform_evidence", limit=50)
        if not mmp_frame.empty:
            st.dataframe(
                mmp_frame[
                    [
                        "transform_id",
                        "variable_from_smiles",
                        "variable_to_smiles",
                        "pair_count",
                        "mean_delta_clogp",
                        "mean_delta_tpsa",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )
    with g3:
        if st.button("Load transform evidence"):
            st.session_state["governance_transform_evidence_report"] = build_transform_evidence_report(db_path=DB_PATH)
            st.session_state["governance_transform_activity_frame"] = db_table_frame("transform_activity_summary", limit=100)
        evidence_report = st.session_state.get("governance_transform_evidence_report")
        if evidence_report:
            e1, e2, e3 = st.columns(3)
            e1.metric("Transforms", evidence_report.get("transform_count", 0))
            e2.metric("Project evidence", evidence_report.get("project_evidence_count", 0))
            e3.metric("Activity summaries", table_counts["transform_activity_summary"])
            st.dataframe(pd.DataFrame(evidence_report.get("entries", [])), hide_index=True, width="stretch")
            activity_summary_frame = st.session_state.get("governance_transform_activity_frame")
            if activity_summary_frame is not None and not activity_summary_frame.empty:
                st.dataframe(
                    activity_summary_frame[
                        [
                            "rule_id",
                            "replacement_label",
                            "transform_id",
                            "target_summary_count",
                            "target_family_summary_count",
                            "activity_cliff_count",
                            "mean_delta_pchembl",
                            "mean_family_delta_pchembl",
                            "max_abs_delta_pchembl",
                            "activity_cliff_risk",
                            "rule_activity_judgment",
                        ]
                    ],
                    hide_index=True,
                    width="stretch",
                )
        else:
            st.caption("Load transform evidence when you need the detailed MMP/activity table.")
    with g4:
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Ring systems", table_counts["ring_system"])
        r2.metric("Literature substituents", table_counts["literature_substituent"])
        r3.metric("Ring replacements", table_counts["ring_replacement"])
        r4.metric("Scaffold rules", table_counts["scaffold_replacement"])
        import_status = build_ring_import_status(db_path=DB_PATH)
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Ertl import", import_status.get("status"))
        i2.metric("Progress", f"{import_status.get('progress_percent') or 0:.3f}%")
        i3.metric("Throughput", f"{import_status.get('last_throughput_rings_per_second') or 0}/s")
        eta = import_status.get("eta_seconds")
        i4.metric("ETA hours", f"{eta / 3600:.1f}" if eta else "-")
        if import_status.get("last_error"):
            st.warning(import_status["last_error"])
        checkpoint = import_status.get("checkpoint_integrity") or {}
        if checkpoint.get("status") not in {None, "ok"}:
            st.warning(f"Checkpoint integrity: {checkpoint.get('status')}")
        with st.expander("Ring import task status"):
            st.json(import_status)
        ring_query_cols = st.columns([0.24, 0.18, 0.18, 0.18, 0.11, 0.11])
        ring_query = ring_query_cols[0].text_input("Ring search", value="", key="ring_search_query")
        ring_class_filter = ring_query_cols[1].selectbox("Ring class", RING_CLASS_OPTIONS)
        source_dataset_filter = ring_query_cols[2].selectbox("Source dataset", RING_SOURCE_DATASET_OPTIONS)
        novelty_filter = ring_query_cols[3].selectbox("Novelty", RING_NOVELTY_BUCKETS)
        ring_page_size = ring_query_cols[4].number_input("Page size", min_value=25, max_value=500, value=100, step=25)
        ring_page = ring_query_cols[5].number_input("Page", min_value=1, max_value=100000, value=1, step=1)
        heavy_cols = st.columns([0.18, 0.18, 0.24, 0.40])
        min_heavy = heavy_cols[0].number_input("Min heavy atoms", min_value=0, max_value=80, value=0)
        max_heavy = heavy_cols[1].number_input("Max heavy atoms", min_value=0, max_value=120, value=0)
        diversity_filter = heavy_cols[2].text_input("Diversity bucket", value="", placeholder="optional exact bucket")
        run_ring_search = heavy_cols[3].button("Search rings", width="stretch")
        if run_ring_search:
            conn = sqlite3.connect(DB_PATH)
            try:
                ring_result = query_ring_systems(
                    conn,
                    search=ring_query or None,
                    ring_class=ring_class_filter or None,
                    source_dataset=source_dataset_filter or None,
                    min_heavy_atom_count=int(min_heavy) if min_heavy else None,
                    max_heavy_atom_count=int(max_heavy) if max_heavy else None,
                    novelty_bucket=novelty_filter or None,
                    diversity_bucket=diversity_filter.strip() or None,
                    page=int(ring_page),
                    page_size=int(ring_page_size),
                )
            finally:
                conn.close()
            st.metric("Matched ring systems", f"{ring_result['total']} across {ring_result['page_count']} pages")
            if ring_result["rows"]:
                st.dataframe(pd.DataFrame(ring_result["rows"]), hide_index=True, width="stretch")
        else:
            st.caption("Use filters and Search rings to inspect the ring novelty/diversity database.")
        with st.expander("Ring source summary"):
            if st.button("Load ring source summary"):
                st.dataframe(pd.DataFrame(ring_source_summary(db_path=DB_PATH)), hide_index=True, width="stretch")
        rgroup_frame = db_table_frame("rgroup_replacement", limit=100)
        if not rgroup_frame.empty:
            st.dataframe(
                rgroup_frame[["source_canonical_smiles", "target_canonical_smiles", "edge_weight", "layer"]],
                hide_index=True,
                width="stretch",
            )
        st.subheader("Scaffold Rule Review")
        scw_filters = st.columns([0.24, 0.22, 0.20, 0.20, 0.14])
        scw_project = scw_filters[0].text_input("Scaffold workspace project", value="", key="scaffold_workspace_project")
        scw_owner = scw_filters[1].text_input("Owner filter", value="", key="scaffold_workspace_owner")
        scw_resolution = scw_filters[2].selectbox(
            "Resolution filter",
            ["", *SCAFFOLD_RULE_RESOLUTION_STATUSES],
            key="scaffold_workspace_resolution",
        )
        scw_version = scw_filters[3].text_input("Rule version filter", value="", key="scaffold_workspace_version")
        if st.button("Build scaffold workspace"):
            workspace_report = build_scaffold_review_workspace_report(
                db_path=DB_PATH,
                project_name=scw_project or None,
                scaffold_rules_path=SCAFFOLD_RULES_PATH,
                scaffold_rule_reviews_path=SCAFFOLD_RULE_REVIEWS_PATH,
                owner_filter=scw_owner or None,
                resolution_status_filter=scw_resolution or None,
                rule_version_filter=scw_version or None,
            )
            write_scaffold_review_workspace_report(workspace_report, SCAFFOLD_WORKSPACE_REPORT_PATH)
            st.session_state["scaffold_workspace_report"] = workspace_report
        if "scaffold_workspace_report" not in st.session_state and SCAFFOLD_WORKSPACE_REPORT_PATH.exists():
            try:
                st.session_state["scaffold_workspace_report"] = json.loads(SCAFFOLD_WORKSPACE_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "scaffold_workspace_report" in st.session_state:
            workspace_report = st.session_state["scaffold_workspace_report"]
            sw1, sw2, sw3, sw4 = st.columns(4)
            sw1.metric("Rules", workspace_report.get("rule_count", 0))
            sw2.metric("Candidates", workspace_report.get("candidate_count", 0))
            sw3.metric("Entries", workspace_report.get("workspace_entry_count", 0))
            sw4.metric("Priorities", len(workspace_report.get("review_priority_counts") or {}))
            active_filters = [
                f"{name}={value}"
                for name, value in [
                    ("owner", workspace_report.get("owner_filter")),
                    ("resolution", workspace_report.get("resolution_status_filter")),
                    ("rule_version", workspace_report.get("rule_version_filter")),
                ]
                if value
            ]
            if active_filters:
                st.caption(" | ".join(active_filters))
            workspace_rows = [
                {key: value for key, value in row.items() if key != "example_candidates"}
                for row in workspace_report.get("entries", [])
            ]
            if workspace_rows:
                st.dataframe(pd.DataFrame(workspace_rows), hide_index=True, width="stretch")
                selected_workspace = st.selectbox(
                    "Workspace entry",
                    [row["workspace_key"] for row in workspace_rows],
                    key="scaffold_workspace_entry",
                )
                selected_entry = next((row for row in workspace_report.get("entries", []) if row.get("workspace_key") == selected_workspace), {})
                examples = selected_entry.get("example_candidates") or []
                if examples:
                    st.dataframe(pd.DataFrame(examples), hide_index=True, width="stretch")
                    with st.expander("Add reviewed example to scaffold calibration set"):
                        cal_cols = st.columns([0.32, 0.18, 0.22, 0.28])
                        cal_candidate = cal_cols[0].selectbox(
                            "Example candidate",
                            [str(item.get("candidate_id")) for item in examples if item.get("candidate_id")],
                            key="scaffold_calibration_candidate",
                        )
                        cal_decision = cal_cols[1].selectbox(
                            "Outcome",
                            ["supported", "failed", "rejected"],
                            key="scaffold_calibration_decision",
                        )
                        cal_reviewer = cal_cols[2].text_input("Reviewer", value="", key="scaffold_calibration_reviewer")
                        cal_note = cal_cols[3].text_input("Evidence note", value="", key="scaffold_calibration_note")
                        if st.button("Append calibration case", width="stretch"):
                            calibration_report = append_workspace_examples_to_calibration_set(
                                workspace_report,
                                [
                                    {
                                        "workspace_key": selected_workspace,
                                        "candidate_id": cal_candidate,
                                        "decision": cal_decision,
                                        "note": cal_note or None,
                                    }
                                ],
                                calibration_path=SCAFFOLD_CALIBRATION_SET_PATH,
                                reviewer=cal_reviewer or None,
                            )
                            st.session_state["scaffold_calibration_append_report"] = calibration_report
                            st.success(
                                f"Calibration cases appended: {calibration_report.get('appended_count', 0)}; "
                                f"skipped: {calibration_report.get('skipped_count', 0)}"
                            )
                        if st.session_state.get("scaffold_calibration_append_report"):
                            st.json(st.session_state["scaffold_calibration_append_report"])
                with st.expander("Scaffold calibration review batch"):
                    batch_cols = st.columns([0.18, 0.26, 0.28, 0.28])
                    template_limit = batch_cols[0].number_input(
                        "Examples per entry",
                        min_value=1,
                        max_value=5,
                        value=1,
                        key="scaffold_batch_examples_per_entry",
                    )
                    template_path = ROOT / "data" / "substituents" / "scaffold_workspace_decisions_streamlit.csv"
                    if batch_cols[1].button("Build decision template", width="stretch"):
                        batch_rows = write_scaffold_workspace_decision_template(
                            workspace_report,
                            template_path,
                            max_examples_per_entry=int(template_limit),
                        )
                        st.session_state["scaffold_workspace_decision_template_rows"] = batch_rows
                        st.session_state["scaffold_workspace_decision_template_path"] = str(template_path)
                    if st.session_state.get("scaffold_workspace_decision_template_rows"):
                        batch_frame = pd.DataFrame(st.session_state["scaffold_workspace_decision_template_rows"])
                        st.dataframe(batch_frame, hide_index=True, width="stretch")
                        st.download_button(
                            "Download scaffold decision template",
                            batch_frame.to_csv(index=False),
                            file_name="scaffold_workspace_decisions.csv",
                            mime="text/csv",
                            width="stretch",
                        )
                    batch_file = batch_cols[2].file_uploader(
                        "Reviewed decision CSV",
                        type=["csv"],
                        key="scaffold_workspace_decision_upload",
                    )
                    batch_reviewer = batch_cols[3].text_input("Batch reviewer", value="", key="scaffold_workspace_decision_reviewer")
                    if batch_file is not None and st.button("Apply scaffold decision batch", width="stretch"):
                        decision_frame = pd.read_csv(batch_file).fillna("")
                        batch_report = append_workspace_examples_to_calibration_set(
                            workspace_report,
                            decision_frame.to_dict("records"),
                            calibration_path=SCAFFOLD_CALIBRATION_SET_PATH,
                            reviewer=batch_reviewer or None,
                        )
                        st.session_state["scaffold_calibration_batch_report"] = batch_report
                        st.success(
                            f"Batch appended: {batch_report.get('appended_count', 0)}; skipped: {batch_report.get('skipped_count', 0)}"
                        )
                    if st.session_state.get("scaffold_calibration_batch_report"):
                        st.json(st.session_state["scaffold_calibration_batch_report"])
                with st.expander("Scaffold calibration audit"):
                    audit_cols = st.columns([0.35, 0.65])
                    if audit_cols[0].button("Build calibration audit", width="stretch"):
                        try:
                            previous_calibration = load_scaffold_calibration_report(SCAFFOLD_CALIBRATION_REPORT_PATH)
                            current_calibration = calibrate_scaffold_rules(load_scaffold_calibration_cases(SCAFFOLD_CALIBRATION_SET_PATH))
                            write_scaffold_calibration_report(current_calibration, SCAFFOLD_CALIBRATION_REPORT_PATH)
                            audit_report = build_scaffold_calibration_audit_report(
                                previous_calibration,
                                current_calibration,
                                workspace_report=workspace_report,
                            )
                            write_scaffold_calibration_audit_report(audit_report, SCAFFOLD_CALIBRATION_AUDIT_PATH)
                            st.session_state["scaffold_calibration_audit_report"] = audit_report
                            st.success("Scaffold calibration audit written.")
                        except Exception as exc:
                            st.error(str(exc))
                    audit_path = SCAFFOLD_CALIBRATION_AUDIT_PATH
                    if "scaffold_calibration_audit_report" not in st.session_state and audit_path.exists():
                        try:
                            st.session_state["scaffold_calibration_audit_report"] = json.loads(audit_path.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    if st.session_state.get("scaffold_calibration_audit_report"):
                        audit_report = st.session_state["scaffold_calibration_audit_report"]
                        audit_cols[1].json(
                            {
                                key: audit_report.get(key)
                                for key in [
                                    "changed_rule_count",
                                    "action_change_count",
                                    "new_rule_signal_count",
                                    "workspace_entry_count",
                                    "suggested_rule_status_change_count",
                                ]
                            }
                        )
                        changed_rules = audit_report.get("changed_rules") or []
                        if changed_rules:
                            st.dataframe(pd.DataFrame(changed_rules), hide_index=True, width="stretch")
                        aligned = audit_report.get("workspace_alignment") or []
                        if aligned:
                            st.dataframe(pd.DataFrame(aligned), hide_index=True, width="stretch")
                        suggestions = audit_report.get("suggested_rule_status_changes") or []
                        if suggestions:
                            st.dataframe(pd.DataFrame(suggestions), hide_index=True, width="stretch")
                            draft_cols = st.columns([0.26, 0.22, 0.22, 0.30])
                            draft_reviewer = draft_cols[0].text_input("Draft reviewer", value="", key="scaffold_review_draft_reviewer")
                            draft_owner = draft_cols[1].text_input("Draft owner", value="", key="scaffold_review_draft_owner")
                            draft_version = draft_cols[2].text_input("Draft version", value="", key="scaffold_review_draft_version")
                            if draft_cols[3].button("Write review drafts", width="stretch"):
                                draft_rows = build_scaffold_rule_review_drafts(
                                    audit_report,
                                    reviewer=draft_reviewer or None,
                                    owner=draft_owner or None,
                                    rule_version=draft_version or None,
                                )
                                write_scaffold_rule_review_drafts(draft_rows, SCAFFOLD_RULE_REVIEW_DRAFTS_PATH)
                                st.session_state["scaffold_rule_review_draft_rows"] = draft_rows
                                st.success(f"Drafted {len(draft_rows)} scaffold review rows; no rule status was applied.")
                            if "scaffold_rule_review_draft_rows" not in st.session_state and SCAFFOLD_RULE_REVIEW_DRAFTS_PATH.exists():
                                try:
                                    st.session_state["scaffold_rule_review_draft_rows"] = load_scaffold_rule_review_drafts(SCAFFOLD_RULE_REVIEW_DRAFTS_PATH)
                                except Exception:
                                    pass
                            draft_rows = st.session_state.get("scaffold_rule_review_draft_rows")
                            if draft_rows:
                                draft_frame = pd.DataFrame(draft_rows)
                                st.dataframe(draft_frame, hide_index=True, width="stretch")
                                pending_drafts = [
                                    row
                                    for row in draft_rows
                                    if str(row.get("draft_status") or "") not in {"applied", "rejected", "retired"}
                                ]
                                if pending_drafts:
                                    bulk_cols = st.columns([0.22, 0.22, 0.22, 0.22, 0.12])
                                    bulk_current = bulk_cols[0].selectbox(
                                        "Bulk current status",
                                        ["draft_not_applied", "deferred", "approved_for_apply", "ready_to_apply"],
                                        key="scaffold_review_bulk_current_status",
                                    )
                                    bulk_confidence = bulk_cols[1].selectbox(
                                        "Bulk confidence",
                                        ["", "high", "medium", "low"],
                                        key="scaffold_review_bulk_confidence",
                                    )
                                    bulk_decision = bulk_cols[2].selectbox(
                                        "Bulk decision",
                                        ["deferred", "rejected", "approved_for_apply", "retired"],
                                        key="scaffold_review_bulk_decision",
                                    )
                                    bulk_note = bulk_cols[3].text_input("Bulk note", value="", key="scaffold_review_bulk_note")
                                    if bulk_cols[4].button("Save bulk", width="stretch"):
                                        bulk_report = bulk_update_scaffold_rule_review_draft_status(
                                            status=bulk_decision,
                                            draft_path=SCAFFOLD_RULE_REVIEW_DRAFTS_PATH,
                                            current_statuses=[bulk_current],
                                            suggestion_confidences=[bulk_confidence] if bulk_confidence else None,
                                            reviewer=draft_reviewer or None,
                                            note=bulk_note or f"UI bulk decision: {bulk_decision}",
                                        )
                                        st.session_state["scaffold_rule_review_draft_rows"] = bulk_report.get("rows") or []
                                        st.session_state["scaffold_rule_review_apply_report"] = {
                                            "processed_count": len(bulk_report.get("rows") or []),
                                            "applied_count": 0,
                                            "skipped_count": bulk_report.get("skipped_count", 0),
                                            "applied_draft_ids": [],
                                            "bulk_updated_count": bulk_report.get("updated_count", 0),
                                        }
                                        st.success(f"Bulk decision saved for {bulk_report.get('updated_count', 0)} scaffold drafts.")
                                    apply_cols = st.columns([0.32, 0.14, 0.14, 0.16, 0.12, 0.12])
                                    selected_draft = apply_cols[0].selectbox(
                                        "Review draft",
                                        pending_drafts,
                                        format_func=lambda row: f"{row.get('draft_id')} | {row.get('scaffold_rule_id')} | {row.get('suggested_status')}",
                                        key="scaffold_review_apply_draft",
                                    )
                                    apply_reviewer = apply_cols[1].text_input("Apply reviewer", value=draft_reviewer or "", key="scaffold_review_apply_reviewer")
                                    apply_owner = apply_cols[2].text_input("Apply owner", value=draft_owner or "", key="scaffold_review_apply_owner")
                                    draft_decision = apply_cols[3].selectbox(
                                        "Draft decision",
                                        ["approved_for_apply", "deferred", "rejected", "retired"],
                                        key="scaffold_review_draft_decision",
                                    )
                                    if apply_cols[4].button("Save decision", width="stretch"):
                                        decision_report = update_scaffold_rule_review_draft_status(
                                            str(selected_draft.get("draft_id")),
                                            status=draft_decision,
                                            draft_path=SCAFFOLD_RULE_REVIEW_DRAFTS_PATH,
                                            reviewer=apply_reviewer or None,
                                            note=f"UI decision: {draft_decision}",
                                        )
                                        st.session_state["scaffold_rule_review_draft_rows"] = decision_report.get("rows") or []
                                        st.session_state["scaffold_rule_review_apply_report"] = {
                                            "processed_count": len(decision_report.get("rows") or []),
                                            "applied_count": 0,
                                            "skipped_count": 0,
                                            "applied_draft_ids": [],
                                            "decision_saved": decision_report.get("status"),
                                        }
                                        st.success(f"Draft decision saved: {draft_decision}")
                                    if apply_cols[5].button("Apply selected", width="stretch"):
                                        apply_report = apply_scaffold_rule_review_drafts(
                                            draft_path=SCAFFOLD_RULE_REVIEW_DRAFTS_PATH,
                                            draft_ids=[str(selected_draft.get("draft_id"))],
                                            reviewer=apply_reviewer or None,
                                            owner=apply_owner or None,
                                            rule_reviews_path=SCAFFOLD_RULE_REVIEWS_PATH,
                                            db_path=DB_PATH,
                                            allow_selected_draft_status=False,
                                        )
                                        st.session_state["scaffold_rule_review_draft_rows"] = apply_report.get("rows") or []
                                        st.session_state["scaffold_rule_review_apply_report"] = apply_report
                                        refreshed_workspace = build_scaffold_review_workspace_report(
                                            db_path=DB_PATH,
                                            project_name=None,
                                            scaffold_rules_path=SCAFFOLD_RULES_PATH,
                                            scaffold_rule_reviews_path=SCAFFOLD_RULE_REVIEWS_PATH,
                                        )
                                        write_scaffold_review_workspace_report(refreshed_workspace, SCAFFOLD_WORKSPACE_REPORT_PATH)
                                        previous_calibration = load_scaffold_calibration_report(SCAFFOLD_CALIBRATION_REPORT_PATH) if SCAFFOLD_CALIBRATION_REPORT_PATH.exists() else {}
                                        refreshed_calibration = calibrate_scaffold_rules(load_scaffold_calibration_cases(SCAFFOLD_CALIBRATION_SET_PATH))
                                        write_scaffold_calibration_report(refreshed_calibration, SCAFFOLD_CALIBRATION_REPORT_PATH)
                                        refreshed_audit = build_scaffold_calibration_audit_report(
                                            previous_calibration,
                                            refreshed_calibration,
                                            workspace_report=refreshed_workspace,
                                        )
                                        write_scaffold_calibration_audit_report(refreshed_audit, SCAFFOLD_CALIBRATION_AUDIT_PATH)
                                        refreshed_gate = build_closed_loop_promotion_gate(root=ROOT, project_name="demo_learning")
                                        write_closed_loop_promotion_gate(refreshed_gate, CLOSED_LOOP_PROMOTION_GATE_PATH)
                                        st.session_state["scaffold_workspace_report"] = refreshed_workspace
                                        st.session_state["scaffold_calibration_report"] = refreshed_calibration
                                        st.session_state["scaffold_calibration_audit_report"] = refreshed_audit
                                        st.session_state["closed_loop_promotion_gate"] = refreshed_gate
                                        st.success(f"Applied {apply_report.get('applied_count', 0)} scaffold draft through rule review.")
                                if st.session_state.get("scaffold_rule_review_apply_report"):
                                    st.json(
                                        {
                                            key: st.session_state["scaffold_rule_review_apply_report"].get(key)
                                            for key in ["processed_count", "applied_count", "skipped_count", "applied_draft_ids"]
                                        }
                                    )
                                st.download_button(
                                    "Download scaffold review drafts",
                                    data=draft_frame.to_csv(index=False),
                                    file_name="scaffold_rule_review_drafts.csv",
                                    mime="text/csv",
                                    width="stretch",
                                )
        scaffold_rules = load_scaffold_replacements(SCAFFOLD_RULES_PATH)
        review_data = load_scaffold_rule_reviews(SCAFFOLD_RULE_REVIEWS_PATH)
        review_lookup = scaffold_rule_review_lookup(review_data)
        scaffold_review_rows = []
        for rule in scaffold_rules:
            review = review_lookup.get(str(rule.get("scaffold_rule_id"))) or {}
            scaffold_review_rows.append(
                {
                    "scaffold_rule_id": rule.get("scaffold_rule_id"),
                    "name": rule.get("name"),
                    "replacement_class": rule.get("replacement_class"),
                    "attachment_count": rule.get("attachment_count"),
                    "review_status": review.get("status", "active"),
                    "resolution_status": review.get("resolution_status", "open"),
                    "owner": review.get("owner"),
                    "score_adjustment": review.get("score_adjustment", 0.0),
                    "reviewed_by": review.get("reviewed_by"),
                    "rule_version": review.get("rule_version"),
                    "review_note": review.get("note"),
                }
            )
        if scaffold_review_rows:
            st.dataframe(pd.DataFrame(scaffold_review_rows), hide_index=True, width="stretch")
            selected_scaffold_rule = st.selectbox(
                "Scaffold rule",
                [row["scaffold_rule_id"] for row in scaffold_review_rows],
                format_func=lambda rid: f"{rid} | {next(row['name'] for row in scaffold_review_rows if row['scaffold_rule_id'] == rid)}",
            )
            selected_review = review_lookup.get(str(selected_scaffold_rule)) or {}
            sr_cols = st.columns([0.13, 0.13, 0.16, 0.18, 0.18, 0.14, 0.08])
            scaffold_status = sr_cols[0].selectbox(
                "Rule status",
                SCAFFOLD_RULE_REVIEW_STATUSES,
                index=SCAFFOLD_RULE_REVIEW_STATUSES.index(selected_review.get("status", "active"))
                if selected_review.get("status", "active") in SCAFFOLD_RULE_REVIEW_STATUSES
                else 0,
                key="scaffold_rule_status",
            )
            scaffold_adjustment = sr_cols[1].number_input(
                "Score adjust",
                min_value=-40.0,
                max_value=40.0,
                value=float(selected_review.get("score_adjustment") or 0.0),
                step=2.5,
                key="scaffold_rule_adjustment",
            )
            scaffold_resolution = sr_cols[2].selectbox(
                "Resolution",
                SCAFFOLD_RULE_RESOLUTION_STATUSES,
                index=SCAFFOLD_RULE_RESOLUTION_STATUSES.index(selected_review.get("resolution_status", "open"))
                if selected_review.get("resolution_status", "open") in SCAFFOLD_RULE_RESOLUTION_STATUSES
                else 0,
                key="scaffold_rule_resolution",
            )
            scaffold_owner = sr_cols[3].text_input("Owner", value=selected_review.get("owner") or "", key="scaffold_rule_owner")
            scaffold_reviewer = sr_cols[4].text_input("Reviewer", value=selected_review.get("reviewed_by") or "", key="scaffold_rule_reviewer")
            scaffold_version = sr_cols[5].text_input("Version", value=selected_review.get("rule_version") or review_data.get("version") or "", key="scaffold_rule_version")
            scaffold_note = st.text_input("Rule note", value=selected_review.get("note") or "", key="scaffold_rule_note")
            if sr_cols[6].button("Save", width="stretch", key="save_scaffold_rule_review"):
                update_scaffold_rule_review(
                    selected_scaffold_rule,
                    status=scaffold_status,
                    reviewer=scaffold_reviewer or None,
                    owner=scaffold_owner or None,
                    resolution_status=scaffold_resolution,
                    rule_version=scaffold_version or None,
                    note=scaffold_note or None,
                    score_adjustment=float(scaffold_adjustment),
                    path=SCAFFOLD_RULE_REVIEWS_PATH,
                    db_path=DB_PATH,
                )
                st.success("Scaffold rule review saved.")
            with st.expander("Scaffold rule audit trail"):
                event_limit = st.number_input("Audit rows", min_value=10, max_value=500, value=100, step=10, key="scaffold_audit_limit")
                audit_rule_filter = st.checkbox("Only selected rule", value=True, key="scaffold_audit_selected_only")
                audit_rows = list_scaffold_rule_review_events(
                    db_path=DB_PATH,
                    scaffold_rule_id=str(selected_scaffold_rule) if audit_rule_filter else None,
                    limit=int(event_limit),
                )
                if audit_rows:
                    st.dataframe(pd.DataFrame(audit_rows).drop(columns=["payload_json"], errors="ignore"), hide_index=True, width="stretch")
                else:
                    st.caption("No scaffold rule review events in SQLite yet.")
    with g5:
        review_rows = load_sample_review_queue(RGROUP_FEED_SAMPLE_REVIEW_QUEUE_PATH)
        review_summary = summarize_sample_review_queue(review_rows)
        fr1, fr2, fr3, fr4 = st.columns(4)
        fr1.metric("Review rows", review_summary.get("row_count", 0))
        fr2.metric("Pending", review_summary.get("pending_count", 0))
        fr3.metric("Sources", len(review_summary.get("source_dataset_counts") or {}))
        fr4.metric("Strata", review_summary.get("sample_stratum_count", 0))
        if RGROUP_FEED_METADATA_REPORT_PATH.exists():
            try:
                metadata_report = json.loads(RGROUP_FEED_METADATA_REPORT_PATH.read_text(encoding="utf-8"))
                meta_cols = st.columns(4)
                meta_cols[0].metric("Feed files", metadata_report.get("feed_count", 0))
                meta_cols[1].metric("Feed rows", metadata_report.get("row_count", 0))
                meta_cols[2].metric("Allowlist issues", metadata_report.get("allowlist_issue_count", 0))
                meta_cols[3].metric("Freshness issues", metadata_report.get("freshness_issue_count", 0))
            except Exception as exc:
                st.warning(str(exc))
        queue_io_cols = st.columns([0.22, 0.24, 0.30, 0.24])
        if RGROUP_FEED_SAMPLE_REVIEW_QUEUE_PATH.exists():
            queue_io_cols[0].download_button(
                "Download review queue",
                RGROUP_FEED_SAMPLE_REVIEW_QUEUE_PATH.read_text(encoding="utf-8"),
                file_name="rgroup_feed_sample_review_queue.csv",
                mime="text/csv",
                width="stretch",
            )
        if RGROUP_FEED_REVIEW_COVERAGE_CSV_PATH.exists():
            queue_io_cols[1].download_button(
                "Download coverage CSV",
                RGROUP_FEED_REVIEW_COVERAGE_CSV_PATH.read_text(encoding="utf-8"),
                file_name="rgroup_feed_review_coverage.csv",
                mime="text/csv",
                width="stretch",
            )
        reviewed_queue_file = queue_io_cols[2].file_uploader(
            "Reviewed queue CSV",
            type=["csv"],
            key="rgroup_feed_review_queue_upload",
        )
        upload_reviewer = queue_io_cols[3].text_input("Upload reviewer", value="", key="rgroup_feed_review_upload_reviewer")
        if reviewed_queue_file is not None and st.button("Apply uploaded review CSV", width="stretch"):
            uploaded_frame = pd.read_csv(reviewed_queue_file).fillna("")
            valid_decisions = {"accepted", "deferred", "rejected", "retired"}
            applied = []
            skipped = 0
            for row in uploaded_frame.to_dict("records"):
                decision = str(row.get("review_decision") or "").strip().lower()
                if decision not in valid_decisions:
                    skipped += 1
                    continue
                key = sample_review_row_key(row)
                if not key:
                    skipped += 1
                    continue
                applied.append(
                    bulk_update_sample_review_queue(
                        RGROUP_FEED_SAMPLE_REVIEW_QUEUE_PATH,
                        row_keys=[key],
                        review_decision=decision,
                        reviewer=str(row.get("reviewer") or upload_reviewer or "streamlit_upload"),
                        review_notes=str(row.get("review_notes") or ""),
                        write=True,
                    )
                )
            st.session_state["rgroup_feed_review_uploaded_apply_report"] = {
                "uploaded_row_count": len(uploaded_frame),
                "applied_row_count": sum(int(row.get("updated_count") or 0) for row in applied),
                "skipped_row_count": skipped,
            }
            st.success(
                f"Applied {st.session_state['rgroup_feed_review_uploaded_apply_report']['applied_row_count']} uploaded decisions."
            )
        if st.session_state.get("rgroup_feed_review_uploaded_apply_report"):
            st.json(st.session_state["rgroup_feed_review_uploaded_apply_report"])
        cov_cols = st.columns([0.22, 0.18, 0.18, 0.18, 0.24])
        if cov_cols[0].button("Build review coverage", width="stretch"):
            coverage_report = build_sample_review_coverage(review_rows)
            write_sample_review_coverage_report(
                coverage_report,
                json_path=RGROUP_FEED_REVIEW_COVERAGE_PATH,
                csv_path=RGROUP_FEED_REVIEW_COVERAGE_CSV_PATH,
            )
            st.session_state["rgroup_feed_review_coverage"] = coverage_report
        if RGROUP_FEED_REVIEW_COVERAGE_PATH.exists() and "rgroup_feed_review_coverage" not in st.session_state:
            try:
                st.session_state["rgroup_feed_review_coverage"] = json.loads(RGROUP_FEED_REVIEW_COVERAGE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        coverage = st.session_state.get("rgroup_feed_review_coverage")
        if coverage:
            cov_cols[1].metric("Coverage cells", coverage.get("coverage_cell_count", 0))
            cov_cols[2].metric("No review", coverage.get("no_review_count", 0))
            cov_cols[3].metric("Low coverage", coverage.get("low_coverage_count", 0))
            cov_cols[4].metric("Covered", coverage.get("covered_count", 0))
            coverage_rows = coverage.get("rows") or []
            if coverage_rows:
                with st.expander("Review coverage heatmap rows"):
                    st.dataframe(pd.DataFrame(coverage_rows), hide_index=True, width="stretch")
        governance_delta_cols = st.columns([0.25, 0.25, 0.25, 0.25])
        if DATA_FOUNDATION_REPORT_PATH.exists():
            try:
                foundation_report = json.loads(DATA_FOUNDATION_REPORT_PATH.read_text(encoding="utf-8"))
                feed_governance = foundation_report.get("rgroup_feed_governance") or {}
                governance_delta_cols[0].metric("Feed row delta", feed_governance.get("row_count_delta", 0))
                governance_delta_cols[1].metric("Provenance complete", feed_governance.get("row_level_provenance_count", 0))
            except Exception:
                pass
        if WEEKLY_RELEASE_DIFF_PATH.exists():
            try:
                weekly_report = json.loads(WEEKLY_RELEASE_DIFF_PATH.read_text(encoding="utf-8"))
                workspace_delta = (weekly_report.get("normalized_pair_deltas") or {}).get("workspace_since_head") or {}
                governance_delta_cols[2].metric("Pair added", workspace_delta.get("added_count", 0))
                governance_delta_cols[3].metric("Pair changed", workspace_delta.get("changed_count", 0))
                top_changed = workspace_delta.get("top_changed") or []
                top_added = workspace_delta.get("top_added") or []
                if top_changed or top_added:
                    with st.expander("Normalized pair delta leaders"):
                        st.dataframe(pd.DataFrame((top_changed + top_added)[:50]), hide_index=True, width="stretch")
            except Exception:
                pass
        contradiction_cols = st.columns([0.22, 0.16, 0.16, 0.16, 0.15, 0.15])
        if contradiction_cols[0].button("Build pair conflict queue", width="stretch"):
            pair_conflicts = build_rgroup_normalized_pair_contradiction_report(db_path=DB_PATH)
            write_rgroup_normalized_pair_contradiction_report(
                pair_conflicts,
                RGROUP_PAIR_CONTRADICTION_PATH,
                csv_path=RGROUP_PAIR_CONTRADICTION_CSV_PATH,
            )
            st.session_state["rgroup_pair_contradictions"] = pair_conflicts
        if contradiction_cols[4].button("First-pass classify", width="stretch", key="first_pass_pair_conflicts"):
            summary = apply_rgroup_pair_contradiction_first_pass(
                RGROUP_PAIR_CONTRADICTION_PATH,
                reviewer="streamlit_pair_conflict_triage",
                review_path=RGROUP_PAIR_CONTRADICTION_REVIEW_PATH,
            )
            write_rgroup_pair_contradiction_decision_summary(summary, RGROUP_PAIR_CONTRADICTION_DECISION_PATH)
            pair_conflicts = build_rgroup_normalized_pair_contradiction_report(db_path=DB_PATH)
            write_rgroup_normalized_pair_contradiction_report(
                pair_conflicts,
                RGROUP_PAIR_CONTRADICTION_PATH,
                csv_path=RGROUP_PAIR_CONTRADICTION_CSV_PATH,
            )
            st.session_state["rgroup_pair_contradictions"] = pair_conflicts
            st.session_state["rgroup_pair_contradiction_decisions"] = summary
        if RGROUP_PAIR_CONTRADICTION_PATH.exists() and "rgroup_pair_contradictions" not in st.session_state:
            try:
                st.session_state["rgroup_pair_contradictions"] = json.loads(RGROUP_PAIR_CONTRADICTION_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if RGROUP_PAIR_CONTRADICTION_DECISION_PATH.exists() and "rgroup_pair_contradiction_decisions" not in st.session_state:
            try:
                st.session_state["rgroup_pair_contradiction_decisions"] = json.loads(RGROUP_PAIR_CONTRADICTION_DECISION_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        pair_conflicts = st.session_state.get("rgroup_pair_contradictions") or {}
        pair_decisions = st.session_state.get("rgroup_pair_contradiction_decisions") or {}
        if pair_conflicts:
            contradiction_cols[1].metric("Pair conflicts", pair_conflicts.get("row_count", 0))
            contradiction_cols[2].metric("High", pair_conflicts.get("high_priority_count", 0))
            contradiction_cols[3].metric("Open high", pair_decisions.get("open_high_priority_count", pair_conflicts.get("open_high_priority_count", 0)))
            if RGROUP_PAIR_CONTRADICTION_CSV_PATH.exists():
                contradiction_cols[5].download_button(
                    "Download pair conflicts",
                    RGROUP_PAIR_CONTRADICTION_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="rgroup_normalized_pair_contradictions.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if pair_decisions:
                with st.expander("Pair conflict decision summary"):
                    st.json(pair_decisions, expanded=False)
            if pair_conflicts.get("rows"):
                with st.expander("R-group pair conflict queue"):
                    st.dataframe(pd.DataFrame(pair_conflicts["rows"]).head(100), hide_index=True, width="stretch")
        with st.expander("Source-owner conflict decisions", expanded=False):
            owner_cols = st.columns([0.22, 0.22, 0.22, 0.34])
            if owner_cols[0].button("Build owner packet", width="stretch"):
                packet = build_rgroup_pair_conflict_owner_review_packet(
                    RGROUP_PAIR_CONTRADICTION_PATH,
                    review_path=RGROUP_PAIR_CONTRADICTION_REVIEW_PATH,
                    owner_decision_ledger_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH,
                )
                write_rgroup_pair_conflict_owner_review_packet(
                    packet,
                    json_path=RGROUP_PAIR_OWNER_REVIEW_PACKET_PATH,
                    csv_path=RGROUP_PAIR_OWNER_REVIEW_PACKET_CSV_PATH,
                )
                st.session_state["rgroup_pair_owner_packet"] = packet
            if owner_cols[1].button("Keep deferred", width="stretch"):
                packet = build_rgroup_pair_conflict_owner_review_packet(
                    RGROUP_PAIR_CONTRADICTION_PATH,
                    review_path=RGROUP_PAIR_CONTRADICTION_REVIEW_PATH,
                    owner_decision_ledger_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH,
                )
                ledger = build_rgroup_pair_conflict_owner_decision_ledger(
                    packet,
                    reviewer="streamlit_owner_ledger",
                    mark_all_keep_deferred=True,
                    apply_to_reviews=True,
                    review_path=RGROUP_PAIR_CONTRADICTION_REVIEW_PATH,
                    contradiction_report=RGROUP_PAIR_CONTRADICTION_PATH,
                )
                write_rgroup_pair_conflict_owner_decision_ledger(
                    ledger,
                    json_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_PATH,
                    csv_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH,
                )
                refreshed_packet = build_rgroup_pair_conflict_owner_review_packet(
                    RGROUP_PAIR_CONTRADICTION_PATH,
                    review_path=RGROUP_PAIR_CONTRADICTION_REVIEW_PATH,
                    owner_decision_ledger_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH,
                )
                write_rgroup_pair_conflict_owner_review_packet(
                    refreshed_packet,
                    json_path=RGROUP_PAIR_OWNER_REVIEW_PACKET_PATH,
                    csv_path=RGROUP_PAIR_OWNER_REVIEW_PACKET_CSV_PATH,
                )
                st.session_state["rgroup_pair_owner_ledger"] = ledger
                st.session_state["rgroup_pair_owner_packet"] = refreshed_packet
            uploaded_owner_ledger = owner_cols[2].file_uploader("Owner ledger CSV", type=["csv"], key="rgroup_owner_ledger_upload")
            if uploaded_owner_ledger is not None and owner_cols[3].button("Apply owner ledger", width="stretch"):
                RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
                RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH.write_bytes(uploaded_owner_ledger.getvalue())
                packet = build_rgroup_pair_conflict_owner_review_packet(
                    RGROUP_PAIR_CONTRADICTION_PATH,
                    review_path=RGROUP_PAIR_CONTRADICTION_REVIEW_PATH,
                    owner_decision_ledger_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH,
                )
                ledger = build_rgroup_pair_conflict_owner_decision_ledger(
                    packet,
                    reviewer="streamlit_owner_ledger_upload",
                    apply_to_reviews=True,
                    review_path=RGROUP_PAIR_CONTRADICTION_REVIEW_PATH,
                    contradiction_report=RGROUP_PAIR_CONTRADICTION_PATH,
                )
                write_rgroup_pair_conflict_owner_decision_ledger(
                    ledger,
                    json_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_PATH,
                    csv_path=RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH,
                )
                write_rgroup_pair_conflict_owner_review_packet(
                    packet,
                    json_path=RGROUP_PAIR_OWNER_REVIEW_PACKET_PATH,
                    csv_path=RGROUP_PAIR_OWNER_REVIEW_PACKET_CSV_PATH,
                )
                st.session_state["rgroup_pair_owner_ledger"] = ledger
                st.session_state["rgroup_pair_owner_packet"] = packet
            for state_key, path in [
                ("rgroup_pair_owner_packet", RGROUP_PAIR_OWNER_REVIEW_PACKET_PATH),
                ("rgroup_pair_owner_ledger", RGROUP_PAIR_OWNER_DECISION_LEDGER_PATH),
            ]:
                if path.exists() and state_key not in st.session_state:
                    try:
                        st.session_state[state_key] = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            owner_packet = st.session_state.get("rgroup_pair_owner_packet") or {}
            owner_ledger = st.session_state.get("rgroup_pair_owner_ledger") or {}
            owner_metrics = st.columns(5)
            owner_metrics[0].metric("Packet", owner_packet.get("status", "missing"))
            owner_metrics[1].metric("Deferred", owner_packet.get("deferred_conflict_count", 0))
            owner_metrics[2].metric("Pending owner", owner_packet.get("pending_owner_review_count", 0))
            owner_metrics[3].metric("Ledger", owner_ledger.get("status", "missing"))
            owner_metrics[4].metric("Ledger rows", owner_ledger.get("row_count", 0))
            download_cols = st.columns(2)
            if RGROUP_PAIR_OWNER_REVIEW_PACKET_CSV_PATH.exists():
                download_cols[0].download_button(
                    "Download owner packet",
                    RGROUP_PAIR_OWNER_REVIEW_PACKET_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="rgroup_pair_conflict_owner_review_packet.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH.exists():
                download_cols[1].download_button(
                    "Download owner ledger",
                    RGROUP_PAIR_OWNER_DECISION_LEDGER_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="rgroup_pair_conflict_owner_decision_ledger.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if owner_packet.get("rows"):
                st.dataframe(pd.DataFrame(owner_packet["rows"]).head(100), hide_index=True, width="stretch")
        with st.expander("Next feed-drop staging", expanded=False):
            staging_cols = st.columns([0.22, 0.22, 0.22, 0.34])
            if staging_cols[0].button("Refresh onboarding gate", width="stretch"):
                onboarding = build_rgroup_feed_onboarding_gate()
                write_rgroup_feed_onboarding_gate(
                    onboarding,
                    json_path=RGROUP_FEED_ONBOARDING_GATE_PATH,
                    csv_path=RGROUP_FEED_ONBOARDING_GATE_CSV_PATH,
                )
                st.session_state["rgroup_feed_onboarding_gate"] = onboarding
            if staging_cols[1].button("Prepare staging", width="stretch"):
                staging = build_rgroup_feed_drop_staging_package(output_dir=RGROUP_FEED_DROP_STAGING_DIR)
                write_rgroup_feed_drop_staging_report(
                    staging,
                    json_path=RGROUP_FEED_DROP_STAGING_PATH,
                    csv_path=RGROUP_FEED_DROP_STAGING_CSV_PATH,
                )
                st.session_state["rgroup_feed_drop_staging"] = staging
            if staging_cols[2].button("Validate staging", width="stretch"):
                staging_gate = build_rgroup_feed_drop_staging_gate(
                    staging_report_path=RGROUP_FEED_DROP_STAGING_PATH,
                    staging_dir=RGROUP_FEED_DROP_STAGING_DIR,
                )
                write_rgroup_feed_drop_staging_gate(
                    staging_gate,
                    json_path=RGROUP_FEED_DROP_STAGING_GATE_PATH,
                    csv_path=RGROUP_FEED_DROP_STAGING_GATE_CSV_PATH,
                )
                st.session_state["rgroup_feed_drop_staging_gate"] = staging_gate
            for state_key, path in [
                ("rgroup_feed_onboarding_gate", RGROUP_FEED_ONBOARDING_GATE_PATH),
                ("rgroup_feed_drop_staging", RGROUP_FEED_DROP_STAGING_PATH),
                ("rgroup_feed_drop_staging_gate", RGROUP_FEED_DROP_STAGING_GATE_PATH),
            ]:
                if path.exists() and state_key not in st.session_state:
                    try:
                        st.session_state[state_key] = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            onboarding = st.session_state.get("rgroup_feed_onboarding_gate") or {}
            staging = st.session_state.get("rgroup_feed_drop_staging") or {}
            staging_gate = st.session_state.get("rgroup_feed_drop_staging_gate") or {}
            staging_metrics = st.columns(6)
            staging_metrics[0].metric("Onboarding", onboarding.get("status", "missing"))
            staging_metrics[1].metric("Feeds", onboarding.get("feed_file_count", 0))
            staging_metrics[2].metric("Staging", staging.get("status", "missing"))
            staging_metrics[3].metric("Templates", staging.get("template_file_count", 0))
            staging_metrics[4].metric("Gate", staging_gate.get("status", "missing"))
            staging_metrics[5].metric("Staged rows", staging_gate.get("staged_row_count", 0))
            if staging.get("rows"):
                st.dataframe(pd.DataFrame(staging["rows"]), hide_index=True, width="stretch")
            if staging_gate.get("rows"):
                st.dataframe(pd.DataFrame(staging_gate["rows"]), hide_index=True, width="stretch")
            staging_download_cols = st.columns(3)
            manifest_path = Path(staging.get("manifest_path") or RGROUP_FEED_DROP_STAGING_DIR / "feed_drop_manifest.yaml")
            if manifest_path.exists():
                staging_download_cols[0].download_button(
                    "Download staging manifest",
                    manifest_path.read_text(encoding="utf-8"),
                    file_name="feed_drop_manifest.yaml",
                    mime="text/yaml",
                    width="stretch",
                )
            if RGROUP_FEED_DROP_STAGING_CSV_PATH.exists():
                staging_download_cols[1].download_button(
                    "Download staging CSV",
                    RGROUP_FEED_DROP_STAGING_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="rgroup_next_feed_drop_staging.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if RGROUP_FEED_DROP_STAGING_GATE_CSV_PATH.exists():
                staging_download_cols[2].download_button(
                    "Download staging gate",
                    RGROUP_FEED_DROP_STAGING_GATE_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="rgroup_next_feed_drop_staging_gate.csv",
                    mime="text/csv",
                    width="stretch",
                )
        if review_rows:
            source_options = ["", *sorted(review_summary.get("source_dataset_counts") or {})]
            decision_options = ["", "pending", "accepted", "deferred", "rejected", "retired"]
            filt_cols = st.columns([0.22, 0.18, 0.22, 0.22, 0.16])
            feed_source = filt_cols[0].selectbox("Source dataset", source_options, key="rgroup_feed_review_source")
            feed_decision = filt_cols[1].selectbox("Decision", decision_options, key="rgroup_feed_review_decision_filter")
            feed_reason = filt_cols[2].text_input("Reason contains", value="", key="rgroup_feed_review_reason")
            feed_stratum = filt_cols[3].text_input("Stratum contains", value="", key="rgroup_feed_review_stratum")
            max_review_rows = filt_cols[4].number_input("Display rows", min_value=10, max_value=500, value=80, step=10)
            filtered_review_rows = filter_sample_review_queue(
                review_rows,
                source_dataset=feed_source or None,
                review_decision=feed_decision or None,
                sample_reason_contains=feed_reason or None,
                sample_stratum_contains=feed_stratum or None,
            )
            st.caption(f"Filtered rows: {len(filtered_review_rows)}")
            if filtered_review_rows:
                review_frame = pd.DataFrame(filtered_review_rows)
                preferred_cols = [
                    "replacement_id",
                    "source_dataset",
                    "source_smiles",
                    "target_smiles",
                    "sample_reason",
                    "sample_stratum",
                    "review_decision",
                    "reviewer",
                    "review_notes",
                ]
                st.dataframe(review_frame[[col for col in preferred_cols if col in review_frame.columns]].head(int(max_review_rows)), hide_index=True, width="stretch")
                bulk_cols = st.columns([0.18, 0.20, 0.44, 0.18])
                bulk_decision = bulk_cols[0].selectbox(
                    "Bulk decision",
                    ["accepted", "deferred", "rejected", "retired"],
                    key="rgroup_feed_review_bulk_decision",
                )
                bulk_reviewer = bulk_cols[1].text_input("Reviewer", value="", key="rgroup_feed_review_bulk_reviewer")
                bulk_note = bulk_cols[2].text_input("Review note", value="", key="rgroup_feed_review_bulk_note")
                if bulk_cols[3].button("Mark filtered", width="stretch"):
                    keys = [sample_review_row_key(row) for row in filtered_review_rows]
                    update_report = bulk_update_sample_review_queue(
                        RGROUP_FEED_SAMPLE_REVIEW_QUEUE_PATH,
                        row_keys=keys,
                        review_decision=bulk_decision,
                        reviewer=bulk_reviewer or "streamlit",
                        review_notes=bulk_note,
                        write=True,
                    )
                    st.session_state["rgroup_feed_review_update_report"] = update_report
                    st.success(f"Updated {update_report.get('updated_count', 0)} review rows.")
                if st.session_state.get("rgroup_feed_review_update_report"):
                    st.json(st.session_state["rgroup_feed_review_update_report"])
            apply_cols = st.columns([0.26, 0.24, 0.50])
            if apply_cols[0].button("Apply review decisions", type="primary", width="stretch"):
                cmd = [
                    sys.executable,
                    str(ROOT / "scripts" / "govern_rgroup_feed_metadata.py"),
                    "--apply-sample-review",
                    "--sample-review-in",
                    str(RGROUP_FEED_SAMPLE_REVIEW_QUEUE_PATH),
                    "--sample-review-apply-report-out",
                    str(RGROUP_FEED_SAMPLE_REVIEW_APPLY_REPORT_PATH),
                    "--write",
                ]
                completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
                st.session_state["rgroup_feed_review_apply_stdout"] = completed.stdout
                st.session_state["rgroup_feed_review_apply_stderr"] = completed.stderr
                st.session_state["rgroup_feed_review_apply_returncode"] = completed.returncode
                if completed.returncode == 0 and RGROUP_FEED_SAMPLE_REVIEW_APPLY_REPORT_PATH.exists():
                    st.session_state["rgroup_feed_review_apply_report"] = json.loads(
                        RGROUP_FEED_SAMPLE_REVIEW_APPLY_REPORT_PATH.read_text(encoding="utf-8")
                    )
                    st.success("Review decisions applied to source feeds.")
                else:
                    st.error(completed.stderr or completed.stdout or "Review apply failed.")
            if apply_cols[1].button("Refresh feed metadata", width="stretch"):
                cmd = [
                    sys.executable,
                    str(ROOT / "scripts" / "govern_rgroup_feed_metadata.py"),
                    "--write",
                    "--require-allowlist",
                ]
                completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
                if completed.returncode == 0 and RGROUP_FEED_METADATA_REPORT_PATH.exists():
                    st.session_state["rgroup_feed_metadata_report"] = json.loads(RGROUP_FEED_METADATA_REPORT_PATH.read_text(encoding="utf-8"))
                    st.success("Feed metadata refreshed.")
                else:
                    st.error(completed.stderr or completed.stdout or "Feed metadata refresh failed.")
            if st.session_state.get("rgroup_feed_review_apply_report"):
                apply_cols[2].json(
                    {
                        key: st.session_state["rgroup_feed_review_apply_report"].get(key)
                        for key in ["queue_row_count", "decision_count", "applied_count", "unmatched_count", "write"]
                    }
                )
        else:
            st.info("No R-group feed sample-review queue was found.")
        st.subheader("Ring Outcome Scoring Overlay")
        overlay_cols = st.columns([0.24, 0.24, 0.24, 0.28])
        if overlay_cols[0].button("Refresh ring outcomes", width="stretch"):
            ring_report = build_ring_outcome_learning_report(db_path=DB_PATH, project_name=None)
            write_ring_outcome_learning_report(
                ring_report,
                json_path=RING_OUTCOME_LEARNING_REPORT_PATH,
                csv_path=RING_OUTCOME_LEARNING_CSV_PATH,
            )
            st.session_state["ring_outcome_learning_report"] = ring_report
        if RING_OUTCOME_LEARNING_REPORT_PATH.exists() and "ring_outcome_learning_report" not in st.session_state:
            try:
                st.session_state["ring_outcome_learning_report"] = json.loads(RING_OUTCOME_LEARNING_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if overlay_cols[1].button("Build scoring overlay", width="stretch"):
            source_report = st.session_state.get("ring_outcome_learning_report") or (
                json.loads(RING_OUTCOME_LEARNING_REPORT_PATH.read_text(encoding="utf-8"))
                if RING_OUTCOME_LEARNING_REPORT_PATH.exists()
                else {}
            )
            overlay = build_ring_outcome_scoring_overlay(
                source_report,
                review_path=RING_OUTCOME_OVERLAY_REVIEW_PATH,
                policy_path=RING_OUTCOME_MATURATION_POLICY_PATH,
                min_observed=3,
                require_approved_review=True,
            )
            write_ring_outcome_scoring_overlay(
                overlay,
                json_path=RING_OUTCOME_OVERLAY_PATH,
                csv_path=RING_OUTCOME_OVERLAY_CSV_PATH,
            )
            st.session_state["ring_outcome_scoring_overlay"] = overlay
        if RING_OUTCOME_OVERLAY_PATH.exists() and "ring_outcome_scoring_overlay" not in st.session_state:
            try:
                st.session_state["ring_outcome_scoring_overlay"] = json.loads(RING_OUTCOME_OVERLAY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        overlay = st.session_state.get("ring_outcome_scoring_overlay")
        source_report = st.session_state.get("ring_outcome_learning_report")
        if source_report:
            overlay_cols[2].metric("Outcome groups", source_report.get("group_count", 0))
            overlay_cols[3].metric("Observed outcomes", source_report.get("observed_outcome_count", 0))
        if overlay:
            ov1, ov2, ov3 = st.columns(3)
            ov1.metric("Overlay contexts", overlay.get("context_count", 0))
            ov2.metric("Active", overlay.get("active_context_count", 0))
            ov3.metric("Blocked", overlay.get("blocked_context_count", 0))
            contexts = overlay.get("contexts") or []
            if contexts:
                st.dataframe(pd.DataFrame(contexts), hide_index=True, width="stretch")
                review_template_cols = st.columns([0.22, 0.20, 0.20, 0.28, 0.10])
                if review_template_cols[0].button("Build overlay review CSV", width="stretch"):
                    review_template = build_ring_outcome_overlay_review_template(
                        overlay,
                        review_path=RING_OUTCOME_OVERLAY_REVIEW_PATH,
                        replay=RING_OUTCOME_OVERLAY_REPLAY_PATH if RING_OUTCOME_OVERLAY_REPLAY_PATH.exists() else None,
                    )
                    write_ring_outcome_overlay_review_template(review_template, RING_OUTCOME_OVERLAY_REVIEW_PATH)
                    st.session_state["ring_outcome_overlay_review_template"] = review_template
                    st.success(f"Overlay review rows: {review_template.get('row_count', 0)}")
                selected_context = review_template_cols[1].selectbox(
                    "Overlay context",
                    contexts,
                    format_func=lambda row: f"{row.get('context_id')} | {row.get('endpoint')} | {row.get('gate_status')}",
                    key="ring_overlay_review_context",
                )
                overlay_decision = review_template_cols[2].selectbox(
                    "Decision",
                    ["pending_review", "approved", "deferred", "rejected"],
                    key="ring_overlay_review_decision",
                )
                overlay_note = review_template_cols[3].text_input("Overlay note", value="", key="ring_overlay_review_note")
                if review_template_cols[4].button("Save", width="stretch", key="save_ring_overlay_review"):
                    try:
                        update = update_ring_outcome_overlay_review(
                            str(selected_context.get("context_id")),
                            decision=overlay_decision,
                            reviewer="streamlit",
                            review_note=overlay_note,
                            approved_score_adjustment=selected_context.get("proposed_score_adjustment"),
                            review_path=RING_OUTCOME_OVERLAY_REVIEW_PATH,
                            overlay=overlay,
                            replay=RING_OUTCOME_OVERLAY_REPLAY_PATH if RING_OUTCOME_OVERLAY_REPLAY_PATH.exists() else None,
                            require_replay=overlay_decision == "approved",
                        )
                        st.success(f"Overlay review saved: {update.get('decision')}")
                    except Exception as exc:
                        st.warning(str(exc))
            task_cols = st.columns([0.28, 0.20, 0.20, 0.32])
            if task_cols[0].button("Build ring follow-up tasks", width="stretch"):
                ring_task_report = build_ring_outcome_residual_tasks(overlay)
                write_ring_outcome_residual_tasks(
                    ring_task_report,
                    json_path=RING_OUTCOME_RESIDUAL_TASKS_PATH,
                    csv_path=RING_OUTCOME_RESIDUAL_TASKS_CSV_PATH,
                )
                merged_registry = merge_ring_outcome_tasks_into_registry(
                    ring_task_report,
                    existing_registry=load_evidence_residual_task_registry(EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH),
                    reviewer="streamlit",
                )
                write_evidence_residual_task_registry(
                    merged_registry,
                    EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                    csv_path=ROOT / "data" / "substituents" / "evidence_residual_task_registry.csv",
                )
                st.session_state["ring_outcome_residual_tasks"] = ring_task_report
                st.session_state["evidence_residual_task_registry"] = merged_registry
            if RING_OUTCOME_RESIDUAL_TASKS_PATH.exists() and "ring_outcome_residual_tasks" not in st.session_state:
                try:
                    st.session_state["ring_outcome_residual_tasks"] = json.loads(RING_OUTCOME_RESIDUAL_TASKS_PATH.read_text(encoding="utf-8"))
                except Exception:
                    pass
            ring_tasks = st.session_state.get("ring_outcome_residual_tasks")
            if ring_tasks:
                task_cols[1].metric("Ring tasks", ring_tasks.get("task_count", 0))
                task_cols[2].metric("High", (ring_tasks.get("priority_counts") or {}).get("high", 0))
                task_cols[3].json(ring_tasks.get("priority_counts") or {})
                if ring_tasks.get("tasks"):
                    with st.expander("Ring follow-up residual tasks"):
                        st.dataframe(pd.DataFrame(ring_tasks.get("tasks") or []), hide_index=True, width="stretch")
            plan_cols = st.columns([0.22, 0.20, 0.20, 0.20, 0.18])
            if plan_cols[0].button("Build ring experiment plan", width="stretch"):
                registry = load_evidence_residual_task_registry(EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH)
                ring_registry = {
                    **registry,
                    "tasks": [
                        dict(row)
                        for row in registry.get("tasks") or []
                        if (
                            str(row.get("task_id") or "").startswith("RINGTASK-")
                            or row.get("task_source") == "ring_outcome_overlay"
                        )
                        and str(row.get("lifecycle_state") or "active").lower() == "active"
                        and str(row.get("status") or "open").lower() in {"open", "planned"}
                    ],
                }
                plan_rows = residual_tasks_to_experiment_plan(
                    ring_registry,
                    project_name="demo_learning",
                    owner="streamlit_ring_plan",
                    batch_size=12,
                )
                RING_OUTCOME_EXPERIMENT_PLAN_JSON_PATH.write_text(
                    json.dumps({"plan_count": len(plan_rows), "plans": plan_rows}, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                pd.DataFrame(plan_rows).to_csv(RING_OUTCOME_EXPERIMENT_PLAN_PATH, index=False)
                template_rows = write_experiment_result_template(plan_rows, RING_OUTCOME_RESULTS_TEMPLATE_PATH, blank_results=True)
                if plan_rows:
                    upsert_experiment_plan_rows(plan_rows, db_path=DB_PATH, source_path=str(RING_OUTCOME_EXPERIMENT_PLAN_PATH.resolve()))
                    updated_registry = update_residual_tasks_from_experiment_plan(
                        plan_rows,
                        registry_path=EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                        reviewer="streamlit_ring_plan",
                        note="Ring outcome residual task converted into project experiment plan.",
                    )
                    write_evidence_residual_task_registry(
                        updated_registry,
                        EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                        csv_path=ROOT / "data" / "substituents" / "evidence_residual_task_registry.csv",
                    )
                st.session_state["ring_outcome_experiment_plan_rows"] = plan_rows
                st.success(f"Ring experiment plan rows: {len(template_rows)}")
            if plan_cols[1].button("Build ring overlay replay", width="stretch"):
                replay = build_ring_outcome_overlay_replay(root=ROOT, overlay_path=RING_OUTCOME_OVERLAY_PATH)
                write_ring_outcome_overlay_replay(
                    replay,
                    json_path=RING_OUTCOME_OVERLAY_REPLAY_PATH,
                    csv_path=RING_OUTCOME_OVERLAY_REPLAY_CSV_PATH,
                )
                st.session_state["ring_outcome_overlay_replay"] = replay
            if RING_OUTCOME_EXPERIMENT_PLAN_PATH.exists():
                plan_frame = pd.read_csv(RING_OUTCOME_EXPERIMENT_PLAN_PATH).fillna("")
                plan_cols[2].metric("Plan rows", len(plan_frame))
                with st.expander("Ring experiment plan"):
                    st.dataframe(plan_frame, hide_index=True, width="stretch")
                    st.download_button(
                        "Download ring experiment plan",
                        RING_OUTCOME_EXPERIMENT_PLAN_PATH.read_text(encoding="utf-8"),
                        file_name="ring_outcome_experiment_plan.csv",
                        mime="text/csv",
                        width="stretch",
                    )
            if RING_OUTCOME_RESULTS_TEMPLATE_PATH.exists():
                plan_cols[3].download_button(
                    "Download result template",
                    RING_OUTCOME_RESULTS_TEMPLATE_PATH.read_text(encoding="utf-8"),
                    file_name="ring_outcome_results_template.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if RING_OUTCOME_OVERLAY_REPLAY_PATH.exists() and "ring_outcome_overlay_replay" not in st.session_state:
                try:
                    st.session_state["ring_outcome_overlay_replay"] = json.loads(RING_OUTCOME_OVERLAY_REPLAY_PATH.read_text(encoding="utf-8"))
                except Exception:
                    pass
            replay = st.session_state.get("ring_outcome_overlay_replay")
            if replay:
                plan_cols[4].metric("Replay", replay.get("status"))
                with st.expander("Ring overlay replay"):
                    rr1, rr2, rr3, rr4 = st.columns(4)
                    rr1.metric("Ring candidates", replay.get("ring_candidate_count", 0))
                    rr2.metric("Matched contexts", replay.get("matched_context_count", 0))
                    rr3.metric("Affected active", replay.get("affected_candidate_count", 0))
                    rr4.metric("Affected proposed", replay.get("proposed_affected_candidate_count", 0))
                    replay_rows = replay.get("rows") or replay.get("top_score_movers") or []
                    if replay_rows:
                        st.dataframe(pd.DataFrame(replay_rows).head(100), hide_index=True, width="stretch")
                    if RING_OUTCOME_OVERLAY_REPLAY_CSV_PATH.exists():
                        st.download_button(
                            "Download ring overlay replay CSV",
                            RING_OUTCOME_OVERLAY_REPLAY_CSV_PATH.read_text(encoding="utf-8"),
                            file_name="ring_outcome_overlay_replay.csv",
                            mime="text/csv",
                            width="stretch",
                        )
        with st.expander("Ring outcome readiness and result package", expanded=False):
            gate_cols = st.columns([0.24, 0.24, 0.22, 0.30])
            readiness_result_csv = RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH if RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH.exists() else RING_OUTCOME_RESULTS_TEMPLATE_PATH
            if gate_cols[0].button("Refresh readiness", width="stretch"):
                readiness = build_ring_outcome_production_readiness(
                    plan_path=RING_OUTCOME_EXPERIMENT_PLAN_PATH,
                    result_csv=readiness_result_csv,
                    intake_manifest_path=RING_OUTCOME_RESULT_INTAKE_MANIFEST_PATH,
                    learning_path=RING_OUTCOME_LEARNING_REPORT_PATH,
                    overlay_path=RING_OUTCOME_OVERLAY_PATH,
                    activation_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_activation.json",
                    replay_path=RING_OUTCOME_OVERLAY_REPLAY_PATH,
                )
                write_ring_outcome_production_readiness(
                    readiness,
                    json_path=RING_OUTCOME_PRODUCTION_READINESS_PATH,
                    csv_path=RING_OUTCOME_PRODUCTION_READINESS_CSV_PATH,
                )
                holdout = build_ring_outcome_holdout_report(
                    learning_path=RING_OUTCOME_LEARNING_REPORT_PATH,
                    overlay_path=RING_OUTCOME_OVERLAY_PATH,
                    replay_path=RING_OUTCOME_OVERLAY_REPLAY_PATH,
                    activation_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_activation.json",
                    readiness_path=RING_OUTCOME_PRODUCTION_READINESS_PATH,
                )
                write_ring_outcome_holdout_report(holdout, json_path=RING_OUTCOME_HOLDOUT_PATH, csv_path=RING_OUTCOME_HOLDOUT_CSV_PATH)
                st.session_state["ring_outcome_production_readiness"] = readiness
                st.session_state["ring_outcome_holdout"] = holdout
            if gate_cols[1].button("Build result package", width="stretch"):
                package = build_ring_outcome_result_package(
                    plan_path=RING_OUTCOME_EXPERIMENT_PLAN_PATH,
                    output_dir=RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH.parent,
                    result_csv=RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH,
                )
                write_ring_outcome_result_package(
                    package,
                    json_path=RING_OUTCOME_RESULT_PACKAGE_PATH,
                    csv_path=RING_OUTCOME_RESULT_PACKAGE_CSV_PATH,
                )
                st.session_state["ring_outcome_result_package"] = package
            for state_key, path in [
                ("ring_outcome_production_readiness", RING_OUTCOME_PRODUCTION_READINESS_PATH),
                ("ring_outcome_holdout", RING_OUTCOME_HOLDOUT_PATH),
                ("ring_outcome_result_package", RING_OUTCOME_RESULT_PACKAGE_PATH),
            ]:
                if path.exists() and state_key not in st.session_state:
                    try:
                        st.session_state[state_key] = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            readiness = st.session_state.get("ring_outcome_production_readiness") or {}
            holdout = st.session_state.get("ring_outcome_holdout") or {}
            package = st.session_state.get("ring_outcome_result_package") or {}
            gate_cols[2].metric("Readiness", readiness.get("status", "missing"))
            gate_cols[3].metric("Package", package.get("status", "missing"))
            readiness_metrics = st.columns(5)
            readiness_metrics[0].metric("Pending", readiness.get("pending_result_count", 0))
            readiness_metrics[1].metric("Importable", readiness.get("importable_result_count", 0))
            readiness_metrics[2].metric("Validation errors", readiness.get("validation_error_count", 0))
            readiness_metrics[3].metric("Holdout", holdout.get("status", "missing"))
            readiness_metrics[4].metric("Ready endpoints", holdout.get("holdout_ready_endpoint_count", 0))
            package_cols = st.columns(3)
            if RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH.exists():
                package_cols[0].download_button(
                    "Download production result CSV",
                    RING_OUTCOME_PRODUCTION_RESULT_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="production_ring_outcome_results_pending.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if RING_OUTCOME_RESULT_PACKAGE_CSV_PATH.exists():
                package_cols[1].download_button(
                    "Download package rows",
                    RING_OUTCOME_RESULT_PACKAGE_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="ring_outcome_result_package.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if RING_OUTCOME_HOLDOUT_CSV_PATH.exists():
                package_cols[2].download_button(
                    "Download holdout rows",
                    RING_OUTCOME_HOLDOUT_CSV_PATH.read_text(encoding="utf-8"),
                    file_name="ring_outcome_holdout_report.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if package.get("rows"):
                st.dataframe(pd.DataFrame(package["rows"]), hide_index=True, width="stretch")
            if readiness.get("strict_import_command"):
                st.code(readiness["strict_import_command"], language="bash")

with project_tab:
    with st.expander("Closed-loop dashboard / replay / iteration package", expanded=True):
        ops_cols = st.columns([0.22, 0.18, 0.18, 0.16, 0.13, 0.13])
        ops_project_name = ops_cols[0].text_input("Closed-loop project", value="demo_learning", key="closed_loop_ops_project")
        replay_endpoint = ops_cols[1].text_input("Replay endpoint", value="", key="closed_loop_replay_endpoint")
        replay_family = ops_cols[2].text_input("Replay family", value="", key="closed_loop_replay_family")
        replay_assay = ops_cols[3].text_input("Replay assay", value="", key="closed_loop_replay_assay")
        if st.button("Refresh project memory", width="stretch", key="project_memory_refresh_build"):
            refresh = refresh_project_memory(root=ROOT, project_name=ops_project_name or None, db_path=DB_PATH)
            st.session_state["project_memory_refresh_report"] = refresh
            for state_key, path in [
                ("project_evidence_expansion_plan", PROJECT_EVIDENCE_EXPANSION_PLAN_PATH),
                ("public_sar_validation_report", PUBLIC_SAR_VALIDATION_REPORT_PATH),
                ("candidate_evidence_priority_report", CANDIDATE_EVIDENCE_PRIORITY_PATH),
                ("public_sar_contradiction_triage", PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH),
                ("public_sar_contradiction_resolution_batch", PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_PATH),
                ("public_sar_contradiction_watchlist", PUBLIC_SAR_CONTRADICTION_WATCHLIST_PATH),
                ("evidence_value_report", EVIDENCE_VALUE_REPORT_PATH),
                ("measurement_feedback_plan", MEASUREMENT_FEEDBACK_PLAN_PATH),
                ("measurement_feedback_import_report", MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH),
                ("measurement_feedback_gap_closure", MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH),
                ("measurement_gap_exact_result_intake", MEASUREMENT_GAP_EXACT_INTAKE_PATH),
                ("measurement_gap_endpoint_governance", MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_PATH),
                ("evidence_value_calibration_report", EVIDENCE_VALUE_CALIBRATION_PATH),
                ("evidence_value_policy_proposal", EVIDENCE_VALUE_POLICY_PROPOSAL_PATH),
                ("evidence_value_policy_replay", EVIDENCE_VALUE_POLICY_REPLAY_PATH),
                ("evidence_value_policy_activation", EVIDENCE_VALUE_POLICY_ACTIVATION_PATH),
                ("evidence_value_policy_active", EVIDENCE_VALUE_POLICY_ACTIVE_PATH),
                ("evidence_value_policy_active_compare", EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_PATH),
                ("profile_impact_review_queue", PROFILE_IMPACT_REVIEW_PATH),
                ("project_memory_review_queue", PROJECT_MEMORY_REVIEW_QUEUE_PATH),
                ("project_memory_review_dashboard", PROJECT_MEMORY_REVIEW_DASHBOARD_PATH),
                ("profile_promotion_rollback_replay", PROFILE_PROMOTION_ROLLBACK_REPLAY_PATH),
                ("profile_rollback_history", PROFILE_ROLLBACK_HISTORY_PATH),
                ("profile_rollback_snapshot_compare", PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH),
                ("closed_loop_promotion_gate", CLOSED_LOOP_PROMOTION_GATE_PATH),
            ]:
                if path.exists():
                    try:
                        st.session_state[state_key] = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            st.success(f"Project memory refresh: {refresh.get('status')}; steps: {refresh.get('passed_step_count')}/{refresh.get('step_count')}")
        if ops_cols[4].button("Build dashboard", width="stretch"):
            dashboard = build_project_closed_loop_dashboard(
                root=ROOT,
                db_path=DB_PATH,
                project_name=ops_project_name or None,
            )
            write_project_closed_loop_dashboard(dashboard, PROJECT_CLOSED_LOOP_DASHBOARD_PATH)
            st.session_state["project_closed_loop_dashboard"] = dashboard
        if ops_cols[5].button("Build replay", width="stretch"):
            target_context = {
                key: value
                for key, value in {
                    "endpoint_group": replay_endpoint,
                    "target_family": replay_family,
                    "assay_type": replay_assay,
                }.items()
                if value
            }
            replay_report = build_closed_loop_replay_report(
                root=ROOT,
                db_path=DB_PATH,
                project_name=ops_project_name or None,
                target_context=target_context or None,
            )
            write_closed_loop_replay_report(replay_report, CLOSED_LOOP_REPLAY_REPORT_PATH)
            st.session_state["closed_loop_replay_report"] = replay_report
        package_cols = st.columns([0.32, 0.48, 0.20])
        package_id = package_cols[0].text_input("Iteration ID", value="", key="closed_loop_iteration_id")
        if package_cols[2].button("Package iteration", width="stretch"):
            manifest = build_next_design_iteration_package(
                root=ROOT,
                project_name=ops_project_name or None,
                package_id=package_id or None,
                output_root=ITERATION_PACKAGE_ROOT,
            )
            st.session_state["next_design_iteration_manifest"] = manifest
            package_cols[1].success(f"Packaged {manifest.get('present_asset_count', 0)} assets.")
        gate_cols = st.columns([0.24, 0.24, 0.24, 0.28])
        if gate_cols[0].button("Compare iterations", width="stretch"):
            comparison = build_latest_iteration_comparison(output_root=ITERATION_PACKAGE_ROOT)
            write_iteration_comparison_report(comparison, ITERATION_COMPARISON_REPORT_PATH)
            st.session_state["iteration_comparison_report"] = comparison
        if gate_cols[1].button("Build promotion gate", width="stretch"):
            gate_report = build_closed_loop_promotion_gate(
                root=ROOT,
                project_name=ops_project_name or None,
            )
            write_closed_loop_promotion_gate(gate_report, CLOSED_LOOP_PROMOTION_GATE_PATH)
            st.session_state["closed_loop_promotion_gate"] = gate_report
        if gate_cols[2].button("Build result template", width="stretch"):
            try:
                template_rows = write_experiment_result_template(
                    read_experiment_plan_csv(RESIDUAL_EXPERIMENT_PLAN_PATH),
                    RESIDUAL_EXPERIMENT_RESULTS_TEMPLATE_PATH,
                )
                st.session_state["closed_loop_residual_result_template_rows"] = template_rows
                gate_cols[3].success(f"Template rows: {len(template_rows)}")
            except Exception as exc:
                gate_cols[3].error(str(exc))
        evidence_cols = st.columns([0.28, 0.72])
        if evidence_cols[0].button("Build evidence pack", width="stretch"):
            pack = build_project_evidence_pack(
                root=ROOT,
                db_path=DB_PATH,
                project_name=ops_project_name or None,
            )
            write_project_evidence_pack(
                pack,
                PROJECT_EVIDENCE_PACK_PATH,
                summary_csv_path=PROJECT_EVIDENCE_PACK_SUMMARY_PATH,
            )
            st.session_state["project_evidence_pack"] = pack
            evidence_cols[1].success(f"Evidence pack: {pack.get('outcome_count', 0)} outcomes, {pack.get('top_public_signal_count', 0)} public signals.")
        advanced_cols = st.columns([0.25, 0.25, 0.25, 0.25])
        if advanced_cols[0].button("Build expansion plan", width="stretch"):
            expansion = build_project_evidence_expansion_plan(root=ROOT, project_name=ops_project_name or None)
            write_project_evidence_expansion_plan(
                expansion,
                PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
                csv_path=PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
            )
            st.session_state["project_evidence_expansion_plan"] = expansion
        if advanced_cols[1].button("Build profile candidates", width="stretch"):
            pack = st.session_state.get("project_evidence_pack")
            if not pack and PROJECT_EVIDENCE_PACK_PATH.exists():
                pack = json.loads(PROJECT_EVIDENCE_PACK_PATH.read_text(encoding="utf-8"))
            candidate_rows = build_residual_adjustment_review_template(pack or {}, min_confidence="medium", min_abs_score_shift=1.0)
            write_residual_adjustment_reviews(candidate_rows, PROJECT_EVIDENCE_GAP_ADJUSTMENT_CANDIDATES_PATH)
            st.session_state["project_evidence_gap_adjustment_candidates"] = candidate_rows
        promotion_artifact = advanced_cols[2].text_input(
            "Promotion artifact",
            value=str(ROOT / "data" / "profiles" / "evidence_weighted_residual_adjusted.yaml"),
            key="profile_promotion_artifact",
        )
        if advanced_cols[3].button("Register promotion", width="stretch"):
            record = build_profile_promotion_record(
                artifact_path=promotion_artifact,
                root=ROOT,
                artifact_type="scoring_profile",
                project_name=ops_project_name or None,
                promotion_status="review_requested",
                reviewer="streamlit",
                note="Registered from Project Memory; activation still follows promotion gate.",
            )
            registry = register_profile_promotion(record, registry_path=PROFILE_PROMOTION_REGISTRY_PATH)
            st.session_state["profile_promotion_registry"] = registry
        execution_cols = st.columns([0.25, 0.25, 0.25, 0.25])
        if execution_cols[0].button("Execute high-priority evidence", width="stretch"):
            execution = execute_project_evidence_expansion_plan(
                root=ROOT,
                plan_path=PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
                csv_path=PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
                priorities={"high"},
                reviewer="streamlit",
            )
            write_project_evidence_execution_report(execution, PROJECT_EVIDENCE_EXECUTION_REPORT_PATH)
            st.session_state["project_evidence_execution_report"] = execution
            st.session_state["project_evidence_expansion_plan"] = load_project_evidence_expansion_plan(PROJECT_EVIDENCE_EXPANSION_PLAN_PATH)
        if execution_cols[1].button("Build public SAR validation", width="stretch"):
            public_sar = build_public_sar_validation_report(
                root=ROOT,
                project_name=ops_project_name or None,
                plan_path=PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
            )
            write_public_sar_validation_report(public_sar, PUBLIC_SAR_VALIDATION_REPORT_PATH, csv_path=PUBLIC_SAR_VALIDATION_CSV_PATH)
            st.session_state["public_sar_validation_report"] = public_sar
            execution_cols[1].success(f"SAR rows: {public_sar.get('row_count', 0)}")
        if st.button("Build candidate evidence priority", width="stretch", key="candidate_evidence_priority_build"):
            priority = build_candidate_evidence_priority_report(root=ROOT, project_name=ops_project_name or None)
            write_candidate_evidence_priority_report(priority, CANDIDATE_EVIDENCE_PRIORITY_PATH, csv_path=CANDIDATE_EVIDENCE_PRIORITY_CSV_PATH)
            st.session_state["candidate_evidence_priority_report"] = priority
            st.success(f"Candidate priority rows: {priority.get('row_count', 0)}; high: {priority.get('high_priority_count', 0)}")
        evidence_value_cols = st.columns([0.33, 0.33, 0.34])
        if evidence_value_cols[0].button("Build SAR contradiction triage", width="stretch"):
            triage = build_public_sar_contradiction_triage(root=ROOT, project_name=ops_project_name or None)
            write_public_sar_contradiction_triage(triage, PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH, csv_path=PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH)
            st.session_state["public_sar_contradiction_triage"] = triage
            evidence_value_cols[0].success(f"Triage rows: {triage.get('row_count', 0)}")
        if evidence_value_cols[0].button("Resolve SAR high batch", width="stretch"):
            result = apply_public_sar_contradiction_resolution_batch(
                triage_path=PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH,
                csv_path=PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH,
                priority="high",
                reviewer="streamlit_policy_v1",
            )
            batch = result.get("batch_report") or {}
            write_public_sar_contradiction_resolution_batch(
                batch,
                PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_PATH,
                csv_path=PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_CSV_PATH,
            )
            st.session_state["public_sar_contradiction_triage"] = result.get("report") or {}
            st.session_state["public_sar_contradiction_resolution_batch"] = batch
            evidence_value_cols[0].success(f"SAR resolved: {batch.get('processed_count', 0)}")
        if evidence_value_cols[0].button("Build SAR watchlist", width="stretch"):
            watchlist = build_public_sar_contradiction_watchlist(root=ROOT, project_name=ops_project_name or None)
            write_public_sar_contradiction_watchlist(
                watchlist,
                PUBLIC_SAR_CONTRADICTION_WATCHLIST_PATH,
                csv_path=PUBLIC_SAR_CONTRADICTION_WATCHLIST_CSV_PATH,
            )
            st.session_state["public_sar_contradiction_watchlist"] = watchlist
            evidence_value_cols[0].success(f"SAR watchlist: {watchlist.get('actionable_count', 0)}")
        if evidence_value_cols[1].button("Build evidence value", width="stretch"):
            value_report = build_evidence_value_report(root=ROOT, project_name=ops_project_name or None)
            write_evidence_value_report(value_report, EVIDENCE_VALUE_REPORT_PATH, csv_path=EVIDENCE_VALUE_CSV_PATH)
            st.session_state["evidence_value_report"] = value_report
            evidence_value_cols[1].success(f"High value: {value_report.get('high_value_count', 0)}")
        if evidence_value_cols[2].button("Build measurement feedback", width="stretch"):
            measurement = build_measurement_feedback_plan(root=ROOT, project_name=ops_project_name or None)
            write_measurement_feedback_plan(
                measurement,
                MEASUREMENT_FEEDBACK_PLAN_PATH,
                csv_path=MEASUREMENT_FEEDBACK_PLAN_CSV_PATH,
                template_path=MEASUREMENT_FEEDBACK_TEMPLATE_PATH,
            )
            st.session_state["measurement_feedback_plan"] = measurement
            evidence_value_cols[2].success(f"Measurement rows: {measurement.get('row_count', 0)}")
        calibration_cols = st.columns([0.25, 0.25, 0.25, 0.25])
        if calibration_cols[0].button("Build evidence value calibration", width="stretch"):
            calibration = build_evidence_value_calibration_report(root=ROOT, project_name=ops_project_name or None)
            write_evidence_value_calibration_report(
                calibration,
                EVIDENCE_VALUE_CALIBRATION_PATH,
                csv_path=EVIDENCE_VALUE_CALIBRATION_CSV_PATH,
            )
            st.session_state["evidence_value_calibration_report"] = calibration
            calibration_cols[1].success(f"Calibration: {calibration.get('status')}; rows: {calibration.get('calibration_row_count', 0)}")
        if calibration_cols[2].button("Build policy proposal", width="stretch"):
            proposal = build_evidence_value_policy_proposal(root=ROOT, project_name=ops_project_name or None)
            write_evidence_value_policy_proposal(
                proposal,
                EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
                csv_path=EVIDENCE_VALUE_POLICY_PROPOSAL_CSV_PATH,
            )
            st.session_state["evidence_value_policy_proposal"] = proposal
            calibration_cols[3].success(f"Proposal: {proposal.get('status')}; changes: {proposal.get('weight_change_count', 0)}")
        if calibration_cols[2].button("Build policy replay", width="stretch"):
            replay = build_evidence_value_policy_replay(root=ROOT, project_name=ops_project_name or None)
            write_evidence_value_policy_replay(
                replay,
                EVIDENCE_VALUE_POLICY_REPLAY_PATH,
                csv_path=EVIDENCE_VALUE_POLICY_REPLAY_CSV_PATH,
            )
            st.session_state["evidence_value_policy_replay"] = replay
            calibration_cols[3].success(f"Replay gate: {replay.get('activation_gate_status')}")
        if calibration_cols[0].button("Build active policy compare", width="stretch"):
            compare = build_evidence_value_policy_active_compare(root=ROOT, project_name=ops_project_name or None)
            write_evidence_value_policy_active_compare(
                compare,
                EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_PATH,
                csv_path=EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_CSV_PATH,
            )
            st.session_state["evidence_value_policy_active_compare"] = compare
            calibration_cols[1].success(f"Active compare: {compare.get('status')}")
        if calibration_cols[2].button("Build profile impact review", width="stretch"):
            profile_review = build_profile_impact_review_queue(root=ROOT, project_name=ops_project_name or None)
            write_profile_impact_review_queue(
                profile_review,
                PROFILE_IMPACT_REVIEW_PATH,
                csv_path=PROFILE_IMPACT_REVIEW_CSV_PATH,
            )
            st.session_state["profile_impact_review_queue"] = profile_review
            calibration_cols[3].success(f"Profile review: {profile_review.get('open_review_count', 0)} open")
        review_queue_cols = st.columns([0.33, 0.33, 0.34])
        if review_queue_cols[0].button("Build measurement gap closure", width="stretch"):
            closure = build_measurement_feedback_gap_closure(root=ROOT, project_name=ops_project_name or None)
            write_measurement_feedback_gap_closure(
                closure,
                MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH,
                csv_path=MEASUREMENT_FEEDBACK_GAP_CLOSURE_CSV_PATH,
            )
            st.session_state["measurement_feedback_gap_closure"] = closure
            if MEASUREMENT_FEEDBACK_PLAN_PATH.exists():
                st.session_state["measurement_feedback_plan"] = json.loads(MEASUREMENT_FEEDBACK_PLAN_PATH.read_text(encoding="utf-8"))
            review_queue_cols[0].success(f"Measurement gaps: {closure.get('open_gap_count', 0)}")
        if review_queue_cols[2].button("Build exact gap intake", width="stretch"):
            intake = build_measurement_gap_exact_result_intake(root=ROOT, project_name=ops_project_name or None)
            write_measurement_gap_exact_result_intake(
                intake,
                MEASUREMENT_GAP_EXACT_INTAKE_PATH,
                csv_path=MEASUREMENT_GAP_EXACT_INTAKE_CSV_PATH,
            )
            st.session_state["measurement_gap_exact_result_intake"] = intake
            review_queue_cols[2].success(f"Exact pending: {intake.get('pending_exact_result_count', 0)}")
        governance_cols = st.columns([0.34, 0.33, 0.33])
        if governance_cols[0].button("Build endpoint governance", width="stretch"):
            governance = build_measurement_gap_endpoint_governance(root=ROOT, project_name=ops_project_name or None)
            write_measurement_gap_endpoint_governance(
                governance,
                MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_PATH,
                csv_path=MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_CSV_PATH,
            )
            st.session_state["measurement_gap_endpoint_governance"] = governance
            governance_cols[0].success(f"Endpoint governance: {governance.get('status')}")
        if review_queue_cols[1].button("Build review queue", width="stretch"):
            queue = build_project_memory_review_queue(root=ROOT, project_name=ops_project_name or None)
            write_project_memory_review_queue(
                queue,
                PROJECT_MEMORY_REVIEW_QUEUE_PATH,
                csv_path=PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH,
            )
            st.session_state["project_memory_review_queue"] = queue
            review_queue_cols[1].success(f"Review queue: {queue.get('row_count', 0)}")
        if governance_cols[1].button("Build review dashboard", width="stretch"):
            review_dashboard = build_project_memory_review_dashboard(root=ROOT, project_name=ops_project_name or None)
            write_project_memory_review_dashboard(
                review_dashboard,
                PROJECT_MEMORY_REVIEW_DASHBOARD_PATH,
                csv_path=PROJECT_MEMORY_REVIEW_DASHBOARD_CSV_PATH,
            )
            st.session_state["project_memory_review_dashboard"] = review_dashboard
            governance_cols[1].success(f"Dashboard: {review_dashboard.get('status')}")
        if execution_cols[2].button("Execute all evidence", width="stretch"):
            execution = execute_project_evidence_expansion_plan(
                root=ROOT,
                plan_path=PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
                csv_path=PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
                priorities=None,
                reviewer="streamlit",
            )
            write_project_evidence_execution_report(execution, PROJECT_EVIDENCE_EXECUTION_REPORT_PATH)
            st.session_state["project_evidence_execution_report"] = execution
            st.session_state["project_evidence_expansion_plan"] = load_project_evidence_expansion_plan(PROJECT_EVIDENCE_EXPANSION_PLAN_PATH)
        if execution_cols[3].button("Build assay triage", width="stretch"):
            triage = build_assay_event_triage_report(db_path=DB_PATH, project_name=None, reviewer="streamlit")
            write_assay_event_triage_report(triage, ASSAY_EVENT_TRIAGE_REPORT_PATH, csv_path=ASSAY_EVENT_TRIAGE_CSV_PATH)
            foundation = build_data_foundation_report(ROOT, db_path=DB_PATH, include_checksums=False)
            save_data_foundation_report(foundation, ROOT / "data" / "substituents" / "data_foundation_report.json")
            st.session_state["assay_event_triage_report"] = triage
            st.session_state["data_foundation_report"] = foundation
        freeze_cols = st.columns([0.33, 0.33, 0.34])
        if freeze_cols[0].button("Build freeze package", width="stretch"):
            freeze = build_profile_promotion_freeze_package(root=ROOT, project_name=ops_project_name or None)
            st.session_state["profile_promotion_freeze_manifest"] = freeze
            freeze_cols[0].success(f"Freeze assets: {freeze.get('present_asset_count', 0)}")
        freeze_note = freeze_cols[1].text_input("Freeze approval note", value="", key="profile_freeze_approval_note")
        if freeze_cols[2].button("Approve freeze tag", width="stretch"):
            approval = review_profile_promotion_freeze(
                freeze_manifest_path=PROFILE_PROMOTION_FREEZE_MANIFEST_PATH,
                approval_status="approved",
                reviewer="streamlit",
                note=freeze_note or None,
            )
            st.session_state["profile_promotion_freeze_approvals"] = approval.get("registry") or {}
            freeze_cols[2].success(f"Release tag: {(approval.get('event') or {}).get('release_tag')}")
        if st.button("Build freeze rollback drill", width="stretch", key="profile_freeze_rollback_drill_build"):
            drill = build_profile_promotion_freeze_rollback_drill(root=ROOT, reviewer="streamlit")
            write_profile_promotion_freeze_rollback_drill(drill, PROFILE_PROMOTION_FREEZE_ROLLBACK_DRILL_PATH)
            st.session_state["profile_promotion_freeze_rollback_drill"] = drill
            st.success(f"Rollback drill: {drill.get('status')}; target: {drill.get('target_freeze_id')}")
        if st.button("Build profile rollback replay", width="stretch", key="profile_rollback_replay_build"):
            rollback_replay = build_profile_promotion_rollback_replay(root=ROOT, project_name=ops_project_name or None)
            write_profile_promotion_rollback_replay(
                rollback_replay,
                PROFILE_PROMOTION_ROLLBACK_REPLAY_PATH,
                csv_path=PROFILE_PROMOTION_ROLLBACK_REPLAY_CSV_PATH,
            )
            st.session_state["profile_promotion_rollback_replay"] = rollback_replay
            st.success(f"Rollback replay rows: {rollback_replay.get('row_count', 0)}")
        if st.button("Build rollback history", width="stretch", key="profile_rollback_history_build"):
            rollback_history = build_profile_rollback_history(root=ROOT, project_name=ops_project_name or None)
            write_profile_rollback_history(
                rollback_history,
                PROFILE_ROLLBACK_HISTORY_PATH,
                csv_path=PROFILE_ROLLBACK_HISTORY_CSV_PATH,
                candidate_csv_path=PROFILE_ROLLBACK_CANDIDATE_HISTORY_CSV_PATH,
            )
            st.session_state["profile_rollback_history"] = rollback_history
            st.success(f"Rollback snapshots: {rollback_history.get('snapshot_count', 0)}")
        if st.button("Compare rollback snapshots", width="stretch", key="profile_rollback_snapshot_compare_build"):
            rollback_history = st.session_state.get("profile_rollback_history")
            if not rollback_history and PROFILE_ROLLBACK_HISTORY_PATH.exists():
                rollback_history = json.loads(PROFILE_ROLLBACK_HISTORY_PATH.read_text(encoding="utf-8"))
            comparison = compare_profile_rollback_snapshots(rollback_history or {}, project_name=ops_project_name or None)
            write_profile_rollback_snapshot_compare(
                comparison,
                PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH,
                csv_path=PROFILE_ROLLBACK_SNAPSHOT_COMPARE_CSV_PATH,
            )
            st.session_state["profile_rollback_snapshot_compare"] = comparison
            st.success(f"Rollback compare: {comparison.get('status')}; changed: {comparison.get('changed_candidate_count', 0)}")
        ab_cols = st.columns([0.26, 0.26, 0.18, 0.14, 0.16])
        ab_base_profile = ab_cols[0].text_input(
            "A/B base profile",
            value=str(ROOT / "data" / "profiles" / "evidence_weighted.yaml"),
            key="profile_ab_base_profile",
        )
        ab_candidate_profile = ab_cols[1].text_input(
            "A/B candidate profile",
            value=promotion_artifact,
            key="profile_ab_candidate_profile",
        )
        ab_direction = ab_cols[2].selectbox("A/B direction", direction_options(), index=0, key="profile_ab_direction")
        ab_top_n = ab_cols[3].number_input("A/B top N", min_value=5, max_value=50, value=20, key="profile_ab_top_n")
        if ab_cols[4].button("Build profile A/B", width="stretch"):
            target_context = {
                key: value
                for key, value in {
                    "endpoint_group": replay_endpoint,
                    "target_family": replay_family,
                    "assay_type": replay_assay,
                }.items()
                if value
            }
            ab_report = build_profile_ab_replay_report(
                smiles=DEFAULT_SMILES,
                direction=ab_direction,
                base_profile_path=ab_base_profile or None,
                candidate_profile_path=ab_candidate_profile or None,
                project_name=ops_project_name or None,
                target_context=target_context or None,
                top_n=int(ab_top_n),
            )
            write_profile_ab_replay_report(ab_report, PROFILE_AB_REPLAY_REPORT_PATH, csv_path=PROFILE_AB_REPLAY_CSV_PATH)
            st.session_state["profile_ab_replay_report"] = ab_report
            ab_cols[4].success(f"A/B changed top N: {ab_report.get('changed_top_n_count', 0)}")
        if st.button("Build profile A/B matrix", width="stretch", key="profile_ab_matrix_build"):
            matrix = build_profile_ab_replay_matrix(
                base_profile_path=ab_base_profile or None,
                candidate_profile_path=ab_candidate_profile or None,
                project_name=ops_project_name or None,
                top_n=int(ab_top_n),
            )
            write_profile_ab_replay_matrix(matrix, PROFILE_AB_REPLAY_MATRIX_PATH, csv_path=PROFILE_AB_REPLAY_MATRIX_CSV_PATH)
            st.session_state["profile_ab_replay_matrix"] = matrix
            st.success(f"A/B scenarios: {matrix.get('scenario_count', 0)}; review required: {matrix.get('review_required_count', 0)}")
        if st.button("Build material A/B review", width="stretch", key="profile_ab_material_review_build"):
            material_review = build_profile_ab_material_change_review(
                root=ROOT,
                matrix_path=PROFILE_AB_REPLAY_MATRIX_PATH,
                project_name=ops_project_name or None,
                reviewer="streamlit",
                decision="accepted_with_review",
                note="Accepted from Project Memory with candidate-level material diff audit.",
            )
            write_profile_ab_material_change_review(
                material_review,
                PROFILE_AB_MATERIAL_REVIEW_PATH,
                csv_path=PROFILE_AB_MATERIAL_REVIEW_CSV_PATH,
            )
            st.session_state["profile_ab_material_change_review"] = material_review
            st.success(f"Material A/B review: {material_review.get('status')}; diffs: {material_review.get('candidate_diff_count', 0)}")

        if "project_closed_loop_dashboard" not in st.session_state and PROJECT_CLOSED_LOOP_DASHBOARD_PATH.exists():
            try:
                st.session_state["project_closed_loop_dashboard"] = json.loads(PROJECT_CLOSED_LOOP_DASHBOARD_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "closed_loop_replay_report" not in st.session_state and CLOSED_LOOP_REPLAY_REPORT_PATH.exists():
            try:
                st.session_state["closed_loop_replay_report"] = json.loads(CLOSED_LOOP_REPLAY_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "iteration_comparison_report" not in st.session_state and ITERATION_COMPARISON_REPORT_PATH.exists():
            try:
                st.session_state["iteration_comparison_report"] = json.loads(ITERATION_COMPARISON_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "closed_loop_promotion_gate" not in st.session_state and CLOSED_LOOP_PROMOTION_GATE_PATH.exists():
            try:
                st.session_state["closed_loop_promotion_gate"] = json.loads(CLOSED_LOOP_PROMOTION_GATE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "project_evidence_pack" not in st.session_state and PROJECT_EVIDENCE_PACK_PATH.exists():
            try:
                st.session_state["project_evidence_pack"] = json.loads(PROJECT_EVIDENCE_PACK_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "project_evidence_expansion_plan" not in st.session_state and PROJECT_EVIDENCE_EXPANSION_PLAN_PATH.exists():
            try:
                st.session_state["project_evidence_expansion_plan"] = json.loads(PROJECT_EVIDENCE_EXPANSION_PLAN_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "project_evidence_execution_report" not in st.session_state and PROJECT_EVIDENCE_EXECUTION_REPORT_PATH.exists():
            try:
                st.session_state["project_evidence_execution_report"] = json.loads(PROJECT_EVIDENCE_EXECUTION_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "public_sar_validation_report" not in st.session_state and PUBLIC_SAR_VALIDATION_REPORT_PATH.exists():
            try:
                st.session_state["public_sar_validation_report"] = json.loads(PUBLIC_SAR_VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "candidate_evidence_priority_report" not in st.session_state and CANDIDATE_EVIDENCE_PRIORITY_PATH.exists():
            try:
                st.session_state["candidate_evidence_priority_report"] = json.loads(CANDIDATE_EVIDENCE_PRIORITY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "public_sar_contradiction_triage" not in st.session_state and PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH.exists():
            try:
                st.session_state["public_sar_contradiction_triage"] = json.loads(PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "public_sar_contradiction_resolution_batch" not in st.session_state and PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_PATH.exists():
            try:
                st.session_state["public_sar_contradiction_resolution_batch"] = json.loads(PUBLIC_SAR_CONTRADICTION_RESOLUTION_BATCH_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "public_sar_contradiction_watchlist" not in st.session_state and PUBLIC_SAR_CONTRADICTION_WATCHLIST_PATH.exists():
            try:
                st.session_state["public_sar_contradiction_watchlist"] = json.loads(PUBLIC_SAR_CONTRADICTION_WATCHLIST_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "evidence_value_report" not in st.session_state and EVIDENCE_VALUE_REPORT_PATH.exists():
            try:
                st.session_state["evidence_value_report"] = json.loads(EVIDENCE_VALUE_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "evidence_value_calibration_report" not in st.session_state and EVIDENCE_VALUE_CALIBRATION_PATH.exists():
            try:
                st.session_state["evidence_value_calibration_report"] = json.loads(EVIDENCE_VALUE_CALIBRATION_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "evidence_value_policy_proposal" not in st.session_state and EVIDENCE_VALUE_POLICY_PROPOSAL_PATH.exists():
            try:
                st.session_state["evidence_value_policy_proposal"] = json.loads(EVIDENCE_VALUE_POLICY_PROPOSAL_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "evidence_value_policy_replay" not in st.session_state and EVIDENCE_VALUE_POLICY_REPLAY_PATH.exists():
            try:
                st.session_state["evidence_value_policy_replay"] = json.loads(EVIDENCE_VALUE_POLICY_REPLAY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "evidence_value_policy_activation" not in st.session_state and EVIDENCE_VALUE_POLICY_ACTIVATION_PATH.exists():
            try:
                st.session_state["evidence_value_policy_activation"] = json.loads(EVIDENCE_VALUE_POLICY_ACTIVATION_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "evidence_value_policy_active" not in st.session_state and EVIDENCE_VALUE_POLICY_ACTIVE_PATH.exists():
            try:
                st.session_state["evidence_value_policy_active"] = json.loads(EVIDENCE_VALUE_POLICY_ACTIVE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "evidence_value_policy_active_compare" not in st.session_state and EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_PATH.exists():
            try:
                st.session_state["evidence_value_policy_active_compare"] = json.loads(EVIDENCE_VALUE_POLICY_ACTIVE_COMPARE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_impact_review_queue" not in st.session_state and PROFILE_IMPACT_REVIEW_PATH.exists():
            try:
                st.session_state["profile_impact_review_queue"] = json.loads(PROFILE_IMPACT_REVIEW_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "measurement_feedback_plan" not in st.session_state and MEASUREMENT_FEEDBACK_PLAN_PATH.exists():
            try:
                st.session_state["measurement_feedback_plan"] = json.loads(MEASUREMENT_FEEDBACK_PLAN_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "measurement_feedback_import_report" not in st.session_state and MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH.exists():
            try:
                st.session_state["measurement_feedback_import_report"] = json.loads(MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "measurement_feedback_gap_closure" not in st.session_state and MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH.exists():
            try:
                st.session_state["measurement_feedback_gap_closure"] = json.loads(MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "measurement_gap_exact_result_intake" not in st.session_state and MEASUREMENT_GAP_EXACT_INTAKE_PATH.exists():
            try:
                st.session_state["measurement_gap_exact_result_intake"] = json.loads(MEASUREMENT_GAP_EXACT_INTAKE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "measurement_gap_endpoint_governance" not in st.session_state and MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_PATH.exists():
            try:
                st.session_state["measurement_gap_endpoint_governance"] = json.loads(MEASUREMENT_GAP_ENDPOINT_GOVERNANCE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "project_memory_review_queue" not in st.session_state and PROJECT_MEMORY_REVIEW_QUEUE_PATH.exists():
            try:
                st.session_state["project_memory_review_queue"] = json.loads(PROJECT_MEMORY_REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "project_memory_review_dashboard" not in st.session_state and PROJECT_MEMORY_REVIEW_DASHBOARD_PATH.exists():
            try:
                st.session_state["project_memory_review_dashboard"] = json.loads(PROJECT_MEMORY_REVIEW_DASHBOARD_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_promotion_registry" not in st.session_state and PROFILE_PROMOTION_REGISTRY_PATH.exists():
            try:
                st.session_state["profile_promotion_registry"] = load_profile_promotion_registry(PROFILE_PROMOTION_REGISTRY_PATH)
            except Exception:
                pass
        if "profile_ab_replay_report" not in st.session_state and PROFILE_AB_REPLAY_REPORT_PATH.exists():
            try:
                st.session_state["profile_ab_replay_report"] = json.loads(PROFILE_AB_REPLAY_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_ab_replay_matrix" not in st.session_state and PROFILE_AB_REPLAY_MATRIX_PATH.exists():
            try:
                st.session_state["profile_ab_replay_matrix"] = json.loads(PROFILE_AB_REPLAY_MATRIX_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_ab_material_change_review" not in st.session_state and PROFILE_AB_MATERIAL_REVIEW_PATH.exists():
            try:
                st.session_state["profile_ab_material_change_review"] = json.loads(PROFILE_AB_MATERIAL_REVIEW_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "assay_event_triage_report" not in st.session_state and ASSAY_EVENT_TRIAGE_REPORT_PATH.exists():
            try:
                st.session_state["assay_event_triage_report"] = json.loads(ASSAY_EVENT_TRIAGE_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "assay_followup_result_import_report" not in st.session_state and ASSAY_FOLLOWUP_IMPORT_REPORT_PATH.exists():
            try:
                st.session_state["assay_followup_result_import_report"] = json.loads(ASSAY_FOLLOWUP_IMPORT_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_promotion_freeze_manifest" not in st.session_state and PROFILE_PROMOTION_FREEZE_MANIFEST_PATH.exists():
            try:
                st.session_state["profile_promotion_freeze_manifest"] = json.loads(PROFILE_PROMOTION_FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_promotion_freeze_approvals" not in st.session_state and PROFILE_PROMOTION_FREEZE_APPROVALS_PATH.exists():
            try:
                st.session_state["profile_promotion_freeze_approvals"] = load_promotion_freeze_approvals(PROFILE_PROMOTION_FREEZE_APPROVALS_PATH)
            except Exception:
                pass
        if "profile_promotion_freeze_rollback_drill" not in st.session_state and PROFILE_PROMOTION_FREEZE_ROLLBACK_DRILL_PATH.exists():
            try:
                st.session_state["profile_promotion_freeze_rollback_drill"] = json.loads(PROFILE_PROMOTION_FREEZE_ROLLBACK_DRILL_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_promotion_rollback_replay" not in st.session_state and PROFILE_PROMOTION_ROLLBACK_REPLAY_PATH.exists():
            try:
                st.session_state["profile_promotion_rollback_replay"] = json.loads(PROFILE_PROMOTION_ROLLBACK_REPLAY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_rollback_history" not in st.session_state and PROFILE_ROLLBACK_HISTORY_PATH.exists():
            try:
                st.session_state["profile_rollback_history"] = json.loads(PROFILE_ROLLBACK_HISTORY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "profile_rollback_snapshot_compare" not in st.session_state and PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH.exists():
            try:
                st.session_state["profile_rollback_snapshot_compare"] = json.loads(PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        if "project_memory_refresh_report" not in st.session_state and PROJECT_MEMORY_REFRESH_PATH.exists():
            try:
                st.session_state["project_memory_refresh_report"] = json.loads(PROJECT_MEMORY_REFRESH_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass

        dashboard = st.session_state.get("project_closed_loop_dashboard") or {}
        if dashboard:
            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("Status", dashboard.get("overall_status") or "-")
            d2.metric("Feedback", (dashboard.get("feedback") or {}).get("feedback_count", 0))
            d3.metric("Open plans", (dashboard.get("experiments") or {}).get("open_plan_count", 0))
            d4.metric("Queue rows", (dashboard.get("next_design_queue") or {}).get("queue_count", 0))
            d5.metric("Residual tasks", (dashboard.get("residual_tasks") or {}).get("task_count", 0))
            residual_rows = (dashboard.get("residual_tasks") or {}).get("top_information_gain_tasks") or []
            if residual_rows:
                st.caption("Top information-gain residual tasks")
                st.dataframe(pd.DataFrame(residual_rows), hide_index=True, width="stretch")
            queue_rows = (dashboard.get("next_design_queue") or {}).get("top_rows") or []
            if queue_rows:
                with st.expander("Next design queue snapshot"):
                    st.dataframe(pd.DataFrame(queue_rows), hide_index=True, width="stretch")

        replay_report = st.session_state.get("closed_loop_replay_report") or {}
        if replay_report:
            mo = replay_report.get("multi_objective_holdout") or {}
            queue_replay = replay_report.get("queue_policy_replay") or {}
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Replay status", replay_report.get("status") or "-")
            r2.metric("Holdout rows", mo.get("holdout_count", 0))
            r3.metric("Rank lift delta", (mo.get("delta") or {}).get("rank_lift_delta"))
            r4.metric("Queue alignment", queue_replay.get("alignment_rate"))
            if queue_replay.get("rows"):
                st.caption("Queue policy replay rows")
                st.dataframe(pd.DataFrame(queue_replay["rows"]), hide_index=True, width="stretch")
        manifest = st.session_state.get("next_design_iteration_manifest") or {}
        if manifest:
            st.json(
                {
                    "iteration_id": manifest.get("iteration_id"),
                    "manifest_path": manifest.get("manifest_path"),
                    "present_asset_count": manifest.get("present_asset_count"),
                    "missing_asset_count": manifest.get("missing_asset_count"),
                }
            )
        comparison = st.session_state.get("iteration_comparison_report") or {}
        if comparison:
            with st.expander("Iteration comparison"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Status", comparison.get("status") or "-")
                c2.metric("Changed assets", comparison.get("changed_asset_count", 0))
                c3.metric("Head iteration", comparison.get("head_iteration_id") or "-")
                if comparison.get("metric_deltas"):
                    st.json(comparison.get("metric_deltas"))
                if comparison.get("changed_assets"):
                    st.dataframe(pd.DataFrame(comparison["changed_assets"]), hide_index=True, width="stretch")
        gate_report = st.session_state.get("closed_loop_promotion_gate") or {}
        if gate_report:
            with st.expander("Promotion gate"):
                g1, g2, g3 = st.columns(3)
                g1.metric("Promotion", gate_report.get("promotion_status") or "-")
                g2.metric("Blocks", gate_report.get("block_count", 0))
                g3.metric("Reviews", gate_report.get("review_count", 0))
                if gate_report.get("checks"):
                    st.dataframe(pd.DataFrame(gate_report["checks"]), hide_index=True, width="stretch")
        review_queue = st.session_state.get("project_memory_review_queue") or {}
        review_dashboard = st.session_state.get("project_memory_review_dashboard") or {}
        if review_dashboard:
            with st.expander("Project Memory review dashboard"):
                rd1, rd2, rd3, rd4 = st.columns(4)
                rd1.metric("Status", review_dashboard.get("status") or "-")
                rd2.metric("Items", review_dashboard.get("row_count", 0))
                rd3.metric("Open-like", review_dashboard.get("open_like_count", 0))
                rd4.metric("Lanes", review_dashboard.get("lane_row_count", 0))
                if review_dashboard.get("lane_status_rows"):
                    st.dataframe(pd.DataFrame(review_dashboard["lane_status_rows"]), hide_index=True, width="stretch")
                if review_dashboard.get("attention_rows"):
                    st.dataframe(pd.DataFrame(review_dashboard["attention_rows"]), hide_index=True, width="stretch")
        if review_queue:
            with st.expander("Project Memory review queue", expanded=True):
                q1, q2, q3, q4 = st.columns(4)
                q1.metric("Status", review_queue.get("status") or "-")
                q2.metric("Items", review_queue.get("row_count", 0))
                q3.metric("Policy gate", review_queue.get("policy_activation_gate_status") or "-")
                q4.metric("Measurement gaps", review_queue.get("measurement_open_gap_count", 0))
                st.caption(f"Open operator items: {review_queue.get('open_operator_item_count', 0)}")
                if review_queue.get("lane_counts"):
                    st.json(review_queue.get("lane_counts"))
                if review_queue.get("rows"):
                    queue_rows = review_queue["rows"]
                    batch_cols = st.columns([0.22, 0.18, 0.18, 0.30, 0.12])
                    lane_options = [""] + sorted({str(row.get("review_lane") or "") for row in queue_rows if row.get("review_lane")})
                    batch_lane = batch_cols[0].selectbox("Batch lane", lane_options, format_func=lambda item: item or "all lanes", key="project_memory_batch_lane")
                    batch_status = batch_cols[1].selectbox("Batch status", sorted(PROJECT_MEMORY_OPERATOR_STATUSES), key="project_memory_batch_status")
                    batch_assignee = batch_cols[2].text_input("Batch assignee", value="", key="project_memory_batch_assignee")
                    batch_note = batch_cols[3].text_input("Batch note", value="", key="project_memory_batch_note")
                    if batch_cols[4].button("Apply batch", width="stretch"):
                        batch_update = apply_project_memory_review_batch(
                            queue_path=PROJECT_MEMORY_REVIEW_QUEUE_PATH,
                            csv_path=PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH,
                            review_lane=batch_lane or None,
                            current_operator_status="open",
                            operator_status=batch_status,
                            assigned_to=batch_assignee or None,
                            reviewer="streamlit",
                            note=batch_note or None,
                        )
                        st.session_state["project_memory_review_queue"] = batch_update.get("queue") or {}
                        st.success(f"Batch applied: {batch_update.get('applied_count', 0)}")
                    pm_cols = st.columns([0.34, 0.16, 0.18, 0.22, 0.10])
                    selected_pm_item = pm_cols[0].selectbox(
                        "Review item",
                        queue_rows,
                        format_func=lambda row: f"{row.get('review_item_id')} | {row.get('review_lane')} | {row.get('priority')}",
                        key="project_memory_review_item_select",
                    )
                    current_pm_status = str(selected_pm_item.get("operator_status") or "open")
                    pm_status_options = sorted(PROJECT_MEMORY_OPERATOR_STATUSES)
                    pm_status = pm_cols[1].selectbox(
                        "Operator status",
                        pm_status_options,
                        index=pm_status_options.index(current_pm_status) if current_pm_status in pm_status_options else 0,
                        key="project_memory_operator_status",
                    )
                    pm_assignee = pm_cols[2].text_input("Assignee", value=str(selected_pm_item.get("assigned_to") or ""), key="project_memory_assignee")
                    pm_note = pm_cols[3].text_input("Operator note", value="", key="project_memory_operator_note")
                    if pm_cols[4].button("Save item", width="stretch"):
                        update_report = update_project_memory_review_item(
                            str(selected_pm_item.get("review_item_id")),
                            operator_status=pm_status,
                            assigned_to=pm_assignee,
                            reviewer="streamlit",
                            note=pm_note,
                            queue_path=PROJECT_MEMORY_REVIEW_QUEUE_PATH,
                            csv_path=PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH,
                        )
                        st.session_state["project_memory_review_queue"] = update_report.get("queue") or {}
                        st.success(f"Project Memory item saved: {pm_status}")
                    st.dataframe(pd.DataFrame(queue_rows), hide_index=True, width="stretch")
                    if PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH.exists():
                        st.download_button(
                            "Download Project Memory review queue",
                            PROJECT_MEMORY_REVIEW_QUEUE_CSV_PATH.read_text(encoding="utf-8"),
                            file_name="project_memory_review_queue.csv",
                            mime="text/csv",
                            width="stretch",
                        )
        evidence_pack = st.session_state.get("project_evidence_pack") or {}
        if evidence_pack:
            with st.expander("Project evidence pack"):
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Status", evidence_pack.get("status") or "-")
                p2.metric("Outcomes", evidence_pack.get("outcome_count", 0))
                p3.metric("Public signals", evidence_pack.get("top_public_signal_count", 0))
                p4.metric("Evidence gaps", len(evidence_pack.get("evidence_gaps") or []))
                if evidence_pack.get("context_summary"):
                    st.dataframe(pd.DataFrame(evidence_pack["context_summary"]), hide_index=True, width="stretch")
                if evidence_pack.get("evidence_gaps"):
                    st.dataframe(pd.DataFrame(evidence_pack["evidence_gaps"]), hide_index=True, width="stretch")
        expansion_plan = st.session_state.get("project_evidence_expansion_plan") or {}
        if expansion_plan:
            with st.expander("Project evidence expansion plan"):
                e1, e2, e3, e4 = st.columns(4)
                e1.metric("Status", expansion_plan.get("status") or "-")
                e2.metric("Tasks", expansion_plan.get("task_count", 0))
                e3.metric("High priority", (expansion_plan.get("priority_counts") or {}).get("high", 0))
                e4.metric("Open execution", expansion_plan.get("open_execution_count", 0))
                if expansion_plan.get("tasks"):
                    task_options = expansion_plan["tasks"]
                    exec_cols = st.columns([0.34, 0.18, 0.18, 0.20, 0.10])
                    selected_task = exec_cols[0].selectbox(
                        "Evidence task",
                        task_options,
                        format_func=lambda row: f"{row.get('task_id')} | {row.get('task_type')} | {row.get('priority')}",
                        key="project_evidence_expansion_task_select",
                    )
                    exec_status = exec_cols[1].selectbox(
                        "Execution status",
                        sorted(PROJECT_EVIDENCE_EXPANSION_STATUSES),
                        key="project_evidence_expansion_status",
                    )
                    exec_owner = exec_cols[2].text_input("Owner", value="", key="project_evidence_expansion_owner")
                    exec_note = exec_cols[3].text_input("Execution note", value="", key="project_evidence_expansion_note")
                    if exec_cols[4].button("Save task", width="stretch"):
                        update_report = update_project_evidence_expansion_task_status(
                            str(selected_task.get("task_id")),
                            status=exec_status,
                            plan_path=PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
                            reviewer="streamlit",
                            owner=exec_owner or None,
                            note=exec_note or None,
                        )
                        st.session_state["project_evidence_expansion_plan"] = update_report.get("plan") or {}
                        st.success(f"Evidence task updated: {exec_status}")
                    st.dataframe(pd.DataFrame(expansion_plan["tasks"]), hide_index=True, width="stretch")
        execution_report = st.session_state.get("project_evidence_execution_report") or {}
        if execution_report:
            with st.expander("Project evidence execution report"):
                x1, x2, x3 = st.columns(3)
                x1.metric("Status", execution_report.get("status") or "-")
                x2.metric("Updated", execution_report.get("updated_count", 0))
                x3.metric("Open execution", execution_report.get("open_execution_count", 0))
                if execution_report.get("updated_tasks"):
                    st.dataframe(pd.DataFrame(execution_report["updated_tasks"]), hide_index=True, width="stretch")
        public_sar = st.session_state.get("public_sar_validation_report") or {}
        if public_sar:
            with st.expander("Public SAR validation"):
                s1, s2, s3 = st.columns(3)
                s1.metric("Rows", public_sar.get("row_count", 0))
                s2.metric("Active context", public_sar.get("active_context_match_count", 0))
                s3.metric("Manual review", public_sar.get("manual_review_count", 0))
                if public_sar.get("rows"):
                    st.dataframe(pd.DataFrame(public_sar["rows"]), hide_index=True, width="stretch")
        candidate_priority = st.session_state.get("candidate_evidence_priority_report") or {}
        if candidate_priority:
            with st.expander("Candidate evidence priority"):
                cp1, cp2, cp3, cp4 = st.columns(4)
                cp1.metric("Rows", candidate_priority.get("row_count", 0))
                cp2.metric("High priority", candidate_priority.get("high_priority_count", 0))
                cp3.metric("SAR linked", candidate_priority.get("sar_linked_count", 0))
                cp4.metric("Material linked", candidate_priority.get("material_diff_linked_count", 0))
                if candidate_priority.get("rows"):
                    st.dataframe(pd.DataFrame(candidate_priority["rows"]), hide_index=True, width="stretch")
        contradiction_triage = st.session_state.get("public_sar_contradiction_triage") or {}
        if contradiction_triage:
            with st.expander("SAR contradiction triage"):
                ct1, ct2, ct3, ct4 = st.columns(4)
                ct1.metric("Rows", contradiction_triage.get("row_count", 0))
                ct2.metric("High priority", contradiction_triage.get("high_priority_count", 0))
                ct3.metric("Candidate linked", contradiction_triage.get("candidate_linked_count", 0))
                ct4.metric("Net contradicted", contradiction_triage.get("net_contradicted_count", 0))
                if contradiction_triage.get("rows"):
                    triage_rows = contradiction_triage["rows"]
                    sar_cols = st.columns([0.30, 0.16, 0.18, 0.18, 0.18])
                    selected_triage = sar_cols[0].selectbox(
                        "SAR triage row",
                        triage_rows,
                        format_func=lambda row: f"{row.get('triage_id')} | {row.get('priority')} | {row.get('source_signal_id')}",
                        key="sar_contradiction_resolution_row",
                    )
                    review_options = sorted(SAR_TRIAGE_REVIEW_STATUSES)
                    resolution_options = [""] + sorted(SAR_TRIAGE_RESOLUTIONS)
                    current_review = str(selected_triage.get("review_status") or "open")
                    current_resolution = str(selected_triage.get("resolution_status") or "")
                    review_status = sar_cols[1].selectbox(
                        "Review status",
                        review_options,
                        index=review_options.index(current_review) if current_review in review_options else 0,
                        key="sar_contradiction_review_status",
                    )
                    resolution_status = sar_cols[2].selectbox(
                        "Resolution",
                        resolution_options,
                        index=resolution_options.index(current_resolution) if current_resolution in resolution_options else 0,
                        key="sar_contradiction_resolution_status",
                    )
                    resolution_note = sar_cols[3].text_input("Resolution note", value="", key="sar_contradiction_resolution_note")
                    if sar_cols[4].button("Save SAR resolution", width="stretch"):
                        if not resolution_status:
                            st.warning("Choose a resolution before saving.")
                        else:
                            updated = update_public_sar_contradiction_resolution(
                                str(selected_triage.get("triage_id")),
                                resolution_status=resolution_status,
                                review_status=review_status,
                                reviewer="streamlit",
                                note=resolution_note or None,
                                triage_path=PUBLIC_SAR_CONTRADICTION_TRIAGE_PATH,
                                csv_path=PUBLIC_SAR_CONTRADICTION_TRIAGE_CSV_PATH,
                            )
                            st.session_state["public_sar_contradiction_triage"] = updated.get("report") or {}
                            st.success(f"SAR resolution saved: {resolution_status}")
                    st.dataframe(pd.DataFrame(contradiction_triage["rows"]), hide_index=True, width="stretch")
        sar_resolution_batch = st.session_state.get("public_sar_contradiction_resolution_batch") or {}
        if sar_resolution_batch:
            with st.expander("SAR contradiction resolution batch"):
                rb1, rb2, rb3, rb4 = st.columns(4)
                rb1.metric("Status", sar_resolution_batch.get("status") or "-")
                rb2.metric("Processed", sar_resolution_batch.get("processed_count", 0))
                rb3.metric("Needs measurement", sar_resolution_batch.get("candidate_measurement_gated_count", 0))
                rb4.metric("Reference watch", sar_resolution_batch.get("reference_only_watch_count", 0))
                if sar_resolution_batch.get("rows"):
                    st.dataframe(pd.DataFrame(sar_resolution_batch["rows"]), hide_index=True, width="stretch")
        sar_watchlist = st.session_state.get("public_sar_contradiction_watchlist") or {}
        if sar_watchlist:
            with st.expander("SAR contradiction watchlist"):
                sw1, sw2, sw3, sw4 = st.columns(4)
                sw1.metric("Status", sar_watchlist.get("status") or "-")
                sw2.metric("Actionable", sar_watchlist.get("actionable_count", 0))
                sw3.metric("Candidate open", sar_watchlist.get("candidate_linked_open_count", 0))
                sw4.metric("Reference deferred", sar_watchlist.get("deferred_reference_only_count", 0))
                if sar_watchlist.get("rows"):
                    st.dataframe(pd.DataFrame(sar_watchlist["rows"]), hide_index=True, width="stretch")
        evidence_value = st.session_state.get("evidence_value_report") or {}
        if evidence_value:
            with st.expander("Evidence value scoring"):
                ev1, ev2, ev3, ev4 = st.columns(4)
                ev1.metric("Rows", evidence_value.get("row_count", 0))
                ev2.metric("High value", evidence_value.get("high_value_count", 0))
                ev3.metric("Contradiction", evidence_value.get("contradiction_resolution_count", 0))
                ev4.metric("Gap measurements", evidence_value.get("evidence_gap_measurement_count", 0))
                if evidence_value.get("rows"):
                    st.dataframe(pd.DataFrame(evidence_value["rows"]), hide_index=True, width="stretch")
        calibration_report = st.session_state.get("evidence_value_calibration_report") or {}
        if calibration_report:
            with st.expander("Evidence value calibration"):
                ec1, ec2, ec3, ec4 = st.columns(4)
                ec1.metric("Status", calibration_report.get("status") or "-")
                ec2.metric("Rows", calibration_report.get("calibration_row_count", 0))
                ec3.metric("MAE", calibration_report.get("mean_absolute_error"))
                ec4.metric("Rank alignment", calibration_report.get("rank_alignment_rate"))
                if calibration_report.get("recommended_weight_adjustments"):
                    st.dataframe(pd.DataFrame(calibration_report["recommended_weight_adjustments"]), hide_index=True, width="stretch")
                if calibration_report.get("value_driver_error_summary"):
                    st.caption("Value driver error summary")
                    st.dataframe(pd.DataFrame(calibration_report["value_driver_error_summary"]), hide_index=True, width="stretch")
                if calibration_report.get("rows"):
                    st.dataframe(pd.DataFrame(calibration_report["rows"]), hide_index=True, width="stretch")
        policy_proposal = st.session_state.get("evidence_value_policy_proposal") or {}
        if policy_proposal:
            with st.expander("Evidence value policy proposal"):
                ep1, ep2, ep3, ep4 = st.columns(4)
                ep1.metric("Status", policy_proposal.get("status") or "-")
                ep2.metric("Approval", policy_proposal.get("approval_status") or "-")
                ep3.metric("Changes", policy_proposal.get("weight_change_count", 0))
                ep4.metric("Activation", policy_proposal.get("activation_status") or "-")
                review_cols = st.columns([0.24, 0.24, 0.34, 0.18])
                proposal_decisions = sorted(EVIDENCE_VALUE_POLICY_PROPOSAL_DECISIONS)
                proposal_decision = review_cols[0].selectbox("Proposal decision", proposal_decisions, key="evidence_policy_proposal_decision")
                proposal_reviewer = review_cols[1].text_input("Proposal reviewer", value="", key="evidence_policy_proposal_reviewer")
                proposal_note = review_cols[2].text_input("Proposal note", value="", key="evidence_policy_proposal_note")
                if review_cols[3].button("Save proposal review", width="stretch"):
                    reviewed = review_evidence_value_policy_proposal(
                        proposal_path=EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
                        decision=proposal_decision,
                        reviewer=proposal_reviewer or "streamlit",
                        note=proposal_note or None,
                    )
                    write_evidence_value_policy_proposal(
                        reviewed,
                        EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
                        csv_path=EVIDENCE_VALUE_POLICY_PROPOSAL_CSV_PATH,
                    )
                    st.session_state["evidence_value_policy_proposal"] = reviewed
                    st.success(f"Proposal review saved: {proposal_decision}")
                activation_cols = st.columns([0.25, 0.35, 0.24, 0.16])
                activation_reviewer = activation_cols[0].text_input("Activation reviewer", value="", key="evidence_policy_activation_reviewer")
                activation_note = activation_cols[1].text_input("Activation note", value="", key="evidence_policy_activation_note")
                activation_disabled = not (
                    policy_proposal.get("approval_status") == "approved"
                    and (st.session_state.get("evidence_value_policy_replay") or {}).get("activation_gate_status") == "ready_for_manual_activation"
                )
                if activation_cols[2].button("Activate approved policy", width="stretch", disabled=activation_disabled):
                    activation = activate_evidence_value_policy_proposal(
                        proposal_path=EVIDENCE_VALUE_POLICY_PROPOSAL_PATH,
                        replay_path=EVIDENCE_VALUE_POLICY_REPLAY_PATH,
                        active_policy_path=EVIDENCE_VALUE_POLICY_ACTIVE_PATH,
                        activation_path=EVIDENCE_VALUE_POLICY_ACTIVATION_PATH,
                        reviewer=activation_reviewer or "streamlit",
                        note=activation_note or None,
                    )
                    write_evidence_value_policy_activation(
                        activation,
                        EVIDENCE_VALUE_POLICY_ACTIVATION_PATH,
                        csv_path=EVIDENCE_VALUE_POLICY_ACTIVATION_CSV_PATH,
                    )
                    st.session_state["evidence_value_policy_activation"] = activation
                    if EVIDENCE_VALUE_POLICY_PROPOSAL_PATH.exists():
                        st.session_state["evidence_value_policy_proposal"] = json.loads(EVIDENCE_VALUE_POLICY_PROPOSAL_PATH.read_text(encoding="utf-8"))
                    if EVIDENCE_VALUE_POLICY_REPLAY_PATH.exists():
                        st.session_state["evidence_value_policy_replay"] = json.loads(EVIDENCE_VALUE_POLICY_REPLAY_PATH.read_text(encoding="utf-8"))
                    if EVIDENCE_VALUE_POLICY_ACTIVE_PATH.exists():
                        st.session_state["evidence_value_policy_active"] = json.loads(EVIDENCE_VALUE_POLICY_ACTIVE_PATH.read_text(encoding="utf-8"))
                    activation_cols[3].success(activation.get("status") or "-")
                if policy_proposal.get("weight_changes"):
                    st.dataframe(pd.DataFrame(policy_proposal["weight_changes"]), hide_index=True, width="stretch")
                st.json(
                    {
                        "proposal_id": policy_proposal.get("proposal_id"),
                        "base_policy_version": policy_proposal.get("base_policy_version"),
                        "proposed_policy_version": policy_proposal.get("proposed_policy_version"),
                        "rollback_compare_status": policy_proposal.get("rollback_compare_status"),
                    }
                )
        policy_replay = st.session_state.get("evidence_value_policy_replay") or {}
        if policy_replay:
            with st.expander("Evidence value policy replay"):
                pr1, pr2, pr3, pr4 = st.columns(4)
                pr1.metric("Status", policy_replay.get("status") or "-")
                pr2.metric("Gate", policy_replay.get("activation_gate_status") or "-")
                pr3.metric("Top N changes", policy_replay.get("top_n_change_count", 0))
                pr4.metric("Max score delta", policy_replay.get("max_abs_score_delta"))
                if policy_replay.get("rows"):
                    st.dataframe(pd.DataFrame(policy_replay["rows"]), hide_index=True, width="stretch")
        policy_activation = st.session_state.get("evidence_value_policy_activation") or {}
        active_policy = st.session_state.get("evidence_value_policy_active") or {}
        if policy_activation or active_policy:
            with st.expander("Evidence value active policy"):
                ap1, ap2, ap3, ap4 = st.columns(4)
                ap1.metric("Activation", policy_activation.get("status") or active_policy.get("activation_status") or "-")
                ap2.metric("Policy", active_policy.get("policy_version") or policy_activation.get("activated_policy_version") or "-")
                ap3.metric("Proposal", active_policy.get("source_proposal_id") or policy_activation.get("proposal_id") or "-")
                ap4.metric("Changes", policy_activation.get("weight_change_count", 0))
                if active_policy.get("weights"):
                    st.dataframe(pd.DataFrame([active_policy["weights"]]), hide_index=True, width="stretch")
        active_compare = st.session_state.get("evidence_value_policy_active_compare") or {}
        if active_compare:
            with st.expander("Evidence value active policy compare"):
                ac1, ac2, ac3, ac4 = st.columns(4)
                ac1.metric("Status", active_compare.get("status") or "-")
                ac2.metric("Max score delta", active_compare.get("max_abs_score_delta", 0))
                ac3.metric("Max rank delta", active_compare.get("max_abs_rank_delta", 0))
                ac4.metric("Profile flags", active_compare.get("profile_impact_review_count", 0))
                if active_compare.get("top_n_rows"):
                    st.dataframe(pd.DataFrame(active_compare["top_n_rows"]), hide_index=True, width="stretch")
        profile_impact_review = st.session_state.get("profile_impact_review_queue") or {}
        if profile_impact_review:
            with st.expander("Profile impact review queue"):
                pir1, pir2, pir3, pir4 = st.columns(4)
                pir1.metric("Status", profile_impact_review.get("status") or "-")
                pir2.metric("Rows", profile_impact_review.get("row_count", 0))
                pir3.metric("Open", profile_impact_review.get("open_review_count", 0))
                pir4.metric("Rollback target", profile_impact_review.get("rollback_target_policy_version") or "-")
                if profile_impact_review.get("severity_counts"):
                    st.json(profile_impact_review.get("severity_counts"))
                if profile_impact_review.get("rows"):
                    st.dataframe(pd.DataFrame(profile_impact_review["rows"]).drop(columns=["review_history"], errors="ignore"), hide_index=True, width="stretch")
        measurement_plan = st.session_state.get("measurement_feedback_plan") or {}
        if measurement_plan:
            with st.expander("Measurement feedback plan"):
                mf1, mf2, mf3, mf4 = st.columns(4)
                mf1.metric("Rows", measurement_plan.get("row_count", 0))
                mf2.metric("High priority", measurement_plan.get("high_priority_count", 0))
                mf3.metric("Candidates", measurement_plan.get("candidate_row_count", 0))
                mf4.metric("Series", measurement_plan.get("series_row_count", 0))
                feedback_cols = st.columns([0.38, 0.20, 0.20, 0.22])
                feedback_file = feedback_cols[0].file_uploader("Filled local evidence CSV", type=["csv"], key="measurement_feedback_result_csv")
                validate_feedback = feedback_cols[1].button(
                    "Validate local evidence",
                    width="stretch",
                    disabled=feedback_file is None,
                )
                import_feedback = feedback_cols[2].button(
                    "Import local evidence",
                    type="primary",
                    width="stretch",
                    disabled=feedback_file is None,
                )
                if feedback_file is not None and validate_feedback:
                    frame = pd.read_csv(feedback_file)
                    validation = validate_measurement_feedback_result_rows(frame.to_dict("records"), measurement_plan)
                    st.session_state["measurement_feedback_import_report"] = {
                        "status": "validation_only",
                        "importable_row_count": validation.get("importable_row_count", 0),
                        "rejected_row_count": validation.get("rejected_row_count", 0),
                        "calibration_ready_row_count": validation.get("calibration_ready_row_count", 0),
                        "validation": {key: value for key, value in validation.items() if key != "importable_rows"},
                    }
                    feedback_cols[1].info(f"Importable: {validation.get('importable_row_count', 0)}")
                if feedback_file is not None and import_feedback:
                    frame = pd.read_csv(feedback_file)
                    import_report = import_measurement_feedback_results_rows(
                        frame.to_dict("records"),
                        root=ROOT,
                        plan_path=MEASUREMENT_FEEDBACK_PLAN_PATH,
                        evidence_value_path=EVIDENCE_VALUE_REPORT_PATH,
                        source_path=feedback_file.name,
                        reviewer="streamlit",
                    )
                    write_measurement_feedback_import_report(
                        import_report,
                        MEASUREMENT_FEEDBACK_IMPORT_REPORT_PATH,
                        csv_path=MEASUREMENT_FEEDBACK_IMPORT_CSV_PATH,
                    )
                    st.session_state["measurement_feedback_import_report"] = import_report
                    if MEASUREMENT_FEEDBACK_PLAN_PATH.exists():
                        st.session_state["measurement_feedback_plan"] = json.loads(MEASUREMENT_FEEDBACK_PLAN_PATH.read_text(encoding="utf-8"))
                    feedback_cols[2].success(f"Imported: {import_report.get('importable_row_count', 0)}")
                if feedback_cols[3].button("Download feedback template", width="stretch"):
                    if MEASUREMENT_FEEDBACK_TEMPLATE_PATH.exists():
                        st.download_button(
                            "Measurement template CSV",
                            data=MEASUREMENT_FEEDBACK_TEMPLATE_PATH.read_text(encoding="utf-8"),
                            file_name="measurement_feedback_results_template.csv",
                            mime="text/csv",
                            width="stretch",
                        )
                if measurement_plan.get("rows"):
                    st.dataframe(pd.DataFrame(measurement_plan["rows"]), hide_index=True, width="stretch")
        feedback_import = st.session_state.get("measurement_feedback_import_report") or {}
        if feedback_import:
            with st.expander("Measurement feedback import"):
                mi1, mi2, mi3, mi4 = st.columns(4)
                mi1.metric("Status", feedback_import.get("status") or "-")
                mi2.metric("Importable", feedback_import.get("importable_row_count", 0))
                mi3.metric("Calibration ready", feedback_import.get("calibration_ready_row_count", 0))
                mi4.metric("Rejected", feedback_import.get("rejected_row_count", 0))
                issues = (feedback_import.get("validation") or {}).get("issues") or []
                if issues:
                    st.dataframe(pd.DataFrame(issues), hide_index=True, width="stretch")
                if feedback_import.get("rows"):
                    st.dataframe(pd.DataFrame(feedback_import["rows"]), hide_index=True, width="stretch")
        gap_closure = st.session_state.get("measurement_feedback_gap_closure") or {}
        if gap_closure:
            with st.expander("Measurement feedback gap closure"):
                mg1, mg2, mg3, mg4 = st.columns(4)
                mg1.metric("Status", gap_closure.get("status") or "-")
                mg2.metric("Open gaps", gap_closure.get("open_gap_count", 0))
                mg3.metric("Endpoint mismatch", gap_closure.get("endpoint_mismatch_count", 0))
                mg4.metric("Needs new", gap_closure.get("needs_new_measurement_count", 0))
                gap_rows = gap_closure.get("rows") or []
                if gap_rows:
                    decision_cols = st.columns([0.32, 0.18, 0.18, 0.22, 0.10])
                    selected_gap = decision_cols[0].selectbox(
                        "Gap row",
                        gap_rows,
                        format_func=lambda row: f"{row.get('measurement_plan_id')} | {row.get('candidate_id')} | {row.get('required_endpoint_group')} | {row.get('closure_status')}",
                        key="measurement_gap_review_row",
                    )
                    gap_decision = decision_cols[1].selectbox("Gap decision", sorted(MEASUREMENT_GAP_DECISIONS), key="measurement_gap_review_decision")
                    gap_reviewer = decision_cols[2].text_input("Gap reviewer", value="", key="measurement_gap_review_reviewer")
                    gap_note = decision_cols[3].text_input("Gap note", value="", key="measurement_gap_review_note")
                    if decision_cols[4].button("Save gap", width="stretch"):
                        reviewed_gap = review_measurement_feedback_gap_closure(
                            gap_path=MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH,
                            plan_path=MEASUREMENT_FEEDBACK_PLAN_PATH,
                            measurement_plan_ids=[str(selected_gap.get("measurement_plan_id") or "")],
                            decision=gap_decision,
                            reviewer=gap_reviewer or "streamlit",
                            note=gap_note or None,
                        )
                        write_measurement_feedback_gap_closure(
                            reviewed_gap,
                            MEASUREMENT_FEEDBACK_GAP_CLOSURE_PATH,
                            csv_path=MEASUREMENT_FEEDBACK_GAP_CLOSURE_CSV_PATH,
                        )
                        st.session_state["measurement_feedback_gap_closure"] = reviewed_gap
                        if MEASUREMENT_FEEDBACK_PLAN_PATH.exists():
                            st.session_state["measurement_feedback_plan"] = json.loads(MEASUREMENT_FEEDBACK_PLAN_PATH.read_text(encoding="utf-8"))
                        st.success(f"Gap decision saved: {gap_decision}")
                if gap_closure.get("rows"):
                    st.dataframe(pd.DataFrame(gap_closure["rows"]), hide_index=True, width="stretch")
        exact_intake = st.session_state.get("measurement_gap_exact_result_intake") or {}
        if exact_intake:
            with st.expander("Measurement gap exact result intake"):
                ei1, ei2, ei3, ei4 = st.columns(4)
                ei1.metric("Status", exact_intake.get("status") or "-")
                ei2.metric("Template rows", exact_intake.get("template_row_count", 0))
                ei3.metric("Pending exact", exact_intake.get("pending_exact_result_count", 0))
                ei4.metric("Importable", exact_intake.get("importable_exact_result_count", 0))
                if exact_intake.get("rows"):
                    st.dataframe(pd.DataFrame(exact_intake["rows"]), hide_index=True, width="stretch")
        endpoint_governance = st.session_state.get("measurement_gap_endpoint_governance") or {}
        if endpoint_governance:
            with st.expander("Measurement gap endpoint governance"):
                eg1, eg2, eg3, eg4 = st.columns(4)
                eg1.metric("Status", endpoint_governance.get("status") or "-")
                eg2.metric("Rows", endpoint_governance.get("row_count", 0))
                eg3.metric("Pending exact", endpoint_governance.get("strict_exact_pending_count", 0))
                eg4.metric("Blocked pairs", endpoint_governance.get("blocked_cross_endpoint_pair_count", 0))
                if endpoint_governance.get("strict_endpoint_status_counts"):
                    st.json(endpoint_governance.get("strict_endpoint_status_counts"))
                if endpoint_governance.get("rows"):
                    st.dataframe(pd.DataFrame(endpoint_governance["rows"]), hide_index=True, width="stretch")
        if st.session_state.get("project_evidence_gap_adjustment_candidates"):
            with st.expander("Profile adjustment candidates"):
                st.dataframe(pd.DataFrame(st.session_state["project_evidence_gap_adjustment_candidates"]), hide_index=True, width="stretch")
        promotion_registry = st.session_state.get("profile_promotion_registry") or {}
        if promotion_registry:
            with st.expander("Profile promotion registry"):
                pr1, pr2, pr3 = st.columns(3)
                pr1.metric("Records", promotion_registry.get("record_count", 0))
                pr2.metric("Requested", (promotion_registry.get("status_counts") or {}).get("review_requested", 0))
                pr3.metric("Active", (promotion_registry.get("status_counts") or {}).get("active", 0))
                if promotion_registry.get("records"):
                    promo_records = promotion_registry["records"]
                    promo_cols = st.columns([0.36, 0.18, 0.18, 0.20, 0.08])
                    selected_promo = promo_cols[0].selectbox(
                        "Promotion record",
                        promo_records,
                        format_func=lambda row: f"{row.get('promotion_id')} | {row.get('artifact_id')} | {row.get('promotion_status')}",
                        key="profile_promotion_record_select",
                    )
                    promo_status = promo_cols[1].selectbox(
                        "Promotion status",
                        ["review_requested", "approved", "active", "deferred", "rejected", "draft"],
                        key="profile_promotion_status_update",
                    )
                    promo_reviewer = promo_cols[2].text_input("Promotion reviewer", value="", key="profile_promotion_reviewer")
                    promo_note = promo_cols[3].text_input("Promotion note", value="", key="profile_promotion_note")
                    if promo_cols[4].button("Save", width="stretch", key="profile_promotion_save_status"):
                        registry = update_profile_promotion_status(
                            str(selected_promo.get("promotion_id")),
                            status=promo_status,
                            registry_path=PROFILE_PROMOTION_REGISTRY_PATH,
                            reviewer=promo_reviewer or "streamlit",
                            note=promo_note or None,
                        )
                        gate_report = build_closed_loop_promotion_gate(root=ROOT, project_name=ops_project_name or None)
                        write_closed_loop_promotion_gate(gate_report, CLOSED_LOOP_PROMOTION_GATE_PATH)
                        st.session_state["profile_promotion_registry"] = registry
                        st.session_state["closed_loop_promotion_gate"] = gate_report
                        st.success(f"Promotion status saved: {promo_status}")
                    st.dataframe(pd.DataFrame(promo_records).drop(columns=["artifact_summary", "status_history"], errors="ignore"), hide_index=True, width="stretch")
        ab_report = st.session_state.get("profile_ab_replay_report") or {}
        if ab_report:
            with st.expander("Profile A/B replay"):
                ab1, ab2, ab3, ab4 = st.columns(4)
                ab1.metric("Status", ab_report.get("status") or "-")
                ab2.metric("Review", ab_report.get("review_status") or "-")
                ab3.metric("Changed top N", ab_report.get("changed_top_n_count", 0))
                ab4.metric("Max score delta", ab_report.get("max_score_delta", 0))
                if ab_report.get("rows"):
                    st.dataframe(pd.DataFrame(ab_report["rows"]), hide_index=True, width="stretch")
        ab_matrix = st.session_state.get("profile_ab_replay_matrix") or {}
        if ab_matrix:
            with st.expander("Profile A/B matrix"):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Status", ab_matrix.get("status") or "-")
                m2.metric("Scenarios", ab_matrix.get("scenario_count", 0))
                m3.metric("Review required", ab_matrix.get("review_required_count", 0))
                m4.metric("Max changed top N", ab_matrix.get("max_changed_top_n_count", 0))
                if ab_matrix.get("summary_rows"):
                    st.dataframe(pd.DataFrame(ab_matrix["summary_rows"]), hide_index=True, width="stretch")
        material_review = st.session_state.get("profile_ab_material_change_review") or {}
        if material_review:
            with st.expander("Profile A/B material review"):
                mr1, mr2, mr3, mr4 = st.columns(4)
                mr1.metric("Status", material_review.get("status") or "-")
                mr2.metric("Material scenarios", material_review.get("material_change_scenario_count", 0))
                mr3.metric("Candidate diffs", material_review.get("candidate_diff_count", 0))
                mr4.metric("Accepted", material_review.get("accepted_profile_change_count", 0))
                if material_review.get("candidate_diff_rows"):
                    st.dataframe(pd.DataFrame(material_review["candidate_diff_rows"]), hide_index=True, width="stretch")
        assay_triage = st.session_state.get("assay_event_triage_report") or {}
        if assay_triage:
            with st.expander("Assay event triage"):
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Status", assay_triage.get("status") or "-")
                t2.metric("Events", assay_triage.get("event_count", 0))
                t3.metric("Resolved follow-up", assay_triage.get("real_followup_resolved_count", 0))
                t4.metric("Planned follow-up", assay_triage.get("planned_followup_count", 0))
                followup_cols = st.columns([0.28, 0.32, 0.20, 0.20])
                if followup_cols[0].button("Build follow-up template", width="stretch"):
                    template = build_assay_followup_result_template(
                        triage_report_path=ASSAY_EVENT_TRIAGE_REPORT_PATH,
                        output_path=ASSAY_FOLLOWUP_TEMPLATE_PATH,
                    )
                    st.session_state["assay_followup_template_report"] = template
                    followup_cols[1].info(f"Template rows: {template.get('template_row_count', 0)}")
                followup_file = followup_cols[1].file_uploader("Filled follow-up CSV", type=["csv"], key="assay_followup_result_csv")
                if followup_file is not None and followup_cols[2].button("Validate follow-up", width="stretch"):
                    frame = pd.read_csv(followup_file)
                    from localmedchem.assay_followup_results import validate_assay_followup_result_rows  # noqa: PLC0415

                    validation = validate_assay_followup_result_rows(frame.to_dict("records"))
                    st.session_state["assay_followup_result_import_report"] = {
                        "status": "validation_only",
                        "validation": validation,
                        "import": {"event_count": 0},
                    }
                    followup_cols[2].info(f"Importable: {validation.get('importable_row_count', 0)}")
                if followup_file is not None and followup_cols[3].button("Import follow-up", type="primary", width="stretch"):
                    frame = pd.read_csv(followup_file)
                    import_report = import_assay_followup_results_rows(
                        frame.to_dict("records"),
                        db_path=DB_PATH,
                        source_path=followup_file.name,
                        project_name=None,
                        reviewer="streamlit",
                    )
                    write_assay_followup_import_report(
                        import_report,
                        ASSAY_FOLLOWUP_IMPORT_REPORT_PATH,
                        csv_path=ASSAY_FOLLOWUP_IMPORT_CSV_PATH,
                    )
                    st.session_state["assay_followup_result_import_report"] = import_report
                    st.session_state["assay_event_triage_report"] = json.loads(ASSAY_EVENT_TRIAGE_REPORT_PATH.read_text(encoding="utf-8"))
                if assay_triage.get("rows"):
                    st.dataframe(pd.DataFrame(assay_triage["rows"]), hide_index=True, width="stretch")
        followup_import = st.session_state.get("assay_followup_result_import_report") or {}
        if followup_import:
            with st.expander("Assay follow-up import"):
                fi1, fi2, fi3 = st.columns(3)
                fi1.metric("Status", followup_import.get("status") or "-")
                fi2.metric("Imported", (followup_import.get("import") or {}).get("event_count", 0))
                fi3.metric("Resolved", followup_import.get("real_followup_resolved_count", 0))
                issues = (followup_import.get("validation") or {}).get("issues") or []
                if issues:
                    st.dataframe(pd.DataFrame(issues), hide_index=True, width="stretch")
        freeze_manifest = st.session_state.get("profile_promotion_freeze_manifest") or {}
        if freeze_manifest:
            with st.expander("Profile promotion freeze"):
                f1, f2, f3 = st.columns(3)
                f1.metric("Freeze", freeze_manifest.get("freeze_id") or "-")
                f2.metric("Present assets", freeze_manifest.get("present_asset_count", 0))
                f3.metric("Missing assets", freeze_manifest.get("missing_asset_count", 0))
                if freeze_manifest.get("assets"):
                    st.dataframe(pd.DataFrame(freeze_manifest["assets"]), hide_index=True, width="stretch")
        freeze_approvals = st.session_state.get("profile_promotion_freeze_approvals") or {}
        if freeze_approvals:
            with st.expander("Profile freeze approvals"):
                fa1, fa2, fa3 = st.columns(3)
                fa1.metric("Active freeze", freeze_approvals.get("active_freeze_id") or "-")
                fa2.metric("Events", freeze_approvals.get("event_count", 0))
                fa3.metric("Release tag", freeze_approvals.get("latest_release_tag") or "-")
                if freeze_approvals.get("events"):
                    st.dataframe(pd.DataFrame(freeze_approvals["events"]), hide_index=True, width="stretch")
        rollback_drill = st.session_state.get("profile_promotion_freeze_rollback_drill") or {}
        if rollback_drill:
            with st.expander("Profile freeze rollback drill"):
                rd1, rd2, rd3, rd4 = st.columns(4)
                rd1.metric("Status", rollback_drill.get("status") or "-")
                rd2.metric("Mode", rollback_drill.get("execution_mode") or "-")
                rd3.metric("Target freeze", rollback_drill.get("target_freeze_id") or "-")
                rd4.metric("Review checks", rollback_drill.get("review_count", 0))
                if rollback_drill.get("checks"):
                    st.dataframe(pd.DataFrame(rollback_drill["checks"]), hide_index=True, width="stretch")
        rollback_replay = st.session_state.get("profile_promotion_rollback_replay") or {}
        if rollback_replay:
            with st.expander("Profile rollback replay"):
                rr1, rr2, rr3, rr4 = st.columns(4)
                rr1.metric("Status", rollback_replay.get("status") or "-")
                rr2.metric("Rows", rollback_replay.get("row_count", 0))
                rr3.metric("Max score delta", rollback_replay.get("max_abs_rollback_score_delta", 0))
                rr4.metric("Max rank delta", rollback_replay.get("max_abs_rollback_rank_delta", 0))
                if rollback_replay.get("rows"):
                    st.dataframe(pd.DataFrame(rollback_replay["rows"]), hide_index=True, width="stretch")
        rollback_history = st.session_state.get("profile_rollback_history") or {}
        if rollback_history:
            with st.expander("Profile rollback history"):
                rh1, rh2, rh3, rh4 = st.columns(4)
                rh1.metric("Status", rollback_history.get("status") or "-")
                rh2.metric("Snapshots", rollback_history.get("snapshot_count", 0))
                rh3.metric("Candidate history", rollback_history.get("candidate_history_count", 0))
                rh4.metric("Transitions", len(rollback_history.get("transitions") or []))
                if rollback_history.get("snapshots"):
                    snapshot_options = [str(row.get("snapshot_id") or "") for row in rollback_history["snapshots"] if row.get("snapshot_id")]
                    if len(snapshot_options) >= 2:
                        compare_cols = st.columns([0.34, 0.34, 0.18, 0.14])
                        base_snapshot = compare_cols[0].selectbox("Base snapshot", snapshot_options, index=min(1, len(snapshot_options) - 1), key="rollback_compare_base_snapshot")
                        head_snapshot = compare_cols[1].selectbox("Head snapshot", snapshot_options, index=0, key="rollback_compare_head_snapshot")
                        if compare_cols[2].button("Compare snapshots", width="stretch"):
                            comparison = compare_profile_rollback_snapshots(
                                rollback_history,
                                base_snapshot_id=base_snapshot,
                                head_snapshot_id=head_snapshot,
                                project_name=ops_project_name or None,
                            )
                            write_profile_rollback_snapshot_compare(
                                comparison,
                                PROFILE_ROLLBACK_SNAPSHOT_COMPARE_PATH,
                                csv_path=PROFILE_ROLLBACK_SNAPSHOT_COMPARE_CSV_PATH,
                            )
                            st.session_state["profile_rollback_snapshot_compare"] = comparison
                            compare_cols[3].success(f"Changed: {comparison.get('changed_candidate_count', 0)}")
                    st.dataframe(pd.DataFrame(rollback_history["snapshots"]), hide_index=True, width="stretch")
                if rollback_history.get("candidate_history_rows"):
                    st.dataframe(pd.DataFrame(rollback_history["candidate_history_rows"]), hide_index=True, width="stretch")
        rollback_compare = st.session_state.get("profile_rollback_snapshot_compare") or {}
        if rollback_compare:
            with st.expander("Rollback snapshot compare"):
                rc1, rc2, rc3, rc4 = st.columns(4)
                rc1.metric("Status", rollback_compare.get("status") or "-")
                rc2.metric("Changed", rollback_compare.get("changed_candidate_count", 0))
                rc3.metric("Added", rollback_compare.get("added_candidate_count", 0))
                rc4.metric("Removed", rollback_compare.get("removed_candidate_count", 0))
                if rollback_compare.get("rows"):
                    st.dataframe(pd.DataFrame(rollback_compare["rows"]), hide_index=True, width="stretch")
        refresh_report = st.session_state.get("project_memory_refresh_report") or {}
        if refresh_report:
            with st.expander("Project memory refresh"):
                rf1, rf2, rf3 = st.columns(3)
                rf1.metric("Status", refresh_report.get("status") or "-")
                rf2.metric("Passed steps", refresh_report.get("passed_step_count", 0))
                rf3.metric("Failed steps", refresh_report.get("failed_step_count", 0))
                if refresh_report.get("steps"):
                    st.dataframe(pd.DataFrame(refresh_report["steps"]), hide_index=True, width="stretch")
        if st.session_state.get("closed_loop_residual_result_template_rows"):
            template_df = pd.DataFrame(st.session_state["closed_loop_residual_result_template_rows"])
            st.download_button(
                "Download residual result template",
                data=template_df.to_csv(index=False),
                file_name="residual_experiment_results_template.csv",
                mime="text/csv",
                width="stretch",
            )
        with st.expander("Residual result import"):
            residual_file = st.file_uploader("Filled residual result CSV", type=["csv"], key="closed_loop_residual_result_csv")
            residual_import_cols = st.columns([0.34, 0.33, 0.33])
            if residual_import_cols[0].button("Build intake manifest", width="stretch"):
                intake = build_residual_result_intake_manifest(
                    plan_path=RESIDUAL_EXPERIMENT_PLAN_PATH,
                    registry_path=EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                )
                write_residual_result_intake_manifest(
                    intake,
                    RESIDUAL_RESULT_INTAKE_MANIFEST_PATH,
                    csv_path=RESIDUAL_RESULT_INTAKE_MANIFEST_CSV_PATH,
                )
                st.session_state["residual_result_intake_manifest"] = intake
                residual_import_cols[1].info(f"Pending intake: {intake.get('pending_intake_count', 0)}")
            if residual_file is not None and residual_import_cols[0].button("Validate residual results", width="stretch"):
                try:
                    residual_frame = pd.read_csv(residual_file)
                    validation = validate_experiment_result_rows(residual_frame.to_dict("records"), residual_only=True)
                    st.session_state["closed_loop_residual_import_report"] = {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "status": "validation_only",
                        "validation_only": True,
                        "source_path": residual_file.name,
                        "validation": validation,
                        "import": {"event_count": 0, "residual_task_closed_count": 0},
                    }
                    residual_import_cols[1].info(f"Importable rows: {validation.get('importable_row_count', 0)}")
                except Exception as exc:
                    residual_import_cols[1].error(str(exc))
            if residual_file is not None and residual_import_cols[2].button("Import and refresh gate", type="primary", width="stretch"):
                try:
                    residual_frame = pd.read_csv(residual_file)
                    import_report = import_residual_experiment_results_rows(
                        residual_frame.to_dict("records"),
                        db_path=DB_PATH,
                        source_path=residual_file.name,
                        residual_task_registry_path=EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
                    )
                    dashboard = build_project_closed_loop_dashboard(
                        root=ROOT,
                        db_path=DB_PATH,
                        project_name=ops_project_name or None,
                    )
                    write_project_closed_loop_dashboard(dashboard, PROJECT_CLOSED_LOOP_DASHBOARD_PATH)
                    replay_report = build_closed_loop_replay_report(
                        root=ROOT,
                        db_path=DB_PATH,
                        project_name=ops_project_name or None,
                    )
                    write_closed_loop_replay_report(replay_report, CLOSED_LOOP_REPLAY_REPORT_PATH)
                    pack = build_project_evidence_pack(
                        root=ROOT,
                        db_path=DB_PATH,
                        project_name=ops_project_name or None,
                    )
                    write_project_evidence_pack(
                        pack,
                        PROJECT_EVIDENCE_PACK_PATH,
                        summary_csv_path=PROJECT_EVIDENCE_PACK_SUMMARY_PATH,
                    )
                    expansion = build_project_evidence_expansion_plan(root=ROOT, project_name=ops_project_name or None)
                    write_project_evidence_expansion_plan(
                        expansion,
                        PROJECT_EVIDENCE_EXPANSION_PLAN_PATH,
                        csv_path=PROJECT_EVIDENCE_EXPANSION_PLAN_CSV_PATH,
                    )
                    gate_report = build_closed_loop_promotion_gate(root=ROOT, project_name=ops_project_name or None)
                    write_closed_loop_promotion_gate(gate_report, CLOSED_LOOP_PROMOTION_GATE_PATH)
                    st.session_state["closed_loop_residual_import_report"] = import_report
                    st.session_state["project_closed_loop_dashboard"] = dashboard
                    st.session_state["closed_loop_replay_report"] = replay_report
                    st.session_state["project_evidence_pack"] = pack
                    st.session_state["project_evidence_expansion_plan"] = expansion
                    st.session_state["closed_loop_promotion_gate"] = gate_report
                    st.success(f"Imported {import_report.get('import', {}).get('event_count', 0)} residual result events.")
                except Exception as exc:
                    st.error(str(exc))
            if st.session_state.get("closed_loop_residual_import_report"):
                report = st.session_state["closed_loop_residual_import_report"]
                validation = report.get("validation") or {}
                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Validation", validation.get("status") or "-")
                v2.metric("Importable", validation.get("importable_row_count", 0))
                v3.metric("Errors", validation.get("error_count", 0))
                v4.metric("Closed tasks", (report.get("import") or {}).get("residual_task_closed_count", 0))
                if validation.get("issues"):
                    st.dataframe(pd.DataFrame(validation["issues"]), hide_index=True, width="stretch")

    st.subheader("Prospective Feedback Control")
    pf1, pf2, pf3 = st.columns([0.3, 0.3, 0.4])
    control_project_name = pf1.text_input("Control project", value="", key="feedback_control_project")
    control_min_feedback = pf2.number_input("Min feedback", min_value=2, max_value=20, value=3, key="feedback_control_min")
    if pf3.button("Build feedback control report", width="stretch"):
        control_report = build_feedback_control_report(
            db_path=DB_PATH,
            project_name=control_project_name or None,
            min_feedback=int(control_min_feedback),
        )
        save_feedback_control_report(
            control_report,
            output_path=ROOT / "data" / "projects" / "demo" / "feedback_control_report.json",
            db_path=DB_PATH,
        )
        st.session_state["feedback_control_report"] = control_report
    control_path = ROOT / "data" / "projects" / "demo" / "feedback_control_report.json"
    if "feedback_control_report" not in st.session_state and control_path.exists():
        try:
            st.session_state["feedback_control_report"] = json.loads(control_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if "feedback_control_report" in st.session_state:
        control = st.session_state["feedback_control_report"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Candidates", control.get("candidate_count", 0))
        c2.metric("Feedback", control.get("feedback_observation_count", 0))
        c3.metric("Uncertainty", len(control.get("uncertainty_flags") or []))
        c4.metric("Drift", len(control.get("drift_flags") or []))
        if control.get("recommended_next_experiments"):
            st.dataframe(pd.DataFrame(control["recommended_next_experiments"]), hide_index=True, width="stretch")
        delta_path = ROOT / "data" / "projects" / "closed_loop" / f"priority_delta_{control_project_name or 'all'}.json"
        if delta_path.exists():
            try:
                priority_delta = json.loads(delta_path.read_text(encoding="utf-8"))
                with st.expander("Closed-loop priority delta"):
                    pd1, pd2, pd3 = st.columns(3)
                    pd1.metric("Delta rows", priority_delta.get("candidate_count", 0))
                    pd2.metric("Feedback linked", priority_delta.get("feedback_linked_count", 0))
                    pd3.metric("Status groups", len(priority_delta.get("status_counts") or {}))
                    if priority_delta.get("priority_delta_rows"):
                        st.dataframe(pd.DataFrame(priority_delta["priority_delta_rows"]), hide_index=True, width="stretch")
                    queue_delta_out = (
                        QUEUE_ANALOG_SERIES_DELTA_PATH
                        if not control_project_name
                        else QUEUE_ANALOG_SERIES_DELTA_PATH.with_name(f"queue_analog_series_delta_{control_project_name}.json")
                    )
                    if st.button("Build queue analog-series delta", width="stretch"):
                        queue_delta_report = build_queue_analog_series_delta(priority_delta)
                        write_queue_analog_series_delta_report(queue_delta_report, queue_delta_out)
                        st.session_state["queue_analog_series_delta_report"] = queue_delta_report
                        st.success(f"Queue analog-series delta written to {queue_delta_out.name}.")
            except Exception:
                pass
        queue_dir = ROOT / "data" / "projects" / "closed_loop"
        queue_files = sorted(queue_dir.glob("next_design_queue_*.json"))
        if queue_files:
            with st.expander("Next design queue"):
                selected_queue = st.selectbox(
                    "Queue file",
                    [path.name for path in queue_files],
                    key="next_design_queue_file",
                )
                queue_path = queue_dir / selected_queue
                try:
                    queue_payload = json.loads(queue_path.read_text(encoding="utf-8"))
                    queue_rows = queue_payload.get("queue") or []
                    if queue_rows:
                        st.dataframe(pd.DataFrame(queue_rows), hide_index=True, width="stretch")
                        review_cols = st.columns([0.30, 0.18, 0.20, 0.22, 0.10])
                        selected_queue_row = review_cols[0].selectbox(
                            "Review row",
                            queue_rows,
                            format_func=lambda row: f"{row.get('queue_id')} | {row.get('candidate_id')} | {row.get('endpoint_group')}",
                            key="next_design_queue_review_row",
                        )
                        queue_decision = review_cols[1].selectbox(
                            "Decision",
                            ["accepted", "deferred", "retired", "needs_review"],
                            key="next_design_queue_decision",
                        )
                        queue_owner = review_cols[2].text_input("Owner", value="", key="next_design_queue_owner")
                        queue_note = review_cols[3].text_input("Note", value="", key="next_design_queue_note")
                        if review_cols[4].button("Save", key="save_next_design_queue_decision", width="stretch"):
                            payload = {
                                **selected_queue_row,
                                "queue_decision": queue_decision,
                                "owner": queue_owner or "streamlit",
                                "review_note": queue_note,
                                "reviewed_at": pd.Timestamp.utcnow().isoformat(),
                            }
                            save_report = save_next_design_queue_decisions([payload], db_path=DB_PATH, source_path=str(queue_path))
                            st.success(f"Saved {save_report.get('saved_count', 0)} queue decision.")
                        with st.expander("Bulk queue actions"):
                            endpoints = sorted({str(row.get("endpoint_group") or "") for row in queue_rows if row.get("endpoint_group")})
                            actions = sorted({str(row.get("recommendation_action") or "") for row in queue_rows if row.get("recommendation_action")})
                            bulk_cols = st.columns([0.18, 0.20, 0.20, 0.16, 0.16, 0.10])
                            bulk_decision = bulk_cols[0].selectbox(
                                "Decision",
                                ["accepted", "deferred", "retired", "needs_review"],
                                key="next_design_queue_bulk_decision",
                            )
                            bulk_endpoint = bulk_cols[1].selectbox(
                                "Endpoint",
                                ["All", *endpoints],
                                key="next_design_queue_bulk_endpoint",
                            )
                            bulk_action = bulk_cols[2].selectbox(
                                "Action",
                                ["All", *actions],
                                key="next_design_queue_bulk_action",
                            )
                            bulk_owner = bulk_cols[3].text_input("Owner", value="", key="next_design_queue_bulk_owner")
                            bulk_note = bulk_cols[4].text_input("Note", value="", key="next_design_queue_bulk_note")
                            bulk_max_rows = bulk_cols[5].number_input(
                                "Max",
                                min_value=1,
                                max_value=max(1, len(queue_rows)),
                                value=min(25, max(1, len(queue_rows))),
                                step=1,
                                key="next_design_queue_bulk_max_rows",
                            )
                            bulk_preview = build_bulk_next_design_queue_decisions(
                                queue_rows,
                                bulk_decision,
                                owner=bulk_owner or "streamlit-bulk",
                                review_note=bulk_note,
                                endpoint_group=None if bulk_endpoint == "All" else bulk_endpoint,
                                recommendation_action=None if bulk_action == "All" else bulk_action,
                                max_rows=int(bulk_max_rows),
                            )
                            st.caption(f"Matched rows: {len(bulk_preview)}")
                            if st.button("Save bulk decisions", key="save_next_design_queue_bulk_decisions", width="stretch"):
                                save_report = save_next_design_queue_decisions(bulk_preview, db_path=DB_PATH, source_path=str(queue_path))
                                st.success(f"Saved {save_report.get('saved_count', 0)} bulk queue decisions.")
                        quality_path = queue_dir / "next_design_queue_decision_quality.json"
                        if st.button("Refresh queue decision quality", key="refresh_queue_decision_quality", width="stretch"):
                            quality_report = build_next_design_queue_decision_quality_report(
                                db_path=DB_PATH,
                                project_name=control_project_name or None,
                            )
                            write_next_design_queue_decision_quality_report(quality_report, quality_path)
                            st.session_state["next_design_queue_decision_quality"] = quality_report
                        audit_rows = list_next_design_queue_decision_events(
                            db_path=DB_PATH,
                            project_name=control_project_name or None,
                            limit=100,
                        )
                        if audit_rows:
                            st.caption("Queue decision audit")
                            st.dataframe(pd.DataFrame(audit_rows).drop(columns=["payload_json"], errors="ignore"), hide_index=True, width="stretch")
                        quality_report = st.session_state.get("next_design_queue_decision_quality")
                        if quality_report:
                            qqual1, qqual2, qqual3 = st.columns(3)
                            qqual1.metric("Decision events", quality_report.get("decision_event_count", 0))
                            qqual2.metric("Observed", quality_report.get("observed_decision_count", 0))
                            qqual3.metric("Decision groups", len(quality_report.get("decision_counts") or {}))
                            if quality_report.get("by_decision_and_endpoint"):
                                st.dataframe(pd.DataFrame(quality_report["by_decision_and_endpoint"]), hide_index=True, width="stretch")
                            if quality_report.get("reviewer_calibration_hints"):
                                st.caption("Reviewer calibration hints")
                                st.dataframe(pd.DataFrame(quality_report["reviewer_calibration_hints"]), hide_index=True, width="stretch")
                        st.download_button(
                            "Download next design queue",
                            data=pd.DataFrame(queue_rows).to_csv(index=False),
                            file_name=selected_queue.replace(".json", ".csv"),
                            mime="text/csv",
                        )
                    else:
                        st.caption("Queue is empty.")
                except Exception:
                    st.caption("Could not read next design queue.")
        queue_delta_files = sorted(queue_dir.glob("queue_analog_series_delta*.json"))
        if queue_delta_files or st.session_state.get("queue_analog_series_delta_report"):
            with st.expander("Queue analog-series delta"):
                selected_delta_payload = st.session_state.get("queue_analog_series_delta_report")
                if queue_delta_files:
                    selected_delta_file = st.selectbox(
                        "Series delta file",
                        [path.name for path in queue_delta_files],
                        key="queue_analog_series_delta_file",
                    )
                    try:
                        selected_delta_payload = json.loads((queue_dir / selected_delta_file).read_text(encoding="utf-8"))
                    except Exception:
                        selected_delta_payload = selected_delta_payload or {}
                if selected_delta_payload:
                    qd1, qd2, qd3 = st.columns(3)
                    qd1.metric("Series", selected_delta_payload.get("series_count", 0))
                    qd2.metric("Candidates", selected_delta_payload.get("candidate_count", 0))
                    qd3.metric("Feedback linked", selected_delta_payload.get("feedback_linked_count", 0))
                    qd_rows = selected_delta_payload.get("series") or []
                    if qd_rows:
                        st.dataframe(
                            pd.DataFrame([{key: value for key, value in row.items() if key != "example_candidates"} for row in qd_rows]),
                            hide_index=True,
                            width="stretch",
                        )
                        st.download_button(
                            "Download queue analog-series delta",
                            data=json.dumps(selected_delta_payload, indent=2, sort_keys=True),
                            file_name="queue_analog_series_delta.json",
                            mime="application/json",
                        )
                    policy_doc = load_queue_analog_series_policy_document(QUEUE_ANALOG_SERIES_POLICY_PATH)
                    policy_versions = [str(item.get("version")) for item in policy_doc.get("versions") or [] if item.get("version")]
                    active_policy = next((item for item in policy_doc.get("versions") or [] if item.get("version") == policy_doc.get("active_version")), {})
                    policy_cols = st.columns([0.3, 0.25, 0.25, 0.2])
                    policy_cols[0].metric("Active policy", policy_doc.get("active_version") or "heuristic-v1")
                    new_policy_version = policy_cols[1].text_input("New policy version", value="", key="queue_policy_new_version")
                    policy_reviewer = policy_cols[2].text_input("Policy reviewer", value="", key="queue_policy_reviewer")
                    policy_blend = policy_cols[3].number_input("Blend", min_value=0.0, max_value=1.0, value=0.45, step=0.05, key="queue_policy_blend")
                    if st.button("Calibrate queue series policy", width="stretch"):
                        try:
                            updated_policy = calibrate_queue_analog_series_policy(
                                selected_delta_payload,
                                previous_policy=policy_doc,
                                version=new_policy_version.strip() or None,
                                reviewer=policy_reviewer or "streamlit",
                                blend=float(policy_blend),
                            )
                            write_queue_analog_series_policy(updated_policy, QUEUE_ANALOG_SERIES_POLICY_PATH)
                            st.success(f"Queue series policy active version: {updated_policy.get('active_version')}")
                        except Exception as exc:
                            st.error(str(exc))
                    if policy_versions:
                        rollback_cols = st.columns([0.4, 0.6])
                        rollback_version = rollback_cols[0].selectbox("Rollback version", policy_versions, key="queue_policy_rollback_version")
                        rollback_note = rollback_cols[1].text_input("Rollback note", value="", key="queue_policy_rollback_note")
                        if st.button("Rollback queue series policy", width="stretch"):
                            try:
                                rolled_back = rollback_queue_analog_series_policy(
                                    policy_doc,
                                    version=rollback_version,
                                    reviewer=policy_reviewer or "streamlit",
                                    note=rollback_note or None,
                                )
                                write_queue_analog_series_policy(rolled_back, QUEUE_ANALOG_SERIES_POLICY_PATH)
                                st.success(f"Rolled back active policy to {rollback_version}.")
                            except Exception as exc:
                                st.error(str(exc))
                    if active_policy.get("context_summaries"):
                        st.dataframe(pd.DataFrame(active_policy.get("context_summaries") or []), hide_index=True, width="stretch")
        plan_cols = st.columns([0.22, 0.22, 0.56])
        plan_size = plan_cols[0].number_input("Plan size", min_value=1, max_value=96, value=24, key="experiment_plan_size")
        endpoint_filter = plan_cols[1].text_input("Endpoint filter", value="", key="experiment_plan_endpoint")
        if plan_cols[2].button("Build experiment plan CSV", width="stretch"):
            endpoints = [endpoint_filter.strip()] if endpoint_filter.strip() else []
            plan_rows = build_experiment_plan(control, batch_size=int(plan_size), endpoint_groups=endpoints)
            plan_path = ROOT / "data" / "projects" / "demo" / "experiment_plan.csv"
            write_experiment_plan_csv(plan_rows, plan_path)
            plan_db_report = upsert_experiment_plan_rows(plan_rows, db_path=DB_PATH, source_path=str(plan_path))
            st.session_state["experiment_plan_rows"] = plan_rows
            st.session_state["experiment_plan_path"] = str(plan_path)
            st.session_state["experiment_plan_db_report"] = plan_db_report
        if st.session_state.get("experiment_plan_rows"):
            plan_frame = pd.DataFrame(st.session_state["experiment_plan_rows"])
            st.dataframe(plan_frame, hide_index=True, width="stretch")
            if st.session_state.get("experiment_plan_db_report"):
                st.caption(f"Tracked {st.session_state['experiment_plan_db_report'].get('upserted_count', 0)} plan rows in project memory.")
            st.download_button(
                "Download experiment plan",
                data=plan_frame.to_csv(index=False),
                file_name="experiment_plan.csv",
                mime="text/csv",
                width="stretch",
            )
        st.subheader("Experiment Result Import")
        result_file = st.file_uploader("Experiment plan/result CSV", type=["csv"], key="experiment_result_csv")
        result_cols = st.columns([0.35, 0.65])
        with result_cols[0]:
            if result_file is not None and st.button("Import experiment results", type="primary", width="stretch"):
                try:
                    result_frame = pd.read_csv(result_file)
                    result_report = import_experiment_results_rows(
                        result_frame.to_dict("records"),
                        db_path=DB_PATH,
                        source_path=result_file.name,
                    )
                    st.session_state["experiment_result_report"] = result_report
                    st.success(f"Imported {result_report['event_count']} result events.")
                except Exception as exc:
                    st.error(str(exc))
        with result_cols[1]:
            if st.button("Refresh experiment learning", width="stretch"):
                st.session_state["experiment_summary"] = summarize_experiment_plans(
                    db_path=DB_PATH,
                    project_name=control_project_name or None,
                )
                st.session_state["assay_learning_summary"] = build_assay_learning_report(db_path=DB_PATH, project_name=control_project_name or None)
            if st.session_state.get("experiment_summary"):
                st.json(st.session_state["experiment_summary"])
            if st.session_state.get("experiment_result_report"):
                st.json(st.session_state["experiment_result_report"])
        learning = st.session_state.get("assay_learning_summary") or {}
        if learning.get("event_count"):
            l1, l2, l3 = st.columns(3)
            l1.metric("Assay events", learning.get("event_count", 0))
            l2.metric("Endpoints learned", learning.get("endpoint_count", 0))
            l3.metric("Retest events", len(learning.get("retest_events") or []))
            st.dataframe(pd.DataFrame(learning.get("endpoints", [])), hide_index=True, width="stretch")
    st.divider()

    st.subheader("Strategy Learning Panel")
    strategy_cols = st.columns([0.20, 0.15, 0.15, 0.14, 0.14, 0.22])
    strategy_project = strategy_cols[0].text_input("Strategy project", value=control_project_name, key="strategy_project_name")
    strategy_family_filter = strategy_cols[1].text_input("Target family", value="", key="strategy_family_filter")
    strategy_endpoint_filter = strategy_cols[2].text_input("Endpoint", value="", key="strategy_endpoint_filter")
    strategy_site_filter = strategy_cols[3].text_input("Site type", value="", key="strategy_site_filter")
    strategy_window_days = strategy_cols[4].number_input("Window days", min_value=30, max_value=1825, value=365, step=30, key="strategy_window_days")
    if strategy_cols[5].button("Build strategy panel", width="stretch"):
        st.session_state["project_strategy_learning_report"] = build_decision_strategy_learning_report(
            db_path=DB_PATH,
            project_name=strategy_project or None,
            since_days=int(strategy_window_days),
        )
    panel_report = st.session_state.get("project_strategy_learning_report")
    if panel_report and panel_report.get("strategies"):
        strategies = panel_report.get("strategies", [])
        if strategy_family_filter:
            strategies = [row for row in strategies if strategy_family_filter.lower() in str(row.get("target_family") or "").lower()]
        if strategy_endpoint_filter:
            strategies = [row for row in strategies if strategy_endpoint_filter.lower() in str(row.get("endpoint_group") or "").lower()]
        if strategy_site_filter:
            strategies = [row for row in strategies if strategy_site_filter.lower() in str(row.get("site_type") or "").lower()]
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Strategies", panel_report.get("strategy_count", 0))
        s2.metric("Observed", panel_report.get("observed_strategy_count", 0))
        s3.metric("Shown", len(strategies))
        s4.metric("Promote", sum(1 for row in strategies if row.get("strategy_recommendation") == "promote_strategy"))
        st.caption(
            f"version {panel_report.get('strategy_version') or '-'} | policy {panel_report.get('policy_version') or '-'} | "
            f"window {panel_report.get('window_days') or 'all'} days"
        )
        st.dataframe(pd.DataFrame(strategies), hide_index=True, width="stretch")
        st.caption("; ".join(panel_report.get("recommended_next_actions") or []))
    else:
        st.caption("Build the strategy panel after decision packets and experiment outcomes exist.")
    if st.session_state.get("last_rows"):
        with st.expander("Compare current candidate table with strategy policy"):
            comparison = compare_strategy_policy_effect(st.session_state["last_rows"])
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("Candidates", comparison.get("candidate_count", 0))
            cc2.metric("Top-N changed", comparison.get("changed_top_n_count", 0))
            cc3.metric("Mean score delta", comparison.get("mean_score_delta", 0))
            if comparison.get("rows"):
                st.dataframe(pd.DataFrame(comparison["rows"]), hide_index=True, width="stretch")

    st.divider()

    st.subheader("Analog Series Panel")
    analog_cols = st.columns([0.25, 0.25, 0.25, 0.25])
    analog_project = analog_cols[0].text_input("Analog project", value=control_project_name, key="analog_project_name")
    analog_csv = analog_cols[1].text_input("Candidates CSV", value="", key="analog_candidates_csv")
    analog_packet = analog_cols[2].text_input("Decision packet JSON", value="", key="analog_decision_packet_path")
    if analog_cols[3].button("Build analog series", width="stretch"):
        analog_report = build_analog_series_report(
            candidates_csv=analog_csv or None,
            db_path=DB_PATH,
            project_name=analog_project or None,
            decision_packet_path=analog_packet or None,
        )
        write_analog_series_report(analog_report, ANALOG_SERIES_REPORT_PATH)
        st.session_state["analog_series_report"] = analog_report
    if "analog_series_report" not in st.session_state and ANALOG_SERIES_REPORT_PATH.exists():
        try:
            st.session_state["analog_series_report"] = json.loads(ANALOG_SERIES_REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    analog_report = st.session_state.get("analog_series_report") or {}
    if analog_report.get("series"):
        ar1, ar2, ar3, ar4 = st.columns(4)
        ar1.metric("Series", analog_report.get("series_count", 0))
        ar2.metric("Observed", analog_report.get("observed_series_count", 0))
        ar3.metric("Candidates", analog_report.get("candidate_count", 0))
        ar4.metric("Actions", len(analog_report.get("recommendation_counts") or {}))
        series_frame = pd.DataFrame([{key: value for key, value in row.items() if key != "example_candidates"} for row in analog_report.get("series", [])])
        st.dataframe(series_frame, hide_index=True, width="stretch")

    st.subheader("Decision Packet Review")
    packets = list_decision_packets(db_path=DB_PATH, project_name=control_project_name or None, limit=50)
    if packets:
        packet_frame = pd.DataFrame(
            [
                {
                    "packet_id": packet.get("packet_id"),
                    "project_name": packet.get("project_name"),
                    "source_run_id": packet.get("source_run_id"),
                    "status": packet.get("status"),
                    "candidate_count": packet.get("candidate_count"),
                    "decision_counts": packet.get("decision_counts"),
                    "updated_at": packet.get("updated_at"),
                    "reviewer": packet.get("reviewer"),
                }
                for packet in packets
            ]
        )
        st.dataframe(packet_frame, hide_index=True, width="stretch")
        selected_packet_id = st.selectbox("Decision packet", [packet["packet_id"] for packet in packets])
        selected_packet = next(packet for packet in packets if packet["packet_id"] == selected_packet_id)
        packet_payload = selected_packet.get("packet") or {}
        packet_cols = st.columns([0.20, 0.20, 0.42, 0.18])
        current_packet_status = selected_packet.get("status") or PACKET_REVIEW_STATUSES[0]
        packet_status_index = PACKET_REVIEW_STATUSES.index(current_packet_status) if current_packet_status in PACKET_REVIEW_STATUSES else 0
        updated_status = packet_cols[0].selectbox("Review status", PACKET_REVIEW_STATUSES, index=packet_status_index, key="packet_review_status")
        updated_reviewer = packet_cols[1].text_input("Reviewer", value=selected_packet.get("reviewer") or "", key="packet_review_reviewer")
        updated_note = packet_cols[2].text_input("Review note", value=selected_packet.get("review_note") or "", key="packet_review_note")
        if packet_cols[3].button("Update packet", width="stretch"):
            update_decision_packet_review(
                DB_PATH,
                selected_packet_id,
                status=updated_status,
                reviewer=updated_reviewer or None,
                review_note=updated_note or None,
            )
            st.success("Decision packet review updated.")
        candidates = packet_payload.get("candidates") or []
        if candidates:
            st.dataframe(pd.DataFrame(candidates), hide_index=True, width="stretch")
        packet_series = (packet_payload.get("analog_series_summary") or {}).get("one_page_summary") or []
        if packet_series:
            with st.expander("Packet analog-series one-page summary", expanded=True):
                st.dataframe(pd.DataFrame(packet_series), hide_index=True, width="stretch")
        if st.button("Build packet retrospective", width="stretch"):
            st.session_state["packet_retrospective"] = build_decision_packet_retrospective(
                db_path=DB_PATH,
                project_name=selected_packet.get("project_name"),
                packet_id=selected_packet_id,
            )
        retrospective = st.session_state.get("packet_retrospective") or {}
        packet_retrospectives = retrospective.get("packets") or []
        if packet_retrospectives:
            packet_retro = packet_retrospectives[0]
            rr1, rr2, rr3 = st.columns(3)
            rr1.metric("Observed candidates", packet_retro.get("observed_candidate_count", 0))
            rr2.metric("Overall hit rate", packet_retro.get("overall_hit_rate") if packet_retro.get("overall_hit_rate") is not None else "-")
            rr3.metric("Retrospective rows", len(packet_retro.get("candidate_outcomes") or []))
            if packet_retro.get("recommendation_summary"):
                st.dataframe(pd.DataFrame(packet_retro["recommendation_summary"]), hide_index=True, width="stretch")
            if packet_retro.get("candidate_outcomes"):
                with st.expander("Candidate retrospective"):
                    st.dataframe(pd.DataFrame(packet_retro["candidate_outcomes"]), hide_index=True, width="stretch")
        if st.button("Build strategy learning", width="stretch"):
            st.session_state["strategy_learning_report"] = build_decision_strategy_learning_report(
                db_path=DB_PATH,
                project_name=selected_packet.get("project_name"),
            )
        strategy_learning = st.session_state.get("strategy_learning_report")
        if strategy_learning and strategy_learning.get("strategies"):
            with st.expander("Strategy learning", expanded=True):
                sl1, sl2 = st.columns(2)
                sl1.metric("Strategies", strategy_learning.get("strategy_count", 0))
                sl2.metric("Observed strategies", strategy_learning.get("observed_strategy_count", 0))
                st.dataframe(pd.DataFrame(strategy_learning.get("strategies", [])), hide_index=True, width="stretch")
        if len(packets) >= 2:
            compare = compare_decision_packets(packets[1].get("packet") or {}, packets[0].get("packet") or {})
            with st.expander("Compare latest packets"):
                st.json(compare)
    else:
        st.info("No saved decision packets yet.")

    st.divider()

    runs = list_project_runs(DB_PATH)
    if not runs:
        st.info("No saved project runs yet.")
    else:
        st.dataframe(saved_runs_frame(runs), hide_index=True, width="stretch")
        selected_run_id = st.selectbox(
            "Saved run",
            [run["run_id"] for run in runs],
            format_func=lambda run_id: f"{run_id} | {next(run.get('project_name') for run in runs if run['run_id'] == run_id)}",
        )
        selected_run = next(run for run in runs if run["run_id"] == selected_run_id)

        meta_cols = st.columns(3)
        meta_cols[0].metric("Project", selected_run.get("project_name") or "-")
        meta_cols[1].metric("Direction", selected_run.get("direction") or "-")
        meta_cols[2].metric("Site", selected_run.get("site_type") or "-")
        st.code(selected_run.get("parent_smiles") or "")

        if st.button("Load saved run details", width="stretch"):
            st.session_state["selected_saved_run_id"] = selected_run_id
            st.session_state["saved_run_candidates"] = load_project_candidates(DB_PATH, selected_run_id)
            st.session_state["saved_run_route_batches"] = load_project_route_batches(DB_PATH, selected_run_id)
            st.session_state["saved_run_feedback_summary"] = summarize_project_feedback(
                db_path=DB_PATH,
                project_name=selected_run.get("project_name"),
            )

        saved_candidates = (
            st.session_state.get("saved_run_candidates")
            if st.session_state.get("selected_saved_run_id") == selected_run_id
            else []
        )
        if saved_candidates:
            st.metric("Candidates", str(len(saved_candidates)))
            st.dataframe(compact_candidate_frame(saved_candidates), hide_index=True, width="stretch")
            selected_candidate_id = st.selectbox(
                "Candidate",
                [row["candidate_id"] for row in saved_candidates],
                format_func=lambda candidate_id: (
                    f"{candidate_id} | "
                    f"{next(row.get('replacement_label') for row in saved_candidates if row['candidate_id'] == candidate_id)}"
                ),
            )
            selected_candidate = next(row for row in saved_candidates if row["candidate_id"] == selected_candidate_id)
            current_status = selected_candidate.get("decision_status") or DECISION_STATUSES[0]
            current_index = DECISION_STATUSES.index(current_status) if current_status in DECISION_STATUSES else 0
            p1, p2 = st.columns([0.36, 0.64])
            with p1:
                status = st.selectbox("Decision status", DECISION_STATUSES, index=current_index)
                st.metric("Score", f"{selected_candidate.get('score', 0):.2f}")
                st.metric("Rank", str(selected_candidate.get("rank") or "-"))
                st.metric("Diverse rank", str(selected_candidate.get("diverse_rank") or "-"))
            with p2:
                note = st.text_area("Candidate note", value=selected_candidate.get("project_note") or "", height=140)
                st.code(selected_candidate.get("smiles") or "")
                if st.button("Save candidate decision", type="primary", width="stretch"):
                    update_candidate_decision(
                        DB_PATH,
                        selected_run_id,
                        selected_candidate_id,
                        decision_status=status,
                        note=note or None,
                    )
                    st.success("Candidate decision saved.")

            if st.button("Load saved candidates into current table", width="stretch"):
                analysis = json.loads(selected_run.get("analysis_json") or "{}")
                st.session_state["last_rows"] = saved_candidates
                st.session_state["last_result"] = {
                    "parent_smiles": selected_run.get("parent_smiles"),
                    "selected_site": {
                        "site_id": selected_run.get("site_id"),
                        "site_type": selected_run.get("site_type"),
                    },
                    "analysis": analysis,
                    "candidates": saved_candidates,
                    "score_weights": json.loads(selected_run.get("score_weights_json") or "{}"),
                }
                st.success("Loaded saved candidates.")
        else:
            st.caption("Load saved run details to inspect candidates, route classes, and project feedback.")

        route_batches = (
            st.session_state.get("saved_run_route_batches")
            if st.session_state.get("selected_saved_run_id") == selected_run_id
            else []
        )
        if route_batches:
            st.divider()
            st.subheader("Chemistry Route Review")
            batch_frame = pd.DataFrame(route_batches)
            st.dataframe(
                batch_frame[
                    [
                        "route_batch_id",
                        "batch_type",
                        "candidate_count",
                        "top_score",
                        "reaction_family",
                        "suggested_building_block",
                        "chemist_approval_status",
                        "route_execution_risk_score",
                        "reagent_overlap_score",
                        "route_risk_flags",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )
            selected_batch_id = st.selectbox("Route batch", [row["route_batch_id"] for row in route_batches])
            selected_batch = next(row for row in route_batches if row["route_batch_id"] == selected_batch_id)
            current_batch_status = selected_batch.get("chemist_approval_status") or ROUTE_BATCH_STATUSES[0]
            current_batch_index = ROUTE_BATCH_STATUSES.index(current_batch_status) if current_batch_status in ROUTE_BATCH_STATUSES else 0
            bstatus = st.selectbox("Batch status", ROUTE_BATCH_STATUSES, index=current_batch_index)
            bnote = st.text_area("Batch approval note", value=selected_batch.get("approval_note") or "", height=90)
            if st.button("Save route batch status", width="stretch"):
                update_route_batch_decision(DB_PATH, selected_run_id, selected_batch_id, status=bstatus, note=bnote)
                st.success("Route batch status saved.")

        st.divider()
        st.subheader("Project Feedback")
        feedback_file = st.file_uploader("Assay or ADME feedback CSV", type=["csv"])
        f1, f2 = st.columns([0.35, 0.65])
        with f1:
            if feedback_file is not None and st.button("Import feedback CSV", type="primary", width="stretch"):
                try:
                    feedback_frame = pd.read_csv(feedback_file)
                    import_report = import_feedback_rows(
                        feedback_frame.to_dict("records"),
                        db_path=DB_PATH,
                        source_path=feedback_file.name,
                    )
                    st.session_state["feedback_import_report"] = import_report
                    st.success(f"Imported {import_report['inserted_count']} feedback rows.")
                except Exception as exc:
                    st.error(str(exc))
        with f2:
            feedback_summary = (
                st.session_state.get("saved_run_feedback_summary")
                if st.session_state.get("selected_saved_run_id") == selected_run_id
                else None
            )
            if st.button("Load feedback summary", width="stretch"):
                feedback_summary = summarize_project_feedback(
                    db_path=DB_PATH,
                    project_name=selected_run.get("project_name"),
                )
                st.session_state["selected_saved_run_id"] = selected_run_id
                st.session_state["saved_run_feedback_summary"] = feedback_summary
            if feedback_summary:
                st.json(feedback_summary)
            if st.button("Calibrate endpoint models", width="stretch"):
                calibration = calibrate_project_models(
                    db_path=DB_PATH,
                    project_name=selected_run.get("project_name"),
                    min_feedback=3,
                )
                save_calibration_report(calibration, db_path=DB_PATH)
                profile_paths = write_calibration_profiles(calibration, ROOT / "data" / "profiles" / "calibrated")
                st.session_state["calibration_report"] = {
                    **calibration,
                    "profile_paths": [str(path) for path in profile_paths],
                }
            if "calibration_report" in st.session_state:
                st.json(st.session_state["calibration_report"])

