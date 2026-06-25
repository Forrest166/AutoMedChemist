from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.release import compare_library_files, write_release_markdown, write_release_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two substituent library releases.")
    parser.add_argument("--previous", default=None, help="Previous YAML/CSV library file.")
    parser.add_argument(
        "--current",
        default=str(ROOT / "data" / "substituents" / "core_substituent_library.yaml"),
        help="Current YAML/CSV library file.",
    )
    parser.add_argument(
        "--json-out",
        default=str(ROOT / "data" / "substituents" / "library_release_report.json"),
    )
    parser.add_argument(
        "--md-out",
        default=str(ROOT / "data" / "substituents" / "library_release_report.md"),
    )
    args = parser.parse_args()

    report = compare_library_files(args.previous, args.current)
    write_release_report(report, args.json_out)
    write_release_markdown(report, args.md_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
