from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_dashboard import (  # noqa: E402
    build_project_closed_loop_dashboard,
    write_project_closed_loop_dashboard,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the project-level closed-loop dashboard report.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "project_closed_loop_dashboard.json"))
    args = parser.parse_args()

    report = build_project_closed_loop_dashboard(
        root=args.root,
        db_path=args.db_path,
        project_name=args.project_name or None,
    )
    write_project_closed_loop_dashboard(report, args.output)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "overall_status": report.get("overall_status"),
                "project_name": report.get("project_name"),
                "feedback_count": (report.get("feedback") or {}).get("feedback_count", 0),
                "open_plan_count": (report.get("experiments") or {}).get("open_plan_count", 0),
                "residual_task_count": (report.get("residual_tasks") or {}).get("task_count", 0),
                "queue_count": (report.get("next_design_queue") or {}).get("queue_count", 0),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
