from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.scaffold_calibration import bulk_update_scaffold_rule_review_draft_status, update_scaffold_rule_review_draft_status  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve, defer, reject, or retire scaffold rule review draft rows.")
    parser.add_argument("--drafts", default=str(ROOT / "data" / "substituents" / "scaffold_rule_review_drafts.csv"))
    parser.add_argument("--draft-id", action="append", default=None)
    parser.add_argument("--current-status", action="append", default=None)
    parser.add_argument("--suggestion-confidence", action="append", default=None)
    parser.add_argument("--status", required=True, help="approved_for_apply, deferred, rejected, retired, or draft_not_applied.")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if args.current_status or args.suggestion_confidence or (args.draft_id and len(args.draft_id) > 1):
        report = bulk_update_scaffold_rule_review_draft_status(
            status=args.status,
            draft_path=args.drafts,
            draft_ids=args.draft_id,
            current_statuses=args.current_status,
            suggestion_confidences=args.suggestion_confidence,
            reviewer=args.reviewer or None,
            note=args.note or None,
        )
        output = {
            "status": report.get("status"),
            "updated_count": report.get("updated_count"),
            "skipped_count": report.get("skipped_count"),
            "updated_draft_ids": report.get("updated_draft_ids"),
            "drafts": str(Path(args.drafts).resolve()),
        }
    else:
        if not args.draft_id:
            raise SystemExit("--draft-id is required unless --current-status or --suggestion-confidence is provided for a batch update.")
        report = update_scaffold_rule_review_draft_status(
            args.draft_id[0],
            status=args.status,
            draft_path=args.drafts,
            reviewer=args.reviewer or None,
            note=args.note or None,
        )
        output = {
            "draft_id": report.get("draft_id"),
            "status": report.get("status"),
            "drafts": str(Path(args.drafts).resolve()),
        }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
