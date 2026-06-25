from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.assay_followup_results import import_assay_followup_results_csv, write_assay_followup_import_report  # noqa: E402
from localmedchem.data_foundation import build_data_foundation_report, save_data_foundation_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import real follow-up assay result rows and refresh assay triage.")
    parser.add_argument("--csv", required=True, help="Filled assay_followup_results_template.csv with measured result payloads.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "assay_followup_result_import_report.json"))
    args = parser.parse_args()
    report = import_assay_followup_results_csv(
        args.csv,
        db_path=args.db,
        project_name=args.project_name or None,
        reviewer=args.reviewer,
    )
    write_assay_followup_import_report(report, args.output)
    foundation = build_data_foundation_report(ROOT, db_path=args.db, include_checksums=False)
    save_data_foundation_report(foundation, json_path=ROOT / "data" / "substituents" / "data_foundation_report.json")
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "imported_events": (report.get("import") or {}).get("event_count"),
                "real_followup_resolved_count": report.get("real_followup_resolved_count"),
                "planned_followup_count": report.get("planned_followup_count"),
                "followup_review_count": report.get("followup_review_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
