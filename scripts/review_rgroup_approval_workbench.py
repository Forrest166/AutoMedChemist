from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_approval_workbench_decisions import (  # noqa: E402
    build_rgroup_approval_workbench_decisions,
    write_rgroup_approval_workbench_decisions,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record local signed decisions for the native R-group approval workbench.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--reviewer", default="local_approval_workbench")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_approval_workbench_decisions.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_approval_workbench_decisions.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_approval_workbench_decisions.md"))
    args = parser.parse_args()
    report = build_rgroup_approval_workbench_decisions(root=args.root, reviewer=args.reviewer)
    write_rgroup_approval_workbench_decisions(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        f"status={report.get('status')} rows={report.get('row_count')} "
        f"approved_rehearsal={report.get('approved_rehearsal_count')} "
        f"deferred={report.get('deferred_holdout_count')}"
    )


if __name__ == "__main__":
    main()
