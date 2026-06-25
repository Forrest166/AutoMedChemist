from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_value_scoring import build_evidence_value_calibration_report, write_evidence_value_calibration_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build evidence-value calibration report from real measurement feedback imports.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--evidence-value-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_report.json"))
    parser.add_argument("--measurement-import-path", default=str(ROOT / "data" / "projects" / "demo" / "measurement_feedback_result_import_report.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_calibration_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_calibration_report.csv"))
    args = parser.parse_args()

    report = build_evidence_value_calibration_report(
        root=args.root,
        project_name=args.project_name or None,
        evidence_value_path=args.evidence_value_path,
        measurement_import_path=args.measurement_import_path,
    )
    write_evidence_value_calibration_report(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "calibration_row_count": report.get("calibration_row_count"),
                "mean_absolute_error": report.get("mean_absolute_error"),
                "rank_alignment_rate": report.get("rank_alignment_rate"),
                "recommended_weight_adjustments": report.get("recommended_weight_adjustments"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
