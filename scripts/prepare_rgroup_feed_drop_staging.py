from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_onboarding import build_rgroup_feed_drop_staging_package, write_rgroup_feed_drop_staging_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare source-specific CSV templates for the next R-group feed drop.")
    parser.add_argument("--output-dir", default=str(ROOT / "data/replacements/feed_drops/next_rgroup_feed_drop"))
    parser.add_argument("--drop-label", default="next_rgroup_feed_drop")
    parser.add_argument("--source-dataset", action="append", dest="source_datasets")
    parser.add_argument("--include-template-example", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Rewrite existing staged CSV templates. Default preserves filled files.")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging.csv"))
    args = parser.parse_args()

    report = build_rgroup_feed_drop_staging_package(
        output_dir=args.output_dir,
        drop_label=args.drop_label,
        source_datasets=args.source_datasets,
        include_example=args.include_template_example,
        overwrite=args.overwrite,
    )
    write_rgroup_feed_drop_staging_report(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
