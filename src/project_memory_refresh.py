from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

from .analog_series import build_analog_series_report, write_analog_series_report
from .assay_event_triage import build_assay_event_triage_report, write_assay_event_triage_report
from .assay_followup_results import build_assay_followup_result_template
from .candidate_evidence_priority import build_candidate_evidence_priority_report, write_candidate_evidence_priority_report
from .candidate_baselines import compare_candidate_baseline, write_candidate_baseline_compare
from .candidate_drilldown import build_candidate_drilldown_packet, write_candidate_drilldown_packet
from .candidate_review_board import build_candidate_review_board, write_candidate_review_board
from .candidate_review_packet import build_candidate_review_packet, write_candidate_review_packet
from .candidate_visual_compare import build_candidate_visual_compare, write_candidate_visual_compare
from .data_foundation import build_data_foundation_report, save_data_foundation_report
from .evidence_value_policy_active_compare import build_evidence_value_policy_active_compare, write_evidence_value_policy_active_compare
from .evidence_value_scoring import (
    build_evidence_value_calibration_report,
    build_evidence_value_report,
    write_evidence_value_calibration_report,
    write_evidence_value_report,
)
from .evidence_value_policy_proposal import (
    build_evidence_value_policy_proposal,
    build_evidence_value_policy_replay,
    write_evidence_value_policy_proposal,
    write_evidence_value_policy_replay,
)
from .iteration_package import build_next_design_iteration_package
from .local_db_health import build_local_db_health_report, write_local_db_health_report
from .local_db_maintenance import build_local_db_maintenance_report, write_local_db_maintenance_report
from .governance_diff import build_local_governance_diff, create_local_governance_baseline, write_local_governance_diff
from .measurement_feedback_plan import (
    build_measurement_feedback_gap_closure,
    build_measurement_gap_exact_result_intake,
    import_measurement_feedback_results_rows,
    measurement_feedback_rows_from_experiment_results,
    read_experiment_result_rows_csv,
    read_measurement_feedback_result_rows_csv,
    build_measurement_feedback_plan,
    write_measurement_feedback_gap_closure,
    write_measurement_gap_exact_result_intake,
    write_measurement_feedback_import_report,
    write_measurement_feedback_plan,
)
from .measurement_gap_endpoint_governance import build_measurement_gap_endpoint_governance, write_measurement_gap_endpoint_governance
from .profile_impact_review import build_profile_impact_review_queue, write_profile_impact_review_queue
from .project_memory_review_queue import (
    build_project_memory_review_dashboard,
    build_project_memory_review_queue,
    write_project_memory_review_dashboard,
    write_project_memory_review_queue,
)
from .profile_rollback_history import (
    build_profile_rollback_history,
    compare_profile_rollback_snapshots,
    write_profile_rollback_history,
    write_profile_rollback_snapshot_compare,
)
from .profile_promotion_rollback_replay import build_profile_promotion_rollback_replay, write_profile_promotion_rollback_replay
from .project_evidence_expansion_plan import build_project_evidence_expansion_plan, write_project_evidence_expansion_plan
from .project_evidence_pack import build_project_evidence_pack, write_project_evidence_pack
from .promotion_gate import build_closed_loop_promotion_gate, write_closed_loop_promotion_gate
from .promotion_readiness_packet import build_promotion_readiness_packet, write_promotion_readiness_packet
from .public_sar import build_public_strategy_signal_report, write_public_strategy_signal_report
from .public_sar_contradiction_triage import (
    apply_public_sar_contradiction_resolution_batch,
    build_public_sar_contradiction_triage,
    build_public_sar_contradiction_watchlist,
    write_public_sar_contradiction_resolution_batch,
    write_public_sar_contradiction_watchlist,
    write_public_sar_contradiction_triage,
)
from .public_sar_validation import build_public_sar_validation_report, write_public_sar_validation_report
from .native_ui_regression import build_native_ui_regression_snapshot, write_native_ui_regression_snapshot
from .release_smoke import build_release_smoke_checklist, write_release_smoke_checklist
from .site_class_guidance import build_site_class_policy_pack, write_site_class_policy_pack


