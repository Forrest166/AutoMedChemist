from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.experiment_tracking import (  # noqa: E402
    import_experiment_results_csv,
    summarize_experiment_plans,
    write_experiment_tracking_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import experiment-plan status updates and completed assay/ADME results.")
    parser.add_argument("--csv", required=True, help="CSV generated from experiment_plan.csv with status/result columns filled in.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--no-feedback", action="store_true", help="Track status/events without writing completed results into project_feedback.")
    parser.add_argument("--residual-task-registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "projects" / "demo" / "experiment_tracking_report.json"))
    args = parser.parse_args()

    import_report = import_experiment_results_csv(
        args.csv,
        db_path=args.db,
        update_feedback=not args.no_feedback,
        residual_task_registry_path=args.residual_task_registry,
    )
    summary = summarize_experiment_plans(db_path=args.db, project_name=args.project_name)
    report = {"import": import_report, "summary": summary}
    write_experiment_tracking_report(report, args.report_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
