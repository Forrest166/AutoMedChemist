from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_staging_curator_signoff import (  # noqa: E402
    record_rgroup_staging_curator_signoff,
    write_rgroup_staging_curator_signoff,
)


def _split(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Record local curator signoff for the R-group staging manual review queue.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--review-queue-ids", default="")
    parser.add_argument("--source-datasets", default="")
    parser.add_argument("--decision", default="ready_for_sandbox_review")
    parser.add_argument("--curator", default="local_curator")
    parser.add_argument("--note", default="")
    parser.add_argument("--version-change-note", default="")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_staging_curator_signoff.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_staging_curator_signoff.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_staging_curator_signoff.md"))
    args = parser.parse_args()
    report = record_rgroup_staging_curator_signoff(
        root=args.root,
        review_queue_ids=_split(args.review_queue_ids),
        source_datasets=_split(args.source_datasets),
        curator_decision=args.decision,
        curator=args.curator,
        curator_note=args.note,
        version_change_note=args.version_change_note,
    )
    write_rgroup_staging_curator_signoff(
        report,
        json_path=args.json_out,
        csv_path=args.csv_out,
        markdown_path=args.markdown_out,
    )
    print(json.dumps({"status": report.get("status"), "updated_count": report.get("updated_count"), "row_count": report.get("row_count")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
