from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.site_detection_confidence import build_site_detection_confidence, write_site_detection_confidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local site-detection confidence rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "site_detection_confidence.md"))
    args = parser.parse_args()
    root = Path(args.root)
    report = build_site_detection_confidence(root=root, project_name=args.project_name)
    json_out = args.json_out or str(root / "data" / "projects" / args.project_name / "site_detection_confidence.json")
    csv_out = args.csv_out or str(root / "data" / "projects" / args.project_name / "site_detection_confidence.csv")
    write_site_detection_confidence(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "low_confidence_count": report.get("low_confidence_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") in {"ready", "review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
