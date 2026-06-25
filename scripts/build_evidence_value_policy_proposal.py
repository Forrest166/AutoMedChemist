from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_value_policy_proposal import build_evidence_value_policy_proposal, write_evidence_value_policy_proposal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a versioned, review-gated evidence-value policy proposal from calibration results.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--calibration-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_calibration_report.json"))
    parser.add_argument("--rollback-compare-path", default=str(ROOT / "data" / "projects" / "demo" / "profile_rollback_snapshot_compare.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.csv"))
    parser.add_argument("--min-calibration-rows", type=int, default=3)
    args = parser.parse_args()

    report = build_evidence_value_policy_proposal(
        root=args.root,
        project_name=args.project_name or None,
        calibration_path=args.calibration_path,
        rollback_compare_path=args.rollback_compare_path,
        min_calibration_rows=args.min_calibration_rows,
    )
    write_evidence_value_policy_proposal(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "proposal_id": report.get("proposal_id"),
                "approval_status": report.get("approval_status"),
                "calibration_row_count": report.get("calibration_row_count"),
                "weight_change_count": report.get("weight_change_count"),
                "rollback_compare_status": report.get("rollback_compare_status"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
