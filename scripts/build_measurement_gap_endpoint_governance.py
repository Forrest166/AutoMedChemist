from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.measurement_gap_endpoint_governance import (  # noqa: E402
    build_measurement_gap_endpoint_governance,
    write_measurement_gap_endpoint_governance,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build non-experimental strict endpoint governance for measurement gaps.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--gap-closure", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_gap_closure.json"))
    parser.add_argument("--exact-intake", default=str(ROOT / "data" / "projects" / "demo" / "measurement_gap_exact_result_intake.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "measurement_gap_endpoint_governance.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_gap_endpoint_governance.csv"))
    args = parser.parse_args()
    report = build_measurement_gap_endpoint_governance(
        root=args.root,
        project_name=args.project_name or None,
        gap_closure_path=args.gap_closure,
        exact_intake_path=args.exact_intake,
    )
    write_measurement_gap_endpoint_governance(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "strict_exact_pending_count": report.get("strict_exact_pending_count"),
                "cross_endpoint_blocked_count": report.get("cross_endpoint_blocked_count"),
                "blocked_cross_endpoint_pair_count": report.get("blocked_cross_endpoint_pair_count"),
                "mode": report.get("mode"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
