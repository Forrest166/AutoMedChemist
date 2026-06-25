from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .analog_series import build_queue_analog_series_delta, write_queue_analog_series_delta_report
from .closed_loop_acceptance import evaluate_closed_loop_drill_acceptance, write_closed_loop_drill_acceptance
from .closed_loop_delta import build_priority_delta_report
from .decision_packet import build_decision_packet, save_decision_packet, write_decision_packet
from .export import export_csv, export_sdf
from .feedback import import_feedback_rows
from .pipeline import run_mvp
from .priority_queue import build_next_design_queue, write_next_design_queue
from .project_store import save_project_run
from .prospective import build_feedback_control_report, save_feedback_control_report


def _write_generation_outputs(result: dict, output_dir: str | Path) -> None:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    rows = result.get("candidates") or []
    export_csv(rows, path / "candidates.csv")
    export_sdf(rows, path / "candidates.sdf")


def synthetic_feedback_rows(result: dict, run_id: str, project_name: str, *, endpoint_group: str, assay_type: str, limit: int = 4) -> list[dict]:
    rows = []
    for index, candidate in enumerate((result.get("candidates") or [])[:limit], start=1):
        score = float(candidate.get("score") or 50.0)
        normalized = max(10.0, min(95.0, score - 8.0 + index * 2.0))
        if index == 2:
            normalized = max(15.0, normalized - 35.0)
        classification = "active" if normalized >= 70 else "fail" if normalized <= 40 else "watch"
        rows.append(
            {
                "run_id": run_id,
                "candidate_id": candidate.get("candidate_id"),
                "project_name": project_name,
                "endpoint": endpoint_group,
                "assay_name": assay_type,
                "assay_type": assay_type,
                "normalized_score": round(normalized, 2),
                "classification": classification,
                "source_path": "closed_loop_drill_synthetic_feedback",
                "note": "Synthetic closed-loop drill outcome for exercising local feedback machinery.",
            }
        )
    return rows


