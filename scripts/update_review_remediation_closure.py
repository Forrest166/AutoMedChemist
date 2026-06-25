from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.review_closure_workbench import build_review_closure_workbench, write_review_closure_workbench  # noqa: E402
from localmedchem.review_remediation_queue import build_review_remediation_queue, write_review_remediation_queue  # noqa: E402


FIELDS = [
    "task_id",
    "closure_status",
    "closure_reason",
    "closure_note",
    "closed_by",
    "closed_at",
    "evidence_link",
    "owner",
    "due_at",
    "event_action",
    "batch_id",
]


def _append_ledger(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser(description="Append a local closure event to the review remediation queue ledger.")
    parser.add_argument("task_id", nargs="+")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--closure-status", default="closed", choices=["open", "closed", "deferred", "accepted_risk", "duplicate", "reopened"])
    parser.add_argument("--reason", default="local_review_resolved")
    parser.add_argument("--note", default="")
    parser.add_argument("--reviewer", default="local_review_owner")
    parser.add_argument("--owner", default="")
    parser.add_argument("--due-at", default="")
    parser.add_argument("--evidence-link", default="")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--ledger", default=None)
    args = parser.parse_args()

    root = Path(args.root)
    ledger = Path(args.ledger) if args.ledger else root / "data" / "projects" / args.project_name / "review_remediation_closure_ledger.csv"
    task_ids = [str(task_id).strip() for task_id in args.task_id if str(task_id).strip()]
    batch_id = args.batch_id or f"closure_batch_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    timestamp = datetime.now(timezone.utc).isoformat()
    for task_id in task_ids:
        event = {
            "task_id": task_id,
            "closure_status": args.closure_status,
            "closure_reason": args.reason,
            "closure_note": args.note,
            "closed_by": args.reviewer,
            "closed_at": timestamp,
            "evidence_link": args.evidence_link,
            "owner": args.owner or args.reviewer,
            "due_at": args.due_at,
            "event_action": args.reason,
            "batch_id": batch_id,
        }
        _append_ledger(ledger, event)
    report = build_review_remediation_queue(root=root, project_name=args.project_name, closure_ledger_path=ledger)
    json_out = root / "data" / "projects" / args.project_name / "review_remediation_queue.json"
    csv_out = root / "data" / "projects" / args.project_name / "review_remediation_queue.csv"
    md_out = root / "docs" / "review_remediation_queue.md"
    write_review_remediation_queue(report, json_path=json_out, csv_path=csv_out, markdown_path=md_out)
    workbench = build_review_closure_workbench(root=root, project_name=args.project_name)
    write_review_closure_workbench(
        workbench,
        json_path=root / "data" / "projects" / args.project_name / "review_closure_workbench.json",
        csv_path=root / "data" / "projects" / args.project_name / "review_closure_workbench.csv",
        markdown_path=root / "docs" / "review_closure_workbench.md",
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "task_ids": task_ids,
                "task_count": len(task_ids),
                "closure_status": args.closure_status,
                "open_count": report.get("open_count"),
                "closed_count": report.get("closed_count"),
                "batch_id": batch_id,
                "ledger": str(ledger.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
