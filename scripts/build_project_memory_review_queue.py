from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_memory_review_queue import build_project_memory_review_queue, write_project_memory_review_queue  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a consolidated Project Memory review queue.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "project_memory_review_queue.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "project_memory_review_queue.csv"))
    args = parser.parse_args()
    report = build_project_memory_review_queue(root=args.root, project_name=args.project_name or None)
    write_project_memory_review_queue(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "policy_activation_gate_status": report.get("policy_activation_gate_status"),
                "measurement_open_gap_count": report.get("measurement_open_gap_count"),
                "sar_deferred_reference_only_count": report.get("sar_deferred_reference_only_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
