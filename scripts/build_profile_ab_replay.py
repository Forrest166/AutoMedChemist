from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.profile_ab_replay import build_profile_ab_replay_report, write_profile_ab_replay_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay candidate generation under two scoring profiles and compare ranking effects.")
    parser.add_argument("--smiles", default="COc1ccc(Cl)cc1")
    parser.add_argument("--direction", default="increase_polarity")
    parser.add_argument("--base-profile", default=str(ROOT / "data" / "profiles" / "evidence_weighted.yaml"))
    parser.add_argument("--candidate-profile", default=str(ROOT / "data" / "profiles" / "evidence_weighted_residual_adjusted.yaml"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--target-family", default="")
    parser.add_argument("--assay-type", default="")
    parser.add_argument("--site-index", type=int, default=0)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=80)
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_replay_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "profile_ab_replay_report.csv"))
    args = parser.parse_args()

    target_context = {
        key: value
        for key, value in {
            "endpoint_group": args.endpoint,
            "target_family": args.target_family,
            "assay_type": args.assay_type,
        }.items()
        if value
    }
    report = build_profile_ab_replay_report(
        smiles=args.smiles,
        direction=args.direction,
        base_profile_path=args.base_profile,
        candidate_profile_path=args.candidate_profile,
        project_name=args.project_name or None,
        target_context=target_context or None,
        site_index=args.site_index,
        top_n=args.top_n,
        max_candidates=args.max_candidates,
    )
    write_profile_ab_replay_report(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "csv_out": str(Path(args.csv_out).resolve()) if args.csv_out else None,
                "status": report.get("status"),
                "review_status": report.get("review_status"),
                "base_profile_id": report.get("base_profile_id"),
                "candidate_profile_id": report.get("candidate_profile_id"),
                "changed_top_n_count": report.get("changed_top_n_count"),
                "max_score_delta": report.get("max_score_delta"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