DEFAULT_PROJECT_MEMORY_REFRESH_PATH = Path("data/projects/demo/project_memory_refresh_report.json")


def _step(step_id: str, label: str, fn: Callable[[], dict | None]) -> dict:
    started = perf_counter()
    try:
        result = fn() or {}
        status = str(result.get("status") or result.get("promotion_status") or "ok")
        ok = status not in {"fail", "failed", "error", "blocked"}
        return {
            "step_id": step_id,
            "label": label,
            "status": status,
            "ok": ok,
            "duration_seconds": round(perf_counter() - started, 3),
            "summary": _summary(result),
        }
    except Exception as exc:
        return {
            "step_id": step_id,
            "label": label,
            "status": "error",
            "ok": False,
            "duration_seconds": round(perf_counter() - started, 3),
            "error": str(exc),
        }


def _summary(report: dict) -> dict:
    keys = [
        "status",
        "promotion_status",
        "row_count",
        "series_count",
        "signal_count",
        "task_count",
        "high_priority_count",
        "high_value_count",
        "processed_count",
        "snapshot_count",
        "candidate_history_count",
        "importable_row_count",
        "calibration_ready_row_count",
        "calibration_row_count",
        "changed_candidate_count",
        "added_candidate_count",
        "removed_candidate_count",
        "weight_change_count",
        "approval_status",
        "block_count",
        "review_count",
        "warning_count",
        "error_count",
        "present_asset_count",
        "missing_asset_count",
        "iteration_id",
        "open_review_count",
        "open_operator_item_count",
        "open_like_count",
        "strict_exact_pending_count",
        "cross_endpoint_blocked_count",
        "blocked_cross_endpoint_pair_count",
        "candidate_count",
        "review_required_count",
        "warn_count",
        "fail_count",
        "profile_impact_review_count",
        "profile_impact_open_count",
        "project_memory_open_like_count",
        "readiness_score",
    ]
    return {key: report.get(key) for key in keys if key in report}


