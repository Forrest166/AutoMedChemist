from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_review_reason_workbench import (  # noqa: E402
    build_candidate_review_reason_workbench,
    record_candidate_review_reason_batch,
    write_candidate_review_reason_workbench,
)


def _split_ids(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a local candidate review reason batch audit event.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--reason-cluster", required=True)
    parser.add_argument("--candidate-ids", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--reviewer", default="native_shell")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    audit_report = record_candidate_review_reason_batch(
        root=args.root,
        project_name=args.project_name,
        reason_cluster=args.reason_cluster,
        candidate_ids=_split_ids(args.candidate_ids),
        batch_status=args.status,
        reviewer=args.reviewer,
        note=args.note,
    )
    project_dir = ROOT / "data" / "projects" / args.project_name
    workbench = build_candidate_review_reason_workbench(root=args.root, project_name=args.project_name)
    write_candidate_review_reason_workbench(
        workbench,
        json_path=project_dir / "candidate_review_reason_workbench.json",
        csv_path=project_dir / "candidate_review_reason_workbench.csv",
        audit_json_path=project_dir / "candidate_review_reason_workbench_audit.json",
        audit_csv_path=project_dir / "candidate_review_reason_workbench_audit.csv",
        markdown_path=ROOT / "docs/candidate_review_reason_workbench.md",
    )
    print(
        json.dumps(
            {
                "status": audit_report.get("status"),
                "row_count": audit_report.get("row_count"),
                "updated_count": audit_report.get("updated_count"),
                "reason_cluster": args.reason_cluster,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
