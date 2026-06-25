from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.operator_trend_summary import build_operator_trend_summary, write_operator_trend_summary  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build compact operator-facing trend summary cards.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=str(ROOT / "data/releases/operator_trend_summary.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/releases/operator_trend_summary.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/operator_trend_summary.md"))
    args = parser.parse_args()
    report = build_operator_trend_summary(root=args.root, project_name=args.project_name)
    write_operator_trend_summary(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "card_count": report.get("card_count"),
                "needs_attention_count": report.get("needs_attention_count"),
                "json_out": str(Path(args.json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
