from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_admission_sandbox_impact_replay import (  # noqa: E402
    build_rgroup_admission_sandbox_impact_replay,
    write_rgroup_admission_sandbox_impact_replay,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R-group admission sandbox impact replay and rollback explanations.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_admission_sandbox_impact_replay.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_admission_sandbox_impact_replay.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_admission_sandbox_impact_replay.md"))
    args = parser.parse_args()
    report = build_rgroup_admission_sandbox_impact_replay(root=args.root, project_name=args.project_name)
    write_rgroup_admission_sandbox_impact_replay(
        report,
        json_path=args.json_out,
        csv_path=args.csv_out,
        markdown_path=args.markdown_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "needs_operator_review_count": report.get("needs_operator_review_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
