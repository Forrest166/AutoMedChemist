from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.measurement_feedback_plan import (  # noqa: E402
    MEASUREMENT_GAP_DECISIONS,
    review_measurement_feedback_gap_closure,
    write_measurement_feedback_gap_closure,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record manual decisions for measurement feedback gap closure rows.")
    parser.add_argument("--gap-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.json"))
    parser.add_argument("--plan-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.csv"))
    parser.add_argument("--measurement-plan-id", action="append", default=[])
    parser.add_argument("--all", action="store_true", help="Apply the decision to all current gap rows.")
    parser.add_argument("--decision", required=True, choices=sorted(MEASUREMENT_GAP_DECISIONS))
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    ids = [] if args.all else args.measurement_plan_id
    report = review_measurement_feedback_gap_closure(
        gap_path=args.gap_path,
        plan_path=args.plan_path,
        measurement_plan_ids=ids,
        decision=args.decision,
        reviewer=args.reviewer or None,
        note=args.note or None,
    )
    write_measurement_feedback_gap_closure(report, args.gap_path, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "open_gap_count": report.get("open_gap_count"),
                "decision_recorded_count": report.get("decision_recorded_count"),
                "pending_exact_measurement_count": report.get("pending_exact_measurement_count"),
                "last_reviewed_count": report.get("last_reviewed_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
