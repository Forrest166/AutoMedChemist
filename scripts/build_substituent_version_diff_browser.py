from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.substituent_version_diff_browser import (  # noqa: E402
    build_substituent_version_diff_browser,
    write_substituent_version_diff_browser,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build substituent version diff and candidate-impact browser rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "substituent_version_diff_browser.md"))
    args = parser.parse_args()
    root = Path(args.root)
    report = build_substituent_version_diff_browser(root=root, project_name=args.project_name)
    json_out = args.json_out or str(root / "data" / "substituents" / "substituent_version_diff_browser.json")
    csv_out = args.csv_out or str(root / "data" / "substituents" / "substituent_version_diff_browser.csv")
    write_substituent_version_diff_browser(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "linked_substituent_count": report.get("linked_substituent_count"),
                "candidate_attention_substituent_count": report.get("candidate_attention_substituent_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
