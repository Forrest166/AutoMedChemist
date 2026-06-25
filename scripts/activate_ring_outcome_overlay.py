from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_overlay import (  # noqa: E402
    DEFAULT_RING_OUTCOME_ACTIVATION_PATH,
    DEFAULT_RING_OUTCOME_ACTIVE_SNAPSHOT_PATH,
    DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    DEFAULT_RING_OUTCOME_REVIEW_PATH,
    build_ring_outcome_overlay_activation_report,
    write_ring_outcome_overlay_activation_report,
)
from localmedchem.ring_outcome_replay import DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_PATH  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the activation gate for approved ring outcome scoring overlays.")
    parser.add_argument("--overlay", default=str(ROOT / DEFAULT_RING_OUTCOME_OVERLAY_PATH))
    parser.add_argument("--replay", default=str(ROOT / DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_PATH))
    parser.add_argument("--reviews", default=str(ROOT / DEFAULT_RING_OUTCOME_REVIEW_PATH))
    parser.add_argument("--json-out", default=str(ROOT / DEFAULT_RING_OUTCOME_ACTIVATION_PATH))
    parser.add_argument("--active-snapshot-out", default=str(ROOT / DEFAULT_RING_OUTCOME_ACTIVE_SNAPSHOT_PATH))
    parser.add_argument("--max-abs-score-delta", type=float, default=5.0)
    parser.add_argument("--max-abs-rank-delta", type=int, default=50)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_ring_outcome_overlay_activation_report(
        args.overlay,
        replay=args.replay,
        review_path=args.reviews,
        max_abs_score_delta=args.max_abs_score_delta,
        max_abs_rank_delta=args.max_abs_rank_delta,
    )
    write_ring_outcome_overlay_activation_report(
        report,
        json_path=args.json_out,
        active_snapshot_path=args.active_snapshot_out,
    )
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") != "activated":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
