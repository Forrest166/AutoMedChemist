from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_promotion_approval_ledger import (  # noqa: E402
    build_rgroup_promotion_approval_ledger,
    write_rgroup_promotion_approval_decision_template,
    write_rgroup_promotion_approval_ledger,
)


def _read_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or apply R-group feed promotion approval decisions.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--template-only", action="store_true")
    parser.add_argument("--template-out", default=str(ROOT / "data/substituents/rgroup_promotion_approval_decisions.csv"))
    parser.add_argument("--decisions-csv")
    parser.add_argument("--decision", choices=["approved", "deferred", "rejected"])
    parser.add_argument("--reviewer", default="local_promotion_reviewer")
    parser.add_argument("--note", default="")
    parser.add_argument("--preserve-existing", action="store_true")
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_promotion_approval_ledger.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_promotion_approval_ledger.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/rgroup_promotion_approval_ledger.md"))
    parser.add_argument("--fail-on-pending", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    if args.template_only:
        template = write_rgroup_promotion_approval_decision_template(
            root=args.root,
            project_name=args.project_name,
            csv_path=args.template_out,
        )
        print(json.dumps(template, indent=2, sort_keys=True))
        return

    json_out = Path(args.json_out)
    if args.preserve_existing:
        existing = _read_existing(json_out)
        if existing.get("status") in {"approved", "reviewed_holdout", "partially_approved_holdout"} and int(existing.get("pending_approval_count") or 0) == 0:
            print(
                json.dumps(
                    {
                        key: existing.get(key)
                        for key in [
                            "status",
                            "mode",
                            "row_count",
                            "approval_required_count",
                            "completed_approval_count",
                            "approved_count",
                            "deferred_count",
                            "rejected_count",
                            "promotion_allowed",
                        ]
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return

    report = build_rgroup_promotion_approval_ledger(
        root=args.root,
        project_name=args.project_name,
        decisions_csv=args.decisions_csv,
        decision=args.decision,
        reviewer=args.reviewer,
        note=args.note,
    )
    write_rgroup_promotion_approval_ledger(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "mode": report.get("mode"),
                "row_count": report.get("row_count"),
                "pending_approval_count": report.get("pending_approval_count"),
                "approved_count": report.get("approved_count"),
                "deferred_count": report.get("deferred_count"),
                "rejected_count": report.get("rejected_count"),
                "promotion_allowed": report.get("promotion_allowed"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.fail_on_blocked and report.get("status") == "blocked":
        raise SystemExit(1)
    if args.fail_on_pending and int(report.get("pending_approval_count") or 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
