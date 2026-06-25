from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_promotion_registry import (  # noqa: E402
    build_profile_promotion_record,
    register_profile_promotion,
    update_profile_promotion_status,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register or update a scoring-profile/policy promotion decision.")
    parser.add_argument("--artifact", default=str(ROOT / "data" / "profiles" / "evidence_weighted_residual_adjusted.yaml"))
    parser.add_argument("--artifact-type", default="scoring_profile")
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--status", default="review_requested")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--note", default="")
    parser.add_argument("--registry", default=str(ROOT / "data" / "profiles" / "profile_promotion_registry.json"))
    parser.add_argument("--promotion-id", default="", help="When provided, update an existing record instead of registering a new one.")
    args = parser.parse_args()

    if args.promotion_id:
        registry = update_profile_promotion_status(
            args.promotion_id,
            status=args.status,
            registry_path=args.registry,
            reviewer=args.reviewer or None,
            note=args.note or None,
        )
        action = "updated"
        record = next((row for row in registry.get("records") or [] if row.get("promotion_id") == args.promotion_id), {})
    else:
        record = build_profile_promotion_record(
            artifact_path=args.artifact,
            root=ROOT,
            artifact_type=args.artifact_type,
            project_name=args.project_name or None,
            promotion_status=args.status,
            reviewer=args.reviewer or None,
            note=args.note or None,
        )
        registry = register_profile_promotion(record, registry_path=args.registry)
        action = "registered"
    print(
        json.dumps(
            {
                "action": action,
                "promotion_id": record.get("promotion_id"),
                "artifact_id": record.get("artifact_id"),
                "promotion_status": record.get("promotion_status"),
                "registry": str(Path(args.registry).resolve()),
                "record_count": registry.get("record_count"),
                "status_counts": registry.get("status_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
