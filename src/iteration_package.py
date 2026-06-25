from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_ITERATION_ROOT = Path("data/projects/iterations")
DEFAULT_ITERATION_COMPARISON_PATH = Path("data/projects/demo/iteration_comparison_report.json")


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_file(directory: Path, pattern: str) -> Path | None:
    paths = [path for path in directory.glob(pattern) if path.is_file()]
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def _latest_next_design_queue_file(directory: Path) -> Path | None:
    paths = [
        path
        for path in directory.glob("next_design_queue*.json")
        if path.is_file() and "decision" not in path.stem
    ]
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def _asset_candidates(root: Path) -> list[tuple[str, Path | None]]:
    queue_dir = root / "data/projects/closed_loop"
    return [
        ("next_design_queue", _latest_next_design_queue_file(queue_dir)),
        ("priority_delta", _latest_file(queue_dir, "priority_delta*.json")),
        ("queue_analog_series_delta", root / "data/projects/closed_loop/queue_analog_series_delta.json"),
        ("queue_analog_series_policy", root / "data/rules/queue_analog_series_policy.yaml"),
        ("multi_objective_calibration", root / "data/projects/demo/multi_objective_calibration_report.json"),
        ("multi_objective_calibrated_profile", root / "data/profiles/calibrated/multi_objective_demo_learning.yaml"),
        ("project_evidence_pack", root / "data/projects/demo/project_evidence_pack.json"),
        ("project_evidence_pack_summary", root / "data/projects/demo/project_evidence_pack_summary.csv"),
        ("project_evidence_expansion_plan", root / "data/projects/demo/project_evidence_expansion_plan.json"),
        ("project_evidence_expansion_plan_csv", root / "data/projects/demo/project_evidence_expansion_plan.csv"),
        ("project_evidence_execution_report", root / "data/projects/demo/project_evidence_execution_report.json"),
        ("public_sar_validation_report", root / "data/projects/demo/public_sar_validation_report.json"),
        ("profile_promotion_registry", root / "data/profiles/profile_promotion_registry.json"),
        ("profile_ab_replay_report", root / "data/projects/demo/profile_ab_replay_report.json"),
        ("profile_ab_replay_report_csv", root / "data/projects/demo/profile_ab_replay_report.csv"),
        ("profile_ab_replay_matrix", root / "data/projects/demo/profile_ab_replay_matrix.json"),
        ("profile_ab_replay_matrix_csv", root / "data/projects/demo/profile_ab_replay_matrix.csv"),
        ("profile_ab_material_change_review", root / "data/projects/demo/profile_ab_material_change_review.json"),
        ("profile_ab_material_change_review_csv", root / "data/projects/demo/profile_ab_material_change_review.csv"),
        ("candidate_evidence_priority_report", root / "data/projects/demo/candidate_evidence_priority_report.json"),
        ("candidate_evidence_priority_report_csv", root / "data/projects/demo/candidate_evidence_priority_report.csv"),
        ("public_sar_contradiction_triage", root / "data/projects/demo/public_sar_contradiction_triage.json"),
        ("public_sar_contradiction_triage_csv", root / "data/projects/demo/public_sar_contradiction_triage.csv"),
        ("public_sar_contradiction_resolution_batch", root / "data/projects/demo/public_sar_contradiction_resolution_batch.json"),
        ("public_sar_contradiction_resolution_batch_csv", root / "data/projects/demo/public_sar_contradiction_resolution_batch.csv"),
        ("public_sar_contradiction_watchlist", root / "data/projects/demo/public_sar_contradiction_watchlist.json"),
        ("public_sar_contradiction_watchlist_csv", root / "data/projects/demo/public_sar_contradiction_watchlist.csv"),
        ("evidence_value_report", root / "data/projects/demo/evidence_value_report.json"),
        ("evidence_value_report_csv", root / "data/projects/demo/evidence_value_report.csv"),
        ("measurement_feedback_plan", root / "data/projects/demo/measurement_feedback_plan.json"),
        ("measurement_feedback_plan_csv", root / "data/projects/demo/measurement_feedback_plan.csv"),
        ("measurement_feedback_results_template", root / "data/projects/demo/measurement_feedback_results_template.csv"),
        ("measurement_feedback_result_import_report", root / "data/projects/demo/measurement_feedback_result_import_report.json"),
        ("measurement_feedback_result_import_report_csv", root / "data/projects/demo/measurement_feedback_result_import_report.csv"),
        ("measurement_feedback_gap_closure", root / "data/projects/demo/measurement_feedback_gap_closure.json"),
        ("measurement_feedback_gap_closure_csv", root / "data/projects/demo/measurement_feedback_gap_closure.csv"),
        ("measurement_gap_exact_result_intake", root / "data/projects/demo/measurement_gap_exact_result_intake.json"),
        ("measurement_gap_exact_result_intake_csv", root / "data/projects/demo/measurement_gap_exact_result_intake.csv"),
        ("measurement_gap_exact_results_template", root / "data/projects/demo/measurement_gap_exact_results_template.csv"),
        ("measurement_gap_endpoint_governance", root / "data/projects/demo/measurement_gap_endpoint_governance.json"),
        ("measurement_gap_endpoint_governance_csv", root / "data/projects/demo/measurement_gap_endpoint_governance.csv"),
        ("evidence_value_calibration_report", root / "data/projects/demo/evidence_value_calibration_report.json"),
        ("evidence_value_calibration_report_csv", root / "data/projects/demo/evidence_value_calibration_report.csv"),
        ("evidence_value_policy_proposal", root / "data/projects/demo/evidence_value_policy_proposal.json"),
        ("evidence_value_policy_proposal_csv", root / "data/projects/demo/evidence_value_policy_proposal.csv"),
        ("evidence_value_policy_replay", root / "data/projects/demo/evidence_value_policy_replay.json"),
        ("evidence_value_policy_replay_csv", root / "data/projects/demo/evidence_value_policy_replay.csv"),
        ("evidence_value_policy_activation", root / "data/projects/demo/evidence_value_policy_activation.json"),
        ("evidence_value_policy_activation_csv", root / "data/projects/demo/evidence_value_policy_activation.csv"),
        ("evidence_value_policy_active", root / "data/projects/demo/evidence_value_policy_active.json"),
        ("evidence_value_policy_active_compare", root / "data/projects/demo/evidence_value_policy_active_compare.json"),
        ("evidence_value_policy_active_compare_csv", root / "data/projects/demo/evidence_value_policy_active_compare.csv"),
        ("profile_impact_review_queue", root / "data/projects/demo/profile_impact_review_queue.json"),
        ("profile_impact_review_queue_csv", root / "data/projects/demo/profile_impact_review_queue.csv"),
        ("project_memory_review_queue", root / "data/projects/demo/project_memory_review_queue.json"),
        ("project_memory_review_queue_csv", root / "data/projects/demo/project_memory_review_queue.csv"),
        ("project_memory_review_dashboard", root / "data/projects/demo/project_memory_review_dashboard.json"),
        ("project_memory_review_dashboard_csv", root / "data/projects/demo/project_memory_review_dashboard.csv"),
        ("promotion_readiness_packet", root / "data/projects/demo/promotion_readiness_packet.json"),
        ("promotion_readiness_packet_csv", root / "data/projects/demo/promotion_readiness_packet.csv"),
        ("residual_adjustment_reviews", root / "data/profiles/calibrated/endpoint_family_residual_adjustment_reviews.csv"),
        ("project_evidence_gap_adjustment_candidates", root / "data/profiles/calibrated/project_evidence_gap_adjustment_candidates.csv"),
        ("residual_adjustment_apply_report", root / "data/profiles/calibrated/endpoint_family_residual_adjustment_apply_report.json"),
        ("residual_task_registry", root / "data/substituents/evidence_residual_task_registry.json"),
        ("residual_experiment_plan", root / "data/projects/demo/residual_experiment_plan.csv"),
        ("residual_result_template", root / "data/projects/demo/residual_experiment_results_template.csv"),
        ("residual_result_intake_manifest", root / "data/projects/demo/residual_result_intake_manifest.json"),
        ("residual_result_import_report", root / "data/projects/demo/residual_result_import_report.json"),
        ("assay_event_triage_report", root / "data/projects/demo/assay_event_triage_report.json"),
        ("assay_followup_result_template", root / "data/projects/demo/assay_followup_results_template.csv"),
        ("assay_followup_result_import_report", root / "data/projects/demo/assay_followup_result_import_report.json"),
        ("profile_promotion_freeze_manifest", root / "data/projects/demo/profile_promotion_freeze_manifest.json"),
        ("profile_promotion_freeze_approvals", root / "data/projects/demo/profile_promotion_freeze_approvals.json"),
        ("profile_promotion_release_tags", root / "data/projects/demo/profile_promotion_release_tags.json"),
        ("profile_promotion_freeze_rollback_drill", root / "data/projects/demo/profile_promotion_freeze_rollback_drill.json"),
        ("profile_promotion_rollback_replay", root / "data/projects/demo/profile_promotion_rollback_replay.json"),
        ("profile_promotion_rollback_replay_csv", root / "data/projects/demo/profile_promotion_rollback_replay.csv"),
        ("profile_rollback_history", root / "data/projects/demo/profile_rollback_history.json"),
        ("profile_rollback_history_csv", root / "data/projects/demo/profile_rollback_history.csv"),
        ("profile_rollback_candidate_history_csv", root / "data/projects/demo/profile_rollback_candidate_history.csv"),
        ("profile_rollback_snapshot_compare", root / "data/projects/demo/profile_rollback_snapshot_compare.json"),
        ("profile_rollback_snapshot_compare_csv", root / "data/projects/demo/profile_rollback_snapshot_compare.csv"),
        ("project_memory_refresh_report", root / "data/projects/demo/project_memory_refresh_report.json"),
        ("scaffold_calibration_audit", root / "data/substituents/scaffold_calibration_audit_report.json"),
        ("scaffold_review_drafts", root / "data/substituents/scaffold_rule_review_drafts.csv"),
        ("closed_loop_acceptance", root / "data/projects/closed_loop_drill/closed_loop_drill_acceptance.json"),
        ("closed_loop_replay", root / "data/projects/demo/closed_loop_replay_report.json"),
        ("closed_loop_promotion_gate", root / "data/projects/demo/closed_loop_promotion_gate.json"),
        ("iteration_comparison", root / "data/projects/demo/iteration_comparison_report.json"),
        ("project_dashboard", root / "data/projects/demo/project_closed_loop_dashboard.json"),
    ]


