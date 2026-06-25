from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_baselines import pin_candidate_baseline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Pin a named local candidate-set baseline.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--note", default="")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    report = pin_candidate_baseline(
        root=args.root,
        project_name=args.project_name,
        baseline_id=args.baseline_id,
        candidates_csv=args.candidates_csv,
        note=args.note,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "baseline_id": report.get("baseline_id"),
                "candidate_count": (report.get("manifest") or {}).get("candidate_count"),
                "baseline_path": (report.get("manifest") or {}).get("baseline_path"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
