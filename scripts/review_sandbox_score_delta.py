from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.sandbox_score_delta_signoff import (  # noqa: E402
    build_sandbox_score_delta_signoff_ledger,
    write_sandbox_score_delta_decision_template,
    write_sandbox_score_delta_signoff_ledger,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or apply operator signoff decisions for sandbox score-delta review rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--write-template", action="store_true")
    parser.add_argument("--decisions-csv", default=None)
    parser.add_argument("--decision", choices=["approved", "deferred", "rejected"], default=None)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--preserve-existing", action="store_true", help="Do not overwrite a complete reviewed ledger.")
    parser.add_argument("--template-out", default=str(ROOT / "data/projects/demo/sandbox_score_delta_review_decisions.csv"))
    parser.add_argument("--json-out", default=str(ROOT / "data/projects/demo/sandbox_score_delta_signoff_ledger.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/projects/demo/sandbox_score_delta_signoff_ledger.csv"))
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/sandbox_score_delta_signoff_ledger.md"))
    parser.add_argument("--fail-on-pending", action="store_true")
    args = parser.parse_args()

    if args.write_template:
        template = write_sandbox_score_delta_decision_template(root=args.root, project_name=args.project_name, csv_path=args.template_out)
        print(json.dumps(template, indent=2, sort_keys=True))
        return

    existing_path = Path(args.json_out)
    if args.preserve_existing and existing_path.exists():
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        if existing.get("status") == "reviewed" and int(existing.get("pending_signoff_count") or 0) == 0:
            print(json.dumps({key: existing.get(key) for key in ["status", "mode", "row_count", "required_signoff_count", "completed_signoff_count", "decision_counts"]}, indent=2, sort_keys=True))
            return

    report = build_sandbox_score_delta_signoff_ledger(
        root=args.root,
        project_name=args.project_name,
        decisions_csv=args.decisions_csv,
        decision=args.decision,
        reviewer=args.reviewer,
        note=args.note,
    )
    write_sandbox_score_delta_signoff_ledger(report, json_path=args.json_out, csv_path=args.csv_out, markdown_path=args.markdown_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_pending and report.get("status") != "reviewed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
