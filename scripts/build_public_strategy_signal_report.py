from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.public_sar import build_public_strategy_signal_report, write_public_strategy_signal_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build public ChEMBL/MMP/ring strategy signal report.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--output", default=str(ROOT / "data" / "substituents" / "public_strategy_signal_report.json"))
    args = parser.parse_args()
    report = build_public_strategy_signal_report(db_path=args.db)
    write_public_strategy_signal_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
