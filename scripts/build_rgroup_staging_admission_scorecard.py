from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_staging_admission_scorecard import (  # noqa: E402
    build_rgroup_staging_admission_scorecard,
    write_rgroup_staging_admission_scorecard,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local R-group staging admission scorecard.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_staging_admission_scorecard.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_staging_admission_scorecard.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_staging_admission_scorecard.md"))
    args = parser.parse_args()
    report = build_rgroup_staging_admission_scorecard(root=args.root)
    write_rgroup_staging_admission_scorecard(
        report,
        json_path=args.json_out,
        csv_path=args.csv_out,
        markdown_path=args.markdown_out,
    )
    print(json.dumps({"status": report.get("status"), "row_count": report.get("row_count"), "top_source": report.get("top_source")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
