from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_approval_workbench import build_rgroup_approval_workbench, write_rgroup_approval_workbench  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build native-filterable R-group promotion approval workbench rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_approval_workbench.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_approval_workbench.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_approval_workbench.md"))
    args = parser.parse_args()
    report = build_rgroup_approval_workbench(root=args.root)
    write_rgroup_approval_workbench(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps({key: report.get(key) for key in ["status", "mode", "row_count", "action_bucket_counts", "promotion_allowed"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
