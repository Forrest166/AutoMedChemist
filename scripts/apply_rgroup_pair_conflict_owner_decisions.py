from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_pair_contradictions import (  # noqa: E402
    build_rgroup_pair_conflict_owner_decision_ledger,
    build_rgroup_pair_conflict_owner_review_packet,
    write_rgroup_pair_conflict_owner_decision_ledger,
    write_rgroup_pair_conflict_owner_review_packet,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and optionally apply source-owner decisions for deferred pair conflicts.")
    parser.add_argument("--packet", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_review_packet.json"))
    parser.add_argument("--review-path", default=str(ROOT / "data/substituents/rgroup_normalized_pair_contradiction_reviews.csv"))
    parser.add_argument("--contradiction-report", default=str(ROOT / "data/substituents/rgroup_normalized_pair_contradictions.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.csv"))
    parser.add_argument("--packet-json-out", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_review_packet.json"))
    parser.add_argument("--packet-csv-out", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_review_packet.csv"))
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--mark-all-keep-deferred", action="store_true")
    parser.add_argument("--apply-to-reviews", action="store_true")
    parser.add_argument("--fail-on-pending", action="store_true")
    args = parser.parse_args()

    ledger = build_rgroup_pair_conflict_owner_decision_ledger(
        args.packet,
        reviewer=args.reviewer,
        mark_all_keep_deferred=args.mark_all_keep_deferred,
        apply_to_reviews=args.apply_to_reviews,
        review_path=args.review_path,
        contradiction_report=args.contradiction_report,
    )
    write_rgroup_pair_conflict_owner_decision_ledger(ledger, json_path=args.json_out, csv_path=args.csv_out)
    packet = build_rgroup_pair_conflict_owner_review_packet(args.contradiction_report, review_path=args.review_path, owner_decision_ledger_path=args.csv_out)
    write_rgroup_pair_conflict_owner_review_packet(packet, json_path=args.packet_json_out, csv_path=args.packet_csv_out)
    print(json.dumps(ledger, indent=2, sort_keys=True))
    if args.fail_on_pending and ledger.get("pending_owner_review_count"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
