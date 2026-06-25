from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.native_drilldown_actions import build_native_drilldown_actions, write_native_drilldown_actions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build native selected-row drilldown action rows for Reports.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--max-actions-per-source", type=int, default=80)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/native_drilldown_actions.md"))
    args = parser.parse_args()

    report = build_native_drilldown_actions(
        root=args.root,
        project_name=args.project_name,
        max_actions_per_source=args.max_actions_per_source,
    )
    project_dir = ROOT / "data" / "projects" / args.project_name
    json_out = args.json_out or str(project_dir / "native_drilldown_actions.json")
    csv_out = args.csv_out or str(project_dir / "native_drilldown_actions.csv")
    write_native_drilldown_actions(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "route_supported_count": report.get("route_supported_count"),
                "json_out": json_out,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
