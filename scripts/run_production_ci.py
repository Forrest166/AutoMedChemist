from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "data" / "releases" / "production_ci_report.json"


def _run_step(step_id: str, command: list[str], *, timeout: int = 180) -> dict:
    started = datetime.now(timezone.utc)
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    ended = datetime.now(timezone.utc)
    return {
        "step_id": step_id,
        "command": command,
        "status": "pass" if result.returncode == 0 else "fail",
        "returncode": result.returncode,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": round((ended - started).total_seconds(), 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def _write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _build_report(results: list[dict], failed: bool, *, post_refresh_steps: list[dict] | None = None) -> dict:
    failed_steps = [row["step_id"] for row in results if row.get("status") != "pass"]
    refresh_failed_steps = [row["step_id"] for row in (post_refresh_steps or []) if row.get("status") != "pass"]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "fail" if failed or refresh_failed_steps else "pass",
        "step_count": len(results),
        "failed_steps": failed_steps + refresh_failed_steps,
        "steps": results,
        "post_refresh_step_count": len(post_refresh_steps or []),
        "post_refresh_steps": post_refresh_steps or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the production data-governance and release-smoke CI sequence.")
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT))
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--classify-pair-conflicts", action="store_true", help="Apply conservative first-pass pair-conflict classifications before smoke.")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--full-pytest", action="store_true", help="Run the full pytest suite instead of production-focused targets.")
    parser.add_argument("--skip-streamlit", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    dashboard_command = [
        py,
        str(ROOT / "scripts" / "build_production_dashboard_snapshot.py"),
        "--fail-on-fail",
    ]
    smoke_production_command = [
        py,
        str(ROOT / "scripts" / "build_release_smoke_checklist.py"),
        "--production",
        "--json-out",
        str(ROOT / "data" / "releases" / "release_smoke_checklist_production.json"),
        "--markdown-out",
        str(ROOT / "docs" / "release_smoke_checklist_production.md"),
    ]
    steps: list[tuple[str, list[str], int]] = [
        (
            "rgroup_feed_governance",
            [
                py,
                str(ROOT / "scripts" / "govern_rgroup_feed_metadata.py"),
                "--write",
                "--require-allowlist",
                "--require-freshness",
                "--sample-strategy",
                "stratified",
            ],
            180,
        ),
        ("rgroup_feed_review_coverage", [py, str(ROOT / "scripts" / "build_rgroup_feed_review_coverage.py")], 120),
        (
            "rgroup_source_expansion",
            [py, str(ROOT / "scripts" / "expand_rgroup_replacement_sources.py"), "--require-source-acceptance", "--require-source-governance"],
            180,
        ),
        (
            "rgroup_normalization",
            [py, str(ROOT / "scripts" / "build_rgroup_normalization_report.py"), "--write-db", "--refresh-raw-db"],
            180,
        ),
        (
            "rgroup_pair_contradictions",
            [py, str(ROOT / "scripts" / "build_rgroup_normalized_pair_contradictions.py"), "--fail-on-blocking"],
            120,
        ),
    ]
    if args.classify_pair_conflicts:
        steps.append(
            (
                "rgroup_pair_conflict_first_pass",
                [py, str(ROOT / "scripts" / "review_rgroup_pair_contradictions.py"), "--first-pass", "--reviewer", "production_ci_pair_conflict_triage"],
                120,
            )
        )
    else:
        steps.append(("rgroup_pair_conflict_decision_summary", [py, str(ROOT / "scripts" / "review_rgroup_pair_contradictions.py")], 120))
    steps.extend(
        [
            ("rgroup_pair_conflict_owner_review_packet", [py, str(ROOT / "scripts" / "build_rgroup_pair_conflict_owner_review_packet.py")], 120),
            (
                "rgroup_pair_conflict_owner_decision_ledger",
                [py, str(ROOT / "scripts" / "apply_rgroup_pair_conflict_owner_decisions.py"), "--reviewer", "production_ci_owner_ledger", "--fail-on-pending"],
                120,
            ),
            ("rgroup_feed_onboarding_gate", [py, str(ROOT / "scripts" / "build_rgroup_feed_onboarding_gate.py"), "--fail-on-blocked"], 120),
            ("rgroup_next_feed_drop_staging", [py, str(ROOT / "scripts" / "prepare_rgroup_feed_drop_staging.py")], 120),
            ("rgroup_staging_fill_reviewed_sources", [py, str(ROOT / "scripts" / "fill_rgroup_staging_from_reviewed_sources.py")], 120),
            ("rgroup_next_feed_drop_staging_gate", [py, str(ROOT / "scripts" / "validate_rgroup_feed_drop_staging.py"), "--fail-on-blocked"], 120),
            ("rgroup_next_feed_drop_promotion_gate", [py, str(ROOT / "scripts" / "promote_rgroup_feed_drop_from_staging.py"), "--dry-run"], 120),
            ("rgroup_next_feed_drop_promotion_diff", [py, str(ROOT / "scripts" / "build_rgroup_feed_drop_promotion_diff.py")], 120),
            ("feed_absorption_audit", [py, str(ROOT / "scripts" / "build_feed_absorption_audit.py"), "--fail-on-blocked"], 120),
            ("feed_absorption_diff_navigator", [py, str(ROOT / "scripts" / "build_feed_absorption_diff_navigator.py"), "--fail-on-blocked"], 120),
            ("ring_outcome_overlay_activation", [py, str(ROOT / "scripts" / "activate_ring_outcome_overlay.py")], 120),
            ("ring_outcome_production_readiness", [py, str(ROOT / "scripts" / "build_ring_outcome_production_readiness.py"), "--fail-on-validation-error"], 120),
            ("ring_outcome_result_package", [py, str(ROOT / "scripts" / "prepare_ring_outcome_result_package.py"), "--fail-on-validation-error"], 120),
            ("ring_outcome_result_package_import_gate", [py, str(ROOT / "scripts" / "import_ring_outcome_result_package.py")], 120),
            ("ring_outcome_result_package_review", [py, str(ROOT / "scripts" / "build_ring_outcome_result_package_review.py"), "--fail-on-validation-error"], 120),
            ("ring_outcome_holdout", [py, str(ROOT / "scripts" / "build_ring_outcome_holdout_report.py"), "--fail-on-review-required"], 120),
            ("measurement_gap_exact_result_intake", [py, str(ROOT / "scripts" / "build_measurement_gap_exact_result_intake.py")], 120),
            ("evidence_value_policy_active_compare", [py, str(ROOT / "scripts" / "build_evidence_value_policy_active_compare.py")], 120),
            ("site_class_policy_pack", [py, str(ROOT / "scripts" / "build_site_class_policy_pack.py")], 120),
            ("site_detection_regression", [py, str(ROOT / "scripts" / "build_site_detection_regression_report.py")], 120),
            ("site_detection_confidence", [py, str(ROOT / "scripts" / "build_site_detection_confidence.py")], 120),
            ("native_portable_package", [py, str(ROOT / "scripts" / "build_native_portable_package.py")], 240),
            ("native_ui_smoke", [py, str(ROOT / "run_native_ui.py"), "--smoke"], 120),
            ("candidate_visual_compare", [py, str(ROOT / "scripts" / "build_candidate_visual_compare.py")], 120),
            ("candidate_structure_interpretation", [py, str(ROOT / "scripts" / "build_candidate_structure_interpretation.py")], 120),
            ("candidate_review_packet", [py, str(ROOT / "scripts" / "build_candidate_review_packet.py")], 120),
            ("candidate_review_board", [py, str(ROOT / "scripts" / "build_candidate_review_board.py")], 120),
            ("candidate_review_analytics", [py, str(ROOT / "scripts" / "build_candidate_review_analytics.py")], 120),
            ("candidate_drilldown_packet", [py, str(ROOT / "scripts" / "build_candidate_drilldown_packet.py")], 120),
            ("local_db_health", [py, str(ROOT / "scripts" / "build_local_db_health_report.py")], 120),
            ("local_db_maintenance", [py, str(ROOT / "scripts" / "build_local_db_maintenance_report.py")], 180),
            ("local_db_maintenance_release_gate", [py, str(ROOT / "scripts" / "build_local_db_maintenance_release_gate.py"), "--fail-on-release-stop"], 120),
            (
                "named_governance_baseline",
                [py, str(ROOT / "scripts" / "build_local_governance_diff.py"), "--create-baseline", "--baseline-name", "default_current"],
                120,
            ),
            ("local_governance_diff", [py, str(ROOT / "scripts" / "build_local_governance_diff.py")], 120),
            (
                "candidate_baseline_compare",
                [
                    py,
                    str(ROOT / "scripts" / "compare_candidate_baseline.py"),
                    "--baseline-id",
                    "local_release_baseline",
                    "--create-if-missing",
                ],
                120,
            ),
            ("candidate_decision_packet", [py, str(ROOT / "scripts" / "build_candidate_decision_packet.py")], 120),
            ("candidate_evidence_drawer", [py, str(ROOT / "scripts" / "build_candidate_evidence_drawer.py")], 120),
            ("candidate_decision_qa", [py, str(ROOT / "scripts" / "build_candidate_decision_qa.py")], 120),
            ("evidence_quality_scorecard", [py, str(ROOT / "scripts" / "build_evidence_quality_scorecard.py")], 120),
            ("candidate_evidence_quality", [py, str(ROOT / "scripts" / "build_candidate_evidence_quality.py")], 120),
            ("candidate_baseline_manager", [py, str(ROOT / "scripts" / "manage_candidate_baselines.py")], 120),
            ("reviewer_operations", [py, str(ROOT / "scripts" / "build_reviewer_operations.py")], 120),
            ("baseline_lineage_compare", [py, str(ROOT / "scripts" / "build_baseline_lineage_compare.py")], 120),
            ("candidate_baseline_lineage", [py, str(ROOT / "scripts" / "build_candidate_baseline_lineage.py")], 120),
            ("baseline_history_explorer", [py, str(ROOT / "scripts" / "build_baseline_history_explorer.py")], 120),
            ("baseline_lineage_history", [py, str(ROOT / "scripts" / "build_baseline_lineage_history.py")], 120),
            ("baseline_lineage_preview", [py, str(ROOT / "scripts" / "build_baseline_lineage_preview.py")], 120),
            ("baseline_lineage_filter_views", [py, str(ROOT / "scripts" / "build_baseline_lineage_filter_views.py")], 120),
            ("review_command_center", [py, str(ROOT / "scripts" / "build_review_command_center.py")], 120),
            ("candidate_remediation_queue", [py, str(ROOT / "scripts" / "build_candidate_remediation_queue.py")], 120),
            ("review_remediation_queue", [py, str(ROOT / "scripts" / "build_review_remediation_queue.py")], 120),
            ("candidate_review_ops_console", [py, str(ROOT / "scripts" / "build_candidate_review_ops_console.py")], 120),
            ("review_closure_workbench", [py, str(ROOT / "scripts" / "build_review_closure_workbench.py")], 120),
            ("review_closure_filter_views", [py, str(ROOT / "scripts" / "build_review_closure_filter_views.py")], 120),
            ("candidate_explanation_panel", [py, str(ROOT / "scripts" / "build_candidate_explanation_panel.py")], 120),
            ("candidate_explanation_compare", [py, str(ROOT / "scripts" / "build_candidate_explanation_compare.py")], 120),
            ("candidate_explanation_drilldown", [py, str(ROOT / "scripts" / "build_candidate_explanation_drilldown.py")], 120),
            ("candidate_explanation_matrix", [py, str(ROOT / "scripts" / "build_candidate_explanation_matrix.py")], 120),
            ("baseline_scenario_board", [py, str(ROOT / "scripts" / "build_baseline_scenario_board.py")], 120),
            ("baseline_whatif_board", [py, str(ROOT / "scripts" / "build_baseline_whatif_board.py")], 120),
            ("substituent_version_diff_browser", [py, str(ROOT / "scripts" / "build_substituent_version_diff_browser.py")], 120),
            ("operator_trend_summary", [py, str(ROOT / "scripts" / "build_operator_trend_summary.py")], 120),
            ("operator_trend_charts", [py, str(ROOT / "scripts" / "build_operator_trend_charts.py")], 120),
            ("medchem_discussion_handoff", [py, str(ROOT / "scripts" / "build_medchem_discussion_handoff.py")], 120),
            ("weekly_release_diff_summary", [py, str(ROOT / "scripts" / "build_weekly_release_diff_summary.py")], 180),
            ("source_expansion_governance", [py, str(ROOT / "scripts" / "build_source_expansion_governance.py"), "--fail-on-blocked"], 120),
            ("feed_promotion_simulator", [py, str(ROOT / "scripts" / "build_feed_promotion_simulator.py"), "--fail-on-blocked"], 120),
            ("rgroup_staging_quality_budget", [py, str(ROOT / "scripts" / "build_rgroup_staging_quality_budget.py"), "--fail-on-blocked"], 120),
            ("rgroup_staging_admission_scorecard", [py, str(ROOT / "scripts" / "build_rgroup_staging_admission_scorecard.py")], 120),
            ("staged_feed_sandbox_scoring", [py, str(ROOT / "scripts" / "build_staged_feed_sandbox_scoring.py"), "--fail-on-blocked"], 120),
            ("sandbox_score_delta_review_packet", [py, str(ROOT / "scripts" / "build_sandbox_score_delta_review_packet.py"), "--fail-on-blocked"], 120),
            (
                "sandbox_score_delta_signoff_ledger",
                [
                    py,
                    str(ROOT / "scripts" / "review_sandbox_score_delta.py"),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "production_ci_holdout",
                    "--note",
                    "Conservative CI holdout; no production scoring approval.",
                    "--preserve-existing",
                    "--fail-on-pending",
                ],
                120,
            ),
            ("sandbox_score_delta_review_packet_signed", [py, str(ROOT / "scripts" / "build_sandbox_score_delta_review_packet.py"), "--fail-on-blocked"], 120),
            ("rgroup_feed_digestion_ledger", [py, str(ROOT / "scripts" / "build_rgroup_feed_digestion_ledger.py"), "--fail-on-blocked"], 120),
            (
                "rgroup_selective_approval_batch",
                [
                    py,
                    str(ROOT / "scripts" / "build_rgroup_selective_approval_batch.py"),
                    "--apply-decisions",
                    "--reviewer",
                    "production_ci_selective_positive_control",
                    "--fail-on-blocked",
                ],
                120,
            ),
            (
                "rgroup_promotion_approval_ledger",
                [
                    py,
                    str(ROOT / "scripts" / "review_rgroup_promotion_approval.py"),
                    "--decision",
                    "deferred",
                    "--reviewer",
                    "production_ci_promotion_holdout",
                    "--note",
                    "Conservative CI promotion holdout; no feed copy approval.",
                    "--preserve-existing",
                    "--fail-on-pending",
                    "--fail-on-blocked",
                ],
                120,
            ),
            ("rgroup_digestion_quality_metrics", [py, str(ROOT / "scripts" / "build_rgroup_digestion_quality_metrics.py"), "--fail-on-blocked"], 120),
            ("rgroup_digestion_quality_closure_queue", [py, str(ROOT / "scripts" / "build_rgroup_digestion_quality_closure_queue.py")], 120),
            (
                "rgroup_digestion_quality_closure_ledger",
                [
                    py,
                    str(ROOT / "scripts" / "review_rgroup_digestion_quality_closure.py"),
                    "--reviewer",
                    "production_ci_quality_closure",
                    "--fail-on-open",
                ],
                120,
            ),
            ("rgroup_digestion_quality_closure_queue_signed", [py, str(ROOT / "scripts" / "build_rgroup_digestion_quality_closure_queue.py")], 120),
            ("feed_promotion_rollback_audit", [py, str(ROOT / "scripts" / "build_feed_promotion_rollback_audit.py"), "--dry-run", "--fail-on-blocked"], 120),
            ("rgroup_approval_workbench", [py, str(ROOT / "scripts" / "build_rgroup_approval_workbench.py")], 120),
            (
                "rgroup_approval_workbench_decisions",
                [py, str(ROOT / "scripts" / "review_rgroup_approval_workbench.py"), "--reviewer", "production_ci_approval_workbench"],
                120,
            ),
            ("rgroup_approval_workbench_signed", [py, str(ROOT / "scripts" / "build_rgroup_approval_workbench.py")], 120),
            ("rgroup_ring_context_alignment", [py, str(ROOT / "scripts" / "build_rgroup_ring_context_alignment.py")], 120),
            ("rgroup_guarded_promotion_rehearsal", [py, str(ROOT / "scripts" / "build_rgroup_guarded_promotion_rehearsal.py"), "--fail-on-blocked"], 120),
            ("ring_rgroup_axis_governance", [py, str(ROOT / "scripts" / "build_ring_rgroup_axis_governance.py")], 120),
            ("rgroup_next_expansion_batch_plan", [py, str(ROOT / "scripts" / "build_rgroup_next_expansion_batch_plan.py"), "--fail-on-blocked"], 120),
            ("rgroup_approval_trend_views", [py, str(ROOT / "scripts" / "build_rgroup_approval_trend_views.py")], 120),
            ("staging_sandbox_filter_views", [py, str(ROOT / "scripts" / "build_staging_sandbox_filter_views.py")], 120),
            ("governed_ingestion_batches", [py, str(ROOT / "scripts" / "build_governed_ingestion_batches.py"), "--fail-on-blocked"], 120),
            ("native_drilldown_actions", [py, str(ROOT / "scripts" / "build_native_drilldown_actions.py")], 120),
            ("native_ui_regression_snapshot", [py, str(ROOT / "scripts" / "build_native_ui_regression_snapshot.py")], 120),
            ("data_foundation_report", [py, str(ROOT / "scripts" / "build_data_foundation_report.py")], 360),
            ("release_smoke_production", smoke_production_command, 120),
            ("production_dashboard_snapshot", dashboard_command, 120),
        ]
    )
    if not args.skip_tests:
        if args.full_pytest:
            steps.append(("pytest_full", [py, "-m", "pytest"], 600))
        else:
            steps.append(
                (
                    "pytest_production_targets",
                    [
                        py,
                        "-m",
                        "pytest",
                        "tests/test_analysis_quality_review.py::test_rgroup_pair_contradiction_review_first_pass_and_update",
                        "tests/test_analysis_quality_review.py::test_rgroup_pair_conflict_owner_review_packet_groups_deferred_rows",
                        "tests/test_analysis_quality_review.py::test_rgroup_pair_conflict_owner_decision_ledger_keeps_deferred_rows",
                        "tests/test_analysis_quality_review.py::test_rgroup_pair_conflict_owner_packet_reuses_ledger_by_pair",
                        "tests/test_analysis_quality_review.py::test_rgroup_feed_onboarding_gate_detects_manifest_coverage",
                        "tests/test_analysis_quality_review.py::test_rgroup_feed_drop_staging_package_writes_templates",
                        "tests/test_analysis_quality_review.py::test_rgroup_feed_drop_staging_preserves_filled_templates_and_gate_ready",
                        "tests/test_analysis_quality_review.py::test_rgroup_feed_drop_promotion_copies_ready_staged_rows_and_manifest",
                        "tests/test_analysis_quality_review.py::test_rgroup_feed_drop_promotion_diff_reviews_ready_staged_rows",
                        "tests/test_analysis_quality_review.py::test_rgroup_selective_approval_positive_control_keeps_partial_holdout",
                        "tests/test_analysis_quality_review.py::test_rgroup_phase42_quality_rollback_workbench_and_ring_alignment",
                        "tests/test_analysis_quality_review.py::test_rgroup_phase43_closure_rehearsal_axis_expansion_and_trends",
                        "tests/test_analysis_quality_review.py::test_ring_outcome_overlay_activation_requires_active_nonzero_and_replay",
                        "tests/test_analysis_quality_review.py::test_ring_outcome_production_readiness_blocks_blank_templates",
                        "tests/test_analysis_quality_review.py::test_ring_outcome_result_package_creates_production_named_pending_template",
                        "tests/test_analysis_quality_review.py::test_ring_outcome_result_package_review_flags_pending_payload",
                        "tests/test_analysis_quality_review.py::test_ring_outcome_holdout_waits_for_real_results_and_replay",
                        "tests/test_analysis_quality_review.py::test_release_smoke_production_mode_fails_unreviewed_feed_coverage",
                        "tests/test_analysis_quality_review.py::test_production_dashboard_snapshot_summarizes_feed_and_ring_gates",
                        "tests/test_data_ops.py::test_candidate_review_board_drilldown_and_baseline_artifacts",
                        "tests/test_data_ops.py::test_candidate_decision_packet_and_operator_trend_summary_artifacts",
                        "tests/test_data_ops.py::test_phase32_evidence_drawer_qa_baseline_charts_and_handoff",
                        "tests/test_data_ops.py::test_phase33_quality_ops_lineage_and_chart_previews",
                        "tests/test_data_ops.py::test_phase34_command_center_remediation_and_lineage_history",
                        "tests/test_data_ops.py::test_rgroup_feed_manifest_policy_templates_are_expanded",
                    ],
                    180,
                )
            )
    if not args.skip_streamlit:
        steps.append(("streamlit_initial_render", [py, "-m", "pytest", "tests/test_streamlit_app.py::test_streamlit_app_initial_render"], 240))

    results = []
    failed = False
    for step_id, command, timeout in steps:
        if step_id == "production_dashboard_snapshot":
            _write_report(_build_report(results, failed), Path(args.report_out))
        try:
            result = _run_step(step_id, command, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            result = {
                "step_id": step_id,
                "command": command,
                "status": "fail",
                "returncode": None,
                "started_at": "",
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": timeout,
                "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr_tail": f"Timed out after {timeout} seconds",
            }
        results.append(result)
        failed = failed or result["status"] != "pass"
        if failed and args.fail_fast:
            break

    report = _build_report(results, failed)
    _write_report(report, Path(args.report_out))
    post_refresh_steps: list[dict] = []
    if not failed:
        post_refresh = _run_step("production_dashboard_snapshot_final_refresh", dashboard_command, timeout=120)
        post_refresh_steps.append(post_refresh)
        failed = failed or post_refresh["status"] != "pass"
        report = _build_report(results, failed, post_refresh_steps=post_refresh_steps)
        _write_report(report, Path(args.report_out))
    print(
        json.dumps(
            {key: value for key, value in report.items() if key not in {"steps", "post_refresh_steps"}},
            indent=2,
            sort_keys=True,
        )
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
