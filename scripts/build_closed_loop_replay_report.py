from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.replay_validation import build_closed_loop_replay_report, write_closed_loop_replay_report  # noqa: E402


def _target_context(args: argparse.Namespace) -> dict:
    return {
        key: value
        for key, value in {
            "endpoint_group": args.endpoint_group,
            "target_family": args.target_family,
            "assay_type": args.assay_type,
        }.items()
        if value
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build holdout/replay validation for the closed-loop project.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--endpoint-group", default="")
    parser.add_argument("--target-family", default="")
    parser.add_argument("--assay-type", default="")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "closed_loop_replay_report.json"))
    args = parser.parse_args()

    report = build_closed_loop_replay_report(
        root=args.root,
        db_path=args.db_path,
        project_name=args.project_name or None,
        target_context=_target_context(args) or None,
    )
    write_closed_loop_replay_report(report, args.output)
    mo = report.get("multi_objective_holdout") or {}
    queue = report.get("queue_policy_replay") or {}
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "status": report.get("status"),
                "holdout_count": mo.get("holdout_count", 0),
                "rank_lift_delta": (mo.get("delta") or {}).get("rank_lift_delta"),
                "queue_alignment_rate": queue.get("alignment_rate"),
                "queue_actionable_series_count": queue.get("actionable_series_count", 0),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
