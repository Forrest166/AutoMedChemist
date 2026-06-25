from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.scaffold_review_workspace import (  # noqa: E402
    build_scaffold_review_workspace_report,
    write_scaffold_review_workspace_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the scaffold/ring review workspace report.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--scaffold-rules", default=str(ROOT / "data" / "rules" / "scaffold_replacements.yaml"))
    parser.add_argument("--scaffold-rule-reviews", default=str(ROOT / "data" / "rules" / "scaffold_rule_reviews.yaml"))
    parser.add_argument("--candidate-limit", type=int, default=5000)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--resolution-status", default=None)
    parser.add_argument("--rule-version", default=None)
    parser.add_argument("--output", default=str(ROOT / "data" / "substituents" / "scaffold_review_workspace_report.json"))
    args = parser.parse_args()

    report = build_scaffold_review_workspace_report(
        db_path=args.db_path,
        project_name=args.project_name,
        scaffold_rules_path=args.scaffold_rules,
        scaffold_rule_reviews_path=args.scaffold_rule_reviews,
        candidate_limit=args.candidate_limit,
        owner_filter=args.owner,
        resolution_status_filter=args.resolution_status,
        rule_version_filter=args.rule_version,
    )
    write_scaffold_review_workspace_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
