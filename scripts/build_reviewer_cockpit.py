from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.reviewer_cockpit import build_reviewer_cockpit, write_reviewer_cockpit  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a unified local reviewer cockpit from reason, closure, and remediation queues.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/reviewer_cockpit.md"))
    args = parser.parse_args()
    root = Path(args.root)
    project_dir = root / "data" / "projects" / args.project_name
    report = build_reviewer_cockpit(root=root, project_name=args.project_name)
    write_reviewer_cockpit(
        report,
        json_path=args.json_out or project_dir / "reviewer_cockpit.json",
        csv_path=args.csv_out or project_dir / "reviewer_cockpit.csv",
        markdown_path=args.markdown_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "lane_counts": report.get("lane_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
