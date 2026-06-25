from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.assay_learning import build_assay_learning_report  # noqa: E402
from localmedchem.calibration import calibrate_project_models, save_calibration_report, write_calibration_profiles, write_calibration_report  # noqa: E402
from localmedchem.database import initialize_database  # noqa: E402
from localmedchem.decision_packet import build_decision_packet, save_decision_packet  # noqa: E402
from localmedchem.experiment_tracking import EXPERIMENT_PLAN_FIELDS, import_experiment_results_rows, upsert_experiment_plan_rows  # noqa: E402
from localmedchem.pipeline import run_mvp  # noqa: E402
from localmedchem.project_store import save_project_run  # noqa: E402


DEFAULT_PROJECT = "demo_learning"
DEFAULT_RUN_ID = "RUN-DEMO-LEARNING-POTENCY"
DEFAULT_PACKET_ID = "DPK-DEMO-LEARNING-POTENCY"

ENDPOINT_SEEDS = [
    {
        "endpoint_group": "potency",
        "run_id": "RUN-DEMO-LEARNING-POTENCY",
        "packet_id": "DPK-DEMO-LEARNING-POTENCY",
        "direction": "increase_polarity",
        "planned_assay": "IC50",
        "assay_type": "IC50",
        "result_unit": "nM",
        "target_context": {"target_family": "kinase", "assay_type": "IC50", "endpoint_group": "potency"},
    },
    {
        "endpoint_group": "solubility",
        "run_id": "RUN-DEMO-LEARNING-SOLUBILITY",
        "packet_id": "DPK-DEMO-LEARNING-SOLUBILITY",
        "direction": "improve_solubility",
        "planned_assay": "kinetic solubility",
        "assay_type": "solubility",
        "result_unit": "uM",
        "target_context": {"target_family": "kinase", "assay_type": "solubility", "endpoint_group": "solubility"},
    },
    {
        "endpoint_group": "metabolic_stability",
        "run_id": "RUN-DEMO-LEARNING-STABILITY",
        "packet_id": "DPK-DEMO-LEARNING-STABILITY",
        "direction": "metabolism_blocking",
        "planned_assay": "human liver microsome stability",
        "assay_type": "microsomal stability",
        "result_unit": "min",
        "target_context": {
            "target_family": "kinase",
            "assay_type": "microsomal stability",
            "endpoint_group": "metabolic_stability",
        },
    },
    {
        "endpoint_group": "permeability",
        "run_id": "RUN-DEMO-LEARNING-PERMEABILITY",
        "packet_id": "DPK-DEMO-LEARNING-PERMEABILITY",
        "direction": "reduce_lipophilicity",
        "planned_assay": "PAMPA permeability",
        "assay_type": "permeability",
        "result_unit": "10^-6 cm/s",
        "target_context": {"target_family": "kinase", "assay_type": "permeability", "endpoint_group": "permeability"},
    },
]

DEMO_NORMALIZED_SCORES = [92, 88, 84, 80, 76, 72, 68, 64, 60, 56, 52, 48, 44, 40, 36, 32, 28, 24, 20, 16, 12, 74, 30, 66]


def _write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPERIMENT_PLAN_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in EXPERIMENT_PLAN_FIELDS})


def _cleanup_existing(db_path: str | Path, plan_ids: list[str], source_path: str) -> None:
    conn = initialize_database(db_path)
    try:
        placeholders = ",".join("?" for _ in plan_ids)
        conn.execute("DELETE FROM project_experiment_event WHERE source_path=? OR plan_id IN (" + placeholders + ")", [source_path, *plan_ids])
        conn.execute("DELETE FROM project_feedback WHERE source_path=? OR feedback_id IN (" + placeholders + ")", [source_path, *[f"FBK-{pid}" for pid in plan_ids]])
        conn.execute("DELETE FROM project_experiment_plan WHERE plan_id IN (" + placeholders + ")", plan_ids)
        conn.commit()
    finally:
        conn.close()


def _result_value(endpoint_group: str, score: float) -> str:
    if endpoint_group == "potency":
        return str(max(1, int(round(15000 / max(score, 1)))))
    if endpoint_group == "solubility":
        return str(round(max(1.0, score * 2.4), 2))
    if endpoint_group == "metabolic_stability":
        return str(round(max(1.0, score * 1.2), 2))
    if endpoint_group == "permeability":
        return str(round(max(0.1, score / 9.0), 2))
    return str(score)


def _classification(score: float) -> str:
    if score >= 68:
        return "active"
    if score <= 35:
        return "inactive"
    return "watch"


