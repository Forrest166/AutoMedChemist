from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.scaffold_calibration import (  # noqa: E402
    build_scaffold_calibration_audit_report,
    calibrate_scaffold_rules,
    load_scaffold_calibration_report,
    load_scaffold_calibration_cases,
    write_scaffold_calibration_audit_report,
    write_scaffold_calibration_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate scaffold/ring operators from curated positive and negative cases.")
    parser.add_argument("--cases", default=str(ROOT / "data" / "rules" / "scaffold_calibration_set.yaml"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "scaffold_calibration_report.json"))
    parser.add_argument("--previous-report", default=str(ROOT / "data" / "substituents" / "scaffold_calibration_report.json"))
    parser.add_argument("--workspace-report", default=str(ROOT / "data" / "substituents" / "scaffold_review_workspace_report.json"))
    parser.add_argument("--audit-out", default=str(ROOT / "data" / "substituents" / "scaffold_calibration_audit_report.json"))
    args = parser.parse_args()

    previous = load_scaffold_calibration_report(args.previous_report) if Path(args.previous_report).exists() else {}
    workspace = json.loads(Path(args.workspace_report).read_text(encoding="utf-8")) if Path(args.workspace_report).exists() else {}
    report = calibrate_scaffold_rules(load_scaffold_calibration_cases(args.cases))
    write_scaffold_calibration_report(report, args.json_out)
    audit = build_scaffold_calibration_audit_report(previous, report, workspace_report=workspace)
    write_scaffold_calibration_audit_report(audit, args.audit_out)
    print(
        json.dumps(
            {
                **report,
                "audit": {
                    key: audit.get(key)
                    for key in [
                        "changed_rule_count",
                        "action_change_count",
                        "new_rule_signal_count",
                        "suggested_rule_status_change_count",
                    ]
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
