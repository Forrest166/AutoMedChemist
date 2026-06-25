from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_explanation_matrix import build_candidate_explanation_matrix, write_candidate_explanation_matrix  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an N-way candidate explanation component matrix.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--candidate-id", action="append", default=[])
    parser.add_argument("--max-candidates", type=int, default=12)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_explanation_matrix.md"))
    args = parser.parse_args()

    report = build_candidate_explanation_matrix(
        root=args.root,
        project_name=args.project_name,
        candidate_ids=args.candidate_id,
        max_candidates=args.max_candidates,
    )
    project_dir = ROOT / "data" / "projects" / args.project_name
    json_out = args.json_out or str(project_dir / "candidate_explanation_matrix.json")
    csv_out = args.csv_out or str(project_dir / "candidate_explanation_matrix.csv")
    write_candidate_explanation_matrix(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "candidate_count": report.get("candidate_count"),
                "stoplist_candidate_count": report.get("stoplist_candidate_count"),
                "pairwise_delta_count": report.get("pairwise_delta_count"),
                "json_out": json_out,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
