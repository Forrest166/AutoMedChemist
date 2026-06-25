from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_holdout import build_ring_outcome_holdout_report, write_ring_outcome_holdout_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build endpoint-level ring outcome holdout readiness report.")
    parser.add_argument("--learning", default=str(ROOT / "data/projects/demo/ring_outcome_learning_report.json"))
    parser.add_argument("--overlay", default=str(ROOT / "data/profiles/calibrated/ring_outcome_scoring_overlay.json"))
    parser.add_argument("--replay", default=str(ROOT / "data/projects/demo/ring_outcome_overlay_replay.json"))
    parser.add_argument("--activation", default=str(ROOT / "data/profiles/calibrated/ring_outcome_overlay_activation.json"))
    parser.add_argument("--readiness", default=str(ROOT / "data/projects/demo/ring_outcome_production_readiness.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data/projects/demo/ring_outcome_holdout_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/projects/demo/ring_outcome_holdout_report.csv"))
    parser.add_argument("--max-abs-rank-delta", type=int, default=50)
    parser.add_argument("--max-abs-score-delta", type=float, default=5.0)
    parser.add_argument("--fail-on-review-required", action="store_true")
    args = parser.parse_args()

    report = build_ring_outcome_holdout_report(
        learning_path=args.learning,
        overlay_path=args.overlay,
        replay_path=args.replay,
        activation_path=args.activation,
        readiness_path=args.readiness,
        max_abs_rank_delta=args.max_abs_rank_delta,
        max_abs_score_delta=args.max_abs_score_delta,
    )
    write_ring_outcome_holdout_report(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_review_required and report.get("status") in {"holdout_review_required"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
