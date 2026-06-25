from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.transform_governance import load_transform_rules, validate_transform_rules  # noqa: E402
from localmedchem.transform_priors import load_transform_priors, validate_transform_priors  # noqa: E402


def save_issues(issues: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rule_id", "name", "severity", "category", "field", "value", "message"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)


def save_prior_issues(issues: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rule_id", "replacement_label", "severity", "category", "field", "value", "message"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate functional-group replacement rule governance.")
    parser.add_argument("--rules", default=str(ROOT / "data" / "rules" / "functional_group_replacements.yaml"))
    parser.add_argument("--priors", default=str(ROOT / "data" / "rules" / "transform_priors.yaml"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "transform_rule_quality_report.json"))
    parser.add_argument("--issues-out", default=str(ROOT / "data" / "substituents" / "transform_rule_quality_issues.csv"))
    parser.add_argument("--prior-report-out", default=str(ROOT / "data" / "substituents" / "transform_prior_quality_report.json"))
    parser.add_argument("--prior-issues-out", default=str(ROOT / "data" / "substituents" / "transform_prior_quality_issues.csv"))
    args = parser.parse_args()

    rules = load_transform_rules(args.rules)
    report = validate_transform_rules(rules)
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    save_issues(report["issues"], Path(args.issues_out))
    prior_report = validate_transform_priors(load_transform_priors(args.priors), known_rule_ids={rule["rule_id"] for rule in rules})
    Path(args.prior_report_out).write_text(json.dumps(prior_report, indent=2, sort_keys=True), encoding="utf-8")
    save_prior_issues(prior_report["issues"], Path(args.prior_issues_out))
    print(
        json.dumps(
            {
                "rules": {key: value for key, value in report.items() if key != "issues"},
                "priors": {key: value for key, value in prior_report.items() if key != "issues"},
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
