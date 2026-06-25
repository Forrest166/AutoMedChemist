from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_evidence_expansion_plan import update_project_evidence_expansion_task_status  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Update execution status for one project evidence expansion task.")
    parser.add_argument("--plan", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.json"))
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--status", required=True, help="open, in_progress, evidence_imported, blocked, deferred, or closed.")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--owner", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    report = update_project_evidence_expansion_task_status(
        args.task_id,
        status=args.status,
        plan_path=args.plan,
        reviewer=args.reviewer or None,
        owner=args.owner or None,
        note=args.note or None,
    )
    plan = report.get("plan") or {}
    print(
        json.dumps(
            {
                "plan": str(Path(args.plan).resolve()),
                "task_id": report.get("task_id"),
                "status": report.get("status"),
                "execution_status_counts": plan.get("execution_status_counts") or {},
                "open_execution_count": plan.get("open_execution_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
