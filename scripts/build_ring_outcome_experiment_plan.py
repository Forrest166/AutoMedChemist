from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_confidence import (  # noqa: E402
    load_evidence_residual_task_registry,
    residual_tasks_to_experiment_plan,
    update_residual_tasks_from_experiment_plan,
)
from localmedchem.experiment_tracking import (  # noqa: E402
    EXPERIMENT_PLAN_FIELDS,
    upsert_experiment_plan_rows,
    write_experiment_result_template,
)


def _is_ring_task(row: dict) -> bool:
    task_id = str(row.get("task_id") or "")
    return task_id.startswith("RINGTASK-") or row.get("task_source") == "ring_outcome_overlay"


def _is_active_plannable(row: dict) -> bool:
    status = str(row.get("status") or "open").strip().lower()
    lifecycle = str(row.get("lifecycle_state") or "active").strip().lower()
    return lifecycle == "active" and status in {"open", "planned"}


def _ring_registry(registry: dict) -> dict:
    tasks = [
        dict(row)
        for row in registry.get("tasks") or []
        if isinstance(row, dict) and _is_ring_task(row) and _is_active_plannable(row)
    ]
    return {**registry, "tasks": tasks}


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
    parser = argparse.ArgumentParser(description="Build project experiment-plan rows from ring-outcome residual tasks.")
    parser.add_argument("--registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_experiment_plan.csv"))
    parser.add_argument("--template-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_results_template.csv"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--owner", default="")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--upsert-db", action="store_true")
    parser.add_argument("--mark-planned", action="store_true")
    parser.add_argument("--reviewer", default="codex_ring_plan")
    args = parser.parse_args()

    registry = load_evidence_residual_task_registry(args.registry)
    ring_registry = _ring_registry(registry)
    rows = residual_tasks_to_experiment_plan(
        ring_registry,
        project_name=args.project_name,
        owner=args.owner,
        batch_size=args.batch_size,
    )

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"plan_count": len(rows), "plans": rows}, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(rows, args.csv_out)
    template_rows = write_experiment_result_template(rows, args.template_out, blank_results=True)

    upsert_report = {"upserted_count": 0}
    if args.upsert_db and rows:
        upsert_report = upsert_experiment_plan_rows(rows, db_path=args.db, source_path=str(Path(args.csv_out).resolve()))

    registry_report = {}
    if args.mark_planned and rows:
        registry_report = update_residual_tasks_from_experiment_plan(
            rows,
            registry_path=args.registry,
            reviewer=args.reviewer,
            note="Ring outcome residual task converted into project experiment plan.",
        ).get("last_plan_sync") or {}

    print(
        json.dumps(
            {
                "plan_count": len(rows),
                "source_task_count": len(ring_registry.get("tasks") or []),
                "json_out": str(json_path.resolve()),
                "csv_out": str(Path(args.csv_out).resolve()),
                "template_out": str(Path(args.template_out).resolve()),
                "template_row_count": len(template_rows),
                "upsert": upsert_report,
                "registry_sync": registry_report,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
