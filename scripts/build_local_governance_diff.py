from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.governance_diff import build_local_governance_diff, write_local_governance_diff  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local candidate/scoring/profile/policy governance diff.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--baseline-dir", default=None)
    parser.add_argument("--create-baseline", action="store_true")
    parser.add_argument("--baseline-name", default=None)
    parser.add_argument("--base-baseline", default=None)
    parser.add_argument("--no-update-snapshot", action="store_true")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/local_governance_diff_report.md"))
    args = parser.parse_args()
    report = build_local_governance_diff(
        root=args.root,
        project_name=args.project_name,
        candidates_csv=args.candidates_csv,
        snapshot_dir=args.snapshot_dir,
        baseline_dir=args.baseline_dir,
        create_baseline=args.create_baseline,
        baseline_name=args.baseline_name,
        base_baseline=args.base_baseline,
        update_snapshot=not args.no_update_snapshot,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "local_governance_diff_report.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "local_governance_diff_report.csv")
    write_local_governance_diff(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "changed_candidate_count": report.get("changed_candidate_count"),
                "added_candidate_count": report.get("added_candidate_count"),
                "removed_candidate_count": report.get("removed_candidate_count"),
                "baseline_name": report.get("baseline_name") or report.get("base_baseline"),
                "baseline_count": report.get("baseline_count"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
