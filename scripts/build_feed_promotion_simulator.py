from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.feed_promotion_simulator import build_feed_promotion_simulator, write_feed_promotion_simulator  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate next feed-drop promotion impacts before governed ingestion.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/feed_promotion_simulator.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/feed_promotion_simulator.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/feed_promotion_simulator.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_feed_promotion_simulator(root=args.root)
    write_feed_promotion_simulator(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "staged_row_count": report.get("staged_row_count"),
                "blocker_count": report.get("blocker_count"),
                "warning_count": report.get("warning_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
