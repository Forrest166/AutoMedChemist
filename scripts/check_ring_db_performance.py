from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_performance import build_ring_db_performance_report, write_ring_db_performance_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Check ring-system SQLite query performance and index coverage.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "ring_db_performance_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "substituents" / "ring_db_performance_report.csv"))
    parser.add_argument("--apply-maintenance", action="store_true")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--warn-ms", type=float, default=250.0)
    parser.add_argument("--cache", default=str(ROOT / "data" / "substituents" / "ring_recommendation_cache.json"))
    parser.add_argument("--cache-ttl-seconds", type=float, default=86400)
    args = parser.parse_args()

    report = build_ring_db_performance_report(
        db_path=args.db,
        apply_maintenance=args.apply_maintenance,
        repetitions=args.repetitions,
        warn_ms=args.warn_ms,
        cache_path=args.cache,
        cache_ttl_seconds=args.cache_ttl_seconds,
    )
    write_ring_db_performance_report(report, args.json_out, args.csv_out)
    print(
        json.dumps(
            {
                "ring_system_count": report.get("ring_system_count"),
                "ertl_ring_system_count": report.get("ertl_ring_system_count"),
                "issue_count": report.get("issue_count"),
                "missing_recommended_indexes": report.get("missing_recommended_indexes"),
                "ring_recommender_cache": report.get("ring_recommender_cache"),
                "json_out": str(Path(args.json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
