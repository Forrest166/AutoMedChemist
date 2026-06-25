from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_pair_contradictions import (  # noqa: E402
    build_rgroup_pair_conflict_owner_review_packet,
    write_rgroup_pair_conflict_owner_review_packet,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a source-owner review packet for deferred R-group pair conflicts.")
    parser.add_argument("--report", default=str(ROOT / "data/substituents/rgroup_normalized_pair_contradictions.json"))
    parser.add_argument("--review-path", default=str(ROOT / "data/substituents/rgroup_normalized_pair_contradiction_reviews.csv"))
    parser.add_argument("--owner-decision-ledger", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_decision_ledger.csv"))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_review_packet.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_pair_conflict_owner_review_packet.csv"))
    parser.add_argument("--fail-on-missing-review", action="store_true")
    args = parser.parse_args()

    packet = build_rgroup_pair_conflict_owner_review_packet(args.report, review_path=args.review_path, owner_decision_ledger_path=args.owner_decision_ledger)
    write_rgroup_pair_conflict_owner_review_packet(packet, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(packet, indent=2, sort_keys=True))
    if args.fail_on_missing_review and packet.get("status") != "owner_review_required":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
