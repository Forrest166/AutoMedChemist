from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_confidence import (  # noqa: E402
    build_evidence_residual_data_tasks,
    load_evidence_residual_task_registry,
    residual_tasks_to_experiment_plan,
    sync_evidence_residual_task_registry,
    update_residual_tasks_from_experiment_plan,
    write_evidence_residual_task_registry,
)
from localmedchem.experiment_tracking import EXPERIMENT_PLAN_FIELDS, upsert_experiment_plan_rows, write_experiment_result_template  # noqa: E402


def _write_csv(rows: list[dict], path: str | Path) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    extras = sorted({key for row in rows for key in row if key not in EXPERIMENT_PLAN_FIELDS})
    fieldnames = EXPERIMENT_PLAN_FIELDS + extras
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the highest-information residual assay batch from current confidence gaps.")
    parser.add_argument("--report", default=str(ROOT / "data" / "substituents" / "evidence_confidence_report.json"))
    parser.add_argument("--registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--registry-csv-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.csv"))
    parser.add_argument("--tasks-json-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_tasks.json"))
    parser.add_argument("--batch-json-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "residual_assay_batch.json"))
    parser.add_argument("--batch-csv-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "residual_assay_batch.csv"))
    parser.add_argument("--result-template-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "residual_assay_results_template.csv"))
    parser.add_argument("--project-name", default="evidence_residual")
    parser.add_argument("--owner", default="codex")
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--max-tasks", type=int, default=40)
    parser.add_argument("--min-abs-residual", type=float, default=0.08)
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--upsert-db", action="store_true")
    parser.add_argument("--mark-planned", action="store_true")
    parser.add_argument("--reviewer", default="codex")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    tasks = build_evidence_residual_data_tasks(report, max_tasks=args.max_tasks, min_abs_residual=args.min_abs_residual)
    registry = sync_evidence_residual_task_registry(
        tasks,
        existing_registry=load_evidence_residual_task_registry(args.registry),
        reviewer=args.reviewer,
    )
    write_evidence_residual_task_registry(registry, args.registry, csv_path=args.registry_csv_out)
    plan_rows = residual_tasks_to_experiment_plan(
        registry,
        project_name=args.project_name,
        owner=args.owner,
        batch_size=args.batch_size,
    )
    if args.mark_planned and plan_rows:
        registry = update_residual_tasks_from_experiment_plan(plan_rows, registry_path=args.registry, reviewer=args.reviewer)
    upsert_report = {"upserted_count": 0}
    if args.upsert_db and plan_rows:
        upsert_report = upsert_experiment_plan_rows(plan_rows, db_path=args.db, source_path=str(Path(args.batch_csv_out).resolve()))
    tasks_path = Path(args.tasks_json_out)
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.write_text(json.dumps({"task_count": len(tasks), "tasks": tasks}, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(plan_rows, args.batch_csv_out)
    result_template_rows = write_experiment_result_template(plan_rows, args.result_template_out, blank_results=True)
    batch_payload = {
        "project_name": args.project_name,
        "batch_count": len(plan_rows),
        "result_template_count": len(result_template_rows),
        "task_count": len(tasks),
        "active_task_count": registry.get("active_task_count"),
        "status_counts": registry.get("status_counts"),
        "selection_basis": "priority, expected_information_gain, abs_residual",
        "upsert": upsert_report,
        "batch": plan_rows,
    }
    batch_path = Path(args.batch_json_out)
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    batch_path.write_text(json.dumps(batch_payload, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "batch_count": len(plan_rows),
                "task_count": len(tasks),
                "active_task_count": registry.get("active_task_count"),
                "batch_json_out": str(batch_path.resolve()),
                "batch_csv_out": str(Path(args.batch_csv_out).resolve()),
                "result_template_out": str(Path(args.result_template_out).resolve()),
                "upsert": upsert_report,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
