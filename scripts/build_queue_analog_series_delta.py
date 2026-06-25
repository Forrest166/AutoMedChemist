from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.analog_series import build_queue_analog_series_delta, write_queue_analog_series_delta_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize closed-loop priority deltas at analog-series level.")
    parser.add_argument("--priority-delta", default=str(ROOT / "data" / "projects" / "closed_loop" / "priority_delta_demo_learning.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "closed_loop" / "queue_analog_series_delta.json"))
    args = parser.parse_args()

    report = json.loads(Path(args.priority_delta).read_text(encoding="utf-8"))
    series_delta = build_queue_analog_series_delta(report)
    write_queue_analog_series_delta_report(series_delta, args.json_out)
    print(
        json.dumps(
            {
                "candidate_count": series_delta.get("candidate_count", 0),
                "series_count": series_delta.get("series_count", 0),
                "json_out": str(Path(args.json_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
