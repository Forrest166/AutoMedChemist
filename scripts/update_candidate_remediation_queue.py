from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_remediation_queue import apply_candidate_remediation_updates  # noqa: E402


def _task_ids(values: list[str]) -> list[str]:
    task_ids: list[str] = []
    for value in values:
        for item in str(value or "").replace(";", ",").split(","):
            item = item.strip()
            if item and item not in task_ids:
                task_ids.append(item)
    return task_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Update local-only candidate remediation task ownership and closure fields.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--task-id", action="append", default=[], help="Task id to update. May be repeated or comma-separated.")
    parser.add_argument("--status", default=None)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--due-date", default=None)
    parser.add_argument("--closure-note", default=None)
    parser.add_argument("--actor", default="native_ui")
    parser.add_argument("--action", default="manual_update")
    args = parser.parse_args()
    result = apply_candidate_remediation_updates(
        root=args.root,
        project_name=args.project_name,
        task_ids=_task_ids(args.task_id),
        status=args.status,
        owner=args.owner,
        due_date=args.due_date,
        closure_note=args.closure_note,
        actor=args.actor,
        action=args.action,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"updated", "no_matching_tasks"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
