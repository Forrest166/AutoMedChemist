from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.assay_learning import build_assay_learning_report  # noqa: E402
from localmedchem.experiment_tracking import write_experiment_tracking_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build stop/go/retest and replicate-confidence learning from experiment events.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--report-out", default=str(ROOT / "data" / "projects" / "demo" / "assay_learning_report.json"))
    args = parser.parse_args()

    report = build_assay_learning_report(db_path=args.db, project_name=args.project_name)
    write_experiment_tracking_report(report, args.report_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
