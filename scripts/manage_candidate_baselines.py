from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_baseline_manager import (  # noqa: E402
    archive_candidate_baseline,
    build_candidate_baseline_manager,
    write_candidate_baseline_manager,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or update the local candidate baseline manager.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--archive-baseline-id", default="")
    parser.add_argument("--reviewer", default="local_reviewer")
    parser.add_argument("--note", default="")
    parser.add_argument("--stale-days", type=int, default=30)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_baseline_manager.md"))
    args = parser.parse_args()
    archive = {}
    if args.archive_baseline_id:
        archive = archive_candidate_baseline(
            root=args.root,
            project_name=args.project_name,
            baseline_id=args.archive_baseline_id,
            reviewer=args.reviewer,
            note=args.note,
        )
    report = build_candidate_baseline_manager(root=args.root, project_name=args.project_name, stale_days=args.stale_days)
    if archive:
        report["archive_update"] = archive
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_baseline_manager.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_baseline_manager.csv")
    write_candidate_baseline_manager(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(json.dumps({"status": report.get("status"), "baseline_count": report.get("baseline_count"), "archive_review_count": report.get("archive_review_count"), "json_out": str(Path(json_out).resolve())}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
