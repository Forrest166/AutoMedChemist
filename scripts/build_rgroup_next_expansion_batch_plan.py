from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_next_expansion_batch_plan import (  # noqa: E402
    build_rgroup_next_expansion_batch_plan,
    write_rgroup_next_expansion_batch_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the next governed analog/literature R-group expansion batch plan.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_next_expansion_batch_plan.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_next_expansion_batch_plan.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_next_expansion_batch_plan.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()
    report = build_rgroup_next_expansion_batch_plan(root=args.root)
    write_rgroup_next_expansion_batch_plan(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    if args.fail_on_blocked and int(report.get("blocked_count") or 0):
        raise SystemExit(1)
    print(
        f"status={report.get('status')} rows={report.get('row_count')} "
        f"ready={report.get('ready_count')} blocked={report.get('blocked_count')} "
        f"cap={report.get('planned_staging_cap_total')}"
    )


if __name__ == "__main__":
    main()
