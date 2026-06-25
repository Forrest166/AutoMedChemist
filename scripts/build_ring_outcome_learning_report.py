from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_learning import (  # noqa: E402
    build_ring_outcome_learning_report,
    write_ring_outcome_learning_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize assay outcomes for ring and ring+R-group enumeration contexts.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--min-group-outcomes", type=int, default=2)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_learning_report.csv"))
    args = parser.parse_args()

    report = build_ring_outcome_learning_report(
        db_path=args.db,
        project_name=args.project_name or None,
        min_group_outcomes=args.min_group_outcomes,
    )
    write_ring_outcome_learning_report(report, json_path=args.json_out, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "ring_candidate_count": report.get("ring_candidate_count"),
                "observed_outcome_count": report.get("observed_outcome_count"),
                "group_count": report.get("group_count"),
                "json_out": str(Path(args.json_out).resolve()),
                "csv_out": str(Path(args.csv_out).resolve()) if args.csv_out else None,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
