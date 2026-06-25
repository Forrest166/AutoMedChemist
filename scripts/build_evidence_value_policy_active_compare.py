from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_value_policy_active_compare import (  # noqa: E402
    build_evidence_value_policy_active_compare,
    write_evidence_value_policy_active_compare,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare active evidence-value policy against its baseline replay.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_active_compare.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_active_compare.csv"))
    args = parser.parse_args()
    report = build_evidence_value_policy_active_compare(root=args.root, project_name=args.project_name or None)
    write_evidence_value_policy_active_compare(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "max_abs_score_delta": report.get("max_abs_score_delta"),
                "max_abs_rank_delta": report.get("max_abs_rank_delta"),
                "profile_impact_review_count": report.get("profile_impact_review_count"),
                "rollback_target_policy_version": report.get("rollback_target_policy_version"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
