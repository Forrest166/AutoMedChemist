from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.experiment_tracking import import_residual_experiment_results_csv, write_experiment_tracking_report  # noqa: E402
from localmedchem.residual_result_intake import build_residual_result_intake_manifest, write_residual_result_intake_manifest  # noqa: E402
from localmedchem.ring_outcome_learning import build_ring_outcome_learning_report, write_ring_outcome_learning_report  # noqa: E402
from localmedchem.ring_outcome_overlay import DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH, build_ring_outcome_overlay_activation_report, build_ring_outcome_scoring_overlay, write_ring_outcome_overlay_activation_report, write_ring_outcome_scoring_overlay  # noqa: E402
from localmedchem.ring_outcome_readiness import build_ring_outcome_production_readiness, write_ring_outcome_production_readiness  # noqa: E402
from localmedchem.ring_outcome_replay import build_ring_outcome_overlay_replay, write_ring_outcome_overlay_replay  # noqa: E402
from localmedchem.ring_outcome_holdout import build_ring_outcome_holdout_report, write_ring_outcome_holdout_report  # noqa: E402
from localmedchem.ring_outcome_tasks import build_ring_outcome_residual_tasks, merge_ring_outcome_tasks_into_registry, write_ring_outcome_residual_tasks  # noqa: E402
from localmedchem.evidence_confidence import (  # noqa: E402
    load_evidence_residual_task_registry,
    residual_tasks_to_experiment_plan,
    update_residual_tasks_from_experiment_plan,
    write_evidence_residual_task_registry,
)
from localmedchem.experiment_tracking import EXPERIMENT_PLAN_FIELDS, upsert_experiment_plan_rows, write_experiment_result_template  # noqa: E402


def _is_active_ring_task(row: dict) -> bool:
    task_id = str(row.get("task_id") or "")
    status = str(row.get("status") or "open").strip().lower()
    lifecycle = str(row.get("lifecycle_state") or "active").strip().lower()
    is_ring = task_id.startswith("RINGTASK-") or row.get("task_source") == "ring_outcome_overlay"
    return bool(is_ring and lifecycle == "active" and status in {"open", "planned"})


