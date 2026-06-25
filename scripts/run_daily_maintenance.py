from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from localmedchem.data_foundation import build_data_foundation_report, data_currency_badge, save_data_foundation_report  # noqa: E402
from localmedchem.database import initialize_database, insert_rgroup_replacements, rebuild_normalized_rgroup_replacements  # noqa: E402
from localmedchem.experiment_tracking import EXPERIMENT_PLAN_FIELDS, upsert_experiment_plan_rows, write_experiment_result_template  # noqa: E402
from localmedchem.analog_series import build_analog_series_report, write_analog_series_report  # noqa: E402
from localmedchem.evidence_confidence import (  # noqa: E402
    build_evidence_confidence_report,
    build_evidence_residual_trend_chart,
    build_endpoint_family_residual_model,
    load_evidence_residual_task_registry,
    residual_tasks_to_experiment_plan,
    update_residual_tasks_from_experiment_plan,
    write_evidence_residual_task_registry,
    write_evidence_confidence_report,
    write_evidence_residual_trend_chart,
    write_endpoint_family_residual_model,
)
from localmedchem.public_sar import build_public_strategy_signal_report, write_public_strategy_signal_report  # noqa: E402
from localmedchem.quality import save_quality_report, validate_data_quality  # noqa: E402
from localmedchem.release_smoke import build_release_smoke_checklist, write_release_smoke_checklist  # noqa: E402
from localmedchem.rgroup_feed_review import build_sample_review_coverage, load_sample_review_queue, write_sample_review_coverage_report  # noqa: E402
from localmedchem.rgroup_normalization import build_rgroup_normalization_report  # noqa: E402
from localmedchem.rgroup_pair_contradictions import (  # noqa: E402
    build_rgroup_normalized_pair_contradiction_report,
    build_rgroup_pair_contradiction_decision_summary,
    write_rgroup_normalized_pair_contradiction_report,
    write_rgroup_pair_contradiction_decision_summary,
)
from localmedchem.ring_import_status import build_ring_import_status, save_ring_import_status  # noqa: E402
from localmedchem.ring_library import load_yaml_collection  # noqa: E402
from localmedchem.ring_outcome_learning import build_ring_outcome_learning_report, write_ring_outcome_learning_report  # noqa: E402
from localmedchem.ring_outcome_overlay import (  # noqa: E402
    DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH,
    build_ring_outcome_overlay_activation_report,
    build_ring_outcome_scoring_overlay,
    write_ring_outcome_overlay_activation_report,
    write_ring_outcome_scoring_overlay,
)
from localmedchem.ring_outcome_replay import build_ring_outcome_overlay_replay, write_ring_outcome_overlay_replay  # noqa: E402
from localmedchem.ring_outcome_tasks import build_ring_outcome_residual_tasks, merge_ring_outcome_tasks_into_registry, write_ring_outcome_residual_tasks  # noqa: E402
from localmedchem.scaffold_review_workspace import build_scaffold_review_workspace_report, write_scaffold_review_workspace_report  # noqa: E402
from localmedchem.transform_evidence import build_transform_evidence_report, write_transform_evidence_markdown, write_transform_evidence_report  # noqa: E402
from run_closed_loop_update import run_closed_loop_update  # noqa: E402
from build_weekly_release_diff_summary import build_weekly_release_diff_summary, render_weekly_markdown  # noqa: E402


def _alert_items(ring_status: dict, quality: dict, foundation: dict | None = None) -> list[dict]:
    items = []
    if ring_status.get("last_error"):
        items.append({"severity": "error", "check": "ring_import_last_error", "message": ring_status["last_error"]})
    if ring_status.get("hours_since_last_import") is not None and float(ring_status["hours_since_last_import"]) > 30:
        items.append({"severity": "warning", "check": "ring_import_stale", "message": f"{ring_status['hours_since_last_import']} hours since last ring import."})
    if quality.get("error_count"):
        items.append({"severity": "error", "check": "quality_errors", "message": f"{quality['error_count']} quality errors."})
    if quality.get("must_fix_warning_count"):
        items.append({"severity": "warning", "check": "quality_must_fix_warnings", "message": f"{quality['must_fix_warning_count']} must-fix warnings."})
    foundation = foundation or {}
    data_drift = foundation.get("data_drift") or {}
    if data_drift.get("status") == "error":
        items.append({"severity": "error", "check": "data_drift", "message": "Data drift exceeded an error threshold."})
    elif data_drift.get("status") == "warning":
        items.append({"severity": "warning", "check": "data_drift", "message": "Data drift warnings should be reviewed."})
    ci_gate = foundation.get("ci_gate") or {}
    if ci_gate.get("status") == "error":
        items.append({"severity": "error", "check": "data_foundation_gate", "message": "Data foundation gate failed."})
    return items


