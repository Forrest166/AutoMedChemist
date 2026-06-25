from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.production_dashboard import (  # noqa: E402
    append_production_dashboard_history,
    build_production_dashboard_snapshot,
    write_production_dashboard_snapshot,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a compact production gate dashboard snapshot.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/releases/production_dashboard_snapshot.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/releases/production_dashboard_snapshot.csv"))
    parser.add_argument("--history-out", default=str(ROOT / "data/releases/production_dashboard_trend_history.json"))
    parser.add_argument("--history-csv-out", default=str(ROOT / "data/releases/production_dashboard_trend_history.csv"))
    parser.add_argument("--skip-history", action="store_true")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    report = build_production_dashboard_snapshot(args.root)
    if not args.skip_history:
        history = append_production_dashboard_history(report, json_path=args.history_out, csv_path=args.history_csv_out)
        report["trend_history_status"] = history.get("status")
        report["trend_history_row_count"] = history.get("row_count")
    write_production_dashboard_snapshot(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_fail and report.get("status") == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
