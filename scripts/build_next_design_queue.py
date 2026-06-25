from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.analog_series import build_queue_analog_series_delta, write_queue_analog_series_delta_report  # noqa: E402
from localmedchem.priority_queue import (  # noqa: E402
    build_next_design_queue,
    load_next_design_queue_decisions,
    load_next_design_queue_decisions_from_db,
    save_next_design_queue_decisions,
    write_next_design_queue,
    write_next_design_queue_decision_template,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote priority-delta rows into a reviewable next-design queue.")
    parser.add_argument("--priority-delta", default=str(ROOT / "data" / "projects" / "closed_loop" / "priority_delta_demo_learning.json"))
    parser.add_argument("--max-rows", type=int, default=24)
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "next_design_queue.csv"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "next_design_queue.json"))
    parser.add_argument("--markdown-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "next_design_queue.md"))
    parser.add_argument("--series-delta-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "queue_analog_series_delta.json"))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument(
        "--analog-series-report",
        default=str(ROOT / "data" / "projects" / "demo" / "analog_series_report.json"),
        help="Optional analog-series report used to prioritize residual-heavy series.",
    )
    parser.add_argument(
        "--queue-decisions",
        default=None,
        help="Optional CSV/JSON reviewer decisions with accepted/deferred/retired queue rows.",
    )
    parser.add_argument("--load-db-decisions", action="store_true", help="Also apply saved SQLite queue decision audit events.")
    parser.add_argument("--save-decisions-db", action="store_true", help="Persist supplied --queue-decisions rows into SQLite audit events.")
    parser.add_argument(
        "--write-decision-template",
        default=None,
        help="Write a queue decision CSV template after building the queue.",
    )
    parser.add_argument(
        "--decision-packet",
        action="append",
        default=[str(ROOT / "data" / "projects" / "demo" / "medchem_decision_packet.json")]
        if (ROOT / "data" / "projects" / "demo" / "medchem_decision_packet.json").exists()
        else [],
        help="Decision packet JSON to use for evidence-uncertainty queue prioritization. May be repeated.",
    )
    parser.add_argument("--skip-series-delta", action="store_true")
    args = parser.parse_args()

    report = json.loads(Path(args.priority_delta).read_text(encoding="utf-8"))
    decision_packets = []
    for packet_path in args.decision_packet or []:
        path = Path(packet_path)
        if path.exists():
            decision_packets.append(json.loads(path.read_text(encoding="utf-8")))
    analog_series_report = {}
    analog_path = Path(args.analog_series_report) if args.analog_series_report else None
    if analog_path and analog_path.exists():
        analog_series_report = json.loads(analog_path.read_text(encoding="utf-8"))
    series_delta = {}
    if not args.skip_series_delta:
        series_delta = build_queue_analog_series_delta(report)
        write_queue_analog_series_delta_report(series_delta, args.series_delta_out)
    elif Path(args.series_delta_out).exists():
        series_delta = json.loads(Path(args.series_delta_out).read_text(encoding="utf-8"))
    queue_decisions = load_next_design_queue_decisions(args.queue_decisions)
    saved_decisions = {"saved_count": 0, "decision_counts": {}}
    if args.save_decisions_db and queue_decisions:
        saved_decisions = save_next_design_queue_decisions(
            queue_decisions,
            db_path=args.db_path,
            source_path=args.queue_decisions,
        )
    if args.load_db_decisions:
        queue_decisions = [*queue_decisions, *load_next_design_queue_decisions_from_db(db_path=args.db_path, project_name=report.get("project_name"))]
    rows = build_next_design_queue(
        report,
        max_rows=args.max_rows,
        decision_packets=decision_packets,
        analog_series_report=analog_series_report,
        queue_analog_series_delta_report=series_delta,
        queue_decisions=queue_decisions,
    )
    write_next_design_queue(rows, csv_path=args.csv_out, json_path=args.json_out, markdown_path=args.markdown_out)
    if args.write_decision_template:
        write_next_design_queue_decision_template(rows, args.write_decision_template)
    output = {
        "queue_count": len(rows),
        "csv_out": str(Path(args.csv_out).resolve()),
        "decision_count": len(queue_decisions),
        "saved_decision_count": saved_decisions.get("saved_count", 0),
        "decision_template_out": str(Path(args.write_decision_template).resolve()) if args.write_decision_template else None,
    }
    if not args.skip_series_delta:
        output["series_delta_count"] = series_delta.get("series_count", 0)
        output["series_delta_out"] = str(Path(args.series_delta_out).resolve())
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
