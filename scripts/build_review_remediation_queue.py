from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.review_remediation_queue import build_review_remediation_queue, write_review_remediation_queue  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local review remediation queue.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--closure-ledger", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/review_remediation_queue.md"))
    args = parser.parse_args()
    report = build_review_remediation_queue(root=args.root, project_name=args.project_name, closure_ledger_path=args.closure_ledger)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "review_remediation_queue.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "review_remediation_queue.csv")
    write_review_remediation_queue(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    ledger_path = Path(args.closure_ledger) if args.closure_ledger else ROOT / "data" / "projects" / args.project_name / "review_remediation_closure_ledger.csv"
    if not ledger_path.exists():
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["task_id", "closure_status", "closure_reason", "closure_note", "closed_by", "closed_at", "evidence_link"])
            writer.writeheader()
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "open_count": report.get("open_count"),
                "closed_count": report.get("closed_count"),
                "closure_event_count": report.get("closure_event_count"),
                "high_priority_count": report.get("high_priority_count"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
