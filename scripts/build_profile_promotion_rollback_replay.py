from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_promotion_rollback_replay import (  # noqa: E402
    build_profile_promotion_rollback_replay,
    write_profile_promotion_rollback_replay,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a dry-run profile promotion rollback replay.")
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--queue", default="")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_promotion_rollback_replay.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_promotion_rollback_replay.csv"))
    args = parser.parse_args()
    report = build_profile_promotion_rollback_replay(
        root=ROOT,
        project_name=args.project_name or None,
        queue_path=args.queue or None,
    )
    write_profile_promotion_rollback_replay(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in [
                    "status",
                    "row_count",
                    "queue_linked_count",
                    "max_abs_rollback_score_delta",
                    "max_abs_rollback_rank_delta",
                    "rollback_action_counts",
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
