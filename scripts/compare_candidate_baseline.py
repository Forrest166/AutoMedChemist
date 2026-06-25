from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_baselines import compare_candidate_baseline, write_candidate_baseline_compare  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare current candidates against a named local candidate-set baseline.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--baseline-id", default="local_release_baseline")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--create-if-missing", action="store_true")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_baseline_compare.md"))
    args = parser.parse_args()
    report = compare_candidate_baseline(
        root=args.root,
        project_name=args.project_name,
        baseline_id=args.baseline_id,
        candidates_csv=args.candidates_csv,
        create_if_missing=args.create_if_missing,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_baseline_compare.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_baseline_compare.csv")
    write_candidate_baseline_compare(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "baseline_id": report.get("baseline_id"),
                "row_count": report.get("row_count"),
                "changed_candidate_count": report.get("changed_candidate_count"),
                "added_candidate_count": report.get("added_candidate_count"),
                "removed_candidate_count": report.get("removed_candidate_count"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
