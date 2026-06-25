from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.multi_objective import (  # noqa: E402
    calibrate_multi_objective_profile,
    write_multi_objective_calibration_report,
    write_multi_objective_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate multi-objective scoring weights from historical project outcomes.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--endpoint-group", default=None)
    parser.add_argument("--target-family", default=None)
    parser.add_argument("--assay-type", default=None)
    parser.add_argument("--profiles", default=str(ROOT / "data" / "rules" / "target_context_profiles.yaml"))
    parser.add_argument("--min-observations", type=int, default=4)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "demo" / "multi_objective_calibration_report.json"))
    parser.add_argument("--profile-out", default=str(ROOT / "data" / "profiles" / "calibrated" / "multi_objective_demo_learning.yaml"))
    args = parser.parse_args()

    target_context = {
        "endpoint_group": args.endpoint_group,
        "target_family": args.target_family,
        "assay_type": args.assay_type,
    }
    report = calibrate_multi_objective_profile(
        db_path=args.db,
        project_name=args.project_name,
        target_context=target_context,
        profiles_path=args.profiles,
        min_observations=args.min_observations,
    )
    write_multi_objective_calibration_report(report, args.json_out)
    write_multi_objective_profile(report["calibrated_profile"], args.profile_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "observation_count": report.get("observation_count"),
                "json_out": str(Path(args.json_out).resolve()),
                "profile_out": str(Path(args.profile_out).resolve()),
                "score_weights": (report.get("calibrated_profile") or {}).get("score_weights"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
