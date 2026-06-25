from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.baseline_history_explorer import build_baseline_history_explorer, write_baseline_history_explorer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local candidate baseline history explorer rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--max-pairwise", type=int, default=12)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/baseline_history_explorer.md"))
    args = parser.parse_args()
    report = build_baseline_history_explorer(root=args.root, project_name=args.project_name, max_pairwise=args.max_pairwise)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_history_explorer.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "baseline_history_explorer.csv")
    write_baseline_history_explorer(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(json.dumps({k: report.get(k) for k in ["status", "mode", "baseline_count", "comparison_count", "row_count"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
