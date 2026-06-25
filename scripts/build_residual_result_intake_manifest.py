from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.residual_result_intake import build_residual_result_intake_manifest, write_residual_result_intake_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a residual result real-payload intake manifest.")
    parser.add_argument("--plan", default=str(ROOT / "data" / "projects" / "demo" / "residual_experiment_plan.csv"))
    parser.add_argument("--results-csv", default="", help="Optional filled residual result CSV to validate.")
    parser.add_argument("--registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "residual_result_intake_manifest.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "residual_result_intake_manifest.csv"))
    args = parser.parse_args()
    report = build_residual_result_intake_manifest(
        plan_path=args.plan,
        result_csv=args.results_csv or None,
        registry_path=args.registry,
    )
    write_residual_result_intake_manifest(report, args.output, csv_path=args.csv_out)
    print(json.dumps({key: report.get(key) for key in ["status", "plan_row_count", "pending_intake_count", "result_payload_count", "importable_row_count", "validation_error_count"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
