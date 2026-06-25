from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.measurement_feedback_plan import (  # noqa: E402
    import_measurement_feedback_results_rows,
    read_measurement_feedback_result_rows_csv,
    write_measurement_feedback_import_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and import real measurement feedback result rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--input", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_results_template.csv"))
    parser.add_argument("--plan-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.json"))
    parser.add_argument("--evidence-value-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_report.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.csv"))
    parser.add_argument("--reviewer", default="")
    args = parser.parse_args()

    rows = read_measurement_feedback_result_rows_csv(args.input)
    report = import_measurement_feedback_results_rows(
        rows,
        root=args.root,
        plan_path=args.plan_path,
        evidence_value_path=args.evidence_value_path,
        source_path=args.input,
        reviewer=args.reviewer or None,
    )
    write_measurement_feedback_import_report(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "importable_row_count": report.get("importable_row_count"),
                "rejected_row_count": report.get("rejected_row_count"),
                "calibration_ready_row_count": report.get("calibration_ready_row_count"),
                "plan_update_count": report.get("plan_update_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if report.get("status") == "validation_failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
