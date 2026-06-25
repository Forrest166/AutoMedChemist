from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.source_expansion_governance import build_source_expansion_governance, write_source_expansion_governance  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the governance guard for ring/R-group/source expansion.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/source_expansion_governance.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/source_expansion_governance.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/source_expansion_governance.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_source_expansion_governance(root=args.root)
    write_source_expansion_governance(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "blocked_gate_count": report.get("blocked_gate_count"),
                "ungated_expansion_allowed": report.get("ungated_expansion_allowed"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
