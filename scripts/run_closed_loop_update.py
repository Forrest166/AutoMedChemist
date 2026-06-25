from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.calibration import calibrate_project_models, save_calibration_report, write_calibration_profiles, write_calibration_report  # noqa: E402
from localmedchem.closed_loop_delta import build_priority_delta_report  # noqa: E402
from localmedchem.experiment_tracking import import_experiment_results_csv, summarize_experiment_plans, write_experiment_tracking_report  # noqa: E402
from localmedchem.analog_series import build_analog_series_report, build_queue_analog_series_delta, write_analog_series_report, write_queue_analog_series_delta_report  # noqa: E402
from localmedchem.assay_learning import build_assay_learning_report  # noqa: E402
from localmedchem.priority_queue import (  # noqa: E402
    build_next_design_queue,
    load_next_design_queue_decisions,
    load_next_design_queue_decisions_from_db,
    save_next_design_queue_decisions,
    write_next_design_queue,
    write_next_design_queue_decision_template,
    build_next_design_queue_decision_quality_report,
    write_next_design_queue_decision_quality_report,
)
from localmedchem.prospective import build_feedback_control_report, save_feedback_control_report  # noqa: E402
from localmedchem.scaffold_calibration import scaffold_context_calibration_report  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"files": {}}
    return json.loads(path.read_text(encoding="utf-8")) or {"files": {}}


