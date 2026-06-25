from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.priority_queue import (  # noqa: E402
    build_bulk_next_design_queue_decisions,
    build_next_design_queue_decision_quality_report,
    list_next_design_queue_decision_events,
    load_next_design_queue_decisions,
    save_next_design_queue_decisions,
    write_next_design_queue_decision_quality_report,
)


def _load_queue_rows(path: str | Path | None) -> list[dict]:
    if path is None:
        return []
    queue_path = Path(path)
    if not queue_path.exists():
        return []
    if queue_path.suffix.lower() == ".json":
        data = json.loads(queue_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
        return [dict(row) for row in data.get("queue") or data.get("candidates") or [] if isinstance(row, dict)]
    with queue_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist and evaluate next-design queue reviewer decisions.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--decisions", default=None, help="CSV/JSON queue decision rows to save into SQLite.")
    parser.add_argument("--queue", default=None, help="Queue JSON/CSV used to generate bulk reviewer decisions.")
    parser.add_argument("--bulk-decision", choices=["accepted", "deferred", "retired", "needs_review"], default=None)
    parser.add_argument("--owner", default="")
    parser.add_argument("--review-note", default="")
    parser.add_argument("--endpoint-group", default=None)
    parser.add_argument("--recommendation-action", default=None)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--bulk-out", default=None)
    parser.add_argument("--save-bulk", action="store_true")
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "next_design_queue_decision_quality.json"))
    parser.add_argument("--list-events", action="store_true")
    args = parser.parse_args()

    saved = {"saved_count": 0, "decision_counts": {}}
    if args.decisions:
        decisions = load_next_design_queue_decisions(args.decisions)
        saved = save_next_design_queue_decisions(decisions, db_path=args.db_path, source_path=args.decisions)

    bulk_report = {"generated_count": 0, "saved": {"saved_count": 0, "decision_counts": {}}}
    if args.bulk_decision:
        queue_rows = _load_queue_rows(args.queue)
        bulk_decisions = build_bulk_next_design_queue_decisions(
            queue_rows,
            args.bulk_decision,
            owner=args.owner,
            review_note=args.review_note,
            endpoint_group=args.endpoint_group,
            recommendation_action=args.recommendation_action,
            max_rows=args.max_rows,
        )
        if args.bulk_out:
            out = Path(args.bulk_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"decisions": bulk_decisions}, indent=2, sort_keys=True), encoding="utf-8")
        if args.save_bulk:
            bulk_report["saved"] = save_next_design_queue_decisions(bulk_decisions, db_path=args.db_path, source_path=args.queue)
        bulk_report.update(
            {
                "generated_count": len(bulk_decisions),
                "queue_path": args.queue,
                "bulk_decision": args.bulk_decision,
                "endpoint_group": args.endpoint_group,
                "recommendation_action": args.recommendation_action,
                "bulk_out": args.bulk_out,
            }
        )

    report = build_next_design_queue_decision_quality_report(
        db_path=args.db_path,
        project_name=args.project_name,
        limit=args.limit,
    )
    report["saved_decisions"] = saved
    report["bulk_decisions"] = bulk_report
    if args.list_events:
        report["decision_events"] = list_next_design_queue_decision_events(
            db_path=args.db_path,
            project_name=args.project_name,
            limit=args.limit,
        )
    write_next_design_queue_decision_quality_report(report, args.json_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
