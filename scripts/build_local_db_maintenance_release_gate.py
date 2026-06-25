from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.local_db_maintenance_release_gate import build_local_db_maintenance_release_gate, write_local_db_maintenance_release_gate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify local DB maintenance rows into release-stop and watch lanes.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/releases/local_db_maintenance_release_gate.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/releases/local_db_maintenance_release_gate.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/local_db_maintenance_release_gate.md"))
    parser.add_argument("--fail-on-release-stop", action="store_true")
    args = parser.parse_args()
    report = build_local_db_maintenance_release_gate(root=args.root)
    write_local_db_maintenance_release_gate(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "release_stop_count": report.get("release_stop_count"),
                "watch_count": report.get("watch_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_release_stop and int(report.get("release_stop_count") or 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
