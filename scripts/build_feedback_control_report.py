from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.prospective import build_feedback_control_report, save_feedback_control_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build prospective feedback-control and active-learning hints.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--min-feedback", type=int, default=3)
    parser.add_argument("--next-experiment-limit", type=int, default=30)
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "feedback_control_report.json"))
    parser.add_argument("--skip-db-write", action="store_true")
    args = parser.parse_args()

    report = build_feedback_control_report(
        db_path=args.db_path,
        project_name=args.project_name,
        min_feedback=args.min_feedback,
        next_experiment_limit=args.next_experiment_limit,
    )
    save_feedback_control_report(report, output_path=args.output, db_path=None if args.skip_db_write else args.db_path)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
