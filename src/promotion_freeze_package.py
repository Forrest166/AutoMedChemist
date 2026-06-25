from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PROMOTION_FREEZE_ROOT = Path("data/projects/promotion_freezes")
DEFAULT_PROMOTION_FREEZE_LATEST_PATH = Path("data/projects/demo/profile_promotion_freeze_manifest.json")

PROMOTION_FREEZE_ASSETS = [
    ("profile_promotion_registry", Path("data/profiles/profile_promotion_registry.json")),
    ("closed_loop_promotion_gate", Path("data/projects/demo/closed_loop_promotion_gate.json")),
    ("profile_ab_replay_report", Path("data/projects/demo/profile_ab_replay_report.json")),
    ("profile_ab_replay_report_csv", Path("data/projects/demo/profile_ab_replay_report.csv")),
    ("profile_ab_replay_matrix", Path("data/projects/demo/profile_ab_replay_matrix.json")),
    ("profile_ab_replay_matrix_csv", Path("data/projects/demo/profile_ab_replay_matrix.csv")),
    ("profile_ab_material_change_review", Path("data/projects/demo/profile_ab_material_change_review.json")),
    ("profile_ab_material_change_review_csv", Path("data/projects/demo/profile_ab_material_change_review.csv")),
    ("candidate_evidence_priority_report", Path("data/projects/demo/candidate_evidence_priority_report.json")),
    ("candidate_evidence_priority_report_csv", Path("data/projects/demo/candidate_evidence_priority_report.csv")),
    ("public_sar_contradiction_triage", Path("data/projects/demo/public_sar_contradiction_triage.json")),
    ("public_sar_contradiction_triage_csv", Path("data/projects/demo/public_sar_contradiction_triage.csv")),
    ("public_sar_contradiction_resolution_batch", Path("data/projects/demo/public_sar_contradiction_resolution_batch.json")),
    ("public_sar_contradiction_resolution_batch_csv", Path("data/projects/demo/public_sar_contradiction_resolution_batch.csv")),
    ("public_sar_contradiction_watchlist", Path("data/projects/demo/public_sar_contradiction_watchlist.json")),
    ("public_sar_contradiction_watchlist_csv", Path("data/projects/demo/public_sar_contradiction_watchlist.csv")),
    ("evidence_value_report", Path("data/projects/demo/evidence_value_report.json")),
    ("evidence_value_report_csv", Path("data/projects/demo/evidence_value_report.csv")),
    ("measurement_feedback_plan", Path("data/projects/demo/measurement_feedback_plan.json")),
    ("measurement_feedback_plan_csv", Path("data/projects/demo/measurement_feedback_plan.csv")),
    ("measurement_feedback_results_template", Path("data/projects/demo/measurement_feedback_results_template.csv")),
    ("measurement_feedback_result_import_report", Path("data/projects/demo/measurement_feedback_result_import_report.json")),
    ("measurement_feedback_result_import_report_csv", Path("data/projects/demo/measurement_feedback_result_import_report.csv")),
    ("measurement_feedback_gap_closure", Path("data/projects/demo/measurement_feedback_gap_closure.json")),
    ("measurement_feedback_gap_closure_csv", Path("data/projects/demo/measurement_feedback_gap_closure.csv")),
    ("measurement_gap_exact_result_intake", Path("data/projects/demo/measurement_gap_exact_result_intake.json")),
    ("measurement_gap_exact_result_intake_csv", Path("data/projects/demo/measurement_gap_exact_result_intake.csv")),
    ("measurement_gap_exact_results_template", Path("data/projects/demo/measurement_gap_exact_results_template.csv")),
    ("measurement_gap_endpoint_governance", Path("data/projects/demo/measurement_gap_endpoint_governance.json")),
    ("measurement_gap_endpoint_governance_csv", Path("data/projects/demo/measurement_gap_endpoint_governance.csv")),
    ("evidence_value_calibration_report", Path("data/projects/demo/evidence_value_calibration_report.json")),
    ("evidence_value_calibration_report_csv", Path("data/projects/demo/evidence_value_calibration_report.csv")),
    ("evidence_value_policy_proposal", Path("data/projects/demo/evidence_value_policy_proposal.json")),
    ("evidence_value_policy_proposal_csv", Path("data/projects/demo/evidence_value_policy_proposal.csv")),
    ("evidence_value_policy_replay", Path("data/projects/demo/evidence_value_policy_replay.json")),
    ("evidence_value_policy_replay_csv", Path("data/projects/demo/evidence_value_policy_replay.csv")),
    ("evidence_value_policy_activation", Path("data/projects/demo/evidence_value_policy_activation.json")),
    ("evidence_value_policy_activation_csv", Path("data/projects/demo/evidence_value_policy_activation.csv")),
    ("evidence_value_policy_active", Path("data/projects/demo/evidence_value_policy_active.json")),
    ("evidence_value_policy_active_compare", Path("data/projects/demo/evidence_value_policy_active_compare.json")),
    ("evidence_value_policy_active_compare_csv", Path("data/projects/demo/evidence_value_policy_active_compare.csv")),
    ("profile_impact_review_queue", Path("data/projects/demo/profile_impact_review_queue.json")),
    ("profile_impact_review_queue_csv", Path("data/projects/demo/profile_impact_review_queue.csv")),
    ("project_memory_review_queue", Path("data/projects/demo/project_memory_review_queue.json")),
    ("project_memory_review_queue_csv", Path("data/projects/demo/project_memory_review_queue.csv")),
    ("project_memory_review_dashboard", Path("data/projects/demo/project_memory_review_dashboard.json")),
    ("project_memory_review_dashboard_csv", Path("data/projects/demo/project_memory_review_dashboard.csv")),
    ("promotion_readiness_packet", Path("data/projects/demo/promotion_readiness_packet.json")),
    ("promotion_readiness_packet_csv", Path("data/projects/demo/promotion_readiness_packet.csv")),
    ("project_evidence_pack", Path("data/projects/demo/project_evidence_pack.json")),
    ("project_evidence_expansion_plan", Path("data/projects/demo/project_evidence_expansion_plan.json")),
    ("project_evidence_execution_report", Path("data/projects/demo/project_evidence_execution_report.json")),
    ("public_sar_validation_report", Path("data/projects/demo/public_sar_validation_report.json")),
    ("residual_result_intake_manifest", Path("data/projects/demo/residual_result_intake_manifest.json")),
    ("residual_result_import_report", Path("data/projects/demo/residual_result_import_report.json")),
    ("assay_followup_result_template", Path("data/projects/demo/assay_followup_results_template.csv")),
    ("assay_followup_result_import_report", Path("data/projects/demo/assay_followup_result_import_report.json")),
    ("residual_task_registry", Path("data/substituents/evidence_residual_task_registry.json")),
    ("assay_event_triage_report", Path("data/projects/demo/assay_event_triage_report.json")),
    ("closed_loop_replay_report", Path("data/projects/demo/closed_loop_replay_report.json")),
    ("release_smoke_checklist", Path("data/releases/release_smoke_checklist.json")),
    ("data_foundation_report", Path("data/substituents/data_foundation_report.json")),
    ("data_foundation_gate", Path("data/substituents/data_foundation_gate.json")),
    ("iteration_comparison_report", Path("data/projects/demo/iteration_comparison_report.json")),
    ("profile_promotion_freeze_approvals", Path("data/projects/demo/profile_promotion_freeze_approvals.json")),
    ("profile_promotion_release_tags", Path("data/projects/demo/profile_promotion_release_tags.json")),
    ("profile_promotion_freeze_rollback_drill", Path("data/projects/demo/profile_promotion_freeze_rollback_drill.json")),
    ("profile_promotion_rollback_replay", Path("data/projects/demo/profile_promotion_rollback_replay.json")),
    ("profile_promotion_rollback_replay_csv", Path("data/projects/demo/profile_promotion_rollback_replay.csv")),
    ("profile_rollback_history", Path("data/projects/demo/profile_rollback_history.json")),
    ("profile_rollback_history_csv", Path("data/projects/demo/profile_rollback_history.csv")),
    ("profile_rollback_candidate_history_csv", Path("data/projects/demo/profile_rollback_candidate_history.csv")),
    ("profile_rollback_snapshot_compare", Path("data/projects/demo/profile_rollback_snapshot_compare.json")),
    ("profile_rollback_snapshot_compare_csv", Path("data/projects/demo/profile_rollback_snapshot_compare.csv")),
    ("project_memory_refresh_report", Path("data/projects/demo/project_memory_refresh_report.json")),
]


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_profile_promotion_freeze_package(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    freeze_id: str | None = None,
    output_root: str | Path = DEFAULT_PROMOTION_FREEZE_ROOT,
    copy_assets: bool = True,
) -> dict:
    root_path = Path(root)
    now = datetime.now(timezone.utc)
    safe_project = (project_name or "project").replace(" ", "_")
    package_id = freeze_id or f"FREEZE-{safe_project}-{now.strftime('%Y%m%dT%H%M%SZ')}"
    package_dir = root_path / output_root / package_id if not Path(output_root).is_absolute() else Path(output_root) / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for asset_id, rel_path in PROMOTION_FREEZE_ASSETS:
        source = root_path / rel_path
        exists = source.exists() and source.is_file()
        package_path = None
        if exists and copy_assets:
            package_path = package_dir / source.name
            shutil.copy2(source, package_path)
        assets.append(
            {
                "asset_id": asset_id,
                "source_path": str(source),
                "exists": exists,
                "package_path": str(package_path) if package_path else None,
                "sha256": _sha256(source) if exists else None,
                "size_bytes": source.stat().st_size if exists else None,
            }
        )
    manifest = {
        "freeze_id": package_id,
        "project_name": project_name,
        "created_at": now.isoformat(),
        "package_dir": str(package_dir),
        "manifest_path": str(package_dir / "profile_promotion_freeze_manifest.json"),
        "asset_count": len(assets),
        "present_asset_count": sum(1 for row in assets if row["exists"]),
        "missing_asset_count": sum(1 for row in assets if not row["exists"]),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "assets": assets,
        "recommended_next_actions": [
            "Review this freeze before activating a profile promotion.",
            "Keep missing assets explicit; do not replace absent measured-result artifacts with synthetic values.",
            "Use profile A/B matrix and promotion gate together when approving activation.",
        ],
    }
    manifest_path = Path(manifest["manifest_path"])
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    latest_path = root_path / DEFAULT_PROMOTION_FREEZE_LATEST_PATH
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
