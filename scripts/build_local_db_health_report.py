from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.local_db_health import build_local_db_health_report, write_local_db_health_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a lightweight local SQLite health report for the native UI.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "releases" / "local_db_health_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "releases" / "local_db_health_report.csv"))
    parser.add_argument("--quick-check", action="store_true", help="Run SQLite PRAGMA quick_check; slower on multi-million-row local DBs.")
    args = parser.parse_args()
    report = build_local_db_health_report(root=args.root, db_path=args.db_path, run_quick_check=args.quick_check)
    write_local_db_health_report(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