def build_next_design_iteration_package(
    *,
    root: str | Path = ".",
    project_name: str | None = None,
    package_id: str | None = None,
    output_root: str | Path = DEFAULT_ITERATION_ROOT,
    copy_assets: bool = True,
) -> dict:
    root_path = Path(root)
    now = datetime.now(timezone.utc)
    safe_project = (project_name or "project").replace(" ", "_")
    iteration_id = package_id or f"ITER-{safe_project}-{now.strftime('%Y%m%dT%H%M%SZ')}"
    package_dir = Path(output_root) / iteration_id
    package_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for asset_id, source in _asset_candidates(root_path):
        exists = bool(source and source.exists())
        target = None
        if exists and source and copy_assets:
            target = package_dir / source.name
            shutil.copy2(source, target)
        assets.append(
            {
                "asset_id": asset_id,
                "source_path": str(source) if source else None,
                "exists": exists,
                "package_path": str(target) if target else None,
                "sha256": _sha256(source) if source and exists else None,
                "size_bytes": source.stat().st_size if source and exists else None,
            }
        )
    manifest = {
        "iteration_id": iteration_id,
        "project_name": project_name,
        "created_at": now.isoformat(),
        "package_dir": str(package_dir),
        "manifest_path": str(package_dir / "iteration_manifest.json"),
        "asset_count": len(assets),
        "present_asset_count": sum(1 for item in assets if item["exists"]),
        "missing_asset_count": sum(1 for item in assets if not item["exists"]),
        "assets": assets,
        "recommended_next_actions": [
            "Compare this manifest against the next iteration before promoting policy/profile changes.",
            "Use package snapshots to reproduce candidate ranking context during review.",
        ],
    }
    manifest_path = package_dir / "iteration_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def load_iteration_manifest(path: str | Path) -> dict:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "iteration_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def latest_iteration_manifests(
    *,
    output_root: str | Path = DEFAULT_ITERATION_ROOT,
    limit: int = 2,
) -> list[dict]:
    root = Path(output_root)
    manifests = []
    if not root.exists():
        return manifests
    for package_dir in root.iterdir():
        if not package_dir.is_dir():
            continue
        manifest = load_iteration_manifest(package_dir)
        if manifest:
            manifest["_manifest_mtime"] = (package_dir / "iteration_manifest.json").stat().st_mtime
            manifests.append(manifest)
    manifests.sort(key=lambda item: float(item.get("_manifest_mtime") or 0.0), reverse=True)
    return manifests[: int(limit)]


