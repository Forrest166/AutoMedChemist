from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.prospective import (  # noqa: E402
    build_experiment_plan,
    build_feedback_control_report,
    save_feedback_control_report,
    write_experiment_plan_csv,
)
from localmedchem.experiment_tracking import upsert_experiment_plan_rows  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a candidate assay plan from feedback-control signals.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--min-feedback", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--endpoint", action="append", default=[])
    parser.add_argument("--control-report-out", default=str(ROOT / "data" / "projects" / "demo" / "feedback_control_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "experiment_plan.csv"))
    parser.add_argument("--skip-db-write", action="store_true")
    args = parser.parse_args()

    report = build_feedback_control_report(
        db_path=args.db_path,
        project_name=args.project_name,
        min_feedback=args.min_feedback,
        next_experiment_limit=max(args.batch_size * 2, args.batch_size),
    )
    save_feedback_control_report(
        report,
        output_path=args.control_report_out,
        db_path=None if args.skip_db_write else args.db_path,
    )
    plan = build_experiment_plan(
        report,
        batch_size=args.batch_size,
        endpoint_groups=args.endpoint,
    )
    write_experiment_plan_csv(plan, args.csv_out)
    plan_db_report = {"upserted_count": 0}
    if not args.skip_db_write:
        plan_db_report = upsert_experiment_plan_rows(plan, db_path=args.db_path, source_path=str(Path(args.csv_out).resolve()))
    print(
        json.dumps(
            {
                "project_name": args.project_name,
                "plan_count": len(plan),
                "plan_db": plan_db_report,
                "csv_out": str(Path(args.csv_out).resolve()),
                "control_report_out": str(Path(args.control_report_out).resolve()),
                "endpoint_filters": args.endpoint,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
