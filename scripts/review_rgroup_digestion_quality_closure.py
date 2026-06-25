from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_digestion_quality_closure_review import (  # noqa: E402
    build_rgroup_digestion_quality_closure_review,
    write_rgroup_digestion_quality_closure_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record conservative decisions for R-group digestion quality closure tasks.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--reviewer", default="local_quality_closure")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_digestion_quality_closure_ledger.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_digestion_quality_closure_ledger.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_digestion_quality_closure_ledger.md"))
    parser.add_argument("--fail-on-open", action="store_true")
    args = parser.parse_args()
    report = build_rgroup_digestion_quality_closure_review(root=args.root, reviewer=args.reviewer)
    write_rgroup_digestion_quality_closure_review(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    if args.fail_on_open and int(report.get("open_count") or 0):
        raise SystemExit(1)
    print(
        f"status={report.get('status')} tasks={report.get('task_count')} "
        f"closed={report.get('closed_count')} open={report.get('open_count')} "
        f"holdout={report.get('holdout_count')}"
    )


if __name__ == "__main__":
    main()
