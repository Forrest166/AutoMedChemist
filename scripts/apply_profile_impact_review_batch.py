from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_impact_review import (  # noqa: E402
    PROFILE_IMPACT_REVIEW_STATUSES,
    apply_profile_impact_review_batch,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a batch reviewer update to profile-impact review rows.")
    parser.add_argument("--review-path", default=str(ROOT / "data" / "projects" / "demo" / "profile_impact_review_queue.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_impact_review_queue.csv"))
    parser.add_argument("--review-id", action="append", default=[])
    parser.add_argument("--severity", default="")
    parser.add_argument("--current-status", default="")
    parser.add_argument("--review-status", required=True, choices=sorted(PROFILE_IMPACT_REVIEW_STATUSES))
    parser.add_argument("--assigned-to", default="")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--note", default="")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    report = apply_profile_impact_review_batch(
        review_path=args.review_path,
        csv_path=args.csv_out,
        review_ids=args.review_id,
        severity=args.severity or None,
        current_review_status=args.current_status or None,
        review_status=args.review_status,
        assigned_to=args.assigned_to or None,
        reviewer=args.reviewer or None,
        note=args.note or None,
        limit=args.limit or None,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "applied_count": report.get("applied_count"),
                "review_status": report.get("review_status"),
                "open_review_count": report.get("open_review_count"),
                "review_ids": report.get("review_ids"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