def write_project_memory_refresh_report(
    report: dict,
    output_path: str | Path = DEFAULT_PROJECT_MEMORY_REFRESH_PATH,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def refresh_project_memory(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    db_path: str | Path = "data/localmedchem.sqlite",
    package_iteration: bool = False,
    allow_historical_experiment_feedback: bool = False,
) -> dict:
    root_path = Path(root)
    db_file = Path(db_path)
    if not db_file.is_absolute():
        db_file = root_path / db_file
    context: dict[str, dict] = {}

    def public_signal() -> dict:
        report = build_public_strategy_signal_report(db_path=db_file)
        write_public_strategy_signal_report(report, root_path / "data/substituents/public_strategy_signal_report.json")
        context["public_strategy_signal_report"] = report
        return report

    def analog_series() -> dict:
        report = build_analog_series_report(db_path=db_file, project_name=project_name)
        write_analog_series_report(report, root_path / "data/projects/demo/analog_series_report.json")
        context["analog_series_report"] = report
        return report

    def evidence_pack() -> dict:
        report = build_project_evidence_pack(root=root_path, db_path=db_file, project_name=project_name)
        write_project_evidence_pack(
            report,
            root_path / "data/projects/demo/project_evidence_pack.json",
            summary_csv_path=root_path / "data/projects/demo/project_evidence_pack_summary.csv",
        )
        context["project_evidence_pack"] = report
        return report

    def expansion_plan() -> dict:
        report = build_project_evidence_expansion_plan(root=root_path, project_name=project_name)
        write_project_evidence_expansion_plan(
            report,
            root_path / "data/projects/demo/project_evidence_expansion_plan.json",
            csv_path=root_path / "data/projects/demo/project_evidence_expansion_plan.csv",
        )
        context["project_evidence_expansion_plan"] = report
        return report

    def sar_validation() -> dict:
        report = build_public_sar_validation_report(root=root_path, project_name=project_name)
        write_public_sar_validation_report(
            report,
            root_path / "data/projects/demo/public_sar_validation_report.json",
            csv_path=root_path / "data/projects/demo/public_sar_validation_report.csv",
        )
        context["public_sar_validation_report"] = report
        return report

    def candidate_priority() -> dict:
        report = build_candidate_evidence_priority_report(root=root_path, project_name=project_name)
        write_candidate_evidence_priority_report(
            report,
            root_path / "data/projects/demo/candidate_evidence_priority_report.json",
            csv_path=root_path / "data/projects/demo/candidate_evidence_priority_report.csv",
        )
        context["candidate_evidence_priority_report"] = report
        return report

    def contradiction_triage() -> dict:
        report = build_public_sar_contradiction_triage(root=root_path, project_name=project_name)
        write_public_sar_contradiction_triage(
            report,
            root_path / "data/projects/demo/public_sar_contradiction_triage.json",
            csv_path=root_path / "data/projects/demo/public_sar_contradiction_triage.csv",
        )
        context["public_sar_contradiction_triage"] = report
        return report

    def contradiction_resolution_batch() -> dict:
        result = apply_public_sar_contradiction_resolution_batch(
            triage_path=root_path / "data/projects/demo/public_sar_contradiction_triage.json",
            csv_path=root_path / "data/projects/demo/public_sar_contradiction_triage.csv",
            priority="high",
            reviewer="sar_resolution_policy_v1",
        )
        batch = result.get("batch_report") or {}
        write_public_sar_contradiction_resolution_batch(
            batch,
            root_path / "data/projects/demo/public_sar_contradiction_resolution_batch.json",
            csv_path=root_path / "data/projects/demo/public_sar_contradiction_resolution_batch.csv",
        )
        context["public_sar_contradiction_triage"] = result.get("report") or context.get("public_sar_contradiction_triage") or {}
        context["public_sar_contradiction_resolution_batch"] = batch
        return batch

    def sar_contradiction_watchlist() -> dict:
        report = build_public_sar_contradiction_watchlist(root=root_path, project_name=project_name)
        write_public_sar_contradiction_watchlist(
            report,
            root_path / "data/projects/demo/public_sar_contradiction_watchlist.json",
            csv_path=root_path / "data/projects/demo/public_sar_contradiction_watchlist.csv",
        )
        context["public_sar_contradiction_watchlist"] = report
        return report

    def evidence_value() -> dict:
        report = build_evidence_value_report(root=root_path, project_name=project_name)
        write_evidence_value_report(
            report,
            root_path / "data/projects/demo/evidence_value_report.json",
            csv_path=root_path / "data/projects/demo/evidence_value_report.csv",
        )
        context["evidence_value_report"] = report
        return report

    def measurement_plan() -> dict:
        report = build_measurement_feedback_plan(root=root_path, project_name=project_name)
        write_measurement_feedback_plan(
            report,
            root_path / "data/projects/demo/measurement_feedback_plan.json",
            csv_path=root_path / "data/projects/demo/measurement_feedback_plan.csv",
            template_path=root_path / "data/projects/demo/measurement_feedback_results_template.csv",
        )
        context["measurement_feedback_plan"] = report
        return report

    def measurement_import() -> dict:
        template_path = root_path / "data/projects/demo/measurement_feedback_results_template.csv"
        import_path = root_path / "data/projects/demo/measurement_feedback_result_import_report.json"
        rows = read_measurement_feedback_result_rows_csv(template_path) if template_path.exists() else []
        mapped: dict = {}
        has_real_rows = any(
            str(row.get("observed_value") or "").strip() or str(row.get("observed_unit") or "").strip()
            for row in rows
        )
        source_path = template_path
        if not has_real_rows:
            plan_path = root_path / "data/projects/demo/measurement_feedback_plan.json"
            if import_path.exists():
                existing = json.loads(import_path.read_text(encoding="utf-8")) or {}
                existing["historical_experiment_fallback_enabled"] = bool(allow_historical_experiment_feedback)
                existing["refresh_mode"] = "reuse_existing_import_report_without_real_feedback"
                write_measurement_feedback_import_report(
                    existing,
                    import_path,
                    csv_path=root_path / "data/projects/demo/measurement_feedback_result_import_report.csv",
                )
                context["measurement_feedback_import_report"] = existing
                return existing
            if allow_historical_experiment_feedback:
                experiment_path = root_path / "data/projects/demo/historical_experiment_results.csv"
                plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
                mapped = measurement_feedback_rows_from_experiment_results(
                    read_experiment_result_rows_csv(experiment_path),
                    plan,
                    reviewer="historical_experiment_import",
                )
                rows = mapped.get("rows") or []
                source_path = experiment_path
        report = import_measurement_feedback_results_rows(
            rows,
            root=root_path,
            plan_path=root_path / "data/projects/demo/measurement_feedback_plan.json",
            evidence_value_path=root_path / "data/projects/demo/evidence_value_report.json",
            source_path=source_path,
            reviewer="refresh_project_memory" if has_real_rows else "historical_experiment_import",
        )
        if mapped:
            report["experiment_mapping"] = {key: value for key, value in mapped.items() if key != "rows"}
        write_measurement_feedback_import_report(
            report,
            root_path / "data/projects/demo/measurement_feedback_result_import_report.json",
            csv_path=root_path / "data/projects/demo/measurement_feedback_result_import_report.csv",
        )
        context["measurement_feedback_import_report"] = report
        return report

    def measurement_gap_closure() -> dict:
        report = build_measurement_feedback_gap_closure(root=root_path, project_name=project_name)
        write_measurement_feedback_gap_closure(
            report,
            root_path / "data/projects/demo/measurement_feedback_gap_closure.json",
            csv_path=root_path / "data/projects/demo/measurement_feedback_gap_closure.csv",
        )
        plan_path = root_path / "data/projects/demo/measurement_feedback_plan.json"
        if plan_path.exists():
            context["measurement_feedback_plan"] = json.loads(plan_path.read_text(encoding="utf-8"))
        context["measurement_feedback_gap_closure"] = report
        return report

    def measurement_gap_exact_intake() -> dict:
        report = build_measurement_gap_exact_result_intake(root=root_path, project_name=project_name)
        write_measurement_gap_exact_result_intake(
            report,
            root_path / "data/projects/demo/measurement_gap_exact_result_intake.json",
            csv_path=root_path / "data/projects/demo/measurement_gap_exact_result_intake.csv",
        )
        context["measurement_gap_exact_result_intake"] = report
        return report

    def measurement_gap_endpoint_governance() -> dict:
        report = build_measurement_gap_endpoint_governance(root=root_path, project_name=project_name)
        write_measurement_gap_endpoint_governance(
            report,
            root_path / "data/projects/demo/measurement_gap_endpoint_governance.json",
            csv_path=root_path / "data/projects/demo/measurement_gap_endpoint_governance.csv",
        )
        context["measurement_gap_endpoint_governance"] = report
        return report

    def site_class_policy_pack() -> dict:
        report = build_site_class_policy_pack(root=root_path)
        write_site_class_policy_pack(
            report,
            root_path / "data/projects/demo/site_class_policy_pack.json",
            csv_path=root_path / "data/projects/demo/site_class_policy_pack.csv",
        )
        context["site_class_policy_pack"] = report
        return report

    def evidence_value_calibration() -> dict:
        report = build_evidence_value_calibration_report(root=root_path, project_name=project_name)
        write_evidence_value_calibration_report(
            report,
            root_path / "data/projects/demo/evidence_value_calibration_report.json",
            csv_path=root_path / "data/projects/demo/evidence_value_calibration_report.csv",
        )
        context["evidence_value_calibration_report"] = report
        return report

    def rollback_replay() -> dict:
        report = build_profile_promotion_rollback_replay(root=root_path, project_name=project_name)
        write_profile_promotion_rollback_replay(
            report,
            root_path / "data/projects/demo/profile_promotion_rollback_replay.json",
            csv_path=root_path / "data/projects/demo/profile_promotion_rollback_replay.csv",
        )
        context["profile_promotion_rollback_replay"] = report
        return report

    def rollback_history() -> dict:
        report = build_profile_rollback_history(root=root_path, project_name=project_name)
        write_profile_rollback_history(
            report,
            root_path / "data/projects/demo/profile_rollback_history.json",
            csv_path=root_path / "data/projects/demo/profile_rollback_history.csv",
            candidate_csv_path=root_path / "data/projects/demo/profile_rollback_candidate_history.csv",
        )
        context["profile_rollback_history"] = report
        return report

    def rollback_snapshot_compare() -> dict:
        history = context.get("profile_rollback_history")
        if history is None:
            history_path = root_path / "data/projects/demo/profile_rollback_history.json"
            history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {}
        report = compare_profile_rollback_snapshots(history or {}, project_name=project_name)
        write_profile_rollback_snapshot_compare(
            report,
            root_path / "data/projects/demo/profile_rollback_snapshot_compare.json",
            csv_path=root_path / "data/projects/demo/profile_rollback_snapshot_compare.csv",
        )
        context["profile_rollback_snapshot_compare"] = report
        return report

    def evidence_value_policy_proposal() -> dict:
        proposal_path = root_path / "data/projects/demo/evidence_value_policy_proposal.json"
        active_policy_path = root_path / "data/projects/demo/evidence_value_policy_active.json"
        existing = json.loads(proposal_path.read_text(encoding="utf-8")) if proposal_path.exists() else {}
        active_policy = json.loads(active_policy_path.read_text(encoding="utf-8")) if active_policy_path.exists() else {}
        if (
            existing.get("activation_status") == "active"
            and active_policy.get("activation_status") == "active"
            and active_policy.get("source_proposal_id") == existing.get("proposal_id")
        ):
            write_evidence_value_policy_proposal(
                existing,
                proposal_path,
                csv_path=root_path / "data/projects/demo/evidence_value_policy_proposal.csv",
            )
            context["evidence_value_policy_proposal"] = existing
            return existing
        report = build_evidence_value_policy_proposal(root=root_path, project_name=project_name)
        write_evidence_value_policy_proposal(
            report,
            proposal_path,
            csv_path=root_path / "data/projects/demo/evidence_value_policy_proposal.csv",
        )
        context["evidence_value_policy_proposal"] = report
        return report

    def evidence_value_policy_replay() -> dict:
        proposal = context.get("evidence_value_policy_proposal") or {}
        replay_path = root_path / "data/projects/demo/evidence_value_policy_replay.json"
        existing = json.loads(replay_path.read_text(encoding="utf-8")) if replay_path.exists() else {}
        if proposal.get("activation_status") == "active" and existing.get("activation_status") == "active":
            write_evidence_value_policy_replay(
                existing,
                replay_path,
                csv_path=root_path / "data/projects/demo/evidence_value_policy_replay.csv",
            )
            context["evidence_value_policy_replay"] = existing
            return existing
        report = build_evidence_value_policy_replay(root=root_path, project_name=project_name)
        write_evidence_value_policy_replay(
            report,
            replay_path,
            csv_path=root_path / "data/projects/demo/evidence_value_policy_replay.csv",
        )
        context["evidence_value_policy_replay"] = report
        return report

    def evidence_value_policy_active_compare() -> dict:
        report = build_evidence_value_policy_active_compare(root=root_path, project_name=project_name)
        write_evidence_value_policy_active_compare(
            report,
            root_path / "data/projects/demo/evidence_value_policy_active_compare.json",
            csv_path=root_path / "data/projects/demo/evidence_value_policy_active_compare.csv",
        )
        context["evidence_value_policy_active_compare"] = report
        return report

    def profile_impact_review() -> dict:
        report = build_profile_impact_review_queue(root=root_path, project_name=project_name)
        write_profile_impact_review_queue(
            report,
            root_path / "data/projects/demo/profile_impact_review_queue.json",
            csv_path=root_path / "data/projects/demo/profile_impact_review_queue.csv",
        )
        context["profile_impact_review_queue"] = report
        return report

    def assay_event_triage() -> dict:
        report = build_assay_event_triage_report(
            db_path=db_file,
            project_name=None,
            reviewer="project_memory_refresh",
        )
        write_assay_event_triage_report(
            report,
            root_path / "data/projects/demo/assay_event_triage_report.json",
            csv_path=root_path / "data/projects/demo/assay_event_triage_report.csv",
        )
        context["assay_followup_result_template"] = build_assay_followup_result_template(
            triage_report_path=root_path / "data/projects/demo/assay_event_triage_report.json",
            output_path=root_path / "data/projects/demo/assay_followup_results_template.csv",
        )
        context["assay_event_triage_report"] = report
        return report

    def project_memory_review_queue() -> dict:
        report = build_project_memory_review_queue(root=root_path, project_name=project_name)
        write_project_memory_review_queue(
            report,
            root_path / "data/projects/demo/project_memory_review_queue.json",
            csv_path=root_path / "data/projects/demo/project_memory_review_queue.csv",
        )
        context["project_memory_review_queue"] = report
        return report

    def project_memory_review_dashboard() -> dict:
        report = build_project_memory_review_dashboard(root=root_path, project_name=project_name)
        write_project_memory_review_dashboard(
            report,
            root_path / "data/projects/demo/project_memory_review_dashboard.json",
            csv_path=root_path / "data/projects/demo/project_memory_review_dashboard.csv",
        )
        context["project_memory_review_dashboard"] = report
        return report

    def promotion_gate() -> dict:
        report = build_closed_loop_promotion_gate(root=root_path, project_name=project_name)
        write_closed_loop_promotion_gate(report, root_path / "data/projects/demo/closed_loop_promotion_gate.json")
        context["closed_loop_promotion_gate"] = report
        return report

    def promotion_readiness_packet() -> dict:
        report = build_promotion_readiness_packet(root=root_path, project_name=project_name)
        write_promotion_readiness_packet(
            report,
            root_path / "data/projects/demo/promotion_readiness_packet.json",
            csv_path=root_path / "data/projects/demo/promotion_readiness_packet.csv",
        )
        context["promotion_readiness_packet"] = report
        return report

    def candidate_visual_compare() -> dict:
        report = build_candidate_visual_compare(root=root_path, project_name="demo")
        write_candidate_visual_compare(
            report,
            json_path=root_path / "data/projects/demo/candidate_visual_compare.json",
            csv_path=root_path / "data/projects/demo/candidate_visual_compare.csv",
            markdown_path=root_path / "docs/candidate_visual_compare.md",
        )
        context["candidate_visual_compare"] = report
        return report

    def candidate_review_packet() -> dict:
        report = build_candidate_review_packet(root=root_path, project_name="demo")
        write_candidate_review_packet(
            report,
            json_path=root_path / "data/projects/demo/candidate_review_packet.json",
            csv_path=root_path / "data/projects/demo/candidate_review_packet.csv",
            markdown_path=root_path / "docs/candidate_review_packet.md",
        )
        context["candidate_review_packet"] = report
        return report

    def candidate_review_board() -> dict:
        report = build_candidate_review_board(root=root_path, project_name="demo")
        write_candidate_review_board(
            report,
            json_path=root_path / "data/projects/demo/candidate_review_board.json",
            csv_path=root_path / "data/projects/demo/candidate_review_board.csv",
            markdown_path=root_path / "docs/candidate_review_board.md",
        )
        context["candidate_review_board"] = report
        return report

    def candidate_drilldown_packet() -> dict:
        report = build_candidate_drilldown_packet(root=root_path, project_name="demo")
        write_candidate_drilldown_packet(
            report,
            json_path=root_path / "data/projects/demo/candidate_drilldown_packet.json",
            csv_path=root_path / "data/projects/demo/candidate_drilldown_packet.csv",
            markdown_path=root_path / "docs/candidate_drilldown_packet.md",
        )
        context["candidate_drilldown_packet"] = report
        return report

    def local_db_maintenance() -> dict:
        report = build_local_db_maintenance_report(root=root_path, db_path=db_file)
        write_local_db_maintenance_report(
            report,
            json_path=root_path / "data/releases/local_db_maintenance_report.json",
            csv_path=root_path / "data/releases/local_db_maintenance_report.csv",
            trend_json_path=root_path / "data/releases/local_db_maintenance_trend_history.json",
            trend_csv_path=root_path / "data/releases/local_db_maintenance_trend_history.csv",
        )
        context["local_db_maintenance_report"] = report
        return report

    def governance_baseline_registry() -> dict:
        registry = root_path / "data/projects/demo/governance_baselines/baseline_registry.json"
        if registry.exists():
            try:
                data = json.loads(registry.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
            if data.get("baselines"):
                return {
                    "status": data.get("status") or "ready",
                    "baseline_count": data.get("baseline_count") or len(data.get("baselines") or []),
                    "baseline_registry_path": str(registry),
                }
        report = create_local_governance_baseline(root=root_path, project_name="demo", baseline_name="default_current")
        context["governance_baseline_registry"] = report
        return report

    def local_governance_diff() -> dict:
        report = build_local_governance_diff(root=root_path, project_name="demo")
        write_local_governance_diff(
            report,
            json_path=root_path / "data/projects/demo/local_governance_diff_report.json",
            csv_path=root_path / "data/projects/demo/local_governance_diff_report.csv",
            markdown_path=root_path / "docs/local_governance_diff_report.md",
        )
        context["local_governance_diff"] = report
        return report

    def candidate_baseline_compare() -> dict:
        report = compare_candidate_baseline(root=root_path, project_name="demo", baseline_id="default_current", create_if_missing=True)
        write_candidate_baseline_compare(
            report,
            json_path=root_path / "data/projects/demo/candidate_baseline_compare.json",
            csv_path=root_path / "data/projects/demo/candidate_baseline_compare.csv",
            markdown_path=root_path / "docs/candidate_baseline_compare.md",
        )
        context["candidate_baseline_compare"] = report
        return report

    def data_foundation() -> dict:
        report = build_data_foundation_report(root_path, db_path=db_file, include_checksums=False)
        save_data_foundation_report(report, json_path=root_path / "data/substituents/data_foundation_report.json")
        gate = report.get("ci_gate") or {}
        (root_path / "data/substituents/data_foundation_gate.json").write_text(
            json.dumps(gate, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        context["data_foundation_report"] = report
        return {**gate, "status": gate.get("status") or report.get("data_currency")}

    def local_db_health() -> dict:
        report = build_local_db_health_report(root=root_path, db_path=db_file)
        write_local_db_health_report(
            report,
            json_path=root_path / "data/releases/local_db_health_report.json",
            csv_path=root_path / "data/releases/local_db_health_report.csv",
        )
        context["local_db_health_report"] = report
        return report

    def native_ui_regression() -> dict:
        report = build_native_ui_regression_snapshot(root=root_path, project_name="demo")
        write_native_ui_regression_snapshot(
            report,
            json_path=root_path / "data/releases/native_ui_regression_snapshot.json",
            markdown_path=root_path / "docs/native_ui_regression_snapshot.md",
        )
        context["native_ui_regression_snapshot"] = report
        return report

    def release_smoke() -> dict:
        report = build_release_smoke_checklist(root_path)
        write_release_smoke_checklist(
            report,
            json_path=root_path / "data/releases/release_smoke_checklist.json",
            markdown_path=root_path / "docs/release_smoke_checklist.md",
        )
        context["release_smoke_checklist"] = report
        return report

    def iteration_package() -> dict:
        report = build_next_design_iteration_package(root=root_path, project_name=project_name)
        context["next_design_iteration_manifest"] = report
        return report

    steps = [
        ("public_strategy_signal_report", "Build public SAR strategy signals", public_signal),
        ("analog_series_report", "Build analog series report", analog_series),
        ("project_evidence_pack", "Build project evidence pack", evidence_pack),
        ("project_evidence_expansion_plan", "Build project evidence expansion plan", expansion_plan),
        ("public_sar_validation_report", "Build public SAR validation", sar_validation),
        ("candidate_evidence_priority_report", "Build candidate evidence priority", candidate_priority),
        ("public_sar_contradiction_triage", "Build contradiction-driven SAR triage", contradiction_triage),
        ("public_sar_contradiction_resolution_batch", "Resolve high-priority SAR contradiction batch", contradiction_resolution_batch),
        ("public_sar_contradiction_watchlist", "Build actionable SAR contradiction watchlist", sar_contradiction_watchlist),
        ("evidence_value_report", "Build evidence value scoring", evidence_value),
        ("measurement_feedback_plan", "Build measurement feedback plan", measurement_plan),
        ("measurement_feedback_import", "Import/validate measurement feedback rows", measurement_import),
        ("measurement_feedback_gap_closure", "Build measurement feedback gap closure", measurement_gap_closure),
        ("measurement_gap_exact_result_intake", "Build exact endpoint measurement gap intake", measurement_gap_exact_intake),
        ("measurement_gap_endpoint_governance", "Build strict endpoint gap governance", measurement_gap_endpoint_governance),
        ("site_class_policy_pack", "Build non-experimental site-class policy pack", site_class_policy_pack),
        ("evidence_value_calibration", "Build evidence value calibration", evidence_value_calibration),
        ("project_evidence_expansion_plan_feedback", "Update expansion plan with measurement feedback", expansion_plan),
        ("profile_promotion_rollback_replay", "Build profile rollback replay", rollback_replay),
        ("profile_rollback_history", "Build rollback history", rollback_history),
        ("profile_rollback_snapshot_compare", "Compare rollback snapshots", rollback_snapshot_compare),
        ("evidence_value_policy_proposal", "Build evidence-value policy proposal", evidence_value_policy_proposal),
        ("evidence_value_policy_replay", "Replay evidence-value policy proposal", evidence_value_policy_replay),
        ("evidence_value_policy_active_compare", "Compare active evidence-value policy", evidence_value_policy_active_compare),
        ("profile_impact_review_queue", "Build profile-impact review queue", profile_impact_review),
        ("assay_event_triage", "Build assay event triage", assay_event_triage),
        ("project_memory_review_queue", "Build Project Memory review queue", project_memory_review_queue),
        ("project_memory_review_dashboard", "Build Project Memory review dashboard", project_memory_review_dashboard),
        ("closed_loop_promotion_gate", "Build promotion gate", promotion_gate),
        ("promotion_readiness_packet", "Build promotion readiness packet", promotion_readiness_packet),
        ("candidate_visual_compare", "Build candidate visual comparison packet", candidate_visual_compare),
        ("candidate_review_packet", "Build candidate review packet", candidate_review_packet),
        ("candidate_review_board", "Build candidate review board", candidate_review_board),
        ("candidate_drilldown_packet", "Build candidate drill-down packet", candidate_drilldown_packet),
        ("local_db_health", "Build local DB health report", local_db_health),
        ("local_db_maintenance", "Build local DB maintenance report", local_db_maintenance),
        ("governance_baseline_registry", "Ensure named governance baseline registry", governance_baseline_registry),
        ("local_governance_diff", "Build local governance diff", local_governance_diff),
        ("candidate_baseline_compare", "Build named candidate baseline compare", candidate_baseline_compare),
        ("native_ui_regression_snapshot", "Build native UI regression snapshot", native_ui_regression),
        ("data_foundation_gate", "Build data foundation gate", data_foundation),
        ("release_smoke_checklist", "Build release smoke checklist", release_smoke),
    ]
    if package_iteration:
        steps.append(("next_design_iteration_package", "Package current iteration", iteration_package))

    results = [_step(step_id, label, fn) for step_id, label, fn in steps]
    status = "fail" if any(not row.get("ok") for row in results) else "pass"
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "step_count": len(results),
        "passed_step_count": sum(1 for row in results if row.get("ok")),
        "failed_step_count": sum(1 for row in results if not row.get("ok")),
        "steps": results,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        "recommended_next_actions": [
            "Use this refresh report as the first check before promoting profile or scoring changes.",
            "Review any failed step before packaging a freeze or iteration.",
            "Keep the refresh focused on local evidence, SAR, assays, profiles, and project memory.",
        ],
    }
    refresh_path = root_path / DEFAULT_PROJECT_MEMORY_REFRESH_PATH
    write_project_memory_refresh_report(report, refresh_path)
    final_smoke = release_smoke()
    for row in report["steps"]:
        if row.get("step_id") == "release_smoke_checklist":
            row["status"] = final_smoke.get("status") or row.get("status")
            row["ok"] = row["status"] not in {"fail", "failed", "error", "blocked"}
            row["summary"] = _summary(final_smoke)
            break
    report["failed_step_count"] = sum(1 for row in report["steps"] if not row.get("ok"))
    report["passed_step_count"] = sum(1 for row in report["steps"] if row.get("ok"))
    report["status"] = "fail" if report["failed_step_count"] else "pass"
    write_project_memory_refresh_report(report, refresh_path)
    return report
