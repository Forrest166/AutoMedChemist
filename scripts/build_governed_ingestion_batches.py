from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.governed_ingestion_batches import build_governed_ingestion_batches, write_governed_ingestion_batches  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build governed intake batch plans for ring/R-group/source expansion.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/governed_ingestion_batches.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/governed_ingestion_batches.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/governed_ingestion_batches.md"))
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_governed_ingestion_batches(root=args.root)
    write_governed_ingestion_batches(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "blocked_batch_count": report.get("blocked_batch_count"),
                "allowed_ingestion_batch_count": report.get("allowed_ingestion_batch_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
