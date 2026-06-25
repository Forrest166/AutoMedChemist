from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_memory_review_queue import (  # noqa: E402
    PROJECT_MEMORY_OPERATOR_STATUSES,
    apply_project_memory_review_batch,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a batch operator status update to Project Memory review queue rows.")
    parser.add_argument("--queue-path", default=str(ROOT / "data" / "projects" / "demo" / "project_memory_review_queue.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "project_memory_review_queue.csv"))
    parser.add_argument("--review-item-id", action="append", default=[])
    parser.add_argument("--review-lane", default="")
    parser.add_argument("--current-status", default="")
    parser.add_argument("--operator-status", required=True, choices=sorted(PROJECT_MEMORY_OPERATOR_STATUSES))
    parser.add_argument("--assigned-to", default="")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--note", default="")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    report = apply_project_memory_review_batch(
        queue_path=args.queue_path,
        csv_path=args.csv_out,
        review_item_ids=args.review_item_id,
        review_lane=args.review_lane or None,
        current_operator_status=args.current_status or None,
        operator_status=args.operator_status,
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
                "operator_status": report.get("operator_status"),
                "review_lane": report.get("review_lane"),
                "open_operator_item_count": report.get("open_operator_item_count"),
                "review_item_ids": report.get("review_item_ids"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
