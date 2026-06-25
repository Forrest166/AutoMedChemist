from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_review_board import build_candidate_review_board, write_candidate_review_board  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local candidate review board with filters and ledger status.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--packet-json", default=None)
    parser.add_argument("--ledger-json", default=None)
    parser.add_argument("--site-class", default="")
    parser.add_argument("--review-bucket", default="")
    parser.add_argument("--review-status", default="")
    parser.add_argument("--local-review-status", default="")
    parser.add_argument("--risk-bucket", default="")
    parser.add_argument("--focused-max-rows", type=int, default=80)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--focused-csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_review_board.md"))
    args = parser.parse_args()
    report = build_candidate_review_board(
        root=args.root,
        project_name=args.project_name,
        packet_json=args.packet_json,
        ledger_json=args.ledger_json,
        site_class=args.site_class,
        review_bucket=args.review_bucket,
        review_status=args.review_status,
        local_review_status=args.local_review_status,
        risk_bucket=args.risk_bucket,
        focused_max_rows=args.focused_max_rows,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_review_board.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_review_board.csv")
    focused_csv_out = args.focused_csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_review_board_focused.csv")
    write_candidate_review_board(report, json_path=json_out, csv_path=csv_out, focused_csv_path=focused_csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "filtered_row_count": report.get("filtered_row_count"),
                "focused_row_count": report.get("focused_row_count"),
                "pending_local_review_count": report.get("pending_local_review_count"),
                "json_out": str(Path(json_out).resolve()),
                "focused_csv_out": str(Path(focused_csv_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
