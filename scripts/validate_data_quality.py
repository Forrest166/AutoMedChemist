from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.quality import save_quality_report, validate_data_quality  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate LocalMedChemModifier data quality gates.")
    parser.add_argument("--output", default=str(ROOT / "data" / "substituents" / "data_quality_hardening_report.json"))
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when errors are present.")
    args = parser.parse_args()

    report = validate_data_quality(ROOT)
    save_quality_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
