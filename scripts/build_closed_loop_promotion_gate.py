from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.promotion_gate import build_closed_loop_promotion_gate, write_closed_loop_promotion_gate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the closed-loop promotion gate report.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--min-queue-alignment-rate", type=float, default=0.6)
    parser.add_argument("--min-rank-lift-delta", type=float, default=-0.02)
    parser.add_argument("--allow-open-residual-plans", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "closed_loop_promotion_gate.json"))
    args = parser.parse_args()

    report = build_closed_loop_promotion_gate(
        root=args.root,
        project_name=args.project_name or None,
        min_queue_alignment_rate=args.min_queue_alignment_rate,
        min_rank_lift_delta=args.min_rank_lift_delta,
        allow_open_residual_plans=args.allow_open_residual_plans,
    )
    write_closed_loop_promotion_gate(report, args.output)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "promotion_status": report.get("promotion_status"),
                "block_count": report.get("block_count"),
                "review_count": report.get("review_count"),
                "pass_count": report.get("pass_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
