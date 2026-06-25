from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.local_db_maintenance import build_local_db_maintenance_report, write_local_db_maintenance_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local SQLite maintenance, cache, and latency-budget report.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--db-path", default=str(ROOT / "data/localmedchem.sqlite"))
    parser.add_argument("--cache-path", default=str(ROOT / "data/substituents/ring_recommendation_cache.json"))
    parser.add_argument("--apply-maintenance", action="store_true")
    parser.add_argument("--warn-ms", type=float, default=250.0)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--json-out", default=str(ROOT / "data/releases/local_db_maintenance_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/releases/local_db_maintenance_report.csv"))
    parser.add_argument("--trend-json-out", default=str(ROOT / "data/releases/local_db_maintenance_trend_history.json"))
    parser.add_argument("--trend-csv-out", default=str(ROOT / "data/releases/local_db_maintenance_trend_history.csv"))
    args = parser.parse_args()
    report = build_local_db_maintenance_report(
        root=args.root,
        db_path=args.db_path,
        cache_path=args.cache_path,
        apply_maintenance=args.apply_maintenance,
        warn_ms=args.warn_ms,
        repetitions=args.repetitions,
    )
    write_local_db_maintenance_report(
        report,
        json_path=args.json_out,
        csv_path=args.csv_out,
        trend_json_path=args.trend_json_out,
        trend_csv_path=args.trend_csv_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "warn_count": report.get("warn_count"),
                "fail_count": report.get("fail_count"),
                "json_out": str(Path(args.json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if report.get("status") == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