def _active_ring_task_registry(registry: dict) -> dict:
    tasks = []
    for row in registry.get("tasks") or []:
        task_id = str(row.get("task_id") or "")
        is_ring = task_id.startswith("RINGTASK-") or row.get("task_source") == "ring_outcome_overlay"
        status = str(row.get("status") or "open").strip().lower()
        lifecycle = str(row.get("lifecycle_state") or "active").strip().lower()
        if is_ring and lifecycle == "active" and status in {"open", "planned"}:
            tasks.append(dict(row))
    return {**registry, "tasks": tasks}


def _write_experiment_plan_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extras = sorted({key for row in rows for key in row if key not in EXPERIMENT_PLAN_FIELDS})
    fields = EXPERIMENT_PLAN_FIELDS + extras
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily LocalMedChem data maintenance, snapshots, and local alerts.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--skip-closed-loop", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    db_path = Path(args.db_path)
    out_dir = root / "data" / "substituents"
    out_dir.mkdir(parents=True, exist_ok=True)

    ring_status = build_ring_import_status(db_path=db_path)
    save_ring_import_status(ring_status, out_dir / "ring_import_status.json")

    quality = validate_data_quality(root)
    save_quality_report(quality, out_dir / "data_quality_hardening_report.json")

    rgroup_rows = load_yaml_collection(root / "data" / "replacements" / "rgroup_replacements.yaml", "rgroup_replacements")
    rgroup_normalization = build_rgroup_normalization_report(rgroup_rows)
    conn = initialize_database(db_path)
    try:
        insert_rgroup_replacements(conn, rgroup_rows)
        rgroup_normalization["sqlite_refresh"] = rebuild_normalized_rgroup_replacements(conn)
    finally:
        conn.close()
    (out_dir / "rgroup_normalization_report.json").write_text(
        json.dumps(rgroup_normalization, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    rgroup_pair_contradictions = build_rgroup_normalized_pair_contradiction_report(db_path=db_path)
    write_rgroup_normalized_pair_contradiction_report(
        rgroup_pair_contradictions,
        out_dir / "rgroup_normalized_pair_contradictions.json",
        csv_path=out_dir / "rgroup_normalized_pair_contradictions.csv",
    )
    rgroup_pair_decisions = build_rgroup_pair_contradiction_decision_summary(
        rgroup_pair_contradictions,
        review_path=out_dir / "rgroup_normalized_pair_contradiction_reviews.csv",
    )
    write_rgroup_pair_contradiction_decision_summary(
        rgroup_pair_decisions,
        out_dir / "rgroup_normalized_pair_contradiction_decisions.json",
    )
    sample_review_rows = load_sample_review_queue(out_dir / "rgroup_feed_sample_review_queue.csv")
    sample_review_coverage = build_sample_review_coverage(sample_review_rows)
    write_sample_review_coverage_report(
        sample_review_coverage,
        json_path=out_dir / "rgroup_feed_review_coverage.json",
        csv_path=out_dir / "rgroup_feed_review_coverage.csv",
    )

    foundation = build_data_foundation_report(root, db_path=db_path)
    save_data_foundation_report(
        foundation,
        json_path=out_dir / "data_foundation_report.json",
        markdown_path=out_dir / "data_foundation_report.md",
        db_path=db_path,
    )

    transform_evidence = build_transform_evidence_report(db_path=db_path)
    write_transform_evidence_report(transform_evidence, out_dir / "transform_evidence_report.json")
    write_transform_evidence_markdown(transform_evidence, out_dir / "transform_evidence_report.md")

    closed_loop = {}
    if not args.skip_closed_loop:
        closed_loop = run_closed_loop_update(
            db_path=db_path,
            projects_dir=root / "data" / "projects",
            manifest_path=root / "data" / "projects" / "experiment_result_import_manifest.json",
            output_dir=root / "data" / "projects" / "closed_loop",
        )

    public_strategy = build_public_strategy_signal_report(db_path=db_path)
    write_public_strategy_signal_report(public_strategy, out_dir / "public_strategy_signal_report.json")

    evidence_confidence_path = out_dir / "evidence_confidence_report.json"
    previous_evidence_confidence = {}
    if evidence_confidence_path.exists():
        try:
            previous_evidence_confidence = json.loads(evidence_confidence_path.read_text(encoding="utf-8"))
        except Exception:
            previous_evidence_confidence = {}
    evidence_confidence = build_evidence_confidence_report(
        db_path=db_path,
        project_name=None,
        previous_report=previous_evidence_confidence,
    )
    write_evidence_confidence_report(evidence_confidence, evidence_confidence_path)
    residual_trend_chart = build_evidence_residual_trend_chart(evidence_confidence)
    write_evidence_residual_trend_chart(
        residual_trend_chart,
        json_path=out_dir / "evidence_residual_trend_chart.json",
        csv_path=out_dir / "evidence_residual_trend_chart.csv",
    )
    endpoint_family_residual_model = build_endpoint_family_residual_model(evidence_confidence)
    write_endpoint_family_residual_model(
        endpoint_family_residual_model,
        out_dir / "endpoint_family_residual_model.json",
    )

    scaffold_workspace = build_scaffold_review_workspace_report(
        db_path=db_path,
        project_name=None,
        scaffold_rules_path=root / "data" / "rules" / "scaffold_replacements.yaml",
        scaffold_rule_reviews_path=root / "data" / "rules" / "scaffold_rule_reviews.yaml",
    )
    write_scaffold_review_workspace_report(scaffold_workspace, out_dir / "scaffold_review_workspace_report.json")

    analog_series = build_analog_series_report(db_path=db_path, project_name=None)
    write_analog_series_report(analog_series, root / "data" / "projects" / "demo" / "analog_series_report.json")
    ring_outcomes = build_ring_outcome_learning_report(db_path=db_path, project_name=None)
    write_ring_outcome_learning_report(
        ring_outcomes,
        json_path=root / "data" / "projects" / "demo" / "ring_outcome_learning_report.json",
        csv_path=root / "data" / "projects" / "demo" / "ring_outcome_learning_report.csv",
    )
    ring_outcome_overlay = build_ring_outcome_scoring_overlay(
        ring_outcomes,
        review_path=root / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_reviews.csv",
        policy_path=root / DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH,
        min_observed=3,
        require_approved_review=True,
    )
    write_ring_outcome_scoring_overlay(
        ring_outcome_overlay,
        json_path=root / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json",
        csv_path=root / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.csv",
    )
    ring_outcome_task_report = build_ring_outcome_residual_tasks(ring_outcome_overlay)
    write_ring_outcome_residual_tasks(
        ring_outcome_task_report,
        json_path=root / "data" / "projects" / "demo" / "ring_outcome_residual_tasks.json",
        csv_path=root / "data" / "projects" / "demo" / "ring_outcome_residual_tasks.csv",
    )
    residual_task_registry = merge_ring_outcome_tasks_into_registry(
        ring_outcome_task_report,
        existing_registry=load_evidence_residual_task_registry(out_dir / "evidence_residual_task_registry.json"),
        reviewer="daily_maintenance",
    )
    ring_experiment_plan_rows = residual_tasks_to_experiment_plan(
        _active_ring_task_registry(residual_task_registry),
        project_name="demo_learning",
        owner="daily_maintenance",
        batch_size=12,
    )
    ring_plan_json_path = root / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.json"
    ring_plan_csv_path = root / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.csv"
    ring_template_path = root / "data" / "projects" / "demo" / "ring_outcome_results_template.csv"
    ring_plan_json_path.write_text(
        json.dumps({"plan_count": len(ring_experiment_plan_rows), "plans": ring_experiment_plan_rows}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_experiment_plan_csv(ring_experiment_plan_rows, ring_plan_csv_path)
    ring_template_rows = write_experiment_result_template(ring_experiment_plan_rows, ring_template_path, blank_results=True)
    ring_plan_upsert = (
        upsert_experiment_plan_rows(ring_experiment_plan_rows, db_path=db_path, source_path=str(ring_plan_csv_path.resolve()))
        if ring_experiment_plan_rows
        else {"upserted_count": 0}
    )
    if ring_experiment_plan_rows:
        residual_task_registry = update_residual_tasks_from_experiment_plan(
            ring_experiment_plan_rows,
            registry_path=out_dir / "evidence_residual_task_registry.json",
            reviewer="daily_maintenance",
            note="Daily ring outcome residual task experiment-plan refresh.",
        )
    write_evidence_residual_task_registry(
        residual_task_registry,
        out_dir / "evidence_residual_task_registry.json",
        csv_path=out_dir / "evidence_residual_task_registry.csv",
    )
    ring_overlay_replay = build_ring_outcome_overlay_replay(
        root=root,
        overlay_path=root / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json",
    )
    write_ring_outcome_overlay_replay(
        ring_overlay_replay,
        json_path=root / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.json",
        csv_path=root / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.csv",
    )
    ring_overlay_activation = build_ring_outcome_overlay_activation_report(
        ring_outcome_overlay,
        replay=ring_overlay_replay,
        review_path=root / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_reviews.csv",
    )
    write_ring_outcome_overlay_activation_report(
        ring_overlay_activation,
        json_path=root / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_activation.json",
        active_snapshot_path=root / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay_active.json",
    )

    alerts = _alert_items(ring_status, quality, foundation)
    alert_level = "error" if any(item["severity"] == "error" for item in alerts) else "warning" if alerts else "ok"
    alert_payload = {"alert_level": alert_level, "alerts": alerts, "created_at": datetime.now(timezone.utc).isoformat()}
    (out_dir / "daily_maintenance_alert.json").write_text(
        json.dumps(alert_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    currency = data_currency_badge(foundation, alert_payload)
    smoke = build_release_smoke_checklist(root)
    write_release_smoke_checklist(
        smoke,
        json_path=root / "data" / "releases" / "release_smoke_checklist.json",
        markdown_path=root / "docs" / "release_smoke_checklist.md",
    )
    weekly_diff = build_weekly_release_diff_summary(root=root)
    (root / "data" / "releases" / "weekly_release_diff_summary.json").write_text(
        json.dumps(weekly_diff, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (root / "docs" / "weekly_release_diff_summary.md").write_text(render_weekly_markdown(weekly_diff), encoding="utf-8")
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "alert_level": alert_level,
        "alerts": alerts,
        "ring_import_status": ring_status,
        "data_currency": currency,
        "data_drift": foundation.get("data_drift"),
        "release_smoke": {
            "status": smoke.get("status"),
            "check_count": len(smoke.get("checks") or []),
        },
        "rgroup_normalization": {
            "input_count": rgroup_normalization.get("input_count"),
            "deduplicated_count": rgroup_normalization.get("deduplicated_count"),
            "duplicate_group_count": rgroup_normalization.get("duplicate_group_count"),
        },
        "rgroup_feed_review_coverage": {
            "review_row_count": sample_review_coverage.get("review_row_count"),
            "coverage_cell_count": sample_review_coverage.get("coverage_cell_count"),
            "no_review_count": sample_review_coverage.get("no_review_count"),
            "low_coverage_count": sample_review_coverage.get("low_coverage_count"),
            "covered_count": sample_review_coverage.get("covered_count"),
        },
        "rgroup_pair_contradictions": {
            "status": rgroup_pair_contradictions.get("status"),
            "row_count": rgroup_pair_contradictions.get("row_count"),
            "high_priority_count": rgroup_pair_contradictions.get("high_priority_count"),
            "blocking_count": rgroup_pair_contradictions.get("blocking_count"),
            "decision_status": rgroup_pair_decisions.get("status"),
            "open_high_priority_count": rgroup_pair_decisions.get("open_high_priority_count"),
        },
        "weekly_release_diff": {
            "risk_level": (weekly_diff.get("release_manifest_diff") or {}).get("risk_level"),
            "added_count": (weekly_diff.get("release_manifest_diff") or {}).get("added_count"),
            "changed_count": (weekly_diff.get("release_manifest_diff") or {}).get("changed_count"),
            "removed_count": (weekly_diff.get("release_manifest_diff") or {}).get("removed_count"),
        },
        "evidence_confidence": {
            "observation_count": evidence_confidence.get("observation_count"),
            "entry_count": evidence_confidence.get("entry_count"),
            "source_counts": evidence_confidence.get("source_counts"),
            "actionable_residual_count": (evidence_confidence.get("residual_quality_summary") or {}).get("actionable_residual_count"),
            "thin_sample_residual_count": (evidence_confidence.get("residual_quality_summary") or {}).get("thin_sample_residual_count"),
            "residual_trend_status": (evidence_confidence.get("residual_trend_delta") or {}).get("status"),
            "residual_trend_changed_count": (evidence_confidence.get("residual_trend_delta") or {}).get("changed_count"),
            "residual_trend_chart_row_count": len(residual_trend_chart),
            "endpoint_family_residual_model_row_count": endpoint_family_residual_model.get("row_count"),
        },
        "public_strategy_signal": {
            "signal_count": public_strategy.get("signal_count"),
            "source_counts": public_strategy.get("source_counts"),
        },
        "scaffold_review_workspace": {
            "workspace_entry_count": scaffold_workspace.get("workspace_entry_count"),
            "review_priority_counts": scaffold_workspace.get("review_priority_counts"),
        },
        "analog_series": {
            "series_count": analog_series.get("series_count"),
            "recommended_series_count": analog_series.get("recommended_series_count"),
        },
        "ring_outcome_learning": {
            "status": ring_outcomes.get("status"),
            "ring_candidate_count": ring_outcomes.get("ring_candidate_count"),
            "observed_outcome_count": ring_outcomes.get("observed_outcome_count"),
            "group_count": ring_outcomes.get("group_count"),
            "promote_context_count": len(ring_outcomes.get("promote_contexts") or []),
            "downweight_context_count": len(ring_outcomes.get("downweight_contexts") or []),
            "overlay_context_count": ring_outcome_overlay.get("context_count"),
            "overlay_active_context_count": ring_outcome_overlay.get("active_context_count"),
            "overlay_blocked_context_count": ring_outcome_overlay.get("blocked_context_count"),
            "residual_task_count": ring_outcome_task_report.get("task_count"),
            "experiment_plan_count": len(ring_experiment_plan_rows),
            "experiment_template_row_count": len(ring_template_rows),
            "experiment_plan_upserted_count": ring_plan_upsert.get("upserted_count"),
            "overlay_replay_status": ring_overlay_replay.get("status"),
            "overlay_replay_ring_candidate_count": ring_overlay_replay.get("ring_candidate_count"),
            "overlay_activation_status": ring_overlay_activation.get("status"),
            "overlay_active_nonzero_context_count": ring_overlay_activation.get("active_nonzero_context_count"),
        },
        "quality_summary": {
            "ok": quality.get("ok"),
            "error_count": quality.get("error_count"),
            "raw_warning_count": quality.get("raw_warning_count"),
            "accepted_warning_count": quality.get("accepted_warning_count"),
            "must_fix_warning_count": quality.get("must_fix_warning_count"),
        },
        "data_foundation_snapshot_id": foundation.get("snapshot_id"),
        "closed_loop": closed_loop,
    }
    (out_dir / "daily_maintenance_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "daily_maintenance_alert.json").write_text(
        json.dumps({"alert_level": alert_level, "alerts": alerts, "created_at": report["created_at"]}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if alert_level == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
