from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_evidence_execution import execute_project_evidence_expansion_plan, write_project_evidence_execution_report  # noqa: E402


def _split(value: str) -> set[str] | None:
    if str(value or "").strip().lower() in {"", "all", "*"}:
        return None
    items = {item.strip() for item in str(value or "").split(",") if item.strip()}
    return items or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute project evidence expansion tasks using existing local evidence.")
    parser.add_argument("--plan", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.json"))
    parser.add_argument("--csv", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.csv"))
    parser.add_argument("--priority", default="high", help="Comma-separated priorities to execute; empty means all.")
    parser.add_argument("--task-type", default="", help="Comma-separated task types to execute.")
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_execution_report.json"))
    args = parser.parse_args()
    report = execute_project_evidence_expansion_plan(
        root=ROOT,
        plan_path=args.plan,
        csv_path=args.csv,
        priorities=_split(args.priority),
        task_types=_split(args.task_type),
        reviewer=args.reviewer,
    )
    write_project_evidence_execution_report(report, args.output)
    print(json.dumps({key: report.get(key) for key in ["status", "updated_count", "skipped_count", "plan_execution_status_counts", "open_execution_count"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
