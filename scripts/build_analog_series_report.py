from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.analog_series import build_analog_series_report, write_analog_series_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build analog-series summaries from candidates, novelty batch, decision packets, and outcomes.")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--decision-packet", default=None)
    parser.add_argument("--candidate-limit", type=int, default=5000)
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "analog_series_report.json"))
    args = parser.parse_args()

    report = build_analog_series_report(
        candidates_csv=args.candidates_csv,
        db_path=args.db_path,
        project_name=args.project_name,
        decision_packet_path=args.decision_packet,
        candidate_limit=args.candidate_limit,
    )
    write_analog_series_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
