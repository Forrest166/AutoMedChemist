from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.scaffold_calibration import scaffold_context_calibration_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate scaffold-context scoring from project feedback.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "scaffold_context_calibration_report.json"))
    parser.add_argument(
        "--profile-out",
        default=None,
        help="Optional YAML profile path to write scaffold_context_calibration into.",
    )
    args = parser.parse_args()

    report = scaffold_context_calibration_report(db_path=args.db_path, project_name=args.project_name)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.profile_out:
        profile = {
            "profile_id": f"scaffold_context_calibrated_{args.project_name or 'all'}",
            "name": f"Scaffold Context Calibrated ({args.project_name or 'all projects'})",
            "score_weights": {"scaffold_context": 0.06},
            **report["calibration_profile"],
        }
        profile_out = Path(args.profile_out)
        profile_out.parent.mkdir(parents=True, exist_ok=True)
        profile_out.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "flag_impacts"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
