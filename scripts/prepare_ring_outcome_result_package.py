from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_readiness import (  # noqa: E402
    build_ring_outcome_result_package,
    write_ring_outcome_result_package,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a production-named ring outcome result intake package.")
    parser.add_argument("--plan-path", default=str(ROOT / "data/projects/demo/ring_outcome_experiment_plan.csv"))
    parser.add_argument("--output-dir", default=str(ROOT / "data/projects/demo/ring_outcome_result_drops"))
    parser.add_argument("--result-csv", default=str(ROOT / "data/projects/demo/ring_outcome_result_drops/production_ring_outcome_results_pending.csv"))
    parser.add_argument("--json-out", default=str(ROOT / "data/projects/demo/ring_outcome_result_package.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/projects/demo/ring_outcome_result_package.csv"))
    parser.add_argument("--overwrite", action="store_true", help="Rewrite the result CSV package. Default preserves filled packages.")
    parser.add_argument("--fail-on-validation-error", action="store_true")
    args = parser.parse_args()

    report = build_ring_outcome_result_package(
        plan_path=args.plan_path,
        output_dir=args.output_dir,
        result_csv=args.result_csv,
        overwrite=args.overwrite,
    )
    write_ring_outcome_result_package(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_validation_error and report.get("validation_error_count"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
