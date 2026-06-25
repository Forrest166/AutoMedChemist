from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_onboarding import (  # noqa: E402
    build_rgroup_feed_onboarding_gate,
    write_rgroup_feed_onboarding_gate,
    write_rgroup_feed_onboarding_template,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the R-group feed onboarding gate and CSV template.")
    parser.add_argument("--feed-dir", default=str(ROOT / "data/replacements/feeds"))
    parser.add_argument("--manifest", default=str(ROOT / "data/replacements/feed_source_manifest.yaml"))
    parser.add_argument("--metadata-report", default=str(ROOT / "data/substituents/rgroup_feed_metadata_report.json"))
    parser.add_argument("--review-coverage", default=str(ROOT / "data/substituents/rgroup_feed_review_coverage.json"))
    parser.add_argument("--pair-decisions", default=str(ROOT / "data/substituents/rgroup_normalized_pair_contradiction_decisions.json"))
    parser.add_argument("--owner-packet", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_review_packet.json"))
    parser.add_argument("--next-drop-label", default="next_rgroup_feed_drop")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_feed_onboarding_gate.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_feed_onboarding_gate.csv"))
    parser.add_argument("--template-out", default=str(ROOT / "data/replacements/feed_onboarding_template.csv"))
    parser.add_argument("--include-template-example", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    template = write_rgroup_feed_onboarding_template(args.template_out, include_example=args.include_template_example)
    report = build_rgroup_feed_onboarding_gate(
        feed_dir=args.feed_dir,
        manifest_path=args.manifest,
        metadata_report_path=args.metadata_report,
        review_coverage_path=args.review_coverage,
        pair_decision_summary_path=args.pair_decisions,
        pair_owner_packet_path=args.owner_packet,
        next_drop_label=args.next_drop_label,
    )
    report["template"] = template
    report["onboarding_template_path"] = template["path"]
    write_rgroup_feed_onboarding_gate(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
