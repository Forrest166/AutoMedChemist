from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.assay_event_triage import build_assay_event_triage_report, write_assay_event_triage_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build low-confidence/retest assay event triage report.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="")
    parser.add_argument("--status", default="planned_followup")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "assay_event_triage_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "assay_event_triage_report.csv"))
    args = parser.parse_args()
    report = build_assay_event_triage_report(
        db_path=args.db,
        project_name=args.project_name or None,
        default_status=args.status,
        reviewer=args.reviewer,
    )
    write_assay_event_triage_report(report, args.output, csv_path=args.csv_out)
    print(json.dumps({key: report.get(key) for key in ["status", "event_count", "unique_followup_event_count", "lineage_group_count", "duplicate_lineage_event_count", "issue_counts", "addressed_issue_counts", "open_issue_counts"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
