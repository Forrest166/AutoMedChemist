from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_onboarding import (  # noqa: E402
    build_rgroup_feed_drop_promotion_diff,
    write_rgroup_feed_drop_promotion_diff,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a review diff for the next staged R-group feed promotion.")
    parser.add_argument("--staging-gate", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging_gate.json"))
    parser.add_argument("--promotion-report", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_promotion.json"))
    parser.add_argument("--feed-dir", default=str(ROOT / "data/replacements/feeds"))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_promotion_diff.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_promotion_diff.csv"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_rgroup_feed_drop_promotion_diff(
        staging_gate_path=args.staging_gate,
        promotion_report_path=args.promotion_report,
        feed_dir=args.feed_dir,
    )
    write_rgroup_feed_drop_promotion_diff(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
