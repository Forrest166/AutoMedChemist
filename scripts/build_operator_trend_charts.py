from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.operator_trend_charts import build_operator_trend_charts, write_operator_trend_charts  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SVG chart cards for operator trend summary rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--summary-path", default=None)
    parser.add_argument("--chart-dir", default=str(ROOT / "data/releases/operator_trend_charts"))
    parser.add_argument("--json-out", default=str(ROOT / "data/releases/operator_trend_charts.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/releases/operator_trend_charts.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/operator_trend_charts.md"))
    args = parser.parse_args()
    report = build_operator_trend_charts(root=args.root, summary_path=args.summary_path, chart_dir=args.chart_dir)
    write_operator_trend_charts(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps({"status": report.get("status"), "chart_count": report.get("chart_count"), "json_out": str(Path(args.json_out).resolve())}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
