from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_review_analytics import build_candidate_review_analytics, write_candidate_review_analytics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local candidate review-board analytics.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--board-path", default=None)
    parser.add_argument("--ledger-path", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_review_analytics.md"))
    args = parser.parse_args()
    report = build_candidate_review_analytics(
        root=args.root,
        project_name=args.project_name,
        board_path=args.board_path,
        ledger_path=args.ledger_path,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_review_analytics.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_review_analytics.csv")
    write_candidate_review_analytics(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "pending_backlog_count": report.get("pending_backlog_count"),
                "card_count": len(report.get("cards") or []),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
