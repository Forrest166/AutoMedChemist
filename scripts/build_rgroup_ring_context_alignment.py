from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_ring_context_alignment import build_rgroup_ring_context_alignment, write_rgroup_ring_context_alignment  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Align R-group approval rows with ring/scaffold context hints.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_ring_context_alignment.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_ring_context_alignment.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_ring_context_alignment.md"))
    args = parser.parse_args()
    report = build_rgroup_ring_context_alignment(root=args.root)
    write_rgroup_ring_context_alignment(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps({key: report.get(key) for key in ["status", "mode", "row_count", "axis_counts", "combined_review_count"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
