from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_digestion_ledger import build_rgroup_feed_digestion_ledger, write_rgroup_feed_digestion_ledger  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build row-level digestion ledger for staged R-group feed rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_feed_digestion_ledger.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_feed_digestion_ledger.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_feed_digestion_ledger.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()
    report = build_rgroup_feed_digestion_ledger(root=args.root, project_name=args.project_name)
    write_rgroup_feed_digestion_ledger(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps({key: report.get(key) for key in ["status", "mode", "row_count", "accepted_count", "deferred_count", "held_out_count", "promoted_count"]}, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
