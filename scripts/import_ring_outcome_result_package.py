from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.ring_outcome_readiness import (  # noqa: E402
    build_ring_outcome_result_package,
    write_ring_outcome_result_package,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly import the production ring outcome result package when real payload is ready.")
    parser.add_argument("--plan-path", default=str(ROOT / "data/projects/demo/ring_outcome_experiment_plan.csv"))
    parser.add_argument("--result-csv", default=str(ROOT / "data/projects/demo/ring_outcome_result_drops/production_ring_outcome_results_pending.csv"))
    parser.add_argument("--package-json-out", default=str(ROOT / "data/projects/demo/ring_outcome_result_package.json"))
    parser.add_argument("--package-csv-out", default=str(ROOT / "data/projects/demo/ring_outcome_result_package.csv"))
    parser.add_argument("--report-out", default=str(ROOT / "data/projects/demo/ring_outcome_result_package_import_gate.json"))
    parser.add_argument("--db", default=str(ROOT / "data/localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--import-if-ready", action="store_true")
    parser.add_argument("--fail-if-not-ready", action="store_true")
    args = parser.parse_args()

    package = build_ring_outcome_result_package(
        plan_path=args.plan_path,
        output_dir=Path(args.result_csv).parent,
        result_csv=args.result_csv,
        overwrite=False,
    )
    write_ring_outcome_result_package(package, json_path=args.package_json_out, csv_path=args.package_csv_out)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": package.get("status"),
        "result_csv": package.get("result_csv"),
        "importable_result_count": package.get("importable_result_count"),
        "pending_result_count": package.get("pending_result_count"),
        "validation_error_count": package.get("validation_error_count"),
        "import_attempted": False,
        "import_returncode": None,
        "import_stdout_tail": "",
        "import_stderr_tail": "",
        "strict_import_command": package.get("strict_import_command"),
    }
    if package.get("status") == "ready_for_strict_import" and args.import_if_ready:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "import_ring_outcome_results.py"),
            "--csv",
            str(Path(args.result_csv)),
            "--db",
            str(Path(args.db)),
            "--project-name",
            args.project_name,
            "--plan-path",
            str(Path(args.plan_path)),
            "--strict",
            "--require-production-source",
            "--no-feedback",
        ]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        report.update(
            {
                "import_attempted": True,
                "import_returncode": completed.returncode,
                "import_stdout_tail": completed.stdout[-4000:],
                "import_stderr_tail": completed.stderr[-4000:],
                "status": "imported" if completed.returncode == 0 else "import_failed",
            }
        )
    elif package.get("status") == "ready_for_strict_import":
        report["status"] = "ready_for_strict_import"

    out = Path(args.report_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") == "import_failed":
        raise SystemExit(1)
    if args.fail_if_not_ready and report.get("status") not in {"ready_for_strict_import", "imported"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
