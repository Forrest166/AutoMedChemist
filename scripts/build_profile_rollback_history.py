from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_rollback_history import build_profile_rollback_history, write_profile_rollback_history  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build multi-freeze and multi-iteration profile rollback history.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_rollback_history.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_rollback_history.csv"))
    parser.add_argument("--candidate-csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_rollback_candidate_history.csv"))
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    report = build_profile_rollback_history(root=args.root, project_name=args.project_name or None, limit=args.limit)
    write_profile_rollback_history(report, args.output, csv_path=args.csv_out, candidate_csv_path=args.candidate_csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "snapshot_count": report.get("snapshot_count"),
                "candidate_history_count": report.get("candidate_history_count"),
                "snapshot_type_counts": report.get("snapshot_type_counts"),
                "snapshot_status_counts": report.get("snapshot_status_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
