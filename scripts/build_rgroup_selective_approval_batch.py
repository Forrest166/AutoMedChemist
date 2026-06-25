from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_selective_approval_batch import (  # noqa: E402
    build_rgroup_selective_approval_batch,
    write_rgroup_selective_approval_batch,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a governed positive-control R-group promotion approval batch.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--min-confidence", type=float, default=0.8)
    parser.add_argument("--apply-decisions", action="store_true")
    parser.add_argument("--reviewer", default="production_ci_selective_positive_control")
    parser.add_argument("--decisions-csv", default=str(ROOT / "data/substituents/rgroup_promotion_approval_decisions.csv"))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_selective_approval_batch.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_selective_approval_batch.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_selective_approval_batch.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_rgroup_selective_approval_batch(
        root=args.root,
        project_name=args.project_name,
        min_confidence=args.min_confidence,
        apply_decisions=args.apply_decisions,
        reviewer=args.reviewer,
        decisions_csv=args.decisions_csv,
    )
    write_rgroup_selective_approval_batch(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "candidate_count": report.get("candidate_count"),
                "positive_control_approved_count": report.get("positive_control_approved_count"),
                "holdout_count": report.get("holdout_count"),
                "production_promotion_allowed": report.get("production_promotion_allowed"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
