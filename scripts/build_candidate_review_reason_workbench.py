from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_review_reason_workbench import (  # noqa: E402
    build_candidate_review_reason_workbench,
    write_candidate_review_reason_workbench,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local candidate review reason workbench and audit replay.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--audit-json-out", default=None)
    parser.add_argument("--audit-csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_review_reason_workbench.md"))
    args = parser.parse_args()
    project_dir = ROOT / "data" / "projects" / args.project_name
    report = build_candidate_review_reason_workbench(root=args.root, project_name=args.project_name)
    write_candidate_review_reason_workbench(
        report,
        json_path=args.json_out or project_dir / "candidate_review_reason_workbench.json",
        csv_path=args.csv_out or project_dir / "candidate_review_reason_workbench.csv",
        audit_json_path=args.audit_json_out or project_dir / "candidate_review_reason_workbench_audit.json",
        audit_csv_path=args.audit_csv_out or project_dir / "candidate_review_reason_workbench_audit.csv",
        markdown_path=args.markdown_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "row_count": report.get("row_count"),
                "audit_event_count": report.get("audit_event_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
