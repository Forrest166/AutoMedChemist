from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.baseline_lineage_history import build_baseline_lineage_history, write_baseline_lineage_history  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Append and write baseline lineage history.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--pairwise-csv-out", default=None)
    parser.add_argument("--chart-csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/baseline_lineage_history.md"))
    parser.add_argument("--max-entries", type=int, default=200)
    args = parser.parse_args()
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_lineage_history.json")
    report = build_baseline_lineage_history(
        root=args.root,
        project_name=args.project_name,
        history_path=Path(json_out).relative_to(ROOT) if Path(json_out).is_absolute() and str(Path(json_out)).startswith(str(ROOT)) else json_out,
        max_entries=args.max_entries,
    )
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_lineage_history.csv")
    pairwise_csv_out = args.pairwise_csv_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_lineage_history_pairwise.csv")
    chart_csv_out = args.chart_csv_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_lineage_history_chart.csv")
    write_baseline_lineage_history(
        report,
        json_path=json_out,
        csv_path=csv_out,
        pairwise_csv_path=pairwise_csv_out,
        chart_csv_path=chart_csv_out,
        markdown_path=args.markdown_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "pairwise_row_count": report.get("pairwise_row_count"),
                "latest_movement_row_count": report.get("latest_movement_row_count"),
                "json_out": str(Path(json_out).resolve()),
                "pairwise_csv_out": str(Path(pairwise_csv_out).resolve()),
                "chart_csv_out": str(Path(chart_csv_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
