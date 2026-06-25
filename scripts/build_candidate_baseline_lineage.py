from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_baseline_lineage import build_candidate_baseline_lineage, write_candidate_baseline_lineage  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate baseline lineage compare across local baselines.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--base-baseline-id", default="")
    parser.add_argument("--head-baseline-id", default="")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_baseline_lineage.md"))
    args = parser.parse_args()
    report = build_candidate_baseline_lineage(
        root=args.root,
        project_name=args.project_name,
        base_baseline_id=args.base_baseline_id,
        head_baseline_id=args.head_baseline_id,
        candidates_csv=args.candidates_csv,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_baseline_lineage.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_baseline_lineage.csv")
    write_candidate_baseline_lineage(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "entered_count": report.get("entered_count"),
                "exited_count": report.get("exited_count"),
                "changed_count": report.get("changed_count"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
