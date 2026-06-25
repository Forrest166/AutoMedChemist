from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.closed_loop_acceptance import (  # noqa: E402
    evaluate_closed_loop_drill_acceptance,
    write_closed_loop_drill_acceptance,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a closed-loop drill report against acceptance criteria.")
    parser.add_argument("--report", default=str(ROOT / "data" / "projects" / "closed_loop_drill" / "closed_loop_drill_report.json"))
    parser.add_argument("--criteria", default=str(ROOT / "data" / "rules" / "closed_loop_acceptance.yaml"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "closed_loop_drill" / "closed_loop_drill_acceptance.json"))
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    acceptance = evaluate_closed_loop_drill_acceptance(report, criteria_path=args.criteria)
    write_closed_loop_drill_acceptance(acceptance, args.json_out)
    print(json.dumps(acceptance, indent=2, sort_keys=True))
    if acceptance.get("status") == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
