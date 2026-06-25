from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.public_sar_contradiction_triage import (  # noqa: E402
    apply_public_sar_contradiction_resolution_batch,
    write_public_sar_contradiction_resolution_batch,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply first-pass SAR contradiction resolution policy to high-priority open rows.")
    parser.add_argument("--triage-path", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.json"))
    parser.add_argument("--triage-csv-out", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.csv"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_resolution_batch.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_resolution_batch.csv"))
    parser.add_argument("--priority", default="high")
    parser.add_argument("--reviewer", default="sar_resolution_policy_v1")
    parser.add_argument("--overwrite-existing", action="store_true")
    args = parser.parse_args()

    result = apply_public_sar_contradiction_resolution_batch(
        triage_path=args.triage_path,
        csv_path=args.triage_csv_out,
        priority=args.priority,
        reviewer=args.reviewer,
        overwrite_existing=args.overwrite_existing,
    )
    batch = result.get("batch_report") or {}
    write_public_sar_contradiction_resolution_batch(batch, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": batch.get("status"),
                "processed_count": batch.get("processed_count"),
                "candidate_measurement_gated_count": batch.get("candidate_measurement_gated_count"),
                "reference_only_watch_count": batch.get("reference_only_watch_count"),
                "resolution_status_counts": batch.get("resolution_status_counts"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
