from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.staged_feed_sandbox_scoring import build_staged_feed_sandbox_scoring, write_staged_feed_sandbox_scoring  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview staged feed impact on candidate scoring without production writes.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--max-candidates", type=int, default=25)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/staged_feed_sandbox_scoring.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_staged_feed_sandbox_scoring(
        root=args.root,
        project_name=args.project_name,
        max_candidates=args.max_candidates,
    )
    project_dir = ROOT / "data" / "projects" / args.project_name
    json_out = args.json_out or str(project_dir / "staged_feed_sandbox_scoring.json")
    csv_out = args.csv_out or str(project_dir / "staged_feed_sandbox_scoring.csv")
    write_staged_feed_sandbox_scoring(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "candidate_count": report.get("candidate_count"),
                "staged_row_count": report.get("staged_row_count"),
                "candidate_with_staged_match_count": report.get("candidate_with_staged_match_count"),
                "production_scoring_affected": report.get("production_scoring_affected"),
                "json_out": json_out,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
