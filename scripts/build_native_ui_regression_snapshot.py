from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.native_ui_regression import (  # noqa: E402
    build_native_ui_regression_snapshot,
    write_native_ui_regression_snapshot,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build native UI regression snapshot for quality, package, DB, and candidate schema checks.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=str(ROOT / "data" / "releases" / "native_ui_regression_snapshot.json"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "native_ui_regression_snapshot.md"))
    args = parser.parse_args()
    report = build_native_ui_regression_snapshot(root=args.root, project_name=args.project_name)
    write_native_ui_regression_snapshot(report, json_path=args.json_out, markdown_path=args.markdown_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
