from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_overlay import (  # noqa: E402
    DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    DEFAULT_RING_OUTCOME_REVIEW_PATH,
    build_ring_outcome_overlay_review_template,
    update_ring_outcome_overlay_review,
    write_ring_outcome_overlay_review_template,
)
from localmedchem.ring_outcome_replay import DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_PATH  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or update reviewer decisions for ring outcome scoring overlay contexts.")
    parser.add_argument("--overlay", default=str(ROOT / DEFAULT_RING_OUTCOME_OVERLAY_PATH))
    parser.add_argument("--replay", default=str(ROOT / DEFAULT_RING_OUTCOME_OVERLAY_REPLAY_PATH))
    parser.add_argument("--review-out", default=str(ROOT / DEFAULT_RING_OUTCOME_REVIEW_PATH))
    parser.add_argument("--write-template", action="store_true")
    parser.add_argument("--context-id", default="")
    parser.add_argument("--decision", choices=["pending_review", "approved", "rejected", "deferred"], default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--approved-score-adjustment", default="")
    parser.add_argument("--no-replay-required", action="store_true")
    args = parser.parse_args()

    if args.write_template or not args.context_id:
        report = build_ring_outcome_overlay_review_template(
            args.overlay,
            review_path=args.review_out,
            replay=args.replay,
        )
        write_ring_outcome_overlay_review_template(report, args.review_out)
        print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2, sort_keys=True))
        return

    report = update_ring_outcome_overlay_review(
        args.context_id,
        decision=args.decision,
        reviewer=args.reviewer,
        review_note=args.note,
        approved_score_adjustment=args.approved_score_adjustment or None,
        review_path=args.review_out,
        overlay=args.overlay,
        replay=args.replay,
        require_replay=not args.no_replay_required,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
