from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_drilldown import build_candidate_drilldown_packet, write_candidate_drilldown_packet  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a candidate drill-down packet linking candidates, images, review, and governance.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--visual-path", default=None)
    parser.add_argument("--review-path", default=None)
    parser.add_argument("--governance-path", default=None)
    parser.add_argument("--board-path", default=None)
    parser.add_argument("--max-rows", type=int, default=120)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_drilldown_packet.md"))
    args = parser.parse_args()
    report = build_candidate_drilldown_packet(
        root=args.root,
        project_name=args.project_name,
        candidates_csv=args.candidates_csv,
        visual_path=args.visual_path,
        review_path=args.review_path,
        governance_path=args.governance_path,
        board_path=args.board_path,
        max_rows=args.max_rows,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_drilldown_packet.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_drilldown_packet.csv")
    write_candidate_drilldown_packet(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "linked_visual_rows": report.get("linked_visual_rows"),
                "linked_review_rows": report.get("linked_review_rows"),
                "linked_board_rows": report.get("linked_board_rows"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
