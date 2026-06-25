from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.public_sar_contradiction_triage import (  # noqa: E402
    build_public_sar_contradiction_triage,
    write_public_sar_contradiction_triage,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build contradiction-driven public SAR triage tasks.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.csv"))
    parser.add_argument("--max-rows", type=int, default=80)
    args = parser.parse_args()

    report = build_public_sar_contradiction_triage(
        root=args.root,
        project_name=args.project_name or None,
        max_rows=args.max_rows,
    )
    write_public_sar_contradiction_triage(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "high_priority_count": report.get("high_priority_count"),
                "candidate_linked_count": report.get("candidate_linked_count"),
                "net_contradicted_count": report.get("net_contradicted_count"),
                "triage_action_counts": report.get("triage_action_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
