from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.review_closure_filter_views import build_review_closure_filter_views, write_review_closure_filter_views  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build filtered closure-workbench views for native batch review.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/review_closure_filter_views.md"))
    args = parser.parse_args()

    report = build_review_closure_filter_views(root=args.root, project_name=args.project_name, selected_task_ids=args.task_id)
    project_dir = ROOT / "data" / "projects" / args.project_name
    json_out = args.json_out or str(project_dir / "review_closure_filter_views.json")
    csv_out = args.csv_out or str(project_dir / "review_closure_filter_views.csv")
    write_review_closure_filter_views(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "task_row_count": report.get("task_row_count"),
                "selected_task_count": report.get("selected_task_count"),
                "json_out": json_out,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
