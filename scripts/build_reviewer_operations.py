from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.reviewer_operations import build_reviewer_operations, write_reviewer_operations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reviewer operations report for local candidate review board.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--stale-days", type=int, default=7)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/reviewer_operations.md"))
    args = parser.parse_args()
    report = build_reviewer_operations(root=args.root, project_name=args.project_name, stale_days=args.stale_days)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "reviewer_operations.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "reviewer_operations.csv")
    write_reviewer_operations(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "pending_overdue_count": report.get("pending_overdue_count"),
                "workload_pending_count": report.get("workload_pending_count"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
