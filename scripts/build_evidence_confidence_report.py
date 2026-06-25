from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_confidence import (  # noqa: E402
    build_evidence_confidence_report,
    build_evidence_residual_trend_chart,
    build_endpoint_family_residual_model,
    write_evidence_confidence_report,
    write_evidence_residual_trend_chart,
    write_endpoint_family_residual_model,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build endpoint-specific evidence confidence calibration curves.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--min-observations", type=int, default=3)
    parser.add_argument("--min-residual-observations", type=int, default=6)
    parser.add_argument("--previous-report", default=None, help="Optional previous evidence confidence JSON for residual trend deltas.")
    parser.add_argument("--output", default=str(ROOT / "data" / "substituents" / "evidence_confidence_report.json"))
    parser.add_argument("--trend-json-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_trend_chart.json"))
    parser.add_argument("--trend-csv-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_trend_chart.csv"))
    parser.add_argument("--endpoint-family-model-out", default=str(ROOT / "data" / "substituents" / "endpoint_family_residual_model.json"))
    args = parser.parse_args()

    previous_report = {}
    previous_path = Path(args.previous_report) if args.previous_report else Path(args.output)
    if previous_path.exists():
        try:
            previous_report = json.loads(previous_path.read_text(encoding="utf-8"))
        except Exception:
            previous_report = {}
    report = build_evidence_confidence_report(
        db_path=args.db_path,
        project_name=args.project_name,
        min_observations=args.min_observations,
        min_residual_observations=args.min_residual_observations,
        previous_report=previous_report,
    )
    write_evidence_confidence_report(report, args.output)
    residual_trend_chart = build_evidence_residual_trend_chart(report)
    write_evidence_residual_trend_chart(
        residual_trend_chart,
        json_path=args.trend_json_out,
        csv_path=args.trend_csv_out,
    )
    endpoint_family_model = build_endpoint_family_residual_model(report)
    write_endpoint_family_residual_model(endpoint_family_model, args.endpoint_family_model_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
