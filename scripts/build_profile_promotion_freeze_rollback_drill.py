from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.promotion_freeze_rollback_drill import (  # noqa: E402
    build_profile_promotion_freeze_rollback_drill,
    write_profile_promotion_freeze_rollback_drill,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a dry-run rollback drill for profile promotion freezes.")
    parser.add_argument("--target-freeze-id", default="")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_promotion_freeze_rollback_drill.json"))
    args = parser.parse_args()
    report = build_profile_promotion_freeze_rollback_drill(
        root=ROOT,
        target_freeze_id=args.target_freeze_id or None,
        reviewer=args.reviewer,
        execute=args.execute,
    )
    write_profile_promotion_freeze_rollback_drill(report, args.output)
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in [
                    "status",
                    "execution_mode",
                    "state_mutated",
                    "target_freeze_id",
                    "block_count",
                    "review_count",
                    "would_release_tag",
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
