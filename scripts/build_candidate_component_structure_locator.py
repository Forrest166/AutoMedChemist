from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_component_structure_locator import (  # noqa: E402
    build_candidate_component_structure_locator,
    write_candidate_component_structure_locator,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate score-component to 2D-structure locator rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_component_structure_locator.md"))
    args = parser.parse_args()
    root = Path(args.root)
    project_dir = root / "data" / "projects" / args.project_name
    report = build_candidate_component_structure_locator(root=root, project_name=args.project_name)
    write_candidate_component_structure_locator(
        report,
        json_path=args.json_out or project_dir / "candidate_component_structure_locator.json",
        csv_path=args.csv_out or project_dir / "candidate_component_structure_locator.csv",
        markdown_path=args.markdown_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "linked_component_count": report.get("linked_component_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
