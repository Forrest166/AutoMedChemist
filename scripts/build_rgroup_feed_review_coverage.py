from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_review import (  # noqa: E402
    DEFAULT_SAMPLE_REVIEW_COVERAGE_CSV_PATH,
    DEFAULT_SAMPLE_REVIEW_COVERAGE_PATH,
    DEFAULT_SAMPLE_REVIEW_PATH,
    build_sample_review_coverage,
    load_sample_review_queue,
    write_sample_review_coverage_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build source/class/endpoint coverage report for R-group feed sample review.")
    parser.add_argument("--queue", default=str(ROOT / DEFAULT_SAMPLE_REVIEW_PATH))
    parser.add_argument("--json-out", default=str(ROOT / DEFAULT_SAMPLE_REVIEW_COVERAGE_PATH))
    parser.add_argument("--csv-out", default=str(ROOT / DEFAULT_SAMPLE_REVIEW_COVERAGE_CSV_PATH))
    parser.add_argument("--min-reviewed-per-stratum", type=int, default=1)
    parser.add_argument(
        "--coverage-field",
        action="append",
        default=None,
        help="Coverage grouping field. Defaults to source_dataset, replacement_class, endpoint_group.",
    )
    args = parser.parse_args()

    rows = load_sample_review_queue(args.queue)
    report = build_sample_review_coverage(
        rows,
        coverage_fields=args.coverage_field,
        min_reviewed_per_stratum=args.min_reviewed_per_stratum,
    )
    write_sample_review_coverage_report(report, json_path=args.json_out, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in [
                    "review_row_count",
                    "coverage_cell_count",
                    "no_review_count",
                    "low_coverage_count",
                    "covered_count",
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
