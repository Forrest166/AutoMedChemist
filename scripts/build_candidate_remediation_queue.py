from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_remediation_queue import (  # noqa: E402
    build_candidate_remediation_queue,
    write_candidate_remediation_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local-only candidate remediation queue rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--due-days", type=int, default=7)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_remediation_queue.md"))
    args = parser.parse_args()
    report = build_candidate_remediation_queue(root=args.root, project_name=args.project_name, due_days=args.due_days)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_remediation_queue.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_remediation_queue.csv")
    write_candidate_remediation_queue(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(json.dumps({k: report.get(k) for k in ["status", "mode", "row_count", "open_count", "high_count", "medium_count"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
