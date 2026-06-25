from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_ab_review import (  # noqa: E402
    build_profile_ab_material_change_review,
    write_profile_ab_material_change_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate-level review records for material profile A/B changes.")
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--matrix", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_replay_matrix.json"))
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--decision", default="accepted_with_review")
    parser.add_argument(
        "--note",
        default="Accepted with candidate-level audit; current material movement is retained for the active profile context.",
    )
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_material_change_review.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_material_change_review.csv"))
    args = parser.parse_args()
    report = build_profile_ab_material_change_review(
        root=ROOT,
        matrix_path=args.matrix,
        project_name=args.project_name,
        reviewer=args.reviewer,
        decision=args.decision,
        note=args.note,
    )
    write_profile_ab_material_change_review(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in [
                    "status",
                    "material_change_scenario_count",
                    "candidate_diff_count",
                    "accepted_profile_change_count",
                    "blocked_profile_change_count",
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
