from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.sandbox_score_delta_review import (  # noqa: E402
    build_sandbox_score_delta_review_packet,
    write_sandbox_score_delta_review_packet,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an operator review packet for staged-feed sandbox score deltas.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out")
    parser.add_argument("--csv-out")
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/sandbox_score_delta_review_packet.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()
    report = build_sandbox_score_delta_review_packet(root=args.root, project_name=args.project_name)
    project_dir = Path(args.root) / "data" / "projects" / args.project_name
    json_out = args.json_out or str(project_dir / "sandbox_score_delta_review_packet.json")
    csv_out = args.csv_out or str(project_dir / "sandbox_score_delta_review_packet.csv")
    write_sandbox_score_delta_review_packet(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
