from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.promotion_gate import build_closed_loop_promotion_gate, write_closed_loop_promotion_gate  # noqa: E402
from localmedchem.scaffold_calibration import (  # noqa: E402
    apply_scaffold_rule_review_drafts,
    build_scaffold_calibration_audit_report,
    calibrate_scaffold_rules,
    load_scaffold_calibration_cases,
    load_scaffold_calibration_report,
    write_scaffold_calibration_audit_report,
    write_scaffold_calibration_report,
)
from localmedchem.scaffold_review_workspace import build_scaffold_review_workspace_report, write_scaffold_review_workspace_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply manually approved scaffold rule review drafts.")
    parser.add_argument("--drafts", default=str(ROOT / "data" / "substituents" / "scaffold_rule_review_drafts.csv"))
    parser.add_argument("--draft-id", action="append", default=[])
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--owner", default="")
    parser.add_argument("--rule-reviews", default=str(ROOT / "data" / "rules" / "scaffold_rule_reviews.yaml"))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--allow-selected-draft-status", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Refresh scaffold workspace/audit and promotion gate after applying drafts.")
    parser.add_argument("--project-name", default="demo_learning")
    args = parser.parse_args()

    report = apply_scaffold_rule_review_drafts(
        draft_path=args.drafts,
        draft_ids=args.draft_id or None,
        reviewer=args.reviewer or None,
        owner=args.owner or None,
        rule_reviews_path=args.rule_reviews,
        db_path=args.db_path,
        allow_selected_draft_status=args.allow_selected_draft_status,
    )
    refreshed = {}
    if args.refresh:
        workspace = build_scaffold_review_workspace_report(
            db_path=args.db_path,
            project_name=None,
            scaffold_rule_reviews_path=args.rule_reviews,
        )
        write_scaffold_review_workspace_report(workspace, ROOT / "data" / "substituents" / "scaffold_review_workspace_report.json")
        calibration_path = ROOT / "data" / "substituents" / "scaffold_calibration_report.json"
        previous = load_scaffold_calibration_report(calibration_path) if calibration_path.exists() else {}
        calibration = calibrate_scaffold_rules(load_scaffold_calibration_cases(ROOT / "data" / "rules" / "scaffold_calibration_set.yaml"))
        write_scaffold_calibration_report(calibration, calibration_path)
        audit = build_scaffold_calibration_audit_report(previous, calibration, workspace_report=workspace)
        write_scaffold_calibration_audit_report(audit, ROOT / "data" / "substituents" / "scaffold_calibration_audit_report.json")
        gate = build_closed_loop_promotion_gate(root=ROOT, project_name=args.project_name or None)
        write_closed_loop_promotion_gate(gate, ROOT / "data" / "projects" / "demo" / "closed_loop_promotion_gate.json")
        refreshed = {
            "workspace_entry_count": workspace.get("entry_count"),
            "audit_suggestion_count": audit.get("suggested_rule_status_change_count"),
            "promotion_gate": gate.get("promotion_status"),
        }
    print(
        json.dumps(
            {
                "drafts": str(Path(args.drafts).resolve()),
                "processed_count": report.get("processed_count"),
                "applied_count": report.get("applied_count"),
                "skipped_count": report.get("skipped_count"),
                "applied_draft_ids": report.get("applied_draft_ids"),
                "refreshed": refreshed,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
