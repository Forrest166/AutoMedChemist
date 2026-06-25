from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.baseline_lineage_compare import (  # noqa: E402
    build_baseline_lineage_compare,
    write_baseline_lineage_compare,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two candidate baselines for lineage entry/exit/change rationale.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--base-baseline-id", default=None)
    parser.add_argument("--head-baseline-id", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/baseline_lineage_compare.md"))
    args = parser.parse_args()
    report = build_baseline_lineage_compare(
        root=args.root,
        project_name=args.project_name,
        base_baseline_id=args.base_baseline_id,
        head_baseline_id=args.head_baseline_id,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_lineage_compare.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_lineage_compare.csv")
    write_baseline_lineage_compare(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "base_baseline_id": report.get("base_baseline_id"),
                "head_baseline_id": report.get("head_baseline_id"),
                "changed_candidate_count": report.get("changed_candidate_count"),
                "entered_candidate_count": report.get("entered_candidate_count"),
                "exited_candidate_count": report.get("exited_candidate_count"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
