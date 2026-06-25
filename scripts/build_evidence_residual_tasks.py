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
    sync_evidence_residual_task_registry,
    write_evidence_residual_task_registry,
)


def _write_csv(rows: list[dict], path: str | Path) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "task_id",
        "priority",
        "recommended_action",
        "endpoint_group",
        "target_family",
        "assay_type",
        "evidence_source",
        "observed_count",
        "additional_outcome_target",
        "abs_residual",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser(description="Build evidence residual data-strengthening tasks from a confidence report.")
    parser.add_argument("--report", default=str(ROOT / "data" / "substituents" / "evidence_confidence_report.json"))
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--min-abs-residual", type=float, default=0.12)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_tasks.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_tasks.csv"))
    parser.add_argument("--registry-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--registry-csv-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.csv"))
    parser.add_argument("--reviewer", default="codex")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    tasks = build_evidence_residual_data_tasks(report, max_tasks=args.max_tasks, min_abs_residual=args.min_abs_residual)
    registry = sync_evidence_residual_task_registry(
        tasks,
        existing_registry=load_evidence_residual_task_registry(args.registry_out),
        reviewer=args.reviewer,
    )
    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"task_count": len(tasks), "tasks": tasks}, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(tasks, args.csv_out)
    write_evidence_residual_task_registry(registry, args.registry_out, csv_path=args.registry_csv_out)
    print(
        json.dumps(
            {
                "task_count": len(tasks),
                "registry_task_count": registry.get("task_count"),
                "active_task_count": registry.get("active_task_count"),
                "json_out": str(json_path.resolve()),
                "csv_out": str(Path(args.csv_out).resolve()),
                "registry_out": str(Path(args.registry_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
