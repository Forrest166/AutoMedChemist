from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.feedback import import_feedback_csv, summarize_project_feedback, write_feedback_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import project assay/ADME feedback for saved candidate runs.")
    parser.add_argument("--csv", required=True, help="CSV with run_id,candidate_id,assay metadata, value, unit, and classification.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--report-out", default=str(ROOT / "data" / "projects" / "demo" / "project_feedback_report.json"))
    args = parser.parse_args()

    import_report = import_feedback_csv(args.csv, db_path=args.db)
    summary = summarize_project_feedback(db_path=args.db, project_name=args.project_name)
    report = {"import": import_report, "summary": summary}
    write_feedback_report(report, args.report_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
