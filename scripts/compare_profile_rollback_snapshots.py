from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_rollback_history import compare_profile_rollback_snapshots, write_profile_rollback_snapshot_compare  # noqa: E402


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    return json.loads(json_path.read_text(encoding="utf-8")) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two profile rollback history snapshots.")
    parser.add_argument("--history-path", default=str(ROOT / "data" / "projects" / "demo" / "profile_rollback_history.json"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--base-snapshot-id", default="")
    parser.add_argument("--head-snapshot-id", default="")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_rollback_snapshot_compare.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_rollback_snapshot_compare.csv"))
    args = parser.parse_args()

    history = _read_json(args.history_path)
    report = compare_profile_rollback_snapshots(
        history,
        base_snapshot_id=args.base_snapshot_id or None,
        head_snapshot_id=args.head_snapshot_id or None,
        project_name=args.project_name or None,
    )
    write_profile_rollback_snapshot_compare(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "base_snapshot_id": report.get("base_snapshot_id"),
                "head_snapshot_id": report.get("head_snapshot_id"),
                "shared_candidate_count": report.get("shared_candidate_count"),
                "changed_candidate_count": report.get("changed_candidate_count"),
                "added_candidate_count": report.get("added_candidate_count"),
                "removed_candidate_count": report.get("removed_candidate_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
