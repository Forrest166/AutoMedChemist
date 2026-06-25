from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_value_scoring import build_evidence_value_report, write_evidence_value_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate evidence-value scoring report.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_report.csv"))
    args = parser.parse_args()

    report = build_evidence_value_report(root=args.root, project_name=args.project_name or None)
    write_evidence_value_report(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "high_value_count": report.get("high_value_count"),
                "contradiction_resolution_count": report.get("contradiction_resolution_count"),
                "evidence_gap_measurement_count": report.get("evidence_gap_measurement_count"),
                "tier_counts": report.get("tier_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