def _endpoint_rows(*, endpoint_config: dict, candidates: list[dict], project_name: str, run_id: str) -> list[dict]:
    endpoint_group = endpoint_config["endpoint_group"]
    if len(candidates) < 20:
        raise SystemExit(f"Need at least 20 demo candidates to seed {endpoint_group} feedback.")
    rows = []
    for idx, (candidate, normalized_score) in enumerate(zip(candidates[: len(DEMO_NORMALIZED_SCORES)], DEMO_NORMALIZED_SCORES), start=1):
        rows.append(
            {
                "plan_id": f"EPL-DEMO-{endpoint_group.upper().replace('_', '-')}-{idx:03d}",
                "plan_rank": idx,
                "plan_role": "candidate_assay",
                "project_name": project_name,
                "run_id": run_id,
                "candidate_id": candidate.get("candidate_id"),
                "endpoint_group": endpoint_group,
                "site_type": candidate.get("site_type"),
                "direction": candidate.get("direction"),
                "enumeration_type": candidate.get("enumeration_type"),
                "replacement_label": candidate.get("replacement_label"),
                "candidate_score": candidate.get("score"),
                "priority_score": candidate.get("score"),
                "rationale": f"Seeded historical {endpoint_group} result for endpoint gate calibration.",
                "owner": "demo_seed",
                "planned_assay": endpoint_config["planned_assay"],
                "assay_type": endpoint_config["assay_type"],
                "status": "completed",
                "notes": "Historical demo assay row; not a procurement workflow.",
                "result_value": _result_value(endpoint_group, float(normalized_score)),
                "result_unit": endpoint_config["result_unit"],
                "result_relation": "=",
                "classification": _classification(float(normalized_score)),
                "normalized_score": normalized_score,
                "replicate_count": 3,
                "replicate_cv": 0.12,
            }
        )
    return rows


def seed_demo_historical_feedback(
    *,
    db_path: str | Path,
    project_name: str = DEFAULT_PROJECT,
    run_id: str = DEFAULT_RUN_ID,
    packet_id: str = DEFAULT_PACKET_ID,
    output_csv: str | Path,
) -> dict:
    endpoint_reports = []
    rows = []
    saved_packet_ids = []
    first_saved_run_id = None
    total_candidate_count = 0
    for endpoint_config in ENDPOINT_SEEDS:
        result = run_mvp(
            "COc1ccc(Cl)cc1",
            endpoint_config["direction"],
            db_path=db_path,
            project_name=project_name,
            target_context=endpoint_config["target_context"],
            max_candidates=120,
            max_substituents=120,
            include_advanced=True,
        )
        saved_run_id = save_project_run(
            result,
            db_path=db_path,
            project_name=project_name,
            run_id=endpoint_config["run_id"],
            note=f"Demo historical {endpoint_config['endpoint_group']} feedback seed for assay-learning calibration.",
            filters={"seeded_historical_feedback": True, "endpoint_group": endpoint_config["endpoint_group"]},
        )
        first_saved_run_id = first_saved_run_id or saved_run_id
        candidates = result.get("candidates") or []
        total_candidate_count += len(candidates)
        endpoint_rows = _endpoint_rows(
            endpoint_config=endpoint_config,
            candidates=candidates,
            project_name=project_name,
            run_id=saved_run_id,
        )
        rows.extend(endpoint_rows)
        packet = build_decision_packet(
            candidates[:30],
            project_name=project_name,
            source_run_id=saved_run_id,
            parent_smiles=result.get("parent_smiles"),
            direction=endpoint_config["direction"],
            site_type=(result.get("selected_site") or {}).get("site_type"),
        )
        saved_packet_ids.append(
            save_decision_packet(
                packet,
                db_path=db_path,
                packet_id=endpoint_config["packet_id"],
                status="approved",
                reviewer="demo_seed",
                review_note=f"Seed packet for {endpoint_config['endpoint_group']} retrospective strategy learning.",
            )
        )
        endpoint_reports.append(
            {
                "endpoint_group": endpoint_config["endpoint_group"],
                "run_id": saved_run_id,
                "packet_id": endpoint_config["packet_id"],
                "candidate_count": len(candidates),
                "seeded_feedback_count": len(endpoint_rows),
            }
        )
    output_path = Path(output_csv)
    _write_csv(rows, output_path)
    source_path = str(output_path.resolve())
    _cleanup_existing(db_path, [row["plan_id"] for row in rows], source_path)
    upsert_report = upsert_experiment_plan_rows(rows, db_path=db_path, source_path=source_path)
    import_report = import_experiment_results_rows(rows, db_path=db_path, source_path=source_path)
    learning = build_assay_learning_report(db_path=db_path, project_name=project_name)
    calibration = calibrate_project_models(db_path=db_path, project_name=project_name, min_feedback=20)
    save_calibration_report(calibration, db_path=db_path)
    report_path = ROOT / "data" / "projects" / "demo" / "demo_learning_model_calibration_report.json"
    write_calibration_report(calibration, report_path)
    profile_paths = write_calibration_profiles(calibration, ROOT / "data" / "profiles" / "calibrated")
    return {
        "project_name": project_name,
        "run_id": first_saved_run_id or run_id,
        "packet_id": saved_packet_ids[0] if saved_packet_ids else packet_id,
        "endpoint_reports": endpoint_reports,
        "candidate_count": total_candidate_count,
        "csv_path": source_path,
        "upsert_report": upsert_report,
        "import_report": import_report,
        "assay_learning": learning,
        "calibration_report": str(report_path.resolve()),
        "profile_paths": [str(path.resolve()) for path in profile_paths],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo historical potency feedback so endpoint gates learn observed thresholds.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default=DEFAULT_PROJECT)
    parser.add_argument("--output-csv", default=str(ROOT / "data" / "projects" / "demo" / "historical_experiment_results.csv"))
    args = parser.parse_args()
    report = seed_demo_historical_feedback(db_path=args.db, project_name=args.project_name, output_csv=args.output_csv)
    report_path = ROOT / "data" / "projects" / "demo" / "historical_feedback_seed_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
