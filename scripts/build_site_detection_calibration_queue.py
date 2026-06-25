from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.site_detection_calibration_queue import (  # noqa: E402
    build_site_detection_calibration_queue,
    write_site_detection_calibration_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local site-detection manual calibration queue.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/site_detection_calibration_queue.md"))
    args = parser.parse_args()
    root = Path(args.root)
    project_dir = root / "data" / "projects" / args.project_name
    report = build_site_detection_calibration_queue(root=root, project_name=args.project_name)
    write_site_detection_calibration_queue(
        report,
        json_path=args.json_out or project_dir / "site_detection_calibration_queue.json",
        csv_path=args.csv_out or project_dir / "site_detection_calibration_queue.csv",
        markdown_path=args.markdown_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "queue_count": report.get("queue_count"),
                "low_confidence_count": report.get("low_confidence_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
