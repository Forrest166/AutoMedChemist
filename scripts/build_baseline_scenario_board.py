from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.baseline_scenario_board import build_baseline_scenario_board, write_baseline_scenario_board  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local baseline scenario board rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "baseline_scenario_board.md"))
    args = parser.parse_args()
    root = Path(args.root)
    report = build_baseline_scenario_board(root=root, project_name=args.project_name)
    json_out = args.json_out or str(root / "data" / "projects" / args.project_name / "baseline_scenario_board.json")
    csv_out = args.csv_out or str(root / "data" / "projects" / args.project_name / "baseline_scenario_board.csv")
    write_baseline_scenario_board(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "attention_count": report.get("attention_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") in {"ready", "missing_inputs"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
