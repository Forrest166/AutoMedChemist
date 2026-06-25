from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.site_detection_regression import (  # noqa: E402
    build_site_detection_regression_report,
    write_site_detection_regression_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local site-detection regression report.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "site_detection_regression_report.md"))
    args = parser.parse_args()
    root = Path(args.root)
    report = build_site_detection_regression_report(root=root, project_name=args.project_name)
    json_out = args.json_out or str(root / "data" / "projects" / args.project_name / "site_detection_regression_report.json")
    csv_out = args.csv_out or str(root / "data" / "projects" / args.project_name / "site_detection_regression_report.csv")
    write_site_detection_regression_report(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "fail_count": report.get("fail_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
