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
from localmedchem.experiment_tracking import EXPERIMENT_PLAN_FIELDS, upsert_experiment_plan_rows  # noqa: E402


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
    parser = argparse.ArgumentParser(description="Build an experiment plan from evidence residual task registry entries.")
    parser.add_argument("--registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "residual_experiment_plan.csv"))
    parser.add_argument("--project-name", default="evidence_residual")
    parser.add_argument("--owner", default="")
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--upsert-db", action="store_true")
    parser.add_argument("--mark-planned", action="store_true")
    parser.add_argument("--reviewer", default="codex")
    args = parser.parse_args()

    registry = load_evidence_residual_task_registry(args.registry)
    rows = residual_tasks_to_experiment_plan(
        registry,
        project_name=args.project_name,
        owner=args.owner,
        batch_size=args.batch_size,
    )
    _write_csv(rows, args.csv_out)
    upsert_report = {"upserted_count": 0}
    if args.upsert_db and rows:
        upsert_report = upsert_experiment_plan_rows(rows, db_path=args.db, source_path=str(Path(args.csv_out).resolve()))
    registry_report = {}
    if args.mark_planned and rows:
        registry_report = update_residual_tasks_from_experiment_plan(rows, registry_path=args.registry, reviewer=args.reviewer).get("last_plan_sync") or {}
    print(
        json.dumps(
            {
                "plan_count": len(rows),
                "csv_out": str(Path(args.csv_out).resolve()),
                "upsert": upsert_report,
                "registry_sync": registry_report,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
