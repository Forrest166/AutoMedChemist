from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.residual_profile_adjustments import (  # noqa: E402
    build_residual_adjustment_review_template,
    write_residual_adjustment_reviews,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build project evidence-gap score-profile adjustment candidates for manual review.")
    parser.add_argument("--evidence-pack", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_pack.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "profiles" / "calibrated" / "project_evidence_gap_adjustment_candidates.csv"))
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--min-confidence", default="medium")
    parser.add_argument("--min-abs-score-shift", type=float, default=1.0)
    args = parser.parse_args()

    pack = json.loads(Path(args.evidence_pack).read_text(encoding="utf-8"))
    rows = build_residual_adjustment_review_template(
        pack,
        reviewer=args.reviewer,
        min_confidence=args.min_confidence,
        min_abs_score_shift=args.min_abs_score_shift,
        auto_decision="",
    )
    write_residual_adjustment_reviews(rows, args.output)
    print(
        json.dumps(
            {
                "status": "written",
                "candidate_count": len(rows),
                "output": str(Path(args.output).resolve()),
                "evidence_pack": str(Path(args.evidence_pack).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
