from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_baselines import archive_candidate_baseline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive a local named candidate baseline without deleting its files.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--note", default="Archived from native baseline manager.")
    args = parser.parse_args()
    report = archive_candidate_baseline(
        root=args.root,
        project_name=args.project_name,
        baseline_id=args.baseline_id,
        note=args.note,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") == "missing_baseline":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
