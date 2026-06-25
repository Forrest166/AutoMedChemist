from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_visual_compare import build_candidate_visual_compare, write_candidate_visual_compare  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local visual comparison packet for candidate rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--candidate-ids", default="", help="Optional comma-separated candidate IDs.")
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_visual_compare.md"))
    args = parser.parse_args()
    ids = [item.strip() for item in args.candidate_ids.split(",") if item.strip()] or None
    report = build_candidate_visual_compare(
        root=args.root,
        project_name=args.project_name,
        candidates_csv=args.candidates_csv,
        output_dir=args.output_dir,
        candidate_ids=ids,
        max_candidates=args.max_candidates,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_visual_compare.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_visual_compare.csv")
    write_candidate_visual_compare(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "candidate_count": report.get("candidate_count"),
                "grid_image_path": report.get("grid_image_path"),
                "json_out": str(Path(json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
