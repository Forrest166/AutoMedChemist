from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_replay import (  # noqa: E402
    build_ring_outcome_overlay_replay,
    write_ring_outcome_overlay_replay,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay ring-outcome scoring overlay effects before activation.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--overlay", default=str(ROOT / "data" / "profiles" / "calibrated" / "ring_outcome_scoring_overlay.json"))
    parser.add_argument("--candidate-glob", action="append", default=None, help="Candidate CSV glob relative to --root.")
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "ring_outcome_overlay_replay.csv"))
    args = parser.parse_args()

    report = build_ring_outcome_overlay_replay(
        root=args.root,
        overlay_path=args.overlay,
        candidate_globs=args.candidate_glob,
    )
    write_ring_outcome_overlay_replay(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
