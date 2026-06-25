from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_overlay import (  # noqa: E402
    DEFAULT_RING_OUTCOME_OVERLAY_CSV_PATH,
    DEFAULT_RING_OUTCOME_OVERLAY_PATH,
    DEFAULT_RING_OUTCOME_REPORT_PATH,
    DEFAULT_RING_OUTCOME_REVIEW_PATH,
    DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH,
    build_ring_outcome_scoring_overlay,
    write_ring_outcome_scoring_overlay,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reviewer-gated scoring overlays from ring outcome learning.")
    parser.add_argument("--report", default=str(ROOT / DEFAULT_RING_OUTCOME_REPORT_PATH))
    parser.add_argument("--review-in", default=str(ROOT / DEFAULT_RING_OUTCOME_REVIEW_PATH))
    parser.add_argument("--policy", default=str(ROOT / DEFAULT_RING_OUTCOME_MATURATION_POLICY_PATH))
    parser.add_argument("--json-out", default=str(ROOT / DEFAULT_RING_OUTCOME_OVERLAY_PATH))
    parser.add_argument("--csv-out", default=str(ROOT / DEFAULT_RING_OUTCOME_OVERLAY_CSV_PATH))
    parser.add_argument("--min-observed", type=int, default=3)
    parser.add_argument("--no-review-gate", action="store_true")
    args = parser.parse_args()

    overlay = build_ring_outcome_scoring_overlay(
        args.report,
        review_path=args.review_in,
        policy_path=args.policy,
        min_observed=args.min_observed,
        require_approved_review=not args.no_review_gate,
    )
    write_ring_outcome_scoring_overlay(overlay, json_path=args.json_out, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "context_count": overlay.get("context_count"),
                "active_context_count": overlay.get("active_context_count"),
                "blocked_context_count": overlay.get("blocked_context_count"),
                "min_observed": overlay.get("min_observed"),
                "require_approved_review": overlay.get("require_approved_review"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