def _manifest_assets(manifest: dict) -> dict[str, dict]:
    return {str(item.get("asset_id")): item for item in manifest.get("assets") or [] if item.get("asset_id")}


def _packaged_asset_path(manifest: dict, asset_id: str) -> Path | None:
    asset = _manifest_assets(manifest).get(asset_id) or {}
    path = asset.get("package_path") or asset.get("source_path")
    if not path:
        return None
    candidate = Path(path)
    if candidate.exists():
        return candidate
    package_dir = Path(manifest.get("package_dir") or "")
    if package_dir and asset.get("package_path"):
        fallback = package_dir / Path(str(asset.get("package_path"))).name
        if fallback.exists():
            return fallback
    return None


def _read_packaged_json(manifest: dict, asset_id: str) -> dict:
    path = _packaged_asset_path(manifest, asset_id)
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_packaged_yaml(manifest: dict, asset_id: str) -> dict:
    path = _packaged_asset_path(manifest, asset_id)
    if not path:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def iteration_metric_snapshot(manifest: dict) -> dict:
    dashboard = _read_packaged_json(manifest, "project_dashboard")
    replay = _read_packaged_json(manifest, "closed_loop_replay")
    multi_objective = _read_packaged_json(manifest, "multi_objective_calibration")
    residual_registry = _read_packaged_json(manifest, "residual_task_registry")
    policy_doc = _read_packaged_yaml(manifest, "queue_analog_series_policy")
    active_policy = {}
    for item in policy_doc.get("versions") or []:
        if item.get("version") == policy_doc.get("active_version"):
            active_policy = item
            break
    return {
        "iteration_id": manifest.get("iteration_id"),
        "created_at": manifest.get("created_at"),
        "project_name": manifest.get("project_name"),
        "present_asset_count": manifest.get("present_asset_count", 0),
        "missing_asset_count": manifest.get("missing_asset_count", 0),
        "dashboard_status": dashboard.get("overall_status"),
        "feedback_count": (dashboard.get("feedback") or {}).get("feedback_count", 0),
        "open_plan_count": (dashboard.get("experiments") or {}).get("open_plan_count", 0),
        "queue_count": (dashboard.get("next_design_queue") or {}).get("queue_count", 0),
        "residual_task_count": (dashboard.get("residual_tasks") or {}).get("task_count", residual_registry.get("task_count", 0)),
        "residual_status_counts": (dashboard.get("residual_tasks") or {}).get("status_counts") or residual_registry.get("status_counts") or {},
        "replay_status": replay.get("status"),
        "replay_holdout_count": (replay.get("multi_objective_holdout") or {}).get("holdout_count", 0),
        "replay_rank_lift_delta": ((replay.get("multi_objective_holdout") or {}).get("delta") or {}).get("rank_lift_delta"),
        "queue_alignment_rate": (replay.get("queue_policy_replay") or {}).get("alignment_rate"),
        "queue_actionable_series_count": (replay.get("queue_policy_replay") or {}).get("actionable_series_count", 0),
        "multi_objective_status": multi_objective.get("status"),
        "multi_objective_observation_count": multi_objective.get("observation_count", 0),
        "multi_objective_weights": (multi_objective.get("calibrated_profile") or {}).get("score_weights") or {},
        "queue_policy_version": policy_doc.get("active_version") or active_policy.get("version"),
        "queue_policy_training_series_count": active_policy.get("training_series_count", 0),
        "queue_policy_context_count": len(active_policy.get("context_action_base_adjustments") or {}),
    }


