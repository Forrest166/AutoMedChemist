from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.review_closure_workbench import build_review_closure_workbench, write_review_closure_workbench  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local review closure workbench with batch groups, due policy, and audit history.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/review_closure_workbench.md"))
    args = parser.parse_args()

    report = build_review_closure_workbench(root=args.root, project_name=args.project_name)
    project_dir = ROOT / "data" / "projects" / args.project_name
    json_out = args.json_out or str(project_dir / "review_closure_workbench.json")
    csv_out = args.csv_out or str(project_dir / "review_closure_workbench.csv")
    write_review_closure_workbench(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "open_count": report.get("open_count"),
                "overdue_count": report.get("overdue_count"),
                "filtered_audit_event_count": report.get("filtered_audit_event_count"),
                "json_out": json_out,
                "csv_out": csv_out,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
