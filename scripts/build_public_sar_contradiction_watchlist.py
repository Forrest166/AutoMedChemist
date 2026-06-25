from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.public_sar_contradiction_triage import build_public_sar_contradiction_watchlist, write_public_sar_contradiction_watchlist  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build actionable watchlist for unresolved public SAR contradictions with project overlap.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--triage-path", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_triage.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_watchlist.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "public_sar_contradiction_watchlist.csv"))
    args = parser.parse_args()
    report = build_public_sar_contradiction_watchlist(root=args.root, project_name=args.project_name or None, triage_path=args.triage_path)
    write_public_sar_contradiction_watchlist(report, args.output, csv_path=args.csv_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "open_unresolved_count": report.get("open_unresolved_count"),
                "actionable_count": report.get("actionable_count"),
                "deferred_reference_only_count": report.get("deferred_reference_only_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
