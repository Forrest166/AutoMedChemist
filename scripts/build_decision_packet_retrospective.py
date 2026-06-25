from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.decision_packet import build_decision_packet_retrospective, write_decision_packet_retrospective  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a retrospective report for saved medchem decision packets.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--packet-id", default=None)
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "decision_packet_retrospective.json"))
    args = parser.parse_args()

    report = build_decision_packet_retrospective(
        db_path=args.db,
        project_name=args.project_name,
        packet_id=args.packet_id,
    )
    write_decision_packet_retrospective(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
