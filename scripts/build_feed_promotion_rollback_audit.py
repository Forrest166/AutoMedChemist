from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.feed_promotion_rollback_audit import build_feed_promotion_rollback_audit, write_feed_promotion_rollback_audit  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a rollback replay audit for approved R-group feed promotion rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--dry-run", action="store_true", help="Document rollback replay only; no files are changed.")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/feed_promotion_rollback_audit.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/feed_promotion_rollback_audit.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/feed_promotion_rollback_audit.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()
    report = build_feed_promotion_rollback_audit(root=args.root)
    write_feed_promotion_rollback_audit(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps({key: report.get(key) for key in ["status", "mode", "row_count", "ready_count", "blocked_count", "promotion_allowed"]}, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