def _write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _project_from_csv(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            first = next(csv.DictReader(handle), None)
            if first and first.get("project_name"):
                return str(first["project_name"]).strip() or None
    except Exception:
        return None
    return None


def _candidate_files(projects_dir: Path) -> list[Path]:
    patterns = [
        "**/incoming_results/*.csv",
        "**/experiment_results/*.csv",
        "**/*experiment_results*.csv",
    ]
    files = []
    for pattern in patterns:
        files.extend(projects_dir.glob(pattern))
    return sorted({path.resolve() for path in files if path.is_file()})


def _load_project_decision_packets(projects_dir: Path, project_name: str | None, *, limit: int = 8) -> list[dict]:
    packet_paths = sorted(projects_dir.glob("**/*decision_packet.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    matching_packets = []
    fallback_packets = []
    for path in packet_paths:
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        packet_project = packet.get("project_name")
        if project_name and packet_project not in {None, "", project_name}:
            fallback_packets.append(packet)
            continue
        matching_packets.append(packet)
        if len(matching_packets) >= limit:
            break
    return (matching_packets or fallback_packets)[:limit]


def run_closed_loop_update(
    *,
    db_path: str | Path,
    projects_dir: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path,
    project_name: str | None = None,
    min_feedback: int = 3,
) -> dict:
    db_path = Path(db_path)
    projects_dir = Path(projects_dir)
    output_dir = Path(output_dir)
    manifest_path = Path(manifest_path)
    manifest = _load_manifest(manifest_path)
    imported = []
    skipped = []
    projects: set[str | None] = {project_name} if project_name else set()
    candidate_files = _candidate_files(projects_dir)
    for path in candidate_files:
        inferred_project = project_name or _project_from_csv(path)
        if inferred_project:
            projects.add(inferred_project)
    before_controls = {
        project: build_feedback_control_report(db_path=db_path, project_name=project, min_feedback=min_feedback)
        for project in projects
    }
    for path in candidate_files:
        sha = _sha256(path)
        key = str(path)
        prior = (manifest.get("files") or {}).get(key) or {}
        if prior.get("sha256") == sha:
            skipped.append({"path": key, "reason": "unchanged"})
            if prior.get("project_name"):
                projects.add(prior.get("project_name"))
            continue
        inferred_project = project_name or _project_from_csv(path)
        result = import_experiment_results_csv(path, db_path=db_path)
        manifest.setdefault("files", {})[key] = {
            "sha256": sha,
            "project_name": inferred_project,
            "result": result,
        }
        imported.append({"path": key, "project_name": inferred_project, **result})
        projects.add(inferred_project)
    _write_manifest(manifest_path, manifest)

    output_dir.mkdir(parents=True, exist_ok=True)
    project_reports = []
    for project in sorted(projects, key=lambda value: str(value or "")):
        tracking = summarize_experiment_plans(db_path=db_path, project_name=project)
        write_experiment_tracking_report(tracking, output_dir / f"experiment_tracking_{project or 'all'}.json")
        calibration = calibrate_project_models(db_path=db_path, project_name=project, min_feedback=min_feedback)
        save_calibration_report(calibration, db_path=db_path)
        write_calibration_report(calibration, output_dir / f"model_calibration_{project or 'all'}.json")
        profiles = write_calibration_profiles(calibration, Path("data/profiles/calibrated"))
        control = build_feedback_control_report(db_path=db_path, project_name=project, min_feedback=min_feedback)
        save_feedback_control_report(control, output_path=output_dir / f"feedback_control_{project or 'all'}.json", db_path=db_path)
        priority_delta = build_priority_delta_report(
            before_controls.get(project),
            control,
            db_path=db_path,
            project_name=project,
        )
        (output_dir / f"priority_delta_{project or 'all'}.json").write_text(
            json.dumps(priority_delta, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        assay_learning = build_assay_learning_report(db_path=db_path, project_name=project)
        (output_dir / f"assay_learning_{project or 'all'}.json").write_text(
            json.dumps(assay_learning, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        analog_series = build_analog_series_report(
            db_path=db_path,
            project_name=project,
            assay_learning_report=assay_learning,
        )
        write_analog_series_report(analog_series, output_dir / f"analog_series_{project or 'all'}.json")
        queue_series_delta = build_queue_analog_series_delta(priority_delta)
        write_queue_analog_series_delta_report(
            queue_series_delta,
            output_dir / f"queue_analog_series_delta_{project or 'all'}.json",
        )
        decision_packets = _load_project_decision_packets(projects_dir, project)
        queue_slug = project or "all"
        queue_decision_path = output_dir / f"next_design_queue_decisions_{queue_slug}.csv"
        queue_decisions = load_next_design_queue_decisions(queue_decision_path)
        if queue_decisions:
            save_next_design_queue_decisions(queue_decisions, db_path=db_path, source_path=queue_decision_path)
        queue_db_decisions = load_next_design_queue_decisions_from_db(db_path=db_path, project_name=project)
        queue_decisions = [*queue_decisions, *queue_db_decisions]
        queue_rows = build_next_design_queue(
            priority_delta,
            max_rows=24,
            decision_packets=decision_packets,
            analog_series_report=analog_series,
            queue_analog_series_delta_report=queue_series_delta,
            queue_decisions=queue_decisions,
        )
        write_next_design_queue(
            queue_rows,
            csv_path=output_dir / f"next_design_queue_{queue_slug}.csv",
            json_path=output_dir / f"next_design_queue_{queue_slug}.json",
            markdown_path=output_dir / f"next_design_queue_{queue_slug}.md",
        )
        write_next_design_queue_decision_template(queue_rows, output_dir / f"next_design_queue_decisions_{queue_slug}_template.csv")
        queue_decision_quality = build_next_design_queue_decision_quality_report(db_path=db_path, project_name=project)
        write_next_design_queue_decision_quality_report(
            queue_decision_quality,
            output_dir / f"next_design_queue_decision_quality_{queue_slug}.json",
        )
        scaffold_report = scaffold_context_calibration_report(db_path=db_path, project_name=project)
        (output_dir / f"scaffold_context_calibration_{project or 'all'}.json").write_text(
            json.dumps(scaffold_report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        project_reports.append(
            {
                "project_name": project,
                "tracking": tracking,
                "calibration_feedback_count": calibration.get("feedback_count"),
                "calibrated_profile_count": len(profiles),
                "feedback_control_recommendation_count": len(control.get("recommended_next_experiments") or []),
                "priority_delta_count": priority_delta.get("candidate_count"),
                "priority_delta_status_counts": priority_delta.get("status_counts"),
                "queue_analog_series_delta_count": queue_series_delta.get("series_count"),
                "queue_analog_series_delta_action_counts": queue_series_delta.get("action_counts"),
                "next_design_queue_count": len(queue_rows),
                "next_design_queue_decision_count": len(queue_decisions),
                "next_design_queue_decision_quality_observed_count": queue_decision_quality.get("observed_decision_count"),
                "decision_packet_context_count": len(decision_packets),
                "analog_series_count": analog_series.get("series_count"),
                "scaffold_context_candidate_count": scaffold_report.get("scaffold_candidate_count"),
            }
        )
    report = {
        "imported_file_count": len(imported),
        "skipped_file_count": len(skipped),
        "imported_files": imported,
        "skipped_files": skipped,
        "project_reports": project_reports,
    }
    (output_dir / "closed_loop_update_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import new experiment results and refresh closed-loop calibration reports.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--projects-dir", default=str(ROOT / "data" / "projects"))
    parser.add_argument("--manifest", default=str(ROOT / "data" / "projects" / "experiment_result_import_manifest.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "projects" / "closed_loop"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--min-feedback", type=int, default=3)
    args = parser.parse_args()
    report = run_closed_loop_update(
        db_path=args.db_path,
        projects_dir=args.projects_dir,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        project_name=args.project_name,
        min_feedback=args.min_feedback,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
