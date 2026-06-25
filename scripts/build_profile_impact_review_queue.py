from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_impact_review import build_profile_impact_review_queue, write_profile_impact_review_queue  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build non-experimental profile-impact review queue from active policy compare.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--active-compare", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_active_compare.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_impact_review_queue.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_impact_review_queue.csv"))
    args = parser.parse_args()
    report = build_profile_impact_review_queue(
        root=args.root,
        project_name=args.project_name or None,
        active_compare_path=args.active_compare,
        existing_review_path=args.output,
    )
    write_profile_impact_review_queue(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "open_review_count": report.get("open_review_count"),
                "severity_counts": report.get("severity_counts"),
                "mode": report.get("mode"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
