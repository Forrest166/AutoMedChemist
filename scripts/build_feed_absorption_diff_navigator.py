from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.feed_absorption_diff_navigator import build_feed_absorption_diff_navigator, write_feed_absorption_diff_navigator  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a drill-down navigator for feed absorption row deltas, duplicates, owner reuse, and coverage gaps.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/feed_absorption_diff_navigator.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/feed_absorption_diff_navigator.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/feed_absorption_diff_navigator.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_feed_absorption_diff_navigator(root=args.root)
    write_feed_absorption_diff_navigator(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "blocker_count": report.get("blocker_count"),
                "warning_count": report.get("warning_count"),
                "feed_delta_count": report.get("feed_delta_count"),
                "duplicate_group_count": report.get("duplicate_group_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
