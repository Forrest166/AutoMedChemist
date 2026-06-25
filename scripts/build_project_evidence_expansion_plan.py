from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_evidence_expansion_plan import (  # noqa: E402
    build_project_evidence_expansion_plan,
    write_project_evidence_expansion_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build project evidence expansion tasks for assay/outcome, MMP/SAR, scaffold, and ring evidence only.")
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.csv"))
    parser.add_argument("--max-public-signal-tasks", type=int, default=12)
    args = parser.parse_args()

    report = build_project_evidence_expansion_plan(
        root=ROOT,
        project_name=args.project_name or None,
        max_public_signal_tasks=args.max_public_signal_tasks,
    )
    write_project_evidence_expansion_plan(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "task_count": report.get("task_count"),
                "task_type_counts": report.get("task_type_counts"),
                "priority_counts": report.get("priority_counts"),
                "output": str(Path(args.output).resolve()),
                "csv_out": str(Path(args.csv_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