def _write_plan_csv(rows: list[dict], path: str | Path) -> None:
    import csv

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    extras = sorted({key for row in rows for key in row if key not in EXPERIMENT_PLAN_FIELDS})
    fieldnames = EXPERIMENT_PLAN_FIELDS + extras
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _refresh_ring_loop(*, db_path: str | Path, registry_path: str | Path, project_name: str | None) -> dict:
    learning = build_ring_outcome_learning_report(db_path=db_path, project_name=project_name)
    write_ring_outcome_learning_report(
        learning,
        json_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.json",
        csv_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.csv",
    )
    overlay = build_ring_outcome_scoring_overlay(
        learning,
        review_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_reviews.csv",
        policy_path=ROOT / DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH,
        min_observed=3,
        require_approved_review=True,
    )
    write_ring_outcome_scoring_overlay(
        overlay,
        json_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json",
        csv_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.csv",
    )
    tasks = build_ring_outcome_residual_tasks(overlay)
    write_ring_outcome_residual_tasks(
        tasks,
        json_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_residual_tasks.json",
        csv_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_residual_tasks.csv",
    )
    registry = merge_ring_outcome_tasks_into_registry(
        tasks,
        existing_registry=load_evidence_residual_task_registry(registry_path),
        reviewer="ring_outcome_result_import",
    )
    ring_registry = {**registry, "tasks": [dict(row) for row in registry.get("tasks") or [] if _is_active_ring_task(row)]}
    plan_rows = residual_tasks_to_experiment_plan(
        ring_registry,
        project_name=project_name or "demo_learning",
        owner="ring_outcome_result_import",
        batch_size=12,
    )
    plan_json_path = ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.json"
    plan_csv_path = ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.csv"
    template_path = ROOT / "data" / "projects" / "demo" / "ring_outcome_results_template.csv"
    plan_json_path.write_text(json.dumps({"plan_count": len(plan_rows), "plans": plan_rows}, indent=2, sort_keys=True), encoding="utf-8")
    _write_plan_csv(plan_rows, plan_csv_path)
    template_rows = write_experiment_result_template(plan_rows, template_path, blank_results=True)
    upsert = upsert_experiment_plan_rows(plan_rows, db_path=db_path, source_path=str(plan_csv_path.resolve())) if plan_rows else {"upserted_count": 0}
    if plan_rows:
        registry = update_residual_tasks_from_experiment_plan(
            plan_rows,
            registry_path=registry_path,
            reviewer="ring_outcome_result_import",
            note="Ring outcome residual task refreshed into experiment plan after result import.",
        )
    write_evidence_residual_task_registry(
        registry,
        registry_path,
        csv_path=ROOT / "data" / "substituents" / "evidence_residual_task_registry.csv",
    )
    replay = build_ring_outcome_overlay_replay(
        root=ROOT,
        overlay_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json",
    )
    write_ring_outcome_overlay_replay(
        replay,
        json_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.json",
        csv_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.csv",
    )
    activation = build_ring_outcome_overlay_activation_report(
        ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json",
        replay=ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.json",
        review_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_reviews.csv",
    )
    write_ring_outcome_overlay_activation_report(
        activation,
        json_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_activation.json",
    )
    readiness = build_ring_outcome_production_readiness(
        plan_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.csv",
        result_csv=ROOT / "data" / "projects" / "demo" / "ring_outcome_results_template.csv",
        intake_manifest_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_result_intake_manifest.json",
        learning_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.json",
        overlay_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json",
        activation_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_activation.json",
        replay_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.json",
    )
    write_ring_outcome_production_readiness(
        readiness,
        json_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_production_readiness.json",
        csv_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_production_readiness.csv",
    )
    holdout = build_ring_outcome_holdout_report(
        learning_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.json",
        overlay_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json",
        replay_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.json",
        activation_path=ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_overlay_activation.json",
        readiness_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_production_readiness.json",
    )
    write_ring_outcome_holdout_report(
        holdout,
        json_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_holdout_report.json",
        csv_path=ROOT / "data" / "projects" / "demo" / "ring_outcome_holdout_report.csv",
    )
    return {
        "ring_outcome_learning": learning.get("status"),
        "learning_group_count": learning.get("group_count"),
        "observed_outcome_count": learning.get("observed_outcome_count"),
        "overlay_context_count": overlay.get("context_count"),
        "overlay_active_context_count": overlay.get("active_context_count"),
        "overlay_activation_status": activation.get("status"),
        "ring_task_count": tasks.get("task_count"),
        "ring_experiment_plan_count": len(plan_rows),
        "ring_experiment_template_row_count": len(template_rows),
        "ring_experiment_plan_upserted_count": upsert.get("upserted_count", 0),
        "overlay_replay_status": replay.get("status"),
        "overlay_replay_ring_candidate_count": replay.get("ring_candidate_count"),
        "ring_outcome_production_readiness": readiness.get("status"),
        "ring_outcome_holdout": holdout.get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and import filled ring-outcome experiment result CSV rows.")
    parser.add_argument("--csv", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_results_template.csv"))
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--plan-path", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.csv"))
    parser.add_argument("--residual-task-registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_result_import_report.json"))
    parser.add_argument("--intake-manifest-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_result_intake_manifest.json"))
    parser.add_argument("--intake-csv-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_result_intake_manifest.csv"))
    parser.add_argument("--import-manifest", default=str(ROOT / "data" / "projects" / "ring_outcome_result_import_manifest.json"))
    parser.add_argument("--allow-duplicate-source", action="store_true")
    parser.add_argument("--require-production-source", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-feedback", action="store_true")
    parser.add_argument("--no-refresh", action="store_true")
    args = parser.parse_args()

    report = import_residual_experiment_results_csv(
        args.csv,
        db_path=args.db,
        update_feedback=not args.no_feedback,
        residual_task_registry_path=args.residual_task_registry,
        strict=args.strict,
        import_manifest_path=args.import_manifest,
        allow_duplicate_source=args.allow_duplicate_source,
        require_production_source=args.require_production_source,
    )
    intake = build_residual_result_intake_manifest(
        plan_path=args.plan_path,
        result_csv=args.csv,
        registry_path=args.residual_task_registry,
    )
    write_residual_result_intake_manifest(
        intake,
        args.intake_manifest_out,
        csv_path=args.intake_csv_out,
    )
    report["ring_outcome_result_intake"] = {
        "status": intake.get("status"),
        "plan_row_count": intake.get("plan_row_count"),
        "result_row_count": intake.get("result_row_count"),
        "importable_row_count": intake.get("importable_row_count"),
        "validation_error_count": intake.get("validation_error_count"),
    }
    if not args.no_refresh:
        report["refreshed_outputs"] = _refresh_ring_loop(
            db_path=args.db,
            registry_path=args.residual_task_registry,
            project_name=args.project_name or None,
        )
    write_experiment_tracking_report(report, args.report_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and ((report.get("validation") or {}).get("error_count") or report.get("status") in {"demo_source_rejected"}):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