def run_closed_loop_drill(
    *,
    db_path: str | Path,
    output_dir: str | Path,
    project_name: str = "closed_loop_drill",
    smiles: str = "COc1ccc(Cl)cc1",
    direction: str = "increase_polarity",
    endpoint_group: str = "potency",
    assay_type: str = "IC50",
    target_family: str | None = "kinase",
    max_candidates: int = 60,
    feedback_limit: int = 4,
    acceptance_criteria_path: str | Path = "data/rules/closed_loop_acceptance.yaml",
) -> dict:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(db_path)
    project_instance_name = f"{project_name}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    target_context = {
        "endpoint_group": endpoint_group,
        "assay_type": assay_type,
        "target_family": target_family,
    }

    before_control = build_feedback_control_report(db_path=db_path, project_name=project_instance_name, min_feedback=1)
    first_result = run_mvp(
        smiles=smiles,
        direction=direction,
        db_path=db_path,
        project_name=project_instance_name,
        target_context=target_context,
        queue_analog_series_delta_path=None,
        max_candidates=max_candidates,
    )
    _write_generation_outputs(first_result, out_dir / "first_generation")
    first_run_id = save_project_run(first_result, db_path=db_path, project_name=project_instance_name, note="closed-loop drill first generation")
    first_packet = build_decision_packet(
        first_result.get("candidates") or [],
        project_name=project_instance_name,
        source_run_id=first_run_id,
        parent_smiles=first_result.get("parent_smiles"),
        direction=direction,
        site_type=(first_result.get("selected_site") or {}).get("site_type"),
        limit=24,
    )
    first_packet_id = save_decision_packet(first_packet, db_path=db_path, reviewer="closed_loop_drill")
    packet_outputs = write_decision_packet(first_packet, out_dir / "medchem_decision_packet")

    feedback_rows = synthetic_feedback_rows(
        first_result,
        first_run_id,
        project_instance_name,
        endpoint_group=endpoint_group,
        assay_type=assay_type,
        limit=feedback_limit,
    )
    feedback_report = import_feedback_rows(feedback_rows, db_path=db_path, source_path="closed_loop_drill_synthetic_feedback")
    feedback_path = out_dir / "synthetic_feedback_rows.json"
    feedback_path.write_text(json.dumps({"feedback_rows": feedback_rows}, indent=2, sort_keys=True), encoding="utf-8")

    after_control = build_feedback_control_report(db_path=db_path, project_name=project_instance_name, min_feedback=1)
    save_feedback_control_report(after_control, output_path=out_dir / "feedback_control_after.json", db_path=db_path)
    priority_delta = build_priority_delta_report(before_control, after_control, db_path=db_path, project_name=project_instance_name)
    priority_delta_path = out_dir / "priority_delta.json"
    priority_delta_path.write_text(json.dumps(priority_delta, indent=2, sort_keys=True), encoding="utf-8")

    queue_series_delta = build_queue_analog_series_delta(priority_delta)
    queue_series_delta_path = out_dir / "queue_analog_series_delta.json"
    write_queue_analog_series_delta_report(queue_series_delta, queue_series_delta_path)

    queue_rows = build_next_design_queue(priority_delta, max_rows=24, decision_packets=[first_packet])
    write_next_design_queue(
        queue_rows,
        csv_path=out_dir / "next_design_queue.csv",
        json_path=out_dir / "next_design_queue.json",
        markdown_path=out_dir / "next_design_queue.md",
    )

    second_result = run_mvp(
        smiles=smiles,
        direction=direction,
        db_path=db_path,
        project_name=project_instance_name,
        target_context=target_context,
        queue_analog_series_delta_path=queue_series_delta_path,
        max_candidates=max_candidates,
    )
    _write_generation_outputs(second_result, out_dir / "second_generation")
    second_run_id = save_project_run(second_result, db_path=db_path, project_name=project_instance_name, note="closed-loop drill second generation")
    adjusted_candidates = [
        {
            "candidate_id": row.get("candidate_id"),
            "rank": row.get("rank"),
            "score": row.get("score"),
            "replacement_label": row.get("replacement_label"),
            "queue_analog_series_delta_action": row.get("queue_analog_series_delta_action"),
            "queue_analog_series_delta_score_delta": row.get("queue_analog_series_delta_score_delta"),
            "queue_analog_series_delta_basis": row.get("queue_analog_series_delta_basis"),
        }
        for row in second_result.get("candidates") or []
        if float(row.get("queue_analog_series_delta_score_delta") or 0.0) != 0.0
    ][:12]

    report = {
        "project_name": project_name,
        "project_instance_name": project_instance_name,
        "first_run_id": first_run_id,
        "second_run_id": second_run_id,
        "first_packet_id": first_packet_id,
        "first_candidate_count": first_result.get("candidate_count"),
        "second_candidate_count": second_result.get("candidate_count"),
        "feedback_inserted_count": feedback_report.get("inserted_count"),
        "priority_delta_count": priority_delta.get("candidate_count"),
        "next_design_queue_count": len(queue_rows),
        "queue_analog_series_delta_count": queue_series_delta.get("series_count"),
        "queue_analog_series_delta_action_counts": queue_series_delta.get("action_counts"),
        "series_adjusted_candidate_count": len(adjusted_candidates),
        "series_adjusted_candidates": adjusted_candidates,
        "outputs": {
            "packet_json": packet_outputs.get("json"),
            "feedback_rows": str(feedback_path.resolve()),
            "priority_delta": str(priority_delta_path.resolve()),
            "queue_analog_series_delta": str(queue_series_delta_path.resolve()),
            "next_design_queue": str((out_dir / "next_design_queue.json").resolve()),
            "first_generation_dir": str((out_dir / "first_generation").resolve()),
            "second_generation_dir": str((out_dir / "second_generation").resolve()),
        },
        "next_actions": [
            "Review adjusted second-generation candidates before promoting series-level score changes into policy defaults.",
            "Use residual data tasks to decide which assay contexts should receive more outcomes before broad expansion.",
        ],
    }
    acceptance = evaluate_closed_loop_drill_acceptance(report, criteria_path=acceptance_criteria_path)
    acceptance_path = out_dir / "closed_loop_drill_acceptance.json"
    write_closed_loop_drill_acceptance(acceptance, acceptance_path)
    report["acceptance"] = acceptance
    report["outputs"]["acceptance"] = str(acceptance_path.resolve())
    report_path = out_dir / "closed_loop_drill_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
