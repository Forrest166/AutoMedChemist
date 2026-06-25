from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.measurement_feedback_plan import build_measurement_feedback_gap_closure, write_measurement_feedback_gap_closure  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manual closure tasks for unmatched measurement feedback plan rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--plan-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.json"))
    parser.add_argument("--import-report-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.json"))
    parser.add_argument("--experiments", default=str(ROOT / "data" / "projects" / "demo" / "historical_experiment_results.csv"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.csv"))
    args = parser.parse_args()
    report = build_measurement_feedback_gap_closure(
        root=args.root,
        project_name=args.project_name or None,
        plan_path=args.plan_path,
        import_report_path=args.import_report_path,
        experiment_result_path=args.experiments,
    )
    write_measurement_feedback_gap_closure(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "open_gap_count": report.get("open_gap_count"),
                "endpoint_mismatch_count": report.get("endpoint_mismatch_count"),
                "needs_new_measurement_count": report.get("needs_new_measurement_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
