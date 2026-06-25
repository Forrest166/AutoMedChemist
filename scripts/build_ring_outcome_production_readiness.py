from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_readiness import (  # noqa: E402
    build_ring_outcome_production_readiness,
    write_ring_outcome_production_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the ring-outcome production readiness gate.")
    parser.add_argument("--plan-path", default=str(ROOT / "data/projects/demo/ring_outcome_experiment_plan.csv"))
    parser.add_argument("--result-csv", default=str(ROOT / "data/projects/demo/ring_outcome_results_template.csv"))
    parser.add_argument("--intake-manifest", default=str(ROOT / "data/projects/demo/ring_outcome_result_intake_manifest.json"))
    parser.add_argument("--learning", default=str(ROOT / "data/projects/demo/ring_outcome_learning_report.json"))
    parser.add_argument("--overlay", default=str(ROOT / "data/profiles/calibrated/ring_outcome_scoring_overlay.json"))
    parser.add_argument("--activation", default=str(ROOT / "data/profiles/calibrated/ring_outcome_overlay_activation.json"))
    parser.add_argument("--replay", default=str(ROOT / "data/projects/demo/ring_outcome_overlay_replay.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data/projects/demo/ring_outcome_production_readiness.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/projects/demo/ring_outcome_production_readiness.csv"))
    parser.add_argument("--fail-on-validation-error", action="store_true")
    args = parser.parse_args()

    report = build_ring_outcome_production_readiness(
        plan_path=args.plan_path,
        result_csv=args.result_csv,
        intake_manifest_path=args.intake_manifest,
        learning_path=args.learning,
        overlay_path=args.overlay,
        activation_path=args.activation,
        replay_path=args.replay,
    )
    write_ring_outcome_production_readiness(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_validation_error and report.get("validation_error_count"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
