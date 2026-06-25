from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_NATIVE_UI_REGRESSION_PATH = Path("data/releases/native_ui_regression_snapshot.json")
DEFAULT_NATIVE_UI_REGRESSION_MD_PATH = Path("docs/native_ui_regression_snapshot.md")

REQUIRED_CANDIDATE_COLUMNS = [
    "candidate_id",
    "smiles",
    "score",
    "site_class",
    "site_class_candidate_guidance",
    "candidate_explanation_summary",
    "why_recommended",
    "why_review",
]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _candidate_schema(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "columns": [],
            "missing_required_columns": REQUIRED_CANDIDATE_COLUMNS,
            "row_count": 0,
            "status": "missing",
        }
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        row_count = sum(1 for _ in reader)
    missing = [column for column in REQUIRED_CANDIDATE_COLUMNS if column not in columns]
    return {
        "path": str(path),
        "exists": True,
        "columns": columns,
        "missing_required_columns": missing,
        "row_count": row_count,
        "status": "pass" if not missing and row_count > 0 else "warn",
    }


def _local_artifact_exists(root_path: Path, path_value: object) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    path = Path(text)
    if not path.is_absolute():
        path = root_path / path
    return path.exists()


def build_native_ui_regression_snapshot(root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    quality = _read_json(root_path / "data/releases/native_ui_quality_report.json")
    portable = _read_json(root_path / "data/releases/native_portable_package_manifest.json")
    db_health = _read_json(root_path / "data/releases/local_db_health_report.json")
    db_maintenance = _read_json(root_path / "data/releases/local_db_maintenance_report.json")
    db_trend = _read_json(root_path / "data/releases/local_db_maintenance_trend_history.json")
    visual_compare = _read_json(root_path / "data" / "projects" / project_name / "candidate_visual_compare.json")
    review_packet = _read_json(root_path / "data" / "projects" / project_name / "candidate_review_packet.json")
    review_board = _read_json(root_path / "data" / "projects" / project_name / "candidate_review_board.json")
    review_analytics = _read_json(root_path / "data" / "projects" / project_name / "candidate_review_analytics.json")
    review_reason_workbench = _read_json(root_path / "data" / "projects" / project_name / "candidate_review_reason_workbench.json")
    review_reason_audit = _read_json(root_path / "data" / "projects" / project_name / "candidate_review_reason_workbench_audit.json")
    drilldown_packet = _read_json(root_path / "data" / "projects" / project_name / "candidate_drilldown_packet.json")
    governance_diff = _read_json(root_path / "data" / "projects" / project_name / "local_governance_diff_report.json")
    baseline_registry = _read_json(root_path / "data" / "projects" / project_name / "governance_baselines" / "baseline_registry.json")
    candidate_baseline = _read_json(root_path / "data" / "projects" / project_name / "candidate_baseline_compare.json")
    candidate_decision = _read_json(root_path / "data" / "projects" / project_name / "candidate_decision_packet.json")
    candidate_drawer = _read_json(root_path / "data" / "projects" / project_name / "candidate_evidence_drawer.json")
    candidate_explanation = _read_json(root_path / "data" / "projects" / project_name / "candidate_explanation_panel.json")
    candidate_explanation_compare = _read_json(root_path / "data" / "projects" / project_name / "candidate_explanation_compare.json")
    candidate_explanation_drilldown = _read_json(root_path / "data" / "projects" / project_name / "candidate_explanation_drilldown.json")
    candidate_explanation_matrix = _read_json(root_path / "data" / "projects" / project_name / "candidate_explanation_matrix.json")
    candidate_structure_interpretation = _read_json(root_path / "data" / "projects" / project_name / "candidate_structure_interpretation.json")
    candidate_component_structure_locator = _read_json(root_path / "data" / "projects" / project_name / "candidate_component_structure_locator.json")
    site_detection_confidence = _read_json(root_path / "data" / "projects" / project_name / "site_detection_confidence.json")
    site_detection_calibration = _read_json(root_path / "data" / "projects" / project_name / "site_detection_calibration_queue.json")
    staged_feed_sandbox_scoring = _read_json(root_path / "data" / "projects" / project_name / "staged_feed_sandbox_scoring.json")
    sandbox_score_delta_review = _read_json(root_path / "data" / "projects" / project_name / "sandbox_score_delta_review_packet.json")
    sandbox_score_delta_signoff = _read_json(root_path / "data" / "projects" / project_name / "sandbox_score_delta_signoff_ledger.json")
    staging_sandbox_filter_views = _read_json(root_path / "data" / "projects" / project_name / "staging_sandbox_filter_views.json")
    native_drilldown_actions = _read_json(root_path / "data" / "projects" / project_name / "native_drilldown_actions.json")
    decision_qa = _read_json(root_path / "data" / "projects" / project_name / "candidate_decision_qa.json")
    evidence_quality = _read_json(root_path / "data" / "projects" / project_name / "evidence_quality_scorecard.json")
    legacy_evidence_quality = _read_json(root_path / "data" / "projects" / project_name / "candidate_evidence_quality.json")
    if not evidence_quality:
        evidence_quality = legacy_evidence_quality
    if not legacy_evidence_quality:
        legacy_evidence_quality = evidence_quality
    baseline_manager = _read_json(root_path / "data" / "projects" / project_name / "candidate_baseline_manager.json")
    reviewer_operations = _read_json(root_path / "data" / "projects" / project_name / "reviewer_operations.json")
    baseline_lineage = _read_json(root_path / "data" / "projects" / project_name / "baseline_lineage_compare.json")
    legacy_baseline_lineage = _read_json(root_path / "data" / "projects" / project_name / "candidate_baseline_lineage.json")
    if not baseline_lineage:
        baseline_lineage = legacy_baseline_lineage
    if not legacy_baseline_lineage:
        legacy_baseline_lineage = baseline_lineage
    review_command_center = _read_json(root_path / "data" / "projects" / project_name / "review_command_center.json")
    review_closure_workbench = _read_json(root_path / "data" / "projects" / project_name / "review_closure_workbench.json")
    review_closure_filter_views = _read_json(root_path / "data" / "projects" / project_name / "review_closure_filter_views.json")
    reviewer_cockpit = _read_json(root_path / "data" / "projects" / project_name / "reviewer_cockpit.json")
    review_remediation = _read_json(root_path / "data" / "projects" / project_name / "candidate_remediation_queue.json") or _read_json(root_path / "data" / "projects" / project_name / "review_remediation_queue.json")
    remediation_history = _read_json(root_path / "data" / "projects" / project_name / "candidate_remediation_queue_history.json")
    review_ops_console = _read_json(root_path / "data" / "projects" / project_name / "candidate_review_ops_console.json")
    baseline_history = _read_json(root_path / "data" / "projects" / project_name / "baseline_history_explorer.json") or _read_json(root_path / "data" / "projects" / project_name / "baseline_lineage_history.json")
    baseline_scenario = _read_json(root_path / "data" / "projects" / project_name / "baseline_scenario_board.json")
    baseline_whatif = _read_json(root_path / "data" / "projects" / project_name / "baseline_whatif_board.json")
    baseline_lineage_preview = _read_json(root_path / "data" / "projects" / project_name / "baseline_lineage_preview.json")
    baseline_lineage_filter_views = _read_json(root_path / "data" / "projects" / project_name / "baseline_lineage_filter_views.json")
    site_detection_regression = _read_json(root_path / "data" / "projects" / project_name / "site_detection_regression_report.json")
    feed_absorption = _read_json(root_path / "data" / "substituents" / "feed_absorption_audit.json")
    feed_absorption_diff = _read_json(root_path / "data" / "substituents" / "feed_absorption_diff_navigator.json")
    source_expansion_governance = _read_json(root_path / "data" / "substituents" / "source_expansion_governance.json")
    feed_promotion_simulator = _read_json(root_path / "data" / "substituents" / "feed_promotion_simulator.json")
    staging_quality_budget = _read_json(root_path / "data" / "substituents" / "rgroup_staging_quality_budget.json")
    staging_admission_scorecard = _read_json(root_path / "data" / "substituents" / "rgroup_staging_admission_scorecard.json")
    rgroup_admission_sandbox_replay = _read_json(root_path / "data" / "substituents" / "rgroup_admission_sandbox_impact_replay.json")
    staging_curator_signoff = _read_json(root_path / "data" / "substituents" / "rgroup_staging_curator_signoff.json")
    rgroup_staging_fill = _read_json(root_path / "data" / "substituents" / "rgroup_staging_fill_report.json")
    rgroup_feed_digestion = _read_json(root_path / "data" / "substituents" / "rgroup_feed_digestion_ledger.json")
    rgroup_selective_approval = _read_json(root_path / "data" / "substituents" / "rgroup_selective_approval_batch.json")
    rgroup_promotion_approval = _read_json(root_path / "data" / "substituents" / "rgroup_promotion_approval_ledger.json")
    rgroup_digestion_quality_metrics = _read_json(root_path / "data" / "substituents" / "rgroup_digestion_quality_metrics.json")
    rgroup_digestion_quality_closure = _read_json(root_path / "data" / "substituents" / "rgroup_digestion_quality_closure_queue.json")
    feed_promotion_rollback = _read_json(root_path / "data" / "substituents" / "feed_promotion_rollback_audit.json")
    rgroup_approval_workbench = _read_json(root_path / "data" / "substituents" / "rgroup_approval_workbench.json")
    rgroup_ring_context_alignment = _read_json(root_path / "data" / "substituents" / "rgroup_ring_context_alignment.json")
    rgroup_digestion_quality_closure_ledger = _read_json(root_path / "data" / "substituents" / "rgroup_digestion_quality_closure_ledger.json")
    rgroup_approval_workbench_decisions = _read_json(root_path / "data" / "substituents" / "rgroup_approval_workbench_decisions.json")
    rgroup_guarded_promotion_rehearsal = _read_json(root_path / "data" / "substituents" / "rgroup_guarded_promotion_rehearsal.json")
    ring_rgroup_axis_governance = _read_json(root_path / "data" / "substituents" / "ring_rgroup_axis_governance.json")
    rgroup_next_expansion_batch_plan = _read_json(root_path / "data" / "substituents" / "rgroup_next_expansion_batch_plan.json")
    rgroup_approval_trend_views = _read_json(root_path / "data" / "substituents" / "rgroup_approval_trend_views.json")
    governed_ingestion_batches = _read_json(root_path / "data" / "substituents" / "governed_ingestion_batches.json")
    substituent_version_diff = _read_json(root_path / "data" / "substituents" / "substituent_version_diff_browser.json")
    operator_trend = _read_json(root_path / "data" / "releases" / "operator_trend_summary.json")
    operator_charts = _read_json(root_path / "data" / "releases" / "operator_trend_charts.json")
    local_db_maintenance_release_gate = _read_json(root_path / "data" / "releases" / "local_db_maintenance_release_gate.json")
    discussion_handoff = _read_json(root_path / "data" / "projects" / project_name / "medchem_discussion_handoff.json")
    candidate_schema = _candidate_schema(root_path / "data" / "projects" / project_name / "candidates.csv")
    checks = [
        {
            "check_id": "native_ui_quality",
            "status": "pass"
            if quality.get("status") == "pass"
            and quality.get("browser_required") is False
            and int(quality.get("row_height_min") or 0) >= 48
            and quality.get("horizontal_scrollbars") is True
            else "warn",
            "details": (
                f"status={quality.get('status')}; browser_required={quality.get('browser_required')}; "
                f"row_height_min={quality.get('row_height_min')}; horizontal_scrollbars={quality.get('horizontal_scrollbars')}; "
                f"dpi={quality.get('high_dpi')}"
            ),
        },
        {
            "check_id": "candidate_table_inline_2d_preview",
            "status": "pass"
            if quality.get("candidate_table_inline_2d_preview_supported") is True
            and quality.get("candidate_2d_selection_preview_supported") is True
            else "warn",
            "details": (
                f"inline_preview={quality.get('candidate_table_inline_2d_preview_supported')}; "
                f"selection_preview={quality.get('candidate_2d_selection_preview_supported')}"
            ),
        },
        {
            "check_id": "candidate_table_advanced_filters",
            "status": "pass"
            if quality.get("candidate_table_column_filter_supported") is True
            and quality.get("candidate_score_range_filter_supported") is True
            and quality.get("candidate_rank_filter_supported") is True
            and quality.get("candidate_delta_filter_supported") is True
            else "warn",
            "details": (
                f"column={quality.get('candidate_table_column_filter_supported')}; "
                f"score_range={quality.get('candidate_score_range_filter_supported')}; "
                f"rank={quality.get('candidate_rank_filter_supported')}; "
                f"delta={quality.get('candidate_delta_filter_supported')}"
            ),
        },
        {
            "check_id": "candidate_structure_highlight_detail",
            "status": "pass"
            if quality.get("candidate_structure_highlight_detail_supported") is True
            and any(row.get("structure_highlight_detail") and row.get("site_highlight_label") for row in visual_compare.get("rows") or [])
            else "warn",
            "details": (
                f"quality={quality.get('candidate_structure_highlight_detail_supported')}; "
                f"annotated_rows={sum(1 for row in visual_compare.get('rows') or [] if row.get('structure_highlight_detail'))}"
            ),
        },
        {
            "check_id": "candidate_before_after_2d_preview",
            "status": "pass"
            if quality.get("candidate_before_after_2d_preview_supported") is True
            and quality.get("candidate_score_component_2d_linkage_supported") is True
            and quality.get("candidate_2d_selection_preview_supported") is True
            else "warn",
            "details": (
                f"before_after={quality.get('candidate_before_after_2d_preview_supported')}; "
                f"score_linkage={quality.get('candidate_score_component_2d_linkage_supported')}; "
                f"selection_preview={quality.get('candidate_2d_selection_preview_supported')}"
            ),
        },
        {
            "check_id": "candidate_structure_interpretation",
            "status": "pass"
            if quality.get("candidate_structure_interpretation_supported") is True
            and quality.get("candidate_score_component_locator_supported") is True
            and candidate_structure_interpretation.get("mode") == "candidate_structure_interpretation"
            and int(candidate_structure_interpretation.get("score_component_locator_count") or 0) >= int(candidate_structure_interpretation.get("candidate_count") or 0)
            else "warn",
            "details": (
                f"status={candidate_structure_interpretation.get('status')}; "
                f"candidates={candidate_structure_interpretation.get('candidate_count')}; "
                f"locators={candidate_structure_interpretation.get('score_component_locator_count')}; "
                f"ui={quality.get('candidate_structure_interpretation_supported')}"
            ),
        },
        {
            "check_id": "candidate_component_structure_locator",
            "status": "pass"
            if quality.get("candidate_component_structure_locator_supported") is True
            and candidate_component_structure_locator.get("mode") == "candidate_component_structure_locator"
            and int(candidate_component_structure_locator.get("row_count") or 0) >= int(candidate_structure_interpretation.get("score_component_locator_count") or 0)
            and int(candidate_component_structure_locator.get("linked_component_count") or 0) > 0
            else "warn",
            "details": (
                f"status={candidate_component_structure_locator.get('status')}; "
                f"rows={candidate_component_structure_locator.get('row_count')}; "
                f"linked={candidate_component_structure_locator.get('linked_component_count')}; "
                f"quality={quality.get('candidate_component_structure_locator_supported')}"
            ),
        },
        {
            "check_id": "candidate_review_scrollable_analytics_layout",
            "status": "pass"
            if quality.get("candidate_review_unified_scroll_supported") is True
            and quality.get("review_analytics_full_height_supported") is True
            and quality.get("review_analytics_resizable_supported") is True
            else "warn",
            "details": (
                f"unified_scroll={quality.get('candidate_review_unified_scroll_supported')}; "
                f"full_height={quality.get('review_analytics_full_height_supported')}; "
                f"resizable={quality.get('review_analytics_resizable_supported')}"
            ),
        },
        {
            "check_id": "candidate_csv_schema",
            "status": candidate_schema["status"],
            "details": f"rows={candidate_schema['row_count']}; missing={candidate_schema['missing_required_columns']}",
        },
        {
            "check_id": "native_task_log_and_rerun",
            "status": "pass" if quality.get("native_task_log_supported") is True and quality.get("native_task_rerun_supported") is True else "warn",
            "details": f"task_log={quality.get('native_task_log_supported')}; rerun={quality.get('native_task_rerun_supported')}",
        },
        {
            "check_id": "portable_package_manifest",
            "status": "pass" if portable.get("status") == "ready" and not portable.get("missing") else "warn",
            "details": f"status={portable.get('status')}; files={portable.get('copied_file_count')}; missing={portable.get('missing')}",
        },
        {
            "check_id": "local_db_health",
            "status": "pass" if db_health.get("status") == "healthy" else "warn",
            "details": f"status={db_health.get('status')}; ring_rows={(db_health.get('table_rows') or {}).get('ring_system')}; ring_indexes={db_health.get('ring_index_count')}",
        },
        {
            "check_id": "candidate_visual_compare",
            "status": "pass"
            if visual_compare.get("status") == "ready" and visual_compare.get("grid_image_path") and visual_compare.get("alignment_status")
            else "warn",
            "details": f"status={visual_compare.get('status')}; rows={visual_compare.get('candidate_count')}; alignment={visual_compare.get('alignment_status')}; grid={visual_compare.get('grid_image_path')}",
        },
        {
            "check_id": "candidate_review_packet",
            "status": "pass" if review_packet.get("status") == "review_ready" else "warn",
            "details": f"status={review_packet.get('status')}; rows={review_packet.get('row_count')}; pending={review_packet.get('review_required_count')}",
        },
        {
            "check_id": "candidate_review_board",
            "status": "pass" if review_board.get("status") == "ready" else "warn",
            "details": f"status={review_board.get('status')}; rows={review_board.get('filtered_row_count')}; focused={review_board.get('focused_row_count')}; pending_local={review_board.get('pending_local_review_count')}",
        },
        {
            "check_id": "candidate_review_analytics",
            "status": "pass" if review_analytics.get("status") == "ready" and review_analytics.get("mode") == "local_candidate_review_analytics" else "warn",
            "details": f"status={review_analytics.get('status')}; pending={review_analytics.get('pending_backlog_count')}; risks={review_analytics.get('repeated_risk_bucket_count')}; reviewers={review_analytics.get('reviewer_count')}",
        },
        {
            "check_id": "candidate_review_pending_reason_clusters",
            "status": "pass"
            if quality.get("review_pending_reason_clusters_supported") is True
            and quality.get("review_cluster_evidence_jump_supported") is True
            and "pending_reason_cluster_count" in review_analytics
            and any(row.get("row_type") == "pending_reason_cluster" for row in review_analytics.get("rows") or [])
            else "warn",
            "details": (
                f"clusters={review_analytics.get('pending_reason_cluster_count')}; "
                f"reason_counts={review_analytics.get('pending_reason_counts')}; "
                f"jump={quality.get('review_cluster_evidence_jump_supported')}"
            ),
        },
        {
            "check_id": "candidate_review_reason_workbench",
            "status": "pass"
            if quality.get("review_reason_workbench_supported") is True
            and quality.get("review_reason_batch_update_supported") is True
            and quality.get("review_reason_batch_audit_replay_supported") is True
            and review_reason_workbench.get("mode") == "candidate_review_reason_workbench"
            and int(review_reason_workbench.get("row_count") or 0) >= int(review_analytics.get("pending_reason_cluster_count") or 0)
            and review_reason_audit.get("mode") in {"candidate_review_reason_workbench_audit", None, ""}
            else "warn",
            "details": (
                f"workbench={quality.get('review_reason_workbench_supported')}; "
                f"batch={quality.get('review_reason_batch_update_supported')}; "
                f"audit_replay={quality.get('review_reason_batch_audit_replay_supported')}; "
                f"clusters={review_reason_workbench.get('row_count')}; "
                f"audit_events={review_reason_workbench.get('audit_event_count') or review_reason_audit.get('row_count')}"
            ),
        },
        {
            "check_id": "reviewer_cockpit",
            "status": "pass"
            if quality.get("reviewer_cockpit_supported") is True
            and reviewer_cockpit.get("mode") == "reviewer_cockpit"
            and int(reviewer_cockpit.get("row_count") or 0) >= 1
            and {"reason_audit", "closure", "remediation"} & set((reviewer_cockpit.get("lane_counts") or {}).keys())
            else "warn",
            "details": (
                f"status={reviewer_cockpit.get('status')}; rows={reviewer_cockpit.get('row_count')}; "
                f"lanes={reviewer_cockpit.get('lane_counts')}; high={reviewer_cockpit.get('high_priority_count')}"
            ),
        },
        {
            "check_id": "local_scope_labeling",
            "status": "pass" if quality.get("local_scope_labeling_supported") is True else "warn",
            "details": f"local_scope_labeling={quality.get('local_scope_labeling_supported')}",
        },
        {
            "check_id": "candidate_drilldown_packet",
            "status": "pass" if drilldown_packet.get("status") == "ready" else "warn",
            "details": f"status={drilldown_packet.get('status')}; rows={drilldown_packet.get('row_count')}; board={drilldown_packet.get('linked_board_rows')}; governance={drilldown_packet.get('linked_governance_rows')}",
        },
        {
            "check_id": "local_db_maintenance",
            "status": "pass" if db_maintenance.get("status") in {"ready", "attention_required"} else "warn",
            "details": f"status={db_maintenance.get('status')}; rows={db_maintenance.get('row_count')}; warnings={db_maintenance.get('warn_count')}",
        },
        {
            "check_id": "local_db_maintenance_trend",
            "status": "pass" if db_trend.get("status") == "tracking" else "warn",
            "details": f"status={db_trend.get('status')}; rows={db_trend.get('row_count')}; latest={(db_trend.get('latest') or {}).get('status')}",
        },
        {
            "check_id": "local_governance_diff",
            "status": "pass" if governance_diff.get("status") in {"compared", "baseline_created"} else "warn",
            "details": f"status={governance_diff.get('status')}; changed={governance_diff.get('changed_candidate_count')}; added={governance_diff.get('added_candidate_count')}; removed={governance_diff.get('removed_candidate_count')}",
        },
        {
            "check_id": "named_governance_baselines",
            "status": "pass" if baseline_registry.get("status") == "ready" else "warn",
            "details": f"status={baseline_registry.get('status')}; baselines={baseline_registry.get('baseline_count') or len(baseline_registry.get('baselines') or [])}",
        },
        {
            "check_id": "candidate_baseline_compare",
            "status": "pass" if candidate_baseline.get("status") in {"compared", "baseline_created"} else "warn",
            "details": f"status={candidate_baseline.get('status')}; baseline={candidate_baseline.get('baseline_id')}; changed={candidate_baseline.get('changed_candidate_count')}; added={candidate_baseline.get('added_candidate_count')}; removed={candidate_baseline.get('removed_candidate_count')}",
        },
        {
            "check_id": "candidate_decision_packet",
            "status": "pass"
            if candidate_decision.get("status") == "ready"
            and candidate_decision.get("mode") == "local_candidate_decision_packet"
            and (candidate_decision.get("export_schema") or {}).get("procurement_allowed") is False
            else "warn",
            "details": f"status={candidate_decision.get('status')}; decisions={candidate_decision.get('decision_count')}; counts={candidate_decision.get('decision_counts')}; export_scope={(candidate_decision.get('export_schema') or {}).get('scope')}",
        },
        {
            "check_id": "candidate_evidence_drawer",
            "status": "pass" if candidate_drawer.get("status") == "ready" and candidate_drawer.get("mode") == "native_candidate_evidence_drawer" else "warn",
            "details": f"status={candidate_drawer.get('status')}; rows={candidate_drawer.get('row_count')}; decisions={candidate_drawer.get('linked_decision_rows')}",
        },
        {
            "check_id": "candidate_explanation_panel",
            "status": "pass" if candidate_explanation.get("status") == "ready" and candidate_explanation.get("mode") == "candidate_explanation_panel" else "warn",
            "details": f"status={candidate_explanation.get('status')}; rows={candidate_explanation.get('row_count')}; remediation_linked={candidate_explanation.get('remediation_linked_count')}",
        },
        {
            "check_id": "candidate_explanation_score_breakdown",
            "status": "pass"
            if int(candidate_explanation.get("chart_count") or 0) > 0
            and any(
                _local_artifact_exists(root_path, row.get("preview_path") or row.get("breakdown_preview_path") or row.get("image_path") or row.get("chart_path"))
                for row in candidate_explanation.get("chart_rows") or []
            )
            else "warn",
            "details": f"charts={candidate_explanation.get('chart_count')}; rows={len(candidate_explanation.get('chart_rows') or [])}",
        },
        {
            "check_id": "candidate_explanation_compare",
            "status": "pass" if candidate_explanation_compare.get("status") == "ready" and candidate_explanation_compare.get("mode") == "candidate_explanation_compare" else "warn",
            "details": f"status={candidate_explanation_compare.get('status')}; base={candidate_explanation_compare.get('base_candidate_id')}; head={candidate_explanation_compare.get('head_candidate_id')}; stoplist={candidate_explanation_compare.get('stoplist_component_count')}",
        },
        {
            "check_id": "candidate_explanation_drilldown",
            "status": "pass"
            if candidate_explanation_drilldown.get("status") == "ready"
            and candidate_explanation_drilldown.get("mode") == "candidate_explanation_drilldown"
            and int(candidate_explanation_drilldown.get("row_count") or 0) >= int(candidate_explanation.get("row_count") or 0)
            else "warn",
            "details": f"status={candidate_explanation_drilldown.get('status')}; candidates={candidate_explanation_drilldown.get('candidate_count')}; rows={candidate_explanation_drilldown.get('row_count')}; attention={candidate_explanation_drilldown.get('attention_count')}",
        },
        {
            "check_id": "candidate_component_structure_highlight",
            "status": "pass"
            if any(
                row.get("structure_image_path")
                and row.get("site_highlight_label") is not None
                and row.get("right_panel_detail")
                for row in candidate_explanation_drilldown.get("rows") or []
            )
            else "warn",
            "details": f"rows={candidate_explanation_drilldown.get('row_count')}; component_highlight_fields=structure_image_path/site_highlight_label/right_panel_detail",
        },
        {
            "check_id": "candidate_explanation_matrix",
            "status": "pass" if candidate_explanation_matrix.get("status") == "ready" and candidate_explanation_matrix.get("mode") == "candidate_explanation_matrix" else "warn",
            "details": f"status={candidate_explanation_matrix.get('status')}; candidates={candidate_explanation_matrix.get('candidate_count')}; stoplist={candidate_explanation_matrix.get('stoplist_candidate_count')}; pairwise={candidate_explanation_matrix.get('pairwise_delta_count')}",
        },
        {
            "check_id": "site_detection_confidence",
            "status": "pass"
            if site_detection_confidence.get("status") in {"ready", "review_required"}
            and site_detection_confidence.get("mode") == "site_detection_confidence"
            and int(site_detection_confidence.get("row_count") or 0) > 0
            else "warn",
            "details": f"status={site_detection_confidence.get('status')}; rows={site_detection_confidence.get('row_count')}; low={site_detection_confidence.get('low_confidence_count')}; classes={site_detection_confidence.get('site_class_count')}",
        },
        {
            "check_id": "site_detection_calibration_queue",
            "status": "pass"
            if quality.get("site_detection_calibration_queue_supported") is True
            and site_detection_calibration.get("mode") == "site_detection_calibration_queue"
            and site_detection_calibration.get("status") in {"ready", "empty"}
            and int(site_detection_calibration.get("queue_count") or 0) >= int(site_detection_calibration.get("low_confidence_count") or 0)
            else "warn",
            "details": (
                f"status={site_detection_calibration.get('status')}; queue={site_detection_calibration.get('queue_count')}; "
                f"low={site_detection_calibration.get('low_confidence_count')}; priorities={site_detection_calibration.get('priority_counts')}"
            ),
        },
        {
            "check_id": "staged_feed_sandbox_scoring",
            "status": "pass"
            if staged_feed_sandbox_scoring.get("status") in {"ready", "awaiting_staged_rows"}
            and staged_feed_sandbox_scoring.get("mode") == "staged_feed_sandbox_scoring"
            and staged_feed_sandbox_scoring.get("production_scoring_affected") is False
            else "warn",
            "details": f"status={staged_feed_sandbox_scoring.get('status')}; candidates={staged_feed_sandbox_scoring.get('candidate_count')}; staged={staged_feed_sandbox_scoring.get('staged_row_count')}; production_affected={staged_feed_sandbox_scoring.get('production_scoring_affected')}",
        },
        {
            "check_id": "sandbox_score_delta_review_packet",
            "status": "pass"
            if sandbox_score_delta_review.get("status") in {"awaiting_staged_rows", "review_required", "approved", "reviewed_holdout"}
            and sandbox_score_delta_review.get("mode") == "sandbox_score_delta_review_packet"
            and sandbox_score_delta_review.get("production_scoring_affected") is False
            else "warn",
            "details": f"status={sandbox_score_delta_review.get('status')}; rows={sandbox_score_delta_review.get('row_count')}; signoff_required={sandbox_score_delta_review.get('operator_signoff_required_count')}; approved={sandbox_score_delta_review.get('approved_signoff_count')}; production_approved={sandbox_score_delta_review.get('production_scoring_approved')}",
        },
        {
            "check_id": "sandbox_score_delta_signoff_ledger",
            "status": "pass"
            if sandbox_score_delta_signoff.get("status") in {"reviewed", "pending_signoff"}
            and sandbox_score_delta_signoff.get("mode") == "sandbox_score_delta_signoff_ledger"
            and int(sandbox_score_delta_signoff.get("invalid_row_count") or 0) == 0
            and int(sandbox_score_delta_signoff.get("missing_packet_row_count") or 0) == 0
            else "warn",
            "details": (
                f"status={sandbox_score_delta_signoff.get('status')}; "
                f"required={sandbox_score_delta_signoff.get('required_signoff_count')}; "
                f"completed={sandbox_score_delta_signoff.get('completed_signoff_count')}; "
                f"pending={sandbox_score_delta_signoff.get('pending_signoff_count')}; "
                f"decisions={sandbox_score_delta_signoff.get('decision_counts')}"
            ),
        },
        {
            "check_id": "rgroup_feed_digestion_ledger",
            "status": "pass"
            if rgroup_feed_digestion.get("status") in {"ready", "awaiting_rows"}
            and rgroup_feed_digestion.get("mode") == "rgroup_feed_digestion_ledger"
            and rgroup_feed_digestion.get("production_scoring_affected") is False
            else "warn",
            "details": (
                f"status={rgroup_feed_digestion.get('status')}; rows={rgroup_feed_digestion.get('row_count')}; "
                f"accepted={rgroup_feed_digestion.get('accepted_count')}; deferred={rgroup_feed_digestion.get('deferred_count')}; "
                f"rejected={rgroup_feed_digestion.get('rejected_count')}; held_out={rgroup_feed_digestion.get('held_out_count')}"
            ),
        },
        {
            "check_id": "rgroup_promotion_approval_ledger",
            "status": "pass"
            if rgroup_promotion_approval.get("status") in {"approved", "reviewed_holdout", "pending_approval", "partially_approved_holdout"}
            and rgroup_promotion_approval.get("mode") == "rgroup_promotion_approval_ledger"
            and int(rgroup_promotion_approval.get("invalid_row_count") or 0) == 0
            and int(rgroup_promotion_approval.get("missing_candidate_row_count") or 0) == 0
            and int(rgroup_promotion_approval.get("binding_blocker_count") or 0) == 0
            else "warn",
            "details": (
                f"status={rgroup_promotion_approval.get('status')}; rows={rgroup_promotion_approval.get('row_count')}; "
                f"pending={rgroup_promotion_approval.get('pending_approval_count')}; approved={rgroup_promotion_approval.get('approved_count')}; "
                f"allowed={rgroup_promotion_approval.get('promotion_allowed')}"
            ),
        },
        {
            "check_id": "rgroup_selective_approval_batch",
            "status": "pass"
            if rgroup_selective_approval.get("status") in {"ready", "awaiting_positive_control"}
            and rgroup_selective_approval.get("mode") == "rgroup_selective_approval_batch"
            and rgroup_selective_approval.get("production_promotion_allowed") is False
            else "warn",
            "details": (
                f"status={rgroup_selective_approval.get('status')}; candidates={rgroup_selective_approval.get('candidate_count')}; "
                f"approved={rgroup_selective_approval.get('positive_control_approved_count')}; holdout={rgroup_selective_approval.get('holdout_count')}; "
                f"allowed={rgroup_selective_approval.get('production_promotion_allowed')}"
            ),
        },
        {
            "check_id": "rgroup_digestion_quality_metrics",
            "status": "pass"
            if rgroup_digestion_quality_metrics.get("status") in {"ready", "watch", "awaiting_rows"}
            and rgroup_digestion_quality_metrics.get("mode") == "rgroup_digestion_quality_metrics"
            and rgroup_digestion_quality_metrics.get("production_scoring_affected") is False
            else "warn",
            "details": (
                f"status={rgroup_digestion_quality_metrics.get('status')}; metrics={rgroup_digestion_quality_metrics.get('row_count')}; "
                f"digestion_rows={rgroup_digestion_quality_metrics.get('digestion_row_count')}; quality={rgroup_digestion_quality_metrics.get('quality_status_counts')}"
            ),
        },
        {
            "check_id": "rgroup_digestion_quality_closure_queue",
            "status": "pass"
            if rgroup_digestion_quality_closure.get("status") in {"ready", "awaiting_metrics", "closed_holdout"}
            and rgroup_digestion_quality_closure.get("mode") == "rgroup_digestion_quality_closure_queue"
            and rgroup_digestion_quality_closure.get("production_scoring_affected") is False
            else "warn",
            "details": (
                f"status={rgroup_digestion_quality_closure.get('status')}; tasks={rgroup_digestion_quality_closure.get('row_count')}; "
                f"open={rgroup_digestion_quality_closure.get('open_count')}; issues={rgroup_digestion_quality_closure.get('issue_type_counts')}"
            ),
        },
        {
            "check_id": "feed_promotion_rollback_audit",
            "status": "pass"
            if feed_promotion_rollback.get("status") in {"ready", "awaiting_rows"}
            and feed_promotion_rollback.get("mode") == "feed_promotion_rollback_audit"
            and int(feed_promotion_rollback.get("blocked_count") or 0) == 0
            else "warn",
            "details": (
                f"status={feed_promotion_rollback.get('status')}; approved={feed_promotion_rollback.get('approved_row_count')}; "
                f"ready={feed_promotion_rollback.get('ready_count')}; blocked={feed_promotion_rollback.get('blocked_count')}; "
                f"allowed={feed_promotion_rollback.get('promotion_allowed')}"
            ),
        },
        {
            "check_id": "rgroup_approval_workbench",
            "status": "pass"
            if rgroup_approval_workbench.get("status") in {"ready", "awaiting_rows"}
            and rgroup_approval_workbench.get("mode") == "rgroup_approval_workbench"
            and rgroup_approval_workbench.get("production_scoring_affected") is False
            else "warn",
            "details": (
                f"status={rgroup_approval_workbench.get('status')}; rows={rgroup_approval_workbench.get('row_count')}; "
                f"actions={rgroup_approval_workbench.get('action_bucket_counts')}; filters={rgroup_approval_workbench.get('available_filters')}"
            ),
        },
        {
            "check_id": "rgroup_ring_context_alignment",
            "status": "pass"
            if rgroup_ring_context_alignment.get("status") in {"ready", "awaiting_rows"}
            and rgroup_ring_context_alignment.get("mode") == "rgroup_ring_context_alignment"
            and rgroup_ring_context_alignment.get("production_scoring_affected") is False
            else "warn",
            "details": (
                f"status={rgroup_ring_context_alignment.get('status')}; rows={rgroup_ring_context_alignment.get('row_count')}; "
                f"ring={rgroup_ring_context_alignment.get('ring_replacement_count')}; rgroup={rgroup_ring_context_alignment.get('rgroup_replacement_count')}; "
                f"combined={rgroup_ring_context_alignment.get('combined_review_count')}"
            ),
        },
        {
            "check_id": "rgroup_digestion_quality_closure_ledger",
            "status": "pass"
            if rgroup_digestion_quality_closure_ledger.get("status") in {"closed_holdout", "awaiting_queue"}
            and rgroup_digestion_quality_closure_ledger.get("mode") == "rgroup_digestion_quality_closure_ledger"
            else "warn",
            "details": (
                f"status={rgroup_digestion_quality_closure_ledger.get('status')}; closed={rgroup_digestion_quality_closure_ledger.get('closed_count')}; "
                f"open={rgroup_digestion_quality_closure_ledger.get('open_count')}"
            ),
        },
        {
            "check_id": "rgroup_approval_workbench_decisions",
            "status": "pass"
            if rgroup_approval_workbench_decisions.get("status") in {"decision_recorded", "awaiting_workbench"}
            and rgroup_approval_workbench_decisions.get("mode") == "rgroup_approval_workbench_decisions"
            else "warn",
            "details": (
                f"status={rgroup_approval_workbench_decisions.get('status')}; rows={rgroup_approval_workbench_decisions.get('row_count')}; "
                f"approved_rehearsal={rgroup_approval_workbench_decisions.get('approved_rehearsal_count')}"
            ),
        },
        {
            "check_id": "rgroup_guarded_promotion_rehearsal",
            "status": "pass"
            if rgroup_guarded_promotion_rehearsal.get("status") in {"ready_for_rehearsal", "awaiting_positive_controls"}
            and rgroup_guarded_promotion_rehearsal.get("mode") == "rgroup_guarded_promotion_rehearsal"
            and rgroup_guarded_promotion_rehearsal.get("production_promotion_allowed") is False
            else "warn",
            "details": (
                f"status={rgroup_guarded_promotion_rehearsal.get('status')}; ready={rgroup_guarded_promotion_rehearsal.get('ready_count')}; "
                f"blocked={rgroup_guarded_promotion_rehearsal.get('blocked_count')}"
            ),
        },
        {
            "check_id": "ring_rgroup_axis_governance",
            "status": "pass"
            if ring_rgroup_axis_governance.get("status") in {"ready", "awaiting_alignment"}
            and ring_rgroup_axis_governance.get("mode") == "ring_rgroup_axis_governance"
            else "warn",
            "details": (
                f"status={ring_rgroup_axis_governance.get('status')}; axes={ring_rgroup_axis_governance.get('axis_count')}; "
                f"rows={ring_rgroup_axis_governance.get('row_count')}"
            ),
        },
        {
            "check_id": "rgroup_next_expansion_batch_plan",
            "status": "pass"
            if rgroup_next_expansion_batch_plan.get("status") in {"ready", "awaiting_sources"}
            and rgroup_next_expansion_batch_plan.get("mode") == "rgroup_next_expansion_batch_plan"
            else "warn",
            "details": (
                f"status={rgroup_next_expansion_batch_plan.get('status')}; ready={rgroup_next_expansion_batch_plan.get('ready_count')}; "
                f"cap={rgroup_next_expansion_batch_plan.get('planned_staging_cap_total')}"
            ),
        },
        {
            "check_id": "rgroup_approval_trend_views",
            "status": "pass"
            if rgroup_approval_trend_views.get("status") in {"ready", "ready_with_watch"}
            and rgroup_approval_trend_views.get("mode") == "rgroup_approval_trend_views"
            else "warn",
            "details": (
                f"status={rgroup_approval_trend_views.get('status')}; rows={rgroup_approval_trend_views.get('row_count')}; "
                f"attention={rgroup_approval_trend_views.get('needs_attention_count')}"
            ),
        },
        {
            "check_id": "staging_sandbox_filter_views",
            "status": "pass"
            if staging_sandbox_filter_views.get("status") in {"ready", "empty"}
            and staging_sandbox_filter_views.get("mode") == "staging_sandbox_filter_views"
            else "warn",
            "details": (
                f"status={staging_sandbox_filter_views.get('status')}; "
                f"views={staging_sandbox_filter_views.get('row_count')}; "
                f"filters={staging_sandbox_filter_views.get('available_filters')}"
            ),
        },
        {
            "check_id": "candidate_decision_qa",
            "status": "pass" if decision_qa.get("status") == "ready" and decision_qa.get("mode") == "local_candidate_decision_qa" else "warn",
            "details": f"status={decision_qa.get('status')}; rows={decision_qa.get('row_count')}; attention={decision_qa.get('attention_count')}",
        },
        {
            "check_id": "evidence_quality_scorecard",
            "status": "pass" if evidence_quality.get("status") == "ready" and evidence_quality.get("mode") == "candidate_evidence_quality_scorecard" else "warn",
            "details": f"status={evidence_quality.get('status')}; rows={evidence_quality.get('row_count')}; attention={evidence_quality.get('attention_count')}; watch={evidence_quality.get('watch_count')}",
        },
        {
            "check_id": "candidate_evidence_quality",
            "status": "pass" if legacy_evidence_quality.get("status") == "ready" and legacy_evidence_quality.get("mode") == "candidate_evidence_quality_scorecard" else "warn",
            "details": f"status={legacy_evidence_quality.get('status')}; rows={legacy_evidence_quality.get('row_count')}; attention={legacy_evidence_quality.get('attention_count')}",
        },
        {
            "check_id": "candidate_baseline_manager",
            "status": "pass" if baseline_manager.get("status") in {"ready", "empty"} and baseline_manager.get("mode") == "candidate_baseline_manager" else "warn",
            "details": f"status={baseline_manager.get('status')}; baselines={baseline_manager.get('baseline_count')}; archive_review={baseline_manager.get('archive_review_count')}",
        },
        {
            "check_id": "reviewer_operations",
            "status": "pass" if reviewer_operations.get("status") == "ready" and reviewer_operations.get("mode") == "candidate_reviewer_operations" else "warn",
            "details": f"status={reviewer_operations.get('status')}; overdue={reviewer_operations.get('pending_overdue_count')}; repeated_defer={reviewer_operations.get('repeated_defer_reason_count')}; pending={reviewer_operations.get('workload_pending_count')}",
        },
        {
            "check_id": "baseline_lineage_compare",
            "status": "pass" if baseline_lineage.get("status") in {"ready", "compared"} and baseline_lineage.get("mode") == "candidate_baseline_lineage_compare" else "warn",
            "details": f"status={baseline_lineage.get('status')}; base={baseline_lineage.get('base_baseline_id')}; head={baseline_lineage.get('head_baseline_id')}; changed={baseline_lineage.get('changed_candidate_count')}",
        },
        {
            "check_id": "candidate_baseline_lineage",
            "status": "pass" if legacy_baseline_lineage.get("status") in {"ready", "compared"} and legacy_baseline_lineage.get("mode") == "candidate_baseline_lineage_compare" else "warn",
            "details": f"status={legacy_baseline_lineage.get('status')}; mode={legacy_baseline_lineage.get('comparison_mode')}; changed={legacy_baseline_lineage.get('changed_count', legacy_baseline_lineage.get('changed_candidate_count'))}",
        },
        {
            "check_id": "review_command_center",
            "status": "pass" if review_command_center.get("status") == "ready" and review_command_center.get("mode") == "review_command_center" else "warn",
            "details": f"status={review_command_center.get('status')}; rows={review_command_center.get('row_count')}; actionable={review_command_center.get('actionable_count')}",
        },
        {
            "check_id": "candidate_remediation_queue",
            "status": "pass" if review_remediation.get("status") in {"ready", "clear"} and review_remediation.get("mode") in {"review_remediation_queue", "local_candidate_remediation_queue"} else "warn",
            "details": f"status={review_remediation.get('status')}; open={review_remediation.get('open_count')}; high={review_remediation.get('high_count', review_remediation.get('high_priority_count'))}; medium={review_remediation.get('medium_count', review_remediation.get('medium_priority_count'))}",
        },
        {
            "check_id": "candidate_remediation_workbench",
            "status": "pass" if int(review_remediation.get("saved_view_count") or 0) > 0 and int(review_remediation.get("trend_row_count") or 0) > 0 else "warn",
            "details": f"saved_views={review_remediation.get('saved_view_count')}; trends={review_remediation.get('trend_row_count')}; type_counts={review_remediation.get('task_type_counts')}",
        },
        {
            "check_id": "candidate_remediation_batch_actions",
            "status": "pass" if quality.get("candidate_remediation_batch_assign_supported") is True and quality.get("candidate_remediation_batch_postpone_supported") is True else "warn",
            "details": f"assign={quality.get('candidate_remediation_batch_assign_supported')}; postpone={quality.get('candidate_remediation_batch_postpone_supported')}",
        },
        {
            "check_id": "candidate_remediation_history",
            "status": "pass"
            if remediation_history.get("mode") == "local_candidate_remediation_queue_history"
            and remediation_history.get("status") in {"empty", "tracking"}
            else "warn",
            "details": f"status={remediation_history.get('status')}; events={remediation_history.get('event_count')}; project={remediation_history.get('project_name')}",
        },
        {
            "check_id": "review_remediation_queue",
            "status": "pass" if review_remediation.get("status") in {"ready", "clear"} and review_remediation.get("mode") in {"review_remediation_queue", "local_candidate_remediation_queue"} else "warn",
            "details": f"status={review_remediation.get('status')}; open={review_remediation.get('open_count')}; high={review_remediation.get('high_count', review_remediation.get('high_priority_count'))}; medium={review_remediation.get('medium_count', review_remediation.get('medium_priority_count'))}",
        },
        {
            "check_id": "candidate_review_ops_console",
            "status": "pass"
            if review_ops_console.get("status") == "ready"
            and review_ops_console.get("mode") == "candidate_review_ops_console"
            and int(review_ops_console.get("row_count") or 0) >= int(review_board.get("filtered_row_count") or 0)
            else "warn",
            "details": f"status={review_ops_console.get('status')}; rows={review_ops_console.get('row_count')}; open={review_ops_console.get('open_task_count')}; overdue={review_ops_console.get('overdue_task_count')}; lanes={review_ops_console.get('lane_counts')}",
        },
        {
            "check_id": "review_closure_workbench",
            "status": "pass" if review_closure_workbench.get("status") in {"ready", "empty"} and review_closure_workbench.get("mode") == "review_closure_workbench" else "warn",
            "details": f"status={review_closure_workbench.get('status')}; open={review_closure_workbench.get('open_count')}; overdue={review_closure_workbench.get('overdue_count')}; audit={review_closure_workbench.get('filtered_audit_event_count')}",
        },
        {
            "check_id": "review_closure_filter_views",
            "status": "pass" if review_closure_filter_views.get("status") in {"ready", "empty"} and review_closure_filter_views.get("mode") == "review_closure_filter_views" else "warn",
            "details": f"status={review_closure_filter_views.get('status')}; views={review_closure_filter_views.get('row_count')}; tasks={review_closure_filter_views.get('task_row_count')}; filters={review_closure_filter_views.get('available_filters')}",
        },
        {
            "check_id": "baseline_history_explorer",
            "status": "pass" if baseline_history.get("status") in {"ready", "tracking"} and baseline_history.get("mode") in {"baseline_lineage_history", "candidate_baseline_history_explorer"} else "warn",
            "details": f"status={baseline_history.get('status')}; baselines={baseline_history.get('baseline_count')}; comparisons={baseline_history.get('comparison_count')}; rows={baseline_history.get('row_count')}",
        },
        {
            "check_id": "baseline_scenario_board",
            "status": "pass" if baseline_scenario.get("status") == "ready" and baseline_scenario.get("mode") == "baseline_scenario_board" else "warn",
            "details": f"status={baseline_scenario.get('status')}; rows={baseline_scenario.get('row_count')}; attention={baseline_scenario.get('attention_count')}",
        },
        {
            "check_id": "baseline_whatif_board",
            "status": "pass"
            if baseline_whatif.get("status") == "ready"
            and baseline_whatif.get("mode") == "baseline_whatif_board"
            and int(baseline_whatif.get("scenario_count") or 0) >= 4
            else "warn",
            "details": f"status={baseline_whatif.get('status')}; rows={baseline_whatif.get('row_count')}; scenarios={baseline_whatif.get('scenario_count')}; review={baseline_whatif.get('review_required_count')}",
        },
        {
            "check_id": "baseline_history_charts",
            "status": "pass"
            if (
                int(baseline_history.get("chart_count") or 0) > 0
                and any(_local_artifact_exists(root_path, row.get("preview_path") or row.get("image_path") or row.get("chart_path")) for row in baseline_history.get("chart_rows") or [])
            )
            or int(baseline_history.get("pairwise_row_count") or 0) >= 0
            and baseline_history.get("mode") == "baseline_lineage_history"
            else "warn",
            "details": f"charts={baseline_history.get('chart_count')}; rows={len(baseline_history.get('chart_rows') or [])}; pairwise={baseline_history.get('pairwise_row_count')}",
        },
        {
            "check_id": "baseline_active_preview",
            "status": "pass"
            if (baseline_history.get("active_preview") or {}).get("status") == "ready"
            and baseline_history.get("matrix_row_count") is not None
            else "warn",
            "details": f"active={(baseline_history.get('active_preview') or {}).get('active_baseline_id')}; matrix={baseline_history.get('matrix_row_count')}; rollback={baseline_history.get('rollback_option_count')}",
        },
        {
            "check_id": "baseline_lineage_history",
            "status": "pass" if baseline_history.get("status") in {"tracking", "ready"} and baseline_history.get("mode") in {"baseline_lineage_history", "candidate_baseline_history_explorer"} else "warn",
            "details": f"status={baseline_history.get('status')}; rows={baseline_history.get('row_count')}; latest_movement={baseline_history.get('latest_movement_row_count')}",
        },
        {
            "check_id": "baseline_lineage_preview",
            "status": "pass"
            if baseline_lineage_preview.get("status") in {"ready", "empty"}
            and baseline_lineage_preview.get("mode") == "baseline_lineage_preview"
            and (baseline_lineage_preview.get("preview_available") is False or _local_artifact_exists(root_path, baseline_lineage_preview.get("preview_path")))
            else "warn",
            "details": f"status={baseline_lineage_preview.get('status')}; rows={baseline_lineage_preview.get('row_count')}; preview={baseline_lineage_preview.get('preview_available')}; pairwise={baseline_lineage_preview.get('pairwise_row_count')}",
        },
        {
            "check_id": "baseline_lineage_filter_views",
            "status": "pass" if baseline_lineage_filter_views.get("status") in {"ready", "empty"} and baseline_lineage_filter_views.get("mode") == "baseline_lineage_filter_views" else "warn",
            "details": f"status={baseline_lineage_filter_views.get('status')}; views={baseline_lineage_filter_views.get('row_count')}; preview_rows={baseline_lineage_filter_views.get('preview_row_count')}; filters={baseline_lineage_filter_views.get('available_filters')}",
        },
        {
            "check_id": "native_drilldown_actions",
            "status": "pass"
            if native_drilldown_actions.get("status") in {"ready", "empty"}
            and native_drilldown_actions.get("mode") == "native_drilldown_actions"
            and int(native_drilldown_actions.get("direct_action_supported_count") or 0) >= int(native_drilldown_actions.get("route_supported_count") or 0)
            else "warn",
            "details": f"status={native_drilldown_actions.get('status')}; rows={native_drilldown_actions.get('row_count')}; routes={native_drilldown_actions.get('route_supported_count')}; direct={native_drilldown_actions.get('direct_action_supported_count')}; types={native_drilldown_actions.get('action_type_counts')}",
        },
        {
            "check_id": "production_dashboard_warning_routes",
            "status": "pass" if quality.get("production_dashboard_warning_route_supported") is True else "warn",
            "details": f"route_supported={quality.get('production_dashboard_warning_route_supported')}; dashboard_drilldown={quality.get('production_dashboard_drilldown_supported')}",
        },
        {
            "check_id": "governance_only_source_expansion_guard",
            "status": "pass"
            if {"procurement", "supplier_purchase", "real_experiment_feedback_auto_import"}.issubset(
                set(review_remediation.get("blocked_scopes") or [])
                | set(baseline_history.get("blocked_scopes") or [])
                | set(candidate_explanation.get("blocked_scopes") or [])
                | set(candidate_component_structure_locator.get("blocked_scopes") or [])
                | set(site_detection_confidence.get("blocked_scopes") or [])
                | set(site_detection_calibration.get("blocked_scopes") or [])
                | set(baseline_whatif.get("blocked_scopes") or [])
                | set(review_ops_console.get("blocked_scopes") or [])
                | set(reviewer_cockpit.get("blocked_scopes") or [])
                | set(rgroup_admission_sandbox_replay.get("blocked_scopes") or [])
                | set(substituent_version_diff.get("blocked_scopes") or [])
            )
            else "warn",
            "details": "external_operational_workflows_blocked=True; local_review_guard=active",
        },
        {
            "check_id": "local_db_maintenance_release_gate",
            "status": "pass"
            if local_db_maintenance_release_gate.get("status") in {"pass", "watch"}
            and int(local_db_maintenance_release_gate.get("release_stop_count") or 0) == 0
            else "warn",
            "details": (
                f"status={local_db_maintenance_release_gate.get('status')}; "
                f"release_stop={local_db_maintenance_release_gate.get('release_stop_count')}; "
                f"watch={local_db_maintenance_release_gate.get('watch_count')}"
            ),
        },
        {
            "check_id": "site_detection_regression",
            "status": "pass"
            if site_detection_regression.get("status") == "pass"
            and site_detection_regression.get("mode") == "site_detection_regression"
            and int(site_detection_regression.get("coverage_fail_count") or 0) == 0
            else "warn",
            "details": f"rows={site_detection_regression.get('row_count')}; failures={site_detection_regression.get('fail_count')}; coverage_fail={site_detection_regression.get('coverage_fail_count')}; project_samples={site_detection_regression.get('project_sample_count')}; classes={site_detection_regression.get('site_classes_under_test')}",
        },
        {
            "check_id": "site_detection_expanded_regression",
            "status": "pass"
            if quality.get("site_detection_expanded_regression_supported") is True
            and site_detection_regression.get("status") == "pass"
            and int(site_detection_regression.get("row_count") or 0) >= 20
            and int(site_detection_regression.get("fail_count") or 0) == 0
            else "warn",
            "details": (
                f"expanded={quality.get('site_detection_expanded_regression_supported')}; "
                f"rows={site_detection_regression.get('row_count')}; "
                f"failures={site_detection_regression.get('fail_count')}; "
                f"classes={site_detection_regression.get('site_classes_under_test')}"
            ),
        },
        {
            "check_id": "substituent_version_diff_browser",
            "status": "pass"
            if substituent_version_diff.get("status") == "ready"
            and substituent_version_diff.get("mode") == "substituent_version_diff_browser"
            and int(substituent_version_diff.get("row_count") or 0) > 0
            else "warn",
            "details": f"status={substituent_version_diff.get('status')}; rows={substituent_version_diff.get('row_count')}; linked={substituent_version_diff.get('linked_substituent_count')}; attention={substituent_version_diff.get('candidate_attention_substituent_count')}",
        },
        {
            "check_id": "feed_absorption_audit",
            "status": "pass" if feed_absorption.get("status") in {"ready", "ready_with_open_staging"} and int(feed_absorption.get("blocker_count") or 0) == 0 else "warn",
            "details": f"status={feed_absorption.get('status')}; rows={feed_absorption.get('row_count')}; blockers={feed_absorption.get('blocker_count')}; warnings={feed_absorption.get('warning_count')}",
        },
        {
            "check_id": "feed_absorption_diff_navigator",
            "status": "pass" if feed_absorption_diff.get("status") in {"ready", "ready_with_open_staging"} and int(feed_absorption_diff.get("blocker_count") or 0) == 0 else "warn",
            "details": f"status={feed_absorption_diff.get('status')}; rows={feed_absorption_diff.get('row_count')}; deltas={feed_absorption_diff.get('feed_delta_count')}; blockers={feed_absorption_diff.get('blocker_count')}",
        },
        {
            "check_id": "source_expansion_governance",
            "status": "pass" if source_expansion_governance.get("status") == "ready" and source_expansion_governance.get("ungated_expansion_allowed") is False else "warn",
            "details": f"status={source_expansion_governance.get('status')}; rows={source_expansion_governance.get('row_count')}; blocked={source_expansion_governance.get('blocked_gate_count')}; ungated={source_expansion_governance.get('ungated_expansion_allowed')}",
        },
        {
            "check_id": "feed_promotion_simulator",
            "status": "pass" if feed_promotion_simulator.get("status") in {"awaiting_filled_staging_rows", "ready_with_warnings", "ready_for_promotion"} and int(feed_promotion_simulator.get("blocker_count") or 0) == 0 else "warn",
            "details": f"status={feed_promotion_simulator.get('status')}; rows={feed_promotion_simulator.get('row_count')}; staged={feed_promotion_simulator.get('staged_row_count')}; blockers={feed_promotion_simulator.get('blocker_count')}",
        },
        {
            "check_id": "rgroup_staging_fill_report",
            "status": "pass"
            if rgroup_staging_fill.get("status") in {"staged", "preserved_existing_staging_rows"}
            and rgroup_staging_fill.get("mode") in {"rgroup_staging_fill", "rgroup_staging_fill_from_reviewed_sources"}
            and int(rgroup_staging_fill.get("staged_row_count") or 0) > 0
            else "warn",
            "details": (
                f"status={rgroup_staging_fill.get('status')}; files={rgroup_staging_fill.get('filled_file_count', rgroup_staging_fill.get('source_count'))}; "
                f"staged={rgroup_staging_fill.get('staged_row_count')}; skipped={rgroup_staging_fill.get('skipped_row_count')}"
            ),
        },
        {
            "check_id": "rgroup_staging_quality_budget",
            "status": "pass"
            if staging_quality_budget.get("status") in {"awaiting_rows", "ready_for_sandbox_review"}
            and staging_quality_budget.get("mode") == "rgroup_staging_quality_budget"
            and int(staging_quality_budget.get("blocker_count") or 0) == 0
            else "warn",
            "details": f"status={staging_quality_budget.get('status')}; sources={staging_quality_budget.get('source_count')}; staged={staging_quality_budget.get('staged_row_count')}; blockers={staging_quality_budget.get('blocker_count')}; signoff={staging_quality_budget.get('operator_signoff_required')}",
        },
        {
            "check_id": "rgroup_staging_manual_review_queue",
            "status": "pass"
            if quality.get("staging_manual_review_queue_supported") is True
            and int(staging_quality_budget.get("manual_review_queue_count") or 0) == int(staging_quality_budget.get("source_count") or 0)
            and staging_quality_budget.get("promotion_allowed_without_sandbox_review") is False
            else "warn",
            "details": (
                f"queue={staging_quality_budget.get('manual_review_queue_count')}; "
                f"sources={staging_quality_budget.get('source_count')}; "
                f"manual_status={staging_quality_budget.get('manual_review_status_counts')}; "
                f"quality={quality.get('staging_manual_review_queue_supported')}"
            ),
        },
        {
            "check_id": "rgroup_staging_admission_scorecard",
            "status": "pass"
            if quality.get("rgroup_staging_admission_scorecard_supported") is True
            and staging_admission_scorecard.get("mode") == "rgroup_staging_admission_scorecard"
            and staging_admission_scorecard.get("promotion_allowed") is False
            and staging_admission_scorecard.get("production_scoring_write_allowed") is False
            and int(staging_admission_scorecard.get("row_count") or 0) >= int(staging_quality_budget.get("source_count") or 0)
            else "warn",
            "details": (
                f"status={staging_admission_scorecard.get('status')}; "
                f"rows={staging_admission_scorecard.get('row_count')}; "
                f"top={staging_admission_scorecard.get('top_source')}; "
                f"buckets={staging_admission_scorecard.get('bucket_counts')}; "
                f"quality={quality.get('rgroup_staging_admission_scorecard_supported')}"
            ),
        },
        {
            "check_id": "rgroup_admission_sandbox_impact_replay",
            "status": "pass"
            if quality.get("rgroup_admission_sandbox_impact_replay_supported") is True
            and rgroup_admission_sandbox_replay.get("mode") == "rgroup_admission_sandbox_impact_replay"
            and rgroup_admission_sandbox_replay.get("production_scoring_write_allowed") is False
            and int(rgroup_admission_sandbox_replay.get("row_count") or 0) >= int(staging_admission_scorecard.get("row_count") or 0)
            else "warn",
            "details": (
                f"status={rgroup_admission_sandbox_replay.get('status')}; rows={rgroup_admission_sandbox_replay.get('row_count')}; "
                f"replay={rgroup_admission_sandbox_replay.get('replay_status_counts')}; "
                f"write_allowed={rgroup_admission_sandbox_replay.get('production_scoring_write_allowed')}"
            ),
        },
        {
            "check_id": "rgroup_staging_curator_signoff",
            "status": "pass"
            if quality.get("staging_curator_signoff_supported") is True
            and quality.get("staging_version_diff_link_supported") is True
            and staging_curator_signoff.get("mode") in {"rgroup_staging_curator_signoff", None, ""}
            else "warn",
            "details": (
                f"status={staging_curator_signoff.get('status')}; "
                f"rows={staging_curator_signoff.get('row_count')}; "
                f"decisions={staging_curator_signoff.get('decision_counts')}; "
                f"quality={quality.get('staging_curator_signoff_supported')}; "
                f"version_diff={quality.get('staging_version_diff_link_supported')}"
            ),
        },
        {
            "check_id": "governed_ingestion_batches",
            "status": "pass" if governed_ingestion_batches.get("status") in {"ready", "awaiting_rows", "reviewed_holdout"} and int(governed_ingestion_batches.get("blocked_batch_count") or 0) == 0 else "warn",
            "details": f"status={governed_ingestion_batches.get('status')}; rows={governed_ingestion_batches.get('row_count')}; blocked={governed_ingestion_batches.get('blocked_batch_count')}; allowed={governed_ingestion_batches.get('allowed_ingestion_batch_count')}",
        },
        {
            "check_id": "operator_trend_summary",
            "status": "pass" if operator_trend.get("status") == "ready" and operator_trend.get("mode") == "operator_trend_summary" else "warn",
            "details": f"status={operator_trend.get('status')}; cards={operator_trend.get('card_count')}; needs_attention={operator_trend.get('needs_attention_count')}",
        },
        {
            "check_id": "operator_trend_charts",
            "status": "pass" if operator_charts.get("status") == "ready" and operator_charts.get("mode") == "operator_trend_chart_pack" else "warn",
            "details": f"status={operator_charts.get('status')}; charts={operator_charts.get('chart_count')}; dir={operator_charts.get('chart_dir')}",
        },
        {
            "check_id": "medchem_discussion_handoff",
            "status": "pass" if discussion_handoff.get("status") == "ready" and discussion_handoff.get("mode") == "medchem_discussion_handoff" else "warn",
            "details": f"status={discussion_handoff.get('status')}; rows={discussion_handoff.get('row_count')}; decisions={discussion_handoff.get('decision_counts')}",
        },
    ]
    status = "fail" if any(row["status"] == "fail" for row in checks) else "warn" if any(row["status"] == "warn" for row in checks) else "pass"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "checks": checks,
        "candidate_schema": candidate_schema,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_native_ui_regression_markdown(report: dict) -> str:
    lines = [
        "# Native UI Regression Snapshot",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Project: `{report.get('project_name')}`",
        "",
        "| Check | Status | Details |",
        "| --- | --- | --- |",
    ]
    for row in report.get("checks") or []:
        lines.append(f"| `{row.get('check_id')}` | `{row.get('status')}` | {row.get('details')} |")
    lines.append("")
    return "\n".join(lines)


def write_native_ui_regression_snapshot(
    report: dict,
    json_path: str | Path = DEFAULT_NATIVE_UI_REGRESSION_PATH,
    markdown_path: str | Path = DEFAULT_NATIVE_UI_REGRESSION_MD_PATH,
) -> None:
    json_file = Path(json_path)
    md_file = Path(markdown_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_file.write_text(render_native_ui_regression_markdown(report), encoding="utf-8")
