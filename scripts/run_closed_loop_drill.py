from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.closed_loop_drill import run_closed_loop_drill  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an end-to-end local closed-loop drill.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "projects" / "closed_loop_drill"))
    parser.add_argument("--project-name", default="closed_loop_drill")
    parser.add_argument("--smiles", default="COc1ccc(Cl)cc1")
    parser.add_argument("--direction", default="increase_polarity")
    parser.add_argument("--endpoint-group", default="potency")
    parser.add_argument("--assay-type", default="IC50")
    parser.add_argument("--target-family", default="kinase")
    parser.add_argument("--max-candidates", type=int, default=60)
    parser.add_argument("--feedback-limit", type=int, default=4)
    parser.add_argument("--acceptance-criteria", default=str(ROOT / "data" / "rules" / "closed_loop_acceptance.yaml"))
    args = parser.parse_args()
    report = run_closed_loop_drill(
        db_path=args.db_path,
        output_dir=args.output_dir,
        project_name=args.project_name,
        smiles=args.smiles,
        direction=args.direction,
        endpoint_group=args.endpoint_group,
        assay_type=args.assay_type,
        target_family=args.target_family,
        max_candidates=args.max_candidates,
        feedback_limit=args.feedback_limit,
        acceptance_criteria_path=args.acceptance_criteria,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
