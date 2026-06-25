from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_review import (  # noqa: E402
    DEFAULT_SAMPLE_REVIEW_PATH,
    build_sample_review_coverage,
    load_sample_review_queue,
    triage_sample_review_queue,
    write_sample_review_coverage_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a conservative first-pass triage to R-group feed sample-review rows.")
    parser.add_argument("--queue", default=str(ROOT / DEFAULT_SAMPLE_REVIEW_PATH))
    parser.add_argument("--reviewer", default="coverage_triage")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--coverage-json-out", default=str(ROOT / "data" / "substituents" / "rgroup_feed_review_coverage.json"))
    parser.add_argument("--coverage-csv-out", default=str(ROOT / "data" / "substituents" / "rgroup_feed_review_coverage.csv"))
    args = parser.parse_args()

    report = triage_sample_review_queue(args.queue, reviewer=args.reviewer, write=not args.dry_run)
    rows = load_sample_review_queue(args.queue)
    coverage = build_sample_review_coverage(rows)
    if not args.dry_run:
        write_sample_review_coverage_report(coverage, json_path=args.coverage_json_out, csv_path=args.coverage_csv_out)
    print(
        json.dumps(
            {
                **report,
                "coverage_cell_count": coverage.get("coverage_cell_count"),
                "no_review_count": coverage.get("no_review_count"),
                "low_coverage_count": coverage.get("low_coverage_count"),
                "covered_count": coverage.get("covered_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
