from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.staging_sandbox_filter_views import build_staging_sandbox_filter_views, write_staging_sandbox_filter_views  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build native filter views for staging budget, sandbox delta review, and digestion ledger.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=str(ROOT / "data/projects/demo/staging_sandbox_filter_views.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/projects/demo/staging_sandbox_filter_views.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/staging_sandbox_filter_views.md"))
    args = parser.parse_args()
    report = build_staging_sandbox_filter_views(root=args.root, project_name=args.project_name)
    write_staging_sandbox_filter_views(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps({key: report.get(key) for key in ["status", "mode", "row_count", "view_type_counts"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
