from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_approval_trend_views import build_rgroup_approval_trend_views, write_rgroup_approval_trend_views  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build approval, closure, rollback, axis, and expansion trend views.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_approval_trend_views.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_approval_trend_views.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_approval_trend_views.md"))
    args = parser.parse_args()
    report = build_rgroup_approval_trend_views(root=args.root)
    write_rgroup_approval_trend_views(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        f"status={report.get('status')} rows={report.get('row_count')} "
        f"needs_attention={report.get('needs_attention_count')}"
    )


if __name__ == "__main__":
    main()
