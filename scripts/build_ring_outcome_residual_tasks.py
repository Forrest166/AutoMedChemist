from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_confidence import (  # noqa: E402
    DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    load_evidence_residual_task_registry,
    write_evidence_residual_task_registry,
)
from localmedchem.ring_outcome_tasks import (  # noqa: E402
    DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    DEFAULT_RING_OUTCOME_TASK_CSV_PATH,
    DEFAULT_RING_OUTCOME_TASK_REPORT_PATH,
    build_ring_outcome_residual_tasks,
    merge_ring_outcome_tasks_into_registry,
    write_ring_outcome_residual_tasks,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create residual measurement tasks for low-sample ring outcome overlay contexts.")
    parser.add_argument("--overlay", default=str(ROOT / DEFAULT_RING_OUTCOME_OVERLAY_PATH))
    parser.add_argument("--json-out", default=str(ROOT / DEFAULT_RING_OUTCOME_TASK_REPORT_PATH))
    parser.add_argument("--csv-out", default=str(ROOT / DEFAULT_RING_OUTCOME_TASK_CSV_PATH))
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--sync-registry", action="store_true")
    parser.add_argument("--registry", default=str(ROOT / DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH))
    parser.add_argument("--registry-csv-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.csv"))
    args = parser.parse_args()

    report = build_ring_outcome_residual_tasks(args.overlay, max_tasks=args.max_tasks)
    write_ring_outcome_residual_tasks(report, json_path=args.json_out, csv_path=args.csv_out)
    registry_summary = {}
    if args.sync_registry:
        registry = merge_ring_outcome_tasks_into_registry(
            report,
            existing_registry=load_evidence_residual_task_registry(args.registry),
            reviewer="ring_outcome_tasks_script",
        )
        write_evidence_residual_task_registry(registry, args.registry, csv_path=args.registry_csv_out)
        registry_summary = {
            "registry_task_count": registry.get("task_count"),
            "registry_active_task_count": registry.get("active_task_count"),
            "registry_status_counts": registry.get("status_counts"),
        }
    print(
        json.dumps(
            {
                "task_count": report.get("task_count"),
                "priority_counts": report.get("priority_counts"),
                **registry_summary,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
