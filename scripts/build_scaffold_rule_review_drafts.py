from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.scaffold_calibration import (  # noqa: E402
    build_scaffold_rule_review_drafts,
    write_scaffold_rule_review_drafts,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manual-review scaffold rule draft rows from calibration audit suggestions.")
    parser.add_argument("--audit", default=str(ROOT / "data" / "substituents" / "scaffold_calibration_audit_report.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "substituents" / "scaffold_rule_review_drafts.csv"))
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--owner", default="")
    parser.add_argument("--rule-version", default="")
    args = parser.parse_args()

    audit_path = Path(args.audit)
    audit_report = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
    rows = build_scaffold_rule_review_drafts(
        audit_report,
        reviewer=args.reviewer or None,
        owner=args.owner or None,
        rule_version=args.rule_version or None,
    )
    write_scaffold_rule_review_drafts(rows, args.output)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "draft_count": len(rows),
                "audit_path": str(audit_path.resolve()),
                "requires_manual_review_count": sum(1 for row in rows if row.get("requires_manual_review")),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
