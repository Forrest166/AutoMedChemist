from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_structure_interpretation import (  # noqa: E402
    build_candidate_structure_interpretation,
    write_candidate_structure_interpretation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local candidate structure interpretation and score-component locators.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_structure_interpretation.md"))
    args = parser.parse_args()
    project_dir = ROOT / "data" / "projects" / args.project_name
    report = build_candidate_structure_interpretation(root=args.root, project_name=args.project_name)
    write_candidate_structure_interpretation(
        report,
        json_path=args.json_out or project_dir / "candidate_structure_interpretation.json",
        csv_path=args.csv_out or project_dir / "candidate_structure_interpretation.csv",
        markdown_path=args.markdown_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "candidate_count": report.get("candidate_count"),
                "score_component_locator_count": report.get("score_component_locator_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