def _numeric_delta(base: object, head: object) -> float | None:
    try:
        return round(float(head or 0.0) - float(base or 0.0), 4)
    except (TypeError, ValueError):
        return None


def compare_next_design_iterations(base_manifest: dict, head_manifest: dict) -> dict:
    base_assets = _manifest_assets(base_manifest)
    head_assets = _manifest_assets(head_manifest)
    asset_ids = sorted(set(base_assets) | set(head_assets))
    asset_rows = []
    for asset_id in asset_ids:
        base = base_assets.get(asset_id) or {}
        head = head_assets.get(asset_id) or {}
        if not base and head:
            status = "added"
        elif base and not head:
            status = "removed"
        elif not base.get("exists") and head.get("exists"):
            status = "became_available"
        elif base.get("exists") and not head.get("exists"):
            status = "became_missing"
        elif base.get("sha256") and head.get("sha256") and base.get("sha256") != head.get("sha256"):
            status = "changed"
        elif base.get("size_bytes") != head.get("size_bytes"):
            status = "size_changed"
        else:
            status = "unchanged"
        asset_rows.append(
            {
                "asset_id": asset_id,
                "status": status,
                "base_exists": bool(base.get("exists")),
                "head_exists": bool(head.get("exists")),
                "base_sha256": base.get("sha256"),
                "head_sha256": head.get("sha256"),
                "base_size_bytes": base.get("size_bytes"),
                "head_size_bytes": head.get("size_bytes"),
                "size_delta": _numeric_delta(base.get("size_bytes"), head.get("size_bytes")),
            }
        )
    base_metrics = iteration_metric_snapshot(base_manifest)
    head_metrics = iteration_metric_snapshot(head_manifest)
    metric_deltas = {}
    for key in [
        "feedback_count",
        "open_plan_count",
        "queue_count",
        "residual_task_count",
        "replay_holdout_count",
        "replay_rank_lift_delta",
        "queue_alignment_rate",
        "queue_actionable_series_count",
        "multi_objective_observation_count",
        "queue_policy_training_series_count",
        "queue_policy_context_count",
    ]:
        metric_deltas[key] = _numeric_delta(base_metrics.get(key), head_metrics.get(key))
    changed_assets = [row for row in asset_rows if row["status"] not in {"unchanged"}]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "next_design_iteration_manifest",
        "base_iteration_id": base_manifest.get("iteration_id"),
        "head_iteration_id": head_manifest.get("iteration_id"),
        "base_created_at": base_manifest.get("created_at"),
        "head_created_at": head_manifest.get("created_at"),
        "asset_count": len(asset_rows),
        "changed_asset_count": len(changed_assets),
        "asset_status_counts": {
            status: sum(1 for row in asset_rows if row["status"] == status)
            for status in sorted({row["status"] for row in asset_rows})
        },
        "base_metrics": base_metrics,
        "head_metrics": head_metrics,
        "metric_deltas": metric_deltas,
        "changed_assets": changed_assets,
        "assets": asset_rows,
        "recommended_next_actions": [
            "Review changed policy/profile/queue assets before promoting a new active design iteration.",
            "Use metric deltas to separate real learning movement from pure data refresh drift.",
            "Keep at least two iteration packages available for every promotion decision.",
        ],
    }


def build_latest_iteration_comparison(
    *,
    output_root: str | Path = DEFAULT_ITERATION_ROOT,
) -> dict:
    latest = latest_iteration_manifests(output_root=output_root, limit=2)
    if len(latest) < 2:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "comparison_type": "next_design_iteration_manifest",
            "status": "insufficient_iterations",
            "iteration_count": len(latest),
            "recommended_next_actions": ["Create at least two iteration packages before comparing iteration drift."],
        }
    head, base = latest[0], latest[1]
    report = compare_next_design_iterations(base, head)
    report["status"] = "compared"
    return report


def write_iteration_comparison_report(report: dict, output_path: str | Path = DEFAULT_ITERATION_COMPARISON_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
