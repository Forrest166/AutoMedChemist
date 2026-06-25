from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_memory_review_queue import (  # noqa: E402
    build_project_memory_review_dashboard,
    write_project_memory_review_dashboard,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Project Memory review queue dashboard.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--queue-path", default=str(ROOT / "data" / "projects" / "demo" / "project_memory_review_queue.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "project_memory_review_dashboard.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "project_memory_review_dashboard.csv"))
    args = parser.parse_args()
    report = build_project_memory_review_dashboard(
        root=args.root,
        project_name=args.project_name or None,
        queue_path=args.queue_path,
    )
    write_project_memory_review_dashboard(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "open_like_count": report.get("open_like_count"),
                "lane_row_count": report.get("lane_row_count"),
                "mode": report.get("mode"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
