from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_quality_scorecard import (  # noqa: E402
    build_evidence_quality_scorecard,
    write_evidence_quality_scorecard,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate evidence quality scorecard.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--stale-days", type=int, default=7)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/evidence_quality_scorecard.md"))
    args = parser.parse_args()
    report = build_evidence_quality_scorecard(root=args.root, project_name=args.project_name, stale_days=args.stale_days)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "evidence_quality_scorecard.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "evidence_quality_scorecard.csv")
    write_evidence_quality_scorecard(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "attention_count": report.get("attention_count"),
                "watch_count": report.get("watch_count"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
