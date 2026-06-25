from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_digestion_quality_closure_queue import (  # noqa: E402
    build_rgroup_digestion_quality_closure_queue,
    write_rgroup_digestion_quality_closure_queue,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a closure queue for R-group digestion quality watch slices.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_digestion_quality_closure_queue.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_digestion_quality_closure_queue.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_digestion_quality_closure_queue.md"))
    args = parser.parse_args()
    report = build_rgroup_digestion_quality_closure_queue(root=args.root)
    write_rgroup_digestion_quality_closure_queue(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps({key: report.get(key) for key in ["status", "mode", "row_count", "open_count", "issue_type_counts"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
