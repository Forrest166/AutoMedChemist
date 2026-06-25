from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_review_board import (  # noqa: E402
    batch_update_candidate_review_status,
    build_candidate_review_board,
    write_candidate_review_board,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch update local candidate review status.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--candidate-ids", required=True, help="Comma-separated candidate IDs.")
    parser.add_argument("--status", required=True, help="Local status such as reviewed, deferred, blocked, or needs_follow_up.")
    parser.add_argument("--reviewer-decision", default="", help="Optional decision label; defaults to --status.")
    parser.add_argument("--reviewer", default="local_reviewer")
    parser.add_argument("--note", default="")
    parser.add_argument("--ledger-json", default=None)
    parser.add_argument("--ledger-csv", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_review_board.md"))
    args = parser.parse_args()
    ids = [item.strip() for item in args.candidate_ids.split(",") if item.strip()]
    update = batch_update_candidate_review_status(
        root=args.root,
        project_name=args.project_name,
        candidate_ids=ids,
        local_review_status=args.status,
        reviewer_decision=args.reviewer_decision,
        reviewer=args.reviewer,
        review_note=args.note,
        ledger_json=args.ledger_json,
        ledger_csv=args.ledger_csv,
    )
    report = build_candidate_review_board(root=args.root, project_name=args.project_name)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_review_board.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_review_board.csv")
    focused_csv_out = str(ROOT / "data" / "projects" / args.project_name / "candidate_review_board_focused.csv")
    write_candidate_review_board(report, json_path=json_out, csv_path=csv_out, focused_csv_path=focused_csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                **update,
                "board_status": report.get("status"),
                "board_json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
