from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_readiness import (  # noqa: E402
    build_ring_outcome_result_package_review,
    write_ring_outcome_result_package_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an operator review packet for the ring outcome result package.")
    parser.add_argument("--package-json", default=str(ROOT / "data/projects/demo/ring_outcome_result_package.json"))
    parser.add_argument("--import-gate", default=str(ROOT / "data/projects/demo/ring_outcome_result_package_import_gate.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data/projects/demo/ring_outcome_result_package_review.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/projects/demo/ring_outcome_result_package_review.csv"))
    parser.add_argument("--fail-on-validation-error", action="store_true")
    args = parser.parse_args()

    report = build_ring_outcome_result_package_review(
        package_path=args.package_json,
        import_gate_path=args.import_gate,
    )
    write_ring_outcome_result_package_review(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_validation_error and report.get("validation_error_count"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
