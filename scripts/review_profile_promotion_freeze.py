from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.promotion_freeze_approval import review_profile_promotion_freeze, rollback_profile_promotion_freeze  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve, reject, defer, or roll back a profile promotion freeze.")
    parser.add_argument("--freeze-manifest", default=str(ROOT / "data" / "projects" / "demo" / "profile_promotion_freeze_manifest.json"))
    parser.add_argument("--status", default="approved", choices=["approved", "rejected", "deferred", "draft", "rolled_back"])
    parser.add_argument("--rollback-freeze-id", default="")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--note", default="")
    parser.add_argument("--release-tag", default="")
    args = parser.parse_args()
    if args.status == "rolled_back":
        if not args.rollback_freeze_id:
            raise SystemExit("--rollback-freeze-id is required when --status rolled_back")
        report = rollback_profile_promotion_freeze(args.rollback_freeze_id, reviewer=args.reviewer, note=args.note or None)
    else:
        report = review_profile_promotion_freeze(
            freeze_manifest_path=args.freeze_manifest,
            approval_status=args.status,
            reviewer=args.reviewer,
            note=args.note or None,
            release_tag=args.release_tag or None,
        )
    event = report.get("event") or {}
    registry = report.get("registry") or {}
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "freeze_id": event.get("freeze_id"),
                "release_tag": event.get("release_tag"),
                "active_freeze_id": registry.get("active_freeze_id"),
                "event_count": registry.get("event_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
