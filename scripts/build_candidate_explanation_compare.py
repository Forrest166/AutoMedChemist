from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_explanation_compare import build_candidate_explanation_compare, write_candidate_explanation_compare  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a side-by-side comparison of two candidate explanation panel rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--base-candidate-id", default=None)
    parser.add_argument("--head-candidate-id", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_explanation_compare.md"))
    args = parser.parse_args()

    report = build_candidate_explanation_compare(
        root=args.root,
        project_name=args.project_name,
        base_candidate_id=args.base_candidate_id,
        head_candidate_id=args.head_candidate_id,
    )
    project_dir = ROOT / "data" / "projects" / args.project_name
    json_out = args.json_out or str(project_dir / "candidate_explanation_compare.json")
    csv_out = args.csv_out or str(project_dir / "candidate_explanation_compare.csv")
    write_candidate_explanation_compare(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "base_candidate_id": report.get("base_candidate_id"),
                "head_candidate_id": report.get("head_candidate_id"),
                "different_component_count": report.get("different_component_count"),
                "stoplist_component_count": report.get("stoplist_component_count"),
                "json_out": json_out,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
