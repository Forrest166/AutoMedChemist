from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.public_sar_contradiction_triage import update_public_sar_contradiction_resolution  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Update manual resolution status for a public SAR contradiction triage row.")
    parser.add_argument("triage_id")
    parser.add_argument("--resolution-status", required=True)
    parser.add_argument("--review-status", default="resolved")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--triage-path", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.csv"))
    args = parser.parse_args()

    report = update_public_sar_contradiction_resolution(
        args.triage_id,
        resolution_status=args.resolution_status,
        review_status=args.review_status,
        reviewer=args.reviewer or None,
        note=args.note or None,
        triage_path=args.triage_path,
        csv_path=args.csv_out,
    )
    print(json.dumps({key: report.get(key) for key in ["status", "triage_id", "event"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
