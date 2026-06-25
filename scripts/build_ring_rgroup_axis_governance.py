from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_rgroup_axis_governance import build_ring_rgroup_axis_governance, write_ring_rgroup_axis_governance  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build first-class ring/R-group axis governance budgets.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/ring_rgroup_axis_governance.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/ring_rgroup_axis_governance.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/ring_rgroup_axis_governance.md"))
    args = parser.parse_args()
    report = build_ring_rgroup_axis_governance(root=args.root)
    write_ring_rgroup_axis_governance(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        f"status={report.get('status')} axes={report.get('axis_count')} "
        f"rows={report.get('row_count')} approved_rehearsal={report.get('approved_rehearsal_count')}"
    )


if __name__ == "__main__":
    main()
