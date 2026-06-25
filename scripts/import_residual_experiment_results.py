from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.experiment_tracking import import_residual_experiment_results_csv, write_experiment_tracking_report  # noqa: E402
from localmedchem.project_evidence_pack import build_project_evidence_pack, write_project_evidence_pack  # noqa: E402
from localmedchem.project_evidence_expansion_plan import build_project_evidence_expansion_plan, write_project_evidence_expansion_plan  # noqa: E402
from localmedchem.project_dashboard import build_project_closed_loop_dashboard, write_project_closed_loop_dashboard  # noqa: E402
from localmedchem.promotion_gate import build_closed_loop_promotion_gate, write_closed_loop_promotion_gate  # noqa: E402
from localmedchem.replay_validation import build_closed_loop_replay_report, write_closed_loop_replay_report  # noqa: E402
from localmedchem.residual_result_intake import build_residual_result_intake_manifest, write_residual_result_intake_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and import filled residual experiment result CSV rows.")
    parser.add_argument("--csv", required=True, help="Filled residual_experiment_results_template.csv.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--residual-task-registry", default=str(ROOT / "data" / "substituents" / "evidence_residual_task_registry.json"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "projects" / "demo" / "residual_result_import_report.json"))
    parser.add_argument("--import-manifest", default=str(ROOT / "data" / "projects" / "experiment_result_import_manifest.json"))
    parser.add_argument("--allow-duplicate-source", action="store_true")
    parser.add_argument("--require-production-source", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail if any row has validation errors.")
    parser.add_argument("--no-feedback", action="store_true", help="Track experiment events without writing candidate feedback.")
    parser.add_argument("--no-refresh", action="store_true", help="Skip dashboard/replay/promotion gate refresh after import.")
    args = parser.parse_args()

    report = import_residual_experiment_results_csv(
        args.csv,
        db_path=args.db,
        update_feedback=not args.no_feedback,
        residual_task_registry_path=args.residual_task_registry,
        strict=args.strict,
        import_manifest_path=args.import_manifest,
        allow_duplicate_source=args.allow_duplicate_source,
        require_production_source=args.require_production_source,
    )
    if not args.no_refresh:
        dashboard = build_project_closed_loop_dashboard(root=ROOT, db_path=args.db, project_name=args.project_name or None)
        write_project_closed_loop_dashboard(dashboard, ROOT / "data" / "projects" / "demo" / "project_closed_loop_dashboard.json")
        replay = build_closed_loop_replay_report(root=ROOT, db_path=args.db, project_name=args.project_name or None)
        write_closed_loop_replay_report(replay, ROOT / "data" / "projects" / "demo" / "closed_loop_replay_report.json")
        evidence_pack = build_project_evidence_pack(root=ROOT, db_path=args.db, project_name=args.project_name or None)
        write_project_evidence_pack(
            evidence_pack,
            ROOT / "data" / "projects" / "demo" / "project_evidence_pack.json",
            summary_csv_path=ROOT / "data" / "projects" / "demo" / "project_evidence_pack_summary.csv",
        )
        expansion = build_project_evidence_expansion_plan(root=ROOT, project_name=args.project_name or None)
        write_project_evidence_expansion_plan(
            expansion,
            ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.json",
            csv_path=ROOT / "data" / "projects" / "demo" / "project_evidence_expansion_plan.csv",
        )
        intake = build_residual_result_intake_manifest(
            plan_path=ROOT / "data" / "projects" / "demo" / "residual_experiment_plan.csv",
            result_csv=args.csv,
            registry_path=args.residual_task_registry,
        )
        write_residual_result_intake_manifest(
            intake,
            ROOT / "data" / "projects" / "demo" / "residual_result_intake_manifest.json",
            csv_path=ROOT / "data" / "projects" / "demo" / "residual_result_intake_manifest.csv",
        )
        gate = build_closed_loop_promotion_gate(root=ROOT, project_name=args.project_name or None)
        write_closed_loop_promotion_gate(gate, ROOT / "data" / "projects" / "demo" / "closed_loop_promotion_gate.json")
        report["refreshed_outputs"] = {
            "project_dashboard": dashboard.get("overall_status"),
            "closed_loop_replay": replay.get("status"),
            "project_evidence_pack": evidence_pack.get("status"),
            "project_evidence_expansion_plan": expansion.get("status"),
            "residual_result_intake": intake.get("status"),
            "promotion_gate": gate.get("promotion_status"),
        }
    write_experiment_tracking_report(report, args.report_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and ((report.get("validation") or {}).get("error_count") or report.get("status") in {"demo_source_rejected"}):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
