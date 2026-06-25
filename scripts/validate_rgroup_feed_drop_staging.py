from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_onboarding import build_rgroup_feed_drop_staging_gate, write_rgroup_feed_drop_staging_gate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate staged R-group feed-drop CSVs before moving them into production feeds.")
    parser.add_argument("--staging-report", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging.json"))
    parser.add_argument("--staging-dir", default=str(ROOT / "data/replacements/feed_drops/next_rgroup_feed_drop"))
    parser.add_argument("--require-rows", action="store_true")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging_gate.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging_gate.csv"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_rgroup_feed_drop_staging_gate(
        staging_report_path=args.staging_report,
        staging_dir=args.staging_dir,
        require_rows=args.require_rows,
    )
    write_rgroup_feed_drop_staging_gate(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
