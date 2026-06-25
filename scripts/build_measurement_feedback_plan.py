from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.measurement_feedback_plan import build_measurement_feedback_plan, write_measurement_feedback_plan  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build measurement feedback plan from candidate evidence value and analog-series gaps.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.csv"))
    parser.add_argument("--template-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_results_template.csv"))
    parser.add_argument("--max-rows", type=int, default=48)
    args = parser.parse_args()

    report = build_measurement_feedback_plan(root=args.root, project_name=args.project_name or None, max_rows=args.max_rows)
    write_measurement_feedback_plan(report, args.output, csv_path=args.csv_out, template_path=args.template_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "high_priority_count": report.get("high_priority_count"),
                "candidate_row_count": report.get("candidate_row_count"),
                "series_row_count": report.get("series_row_count"),
                "measurement_type_counts": report.get("measurement_type_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
