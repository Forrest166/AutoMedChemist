from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_digestion_quality_metrics import build_rgroup_digestion_quality_metrics, write_rgroup_digestion_quality_metrics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build quality metrics for the staged R-group digestion ledger.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_digestion_quality_metrics.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_digestion_quality_metrics.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_digestion_quality_metrics.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()
    report = build_rgroup_digestion_quality_metrics(root=args.root)
    write_rgroup_digestion_quality_metrics(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "digestion_row_count": report.get("digestion_row_count"),
                "quality_status_counts": report.get("quality_status_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
