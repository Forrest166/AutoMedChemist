from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_memory_refresh import refresh_project_memory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh project memory evidence, SAR, profile replay, gates, and smoke reports.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--package-iteration", action="store_true")
    parser.add_argument("--allow-historical-experiment-feedback", action="store_true")
    args = parser.parse_args()

    report = refresh_project_memory(
        root=args.root,
        project_name=args.project_name or None,
        db_path=args.db_path,
        package_iteration=args.package_iteration,
        allow_historical_experiment_feedback=args.allow_historical_experiment_feedback,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
