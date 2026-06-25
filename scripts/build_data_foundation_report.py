from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.data_foundation import build_data_foundation_report, save_data_foundation_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the unified LocalMedChem data-foundation snapshot.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "data_foundation_report.json"))
    parser.add_argument("--md-out", default=str(ROOT / "data" / "substituents" / "data_foundation_report.md"))
    parser.add_argument("--no-checksums", action="store_true")
    parser.add_argument("--skip-db-write", action="store_true")
    args = parser.parse_args()

    report = build_data_foundation_report(
        args.root,
        db_path=args.db_path,
        include_checksums=not args.no_checksums,
    )
    save_data_foundation_report(
        report,
        json_path=args.json_out,
        markdown_path=args.md_out,
        db_path=None if args.skip_db_write else args.db_path,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
