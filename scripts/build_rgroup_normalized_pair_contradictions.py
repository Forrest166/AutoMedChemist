from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_pair_contradictions import (  # noqa: E402
    DEFAULT_CONTRADICTION_CSV_PATH,
    DEFAULT_CONTRADICTION_REPORT_PATH,
    DEFAULT_CONTRADICTION_REVIEW_PATH,
    DEFAULT_DB_PATH,
    build_rgroup_normalized_pair_contradiction_report,
    write_rgroup_normalized_pair_contradiction_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build review queue for governed R-group feed rows that conflict with reverse normalized-pair evidence.")
    parser.add_argument("--db", default=str(ROOT / DEFAULT_DB_PATH))
    parser.add_argument("--json-out", default=str(ROOT / DEFAULT_CONTRADICTION_REPORT_PATH))
    parser.add_argument("--csv-out", default=str(ROOT / DEFAULT_CONTRADICTION_CSV_PATH))
    parser.add_argument("--review", default=str(ROOT / DEFAULT_CONTRADICTION_REVIEW_PATH))
    parser.add_argument("--min-reverse-aggregate-weight", type=int, default=10)
    parser.add_argument("--min-reverse-source-records", type=int, default=1)
    parser.add_argument("--high-weight-threshold", type=int, default=50)
    parser.add_argument("--fail-on-blocking", action="store_true")
    args = parser.parse_args()

    report = build_rgroup_normalized_pair_contradiction_report(
        db_path=args.db,
        review_path=args.review,
        min_reverse_aggregate_weight=args.min_reverse_aggregate_weight,
        min_reverse_source_records=args.min_reverse_source_records,
        high_weight_threshold=args.high_weight_threshold,
    )
    write_rgroup_normalized_pair_contradiction_report(report, args.json_out, csv_path=args.csv_out)
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2, sort_keys=True))
    if args.fail_on_blocking and int(report.get("blocking_count") or 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
