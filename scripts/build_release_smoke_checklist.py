from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.release_smoke import build_release_smoke_checklist, write_release_smoke_checklist  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a compact LocalMedChem release smoke checklist.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "releases" / "release_smoke_checklist.json"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs" / "release_smoke_checklist.md"))
    parser.add_argument("--production", action="store_true", help="Fail on review-coverage warnings that are only warnings in local exploratory mode.")
    args = parser.parse_args()
    report = build_release_smoke_checklist(args.root, production_mode=args.production)
    write_release_smoke_checklist(report, json_path=args.json_out, markdown_path=args.markdown_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
