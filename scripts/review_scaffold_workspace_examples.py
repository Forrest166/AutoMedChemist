from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.scaffold_review_workspace import (  # noqa: E402
    append_workspace_examples_to_calibration_set,
    write_scaffold_workspace_decision_template,
)


def _read_decisions(path: str | Path) -> list[dict]:
    decision_path = Path(path)
    if decision_path.suffix.lower() == ".json":
        data = json.loads(decision_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return list(data.get("decisions") or [])
        return list(data or [])
    with decision_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _auto_accept_promotion_decisions(workspace_report: dict, *, reviewer: str | None) -> list[dict]:
    decisions = []
    for entry in workspace_report.get("entries") or []:
        if entry.get("review_priority") != "candidate_for_promotion":
            continue
        examples = sorted(entry.get("example_candidates") or [], key=lambda row: float(row.get("score") or 0.0), reverse=True)
        if not examples:
            continue
        example = examples[0]
        decisions.append(
            {
                "workspace_key": entry.get("workspace_key"),
                "candidate_id": example.get("candidate_id"),
                "decision": "accepted",
                "reviewer": reviewer,
                "note": "Auto-accepted top promotion candidate for calibration sync; confirm in medchem review before broad rule promotion.",
            }
        )
    return decisions


def _decision_governance_errors(decisions: list[dict], *, require_review_notes: bool, reviewer: str | None) -> list[dict]:
    if not require_review_notes:
        return []
    errors = []
    for index, decision in enumerate(decisions, start=1):
        outcome = str(decision.get("decision") or decision.get("observed_outcome") or "").strip().lower()
        if outcome not in {"accepted", "supported", "positive", "rejected", "failed", "negative"}:
            continue
        resolved_reviewer = decision.get("reviewer") or reviewer
        if not resolved_reviewer or not str(decision.get("note") or "").strip():
            errors.append(
                {
                    "row_number": index,
                    "workspace_key": decision.get("workspace_key"),
                    "candidate_id": decision.get("candidate_id"),
                    "reason": "missing_reviewer_or_note",
                }
            )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Append reviewed scaffold workspace examples into scaffold calibration cases.")
    parser.add_argument("--workspace-report", default=str(ROOT / "data" / "substituents" / "scaffold_review_workspace_report.json"))
    parser.add_argument("--decisions", default=None, help="CSV/JSON with workspace_key,candidate_id,decision,note columns.")
    parser.add_argument("--write-template", default=None, help="Write an accepted/rejected scaffold decision CSV template and exit unless decisions are also supplied.")
    parser.add_argument("--template-examples-per-entry", type=int, default=1)
    parser.add_argument("--auto-accept-promotions", action="store_true", help="Generate accepted decisions for top candidate_for_promotion workspace entries.")
    parser.add_argument("--require-review-notes", action="store_true", help="Require reviewer and note for accepted/rejected rows before calibration sync.")
    parser.add_argument("--calibration-set", default=str(ROOT / "data" / "rules" / "scaffold_calibration_set.yaml"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "scaffold_workspace_calibration_sync_report.json"))
    parser.add_argument("--reviewer", default=None)
    args = parser.parse_args()

    workspace_report = json.loads(Path(args.workspace_report).read_text(encoding="utf-8"))
    template_rows = []
    if args.write_template:
        template_rows = write_scaffold_workspace_decision_template(
            workspace_report,
            args.write_template,
            max_examples_per_entry=args.template_examples_per_entry,
        )
        if not args.decisions and not args.auto_accept_promotions:
            print(
                json.dumps(
                    {
                        "template_out": str(Path(args.write_template).resolve()),
                        "template_row_count": len(template_rows),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return
    decisions = _read_decisions(args.decisions) if args.decisions else []
    if args.auto_accept_promotions:
        decisions.extend(_auto_accept_promotion_decisions(workspace_report, reviewer=args.reviewer))
    if not decisions:
        raise SystemExit("No scaffold workspace decisions supplied. Use --decisions or --auto-accept-promotions.")
    governance_errors = _decision_governance_errors(decisions, require_review_notes=args.require_review_notes, reviewer=args.reviewer)
    if governance_errors:
        raise SystemExit("Scaffold workspace decisions are missing reviewer/note metadata:\n" + json.dumps(governance_errors, indent=2, sort_keys=True))
    report = append_workspace_examples_to_calibration_set(
        workspace_report,
        decisions,
        calibration_path=args.calibration_set,
        reviewer=args.reviewer,
    )
    report["decision_count"] = len(decisions)
    report["template_row_count"] = len(template_rows)
    report["governance_error_count"] = len(governance_errors)
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
