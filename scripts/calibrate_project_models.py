from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.calibration import (  # noqa: E402
    calibrate_project_models,
    save_calibration_report,
    write_calibration_profiles,
    write_calibration_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit lightweight endpoint-specific project calibration profiles.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--min-feedback", type=int, default=3)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "demo" / "model_calibration_report.json"))
    parser.add_argument("--profile-out-dir", default=str(ROOT / "data" / "profiles" / "calibrated"))
    parser.add_argument("--skip-db-save", action="store_true")
    args = parser.parse_args()

    report = calibrate_project_models(
        db_path=args.db,
        project_name=args.project_name,
        min_feedback=args.min_feedback,
    )
    write_calibration_report(report, args.json_out)
    profiles = write_calibration_profiles(report, args.profile_out_dir)
    if not args.skip_db_save:
        save_calibration_report(report, db_path=args.db)

    summary = {
        **report,
        "profile_paths": [str(path.resolve()) for path in profiles],
        "json_out": str(Path(args.json_out).resolve()),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
