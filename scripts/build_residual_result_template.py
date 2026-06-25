from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.experiment_tracking import read_experiment_plan_csv, write_experiment_result_template  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a result-import CSV template from residual experiment plan rows.")
    parser.add_argument("--plan-csv", default=str(ROOT / "data" / "projects" / "demo" / "residual_experiment_plan.csv"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "residual_experiment_results_template.csv"))
    parser.add_argument("--keep-existing-results", action="store_true")
    args = parser.parse_args()

    plan_rows = read_experiment_plan_csv(args.plan_csv)
    rows = write_experiment_result_template(plan_rows, args.output, blank_results=not args.keep_existing_results)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "plan_csv": str(Path(args.plan_csv).resolve()),
                "row_count": len(rows),
                "field_count": len(rows[0]) if rows else 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
