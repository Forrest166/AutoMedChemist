from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.review_batch import apply_review_backlog_batch, build_review_backlog_batch, write_review_backlog_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or apply a batch first-pass review file for substituent backlog records.")
    parser.add_argument("--output", default=str(ROOT / "data" / "substituents" / "review_batch_001.csv"))
    parser.add_argument("--limit", type=int, default=0, help="0 means all backlog rows.")
    parser.add_argument("--apply", action="store_true", help="Apply the generated or provided batch CSV.")
    parser.add_argument("--input", default=None, help="Apply an existing batch CSV instead of generating a new one.")
    parser.add_argument("--reviewed-by", default="batch_review")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch_path = Path(args.input or args.output)
    if args.input is None:
        rows = build_review_backlog_batch(limit=args.limit or None)
        write_review_backlog_batch(rows, batch_path)
    else:
        rows = []

    report = {
        "batch_path": str(batch_path.resolve()),
        "generated_count": len(rows),
        "applied": None,
    }
    if args.apply:
        report["applied"] = apply_review_backlog_batch(batch_path, reviewed_by=args.reviewed_by, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
