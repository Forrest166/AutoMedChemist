from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.residual_profile_adjustments import (  # noqa: E402
    APPROVED_DECISIONS,
    build_residual_adjustment_review_template,
    build_residual_profile_adjustment_document,
    load_residual_adjustment_reviews,
    write_residual_adjusted_profile,
    write_residual_adjustment_reviews,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote approved endpoint-family residual adjustments into a scoring profile.")
    parser.add_argument("--model", default=str(ROOT / "data" / "substituents" / "endpoint_family_residual_model.json"))
    parser.add_argument("--base-profile", default=str(ROOT / "data" / "profiles" / "evidence_weighted.yaml"))
    parser.add_argument("--reviews", default=str(ROOT / "data" / "profiles" / "calibrated" / "endpoint_family_residual_adjustment_reviews.csv"))
    parser.add_argument("--profile-out", default=str(ROOT / "data" / "profiles" / "evidence_weighted_residual_adjusted.yaml"))
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--min-confidence", default="medium")
    parser.add_argument("--min-abs-score-shift", type=float, default=1.0)
    parser.add_argument("--auto-approve-medium", action="store_true", help="Demo/CI shortcut; production use should fill and approve the review CSV.")
    parser.add_argument("--write-review-template-only", action="store_true", help="Write reviewer sign-off rows and stop before applying a profile.")
    parser.add_argument("--overwrite-reviews", action="store_true", help="Allow --write-review-template-only to replace an existing review CSV.")
    parser.add_argument("--require-approved-reviews", action="store_true", help="Fail unless at least one signed-off review row is approved.")
    parser.add_argument("--report-out", default=str(ROOT / "data" / "profiles" / "calibrated" / "endpoint_family_residual_adjustment_apply_report.json"))
    args = parser.parse_args()

    model = json.loads(Path(args.model).read_text(encoding="utf-8"))
    base_profile = yaml.safe_load(Path(args.base_profile).read_text(encoding="utf-8")) or {}
    review_path = Path(args.reviews)
    create_review_template = args.auto_approve_medium or not review_path.exists() or (args.write_review_template_only and args.overwrite_reviews)
    if create_review_template:
        review_rows = build_residual_adjustment_review_template(
            model,
            reviewer=args.reviewer,
            min_confidence=args.min_confidence,
            min_abs_score_shift=args.min_abs_score_shift,
            auto_decision="approved" if args.auto_approve_medium else "",
        )
        write_residual_adjustment_reviews(review_rows, args.reviews)
        if args.write_review_template_only:
            report = {
                "status": "review_template_written",
                "reviews": str(review_path.resolve()),
                "review_row_count": len(review_rows),
                "next_command": "python scripts/apply_endpoint_family_residual_adjustments.py --require-approved-reviews",
            }
            Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            print(json.dumps(report, indent=2, sort_keys=True))
            return
    if args.write_review_template_only:
        reviews = load_residual_adjustment_reviews(args.reviews)
        report = {
            "status": "review_template_exists",
            "reviews": str(review_path.resolve()),
            "review_row_count": len(reviews),
            "profile_written": False,
            "note": "Existing review CSV preserved; use --overwrite-reviews to regenerate it.",
        }
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    reviews = load_residual_adjustment_reviews(args.reviews)
    approved_review_count = sum(
        1
        for review in reviews
        if str(review.get("review_decision") or review.get("decision") or "").strip().lower() in APPROVED_DECISIONS
    )
    if args.require_approved_reviews and approved_review_count == 0:
        report = {
            "status": "review_required",
            "reviews": str(review_path.resolve()),
            "review_row_count": len(reviews),
            "approved_review_count": 0,
            "profile_written": False,
        }
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit("No approved residual adjustment reviews found; fill review_decision=approved before applying.")
    profile = build_residual_profile_adjustment_document(
        model,
        reviews=reviews,
        base_profile=base_profile,
        reviewer=args.reviewer,
        min_confidence=args.min_confidence,
        min_abs_score_shift=args.min_abs_score_shift,
    )
    write_residual_adjusted_profile(profile, args.profile_out)
    config = profile.get("endpoint_family_residual_adjustments") or {}
    report = {
        "status": "applied" if config.get("applied_count") else "no_approved_adjustments_applied",
        "profile_out": str(Path(args.profile_out).resolve()),
        "reviews": str(Path(args.reviews).resolve()),
        "review_row_count": len(reviews),
        "approved_review_count": approved_review_count,
        "applied_count": config.get("applied_count"),
        "profile_id": profile.get("profile_id"),
    }
    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
