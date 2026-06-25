from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.measurement_feedback_plan import (  # noqa: E402
    build_measurement_gap_exact_result_intake,
    write_measurement_gap_exact_result_intake,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build exact-endpoint result intake package for measurement gap closure rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--gap-closure", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.json"))
    parser.add_argument("--plan-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.json"))
    parser.add_argument("--template-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_gap_exact_results_template.csv"))
    parser.add_argument("--results", default="")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "measurement_gap_exact_result_intake.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_gap_exact_result_intake.csv"))
    args = parser.parse_args()
    report = build_measurement_gap_exact_result_intake(
        root=args.root,
        project_name=args.project_name or None,
        gap_closure_path=args.gap_closure,
        plan_path=args.plan_path,
        template_path=args.template_out,
        results_path=args.results or None,
    )
    write_measurement_gap_exact_result_intake(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "template_row_count": report.get("template_row_count"),
                "importable_exact_result_count": report.get("importable_exact_result_count"),
                "pending_exact_result_count": report.get("pending_exact_result_count"),
                "pending_measurement_plan_ids": report.get("pending_measurement_plan_ids"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
