from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_value_policy_proposal import (  # noqa: E402
    activate_evidence_value_policy_proposal,
    write_evidence_value_policy_activation,
    write_evidence_value_policy_proposal,
    write_evidence_value_policy_replay,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manually activate an approved evidence-value policy proposal after replay gate passes.")
    parser.add_argument("--proposal-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.json"))
    parser.add_argument("--replay-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_replay.json"))
    parser.add_argument("--active-policy-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_active.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_activation.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_activation.csv"))
    parser.add_argument("--proposal-csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.csv"))
    parser.add_argument("--replay-csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_replay.csv"))
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    report = activate_evidence_value_policy_proposal(
        proposal_path=args.proposal_path,
        replay_path=args.replay_path,
        active_policy_path=args.active_policy_path,
        activation_path=args.output,
        reviewer=args.reviewer or None,
        note=args.note or None,
    )
    write_evidence_value_policy_activation(report, args.output, csv_path=args.csv_out)
    if Path(args.proposal_path).exists():
        proposal = json.loads(Path(args.proposal_path).read_text(encoding="utf-8"))
        write_evidence_value_policy_proposal(proposal, args.proposal_path, csv_path=args.proposal_csv_out)
    if Path(args.replay_path).exists():
        replay = json.loads(Path(args.replay_path).read_text(encoding="utf-8"))
        write_evidence_value_policy_replay(replay, args.replay_path, csv_path=args.replay_csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "proposal_id": report.get("proposal_id"),
                "activation_status": report.get("activation_status"),
                "activation_gate_status": report.get("activation_gate_status"),
                "activated_policy_version": report.get("activated_policy_version"),
                "blocked_reasons": report.get("blocked_reasons"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
