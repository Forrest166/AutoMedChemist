from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_staging_fill import (  # noqa: E402
    fill_rgroup_staging_from_reviewed_sources,
    write_rgroup_staging_fill_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill next R-group staging CSVs from existing governed reviewed follow-up feeds.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--overwrite", action="store_true", help="Replace existing staged rows after using complete governed source rows.")
    parser.add_argument("--analog-limit", type=int, default=2)
    parser.add_argument("--literature-limit", type=int, default=3)
    parser.add_argument("--patent-limit", type=int, default=3)
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_staging_fill_report.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_staging_fill_report.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_staging_fill_report.md"))
    args = parser.parse_args()
    report = fill_rgroup_staging_from_reviewed_sources(
        root=args.root,
        overwrite=args.overwrite,
        source_limits={
            "analog_series_seed": args.analog_limit,
            "literature_bioisostere_seed": args.literature_limit,
            "patent_mined_seed": args.patent_limit,
        },
    )
    write_rgroup_staging_fill_report(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
