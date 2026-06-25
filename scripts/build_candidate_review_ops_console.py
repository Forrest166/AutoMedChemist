from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_review_ops_console import build_candidate_review_ops_console, write_candidate_review_ops_console  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local candidate review operations console.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "candidate_review_ops_console.md"))
    args = parser.parse_args()
    root = Path(args.root)
    report = build_candidate_review_ops_console(root=root, project_name=args.project_name)
    json_out = args.json_out or str(root / "data" / "projects" / args.project_name / "candidate_review_ops_console.json")
    csv_out = args.csv_out or str(root / "data" / "projects" / args.project_name / "candidate_review_ops_console.csv")
    write_candidate_review_ops_console(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "open_task_count": report.get("open_task_count"),
                "overdue_task_count": report.get("overdue_task_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
