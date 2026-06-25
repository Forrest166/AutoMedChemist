from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_value_policy_proposal import build_evidence_value_policy_replay, write_evidence_value_policy_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a proposed evidence-value policy before manual activation.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--proposal-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_proposal.json"))
    parser.add_argument("--evidence-value-path", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_report.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_replay.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "evidence_value_policy_replay.csv"))
    args = parser.parse_args()
    report = build_evidence_value_policy_replay(
        root=args.root,
        project_name=args.project_name or None,
        proposal_path=args.proposal_path,
        evidence_value_path=args.evidence_value_path,
    )
    write_evidence_value_policy_replay(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "activation_gate_status": report.get("activation_gate_status"),
                "row_count": report.get("row_count"),
                "top_n_change_count": report.get("top_n_change_count"),
                "max_abs_score_delta": report.get("max_abs_score_delta"),
                "max_abs_rank_delta": report.get("max_abs_rank_delta"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
