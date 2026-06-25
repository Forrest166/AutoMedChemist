from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_evidence_priority import (  # noqa: E402
    build_candidate_evidence_priority_report,
    write_candidate_evidence_priority_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate-level evidence priority view from SAR, A/B, queue, and series evidence.")
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--queue", default="")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "candidate_evidence_priority_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "candidate_evidence_priority_report.csv"))
    args = parser.parse_args()
    report = build_candidate_evidence_priority_report(
        root=ROOT,
        project_name=args.project_name or None,
        queue_path=args.queue or None,
    )
    write_candidate_evidence_priority_report(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in [
                    "status",
                    "row_count",
                    "high_priority_count",
                    "sar_linked_count",
                    "material_diff_linked_count",
                    "sufficiency_gap_count",
                    "contradiction_linked_count",
                    "priority_tier_counts",
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
