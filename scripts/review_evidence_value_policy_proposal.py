from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_value_policy_proposal import review_evidence_value_policy_proposal, write_evidence_value_policy_proposal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Review an evidence-value policy proposal without activating it automatically.")
    parser.add_argument("--proposal-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.csv"))
    parser.add_argument("--decision", required=True, choices=["pending_review", "approved", "rejected", "deferred"])
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    report = review_evidence_value_policy_proposal(
        proposal_path=args.proposal_path,
        decision=args.decision,
        reviewer=args.reviewer or None,
        note=args.note or None,
    )
    write_evidence_value_policy_proposal(report, args.proposal_path, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "proposal_id": report.get("proposal_id"),
                "approval_status": report.get("approval_status"),
                "activation_status": report.get("activation_status"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
