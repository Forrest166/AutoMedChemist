from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_confidence import build_evidence_residual_trend_chart, write_evidence_residual_trend_chart  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chart-friendly evidence residual trend rows.")
    parser.add_argument("--report", default=str(ROOT / "data" / "substituents" / "evidence_confidence_report.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_trend_chart.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "substituents" / "evidence_residual_trend_chart.csv"))
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    rows = build_evidence_residual_trend_chart(report)
    write_evidence_residual_trend_chart(rows, json_path=args.json_out, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "row_count": len(rows),
                "json_out": str(Path(args.json_out).resolve()),
                "csv_out": str(Path(args.csv_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
