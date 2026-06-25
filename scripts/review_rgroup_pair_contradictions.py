from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_pair_contradictions import (  # noqa: E402
    DEFAULT_CONTRADICTION_DECISION_SUMMARY_PATH,
    DEFAULT_CONTRADICTION_REPORT_PATH,
    DEFAULT_CONTRADICTION_REVIEW_PATH,
    apply_rgroup_pair_contradiction_first_pass,
    build_rgroup_pair_contradiction_decision_summary,
    build_rgroup_pair_contradiction_review_template,
    update_rgroup_pair_contradiction_review,
    write_rgroup_pair_contradiction_decision_summary,
    write_rgroup_pair_contradiction_review_template,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Review and classify normalized-pair contradiction rows.")
    parser.add_argument("--report", default=str(ROOT / DEFAULT_CONTRADICTION_REPORT_PATH))
    parser.add_argument("--review-out", default=str(ROOT / DEFAULT_CONTRADICTION_REVIEW_PATH))
    parser.add_argument("--summary-out", default=str(ROOT / DEFAULT_CONTRADICTION_DECISION_SUMMARY_PATH))
    parser.add_argument("--write-template", action="store_true", help="Write or refresh the CSV review template.")
    parser.add_argument("--first-pass", action="store_true", help="Apply conservative first-pass decisions to pending rows.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing decisions when running --first-pass.")
    parser.add_argument("--conflict-id", default="")
    parser.add_argument("--decision", default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--resolution-class", default="")
    parser.add_argument("--score-policy-action", default="")
    parser.add_argument("--source-confidence-action", default="")
    args = parser.parse_args()

    if args.write_template:
        template = build_rgroup_pair_contradiction_review_template(args.report, review_path=args.review_out)
        write_rgroup_pair_contradiction_review_template(template, args.review_out)
        summary = build_rgroup_pair_contradiction_decision_summary(template, review_path=args.review_out)
        write_rgroup_pair_contradiction_decision_summary(summary, args.summary_out)
        print(json.dumps({key: value for key, value in template.items() if key != "rows"}, indent=2, sort_keys=True))
        return

    if args.first_pass:
        summary = apply_rgroup_pair_contradiction_first_pass(
            args.report,
            reviewer=args.reviewer or "first_pass_pair_conflict_triage",
            review_path=args.review_out,
            overwrite=args.overwrite,
        )
        write_rgroup_pair_contradiction_decision_summary(summary, args.summary_out)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    if args.conflict_id:
        update = update_rgroup_pair_contradiction_review(
            args.conflict_id,
            decision=args.decision,
            reviewer=args.reviewer,
            review_note=args.note,
            resolution_class=args.resolution_class,
            score_policy_action=args.score_policy_action,
            source_confidence_action=args.source_confidence_action,
            review_path=args.review_out,
            report=args.report,
        )
        template = build_rgroup_pair_contradiction_review_template(args.report, review_path=args.review_out)
        summary = build_rgroup_pair_contradiction_decision_summary(template, review_path=args.review_out)
        write_rgroup_pair_contradiction_decision_summary(summary, args.summary_out)
        print(json.dumps({**update, "summary_status": summary.get("status")}, indent=2, sort_keys=True))
        return

    summary = build_rgroup_pair_contradiction_decision_summary(args.report, review_path=args.review_out)
    write_rgroup_pair_contradiction_decision_summary(summary, args.summary_out)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
