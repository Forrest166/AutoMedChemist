from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.public_sar_validation import build_public_sar_validation_report, write_public_sar_validation_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build public SAR validation mapping for project evidence tasks.")
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--plan", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_validation_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_validation_report.csv"))
    args = parser.parse_args()
    report = build_public_sar_validation_report(root=ROOT, project_name=args.project_name, plan_path=args.plan)
    write_public_sar_validation_report(report, args.output, csv_path=args.csv_out)
    summary_keys = [
        "status",
        "row_count",
        "active_context_match_count",
        "candidate_linked_count",
        "analog_series_linked_count",
        "contradiction_linked_count",
        "reference_only_count",
        "manual_review_count",
        "validation_status_counts",
        "evidence_link_status_counts",
    ]
    print(json.dumps({key: report.get(key) for key in summary_keys}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
