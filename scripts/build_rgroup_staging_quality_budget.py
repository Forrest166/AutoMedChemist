from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.staging_quality_budget import build_staging_quality_budget, write_staging_quality_budget  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build source-level quality budgets for next R-group feed staging rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_staging_quality_budget.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_staging_quality_budget.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_staging_quality_budget.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()
    report = build_staging_quality_budget(root=args.root)
    write_staging_quality_budget(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
