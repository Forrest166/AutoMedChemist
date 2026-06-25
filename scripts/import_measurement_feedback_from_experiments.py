from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.measurement_feedback_plan import (  # noqa: E402
    import_measurement_feedback_results_rows,
    measurement_feedback_rows_from_experiment_results,
    read_experiment_result_rows_csv,
    write_measurement_feedback_import_report,
)


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    return json.loads(json_path.read_text(encoding="utf-8")) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Map historical experiment rows into measurement feedback import rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--experiments", default=str(ROOT / "data" / "projects" / "demo" / "historical_experiment_results.csv"))
    parser.add_argument("--plan-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_plan.json"))
    parser.add_argument("--evidence-value-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_report.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.csv"))
    parser.add_argument("--reviewer", default="historical_experiment_import")
    args = parser.parse_args()

    plan = _read_json(args.plan_path)
    experiment_rows = read_experiment_result_rows_csv(args.experiments)
    mapped = measurement_feedback_rows_from_experiment_results(experiment_rows, plan, reviewer=args.reviewer)
    report = import_measurement_feedback_results_rows(
        mapped.get("rows") or [],
        root=args.root,
        plan_path=args.plan_path,
        evidence_value_path=args.evidence_value_path,
        source_path=args.experiments,
        reviewer=args.reviewer,
    )
    report["experiment_mapping"] = {key: value for key, value in mapped.items() if key != "rows"}
    write_measurement_feedback_import_report(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mapped_rows": mapped.get("generated_row_count"),
                "unmatched_plan_count": mapped.get("unmatched_plan_count"),
                "importable_row_count": report.get("importable_row_count"),
                "calibration_ready_row_count": report.get("calibration_ready_row_count"),
                "plan_update_count": report.get("plan_update_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if report.get("status") == "validation_failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
