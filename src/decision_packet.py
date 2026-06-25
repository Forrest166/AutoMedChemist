from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from .database import initialize_database


DECISION_PACKET_FIELDS = [
    "packet_rank",
    "candidate_id",
    "decision_recommendation",
    "decision_rationale",
    "score",
    "score_without_strategy_prior",
    "strategy_learning_score_delta",
    "queue_analog_series_delta_score_delta",
    "score_after_queue_analog_series_delta",
    "multi_objective_score_delta",
    "multi_objective_profile_id",
    "multi_objective_score",
    "multi_objective_potency_score",
    "multi_objective_stability_score",
    "multi_objective_permeability_score",
    "multi_objective_liability_score",
    "multi_objective_constraint_flags",
    "multi_objective_basis",
    "site_type",
    "direction",
    "enumeration_type",
    "diversity_bucket",
    "replacement_label",
    "evidence_consistency_score",
    "evidence_confidence_calibration_score",
    "evidence_confidence_adjustment",
    "evidence_confidence_sources",
    "evidence_confidence_source_count",
    "evidence_confidence_status",
    "evidence_confidence_target_family",
    "evidence_confidence_assay_type",
    "evidence_confidence_max_abs_residual",
    "evidence_confidence_residual_basis",
    "evidence_confidence_interval_low",
    "evidence_confidence_interval_high",
    "evidence_confidence_interval_width",
    "evidence_confidence_interval_basis",
    "evidence_conflict_flags",
    "evidence_context_judgment",
    "evidence_target_family",
    "evidence_target_family_normalized",
    "evidence_assay_type",
    "mmp_precedent_strength",
    "transform_activity_score",
    "risk_score",
    "synthetic_score",
    "scaffold_context_score",
    "scaffold_local_evidence_score",
    "scaffold_local_evidence_strength",
    "scaffold_local_mmp_score",
    "scaffold_local_mmp_strength",
    "endpoint_gate_decision",
    "endpoint_gate_endpoint",
    "endpoint_gate_basis",
    "scaffold_operator_prior_score",
    "scaffold_operator_prior_basis",
    "strategy_learning_prior_score",
    "strategy_learning_score_adjustment",
    "strategy_learning_recommendation",
    "strategy_learning_basis",
    "queue_analog_series_delta_action",
    "queue_analog_series_delta_score_adjustment",
    "queue_analog_series_delta_mean_priority_delta",
    "queue_analog_series_delta_basis",
    "endpoint_family_residual_score_adjustment",
    "endpoint_family_residual_adjustment_ids",
    "endpoint_family_residual_adjustment_basis",
    "public_strategy_signal_score",
    "public_strategy_signal_basis",
    "public_strategy_signal_count",
    "novelty_batch_pick",
    "novelty_batch_rank",
    "novelty_batch_tier",
    "recommended_experiment",
    "smiles",
]

PACKET_REVIEW_STATUSES = ["needs_review", "in_review", "approved", "rejected", "superseded"]
DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _flags(row: dict) -> set[str]:
    return {flag for flag in str(row.get("evidence_conflict_flags") or "").split(";") if flag}


def decision_recommendation(row: dict) -> tuple[str, str]:
    score = _float(row.get("score"))
    evidence = _float(row.get("evidence_consistency_score"), 100.0)
    risk = _float(row.get("risk_score"), 100.0)
    synthetic = _float(row.get("synthetic_score"), 80.0)
    flags = _flags(row)
    severe_flags = {
        "target_family_activity_contradiction",
        "target_family_activity_cliff_high",
        "project_negative_public_positive",
        "activity_cliff_high",
    }
    if score >= 78 and evidence >= 65 and risk >= 55 and not flags.intersection(severe_flags):
        return "make", "High integrated score with acceptable evidence and risk profile."
    if score < 55 or evidence < 45 or risk < 40:
        return "reject", "Low score or material evidence/risk concern."
    if synthetic < 45:
        return "defer", "Synthetic access looks weak; keep as design idea until chemistry route is clarified."
    if flags:
        return "defer", "Evidence conflict needs assay or project-feedback clarification."
    return "defer", "Moderate candidate; useful as backup or focused follow-up."


def recommended_experiment(row: dict, *, default_endpoint: str = "project_panel") -> str:
    endpoint = row.get("evidence_endpoint_group") or row.get("endpoint_group") or default_endpoint
    if row.get("evidence_context_judgment") == "contradicted":
        return f"Confirm {endpoint} in target-family matched assay."
    if "activity_cliff_high" in _flags(row) or "target_family_activity_cliff_high" in _flags(row):
        return f"Run paired {endpoint} assay with parent and nearest analog."
    if row.get("diverse_pick"):
        return f"Include in next {endpoint} diversity panel."
    return f"Hold for backup {endpoint} panel."


def _packet_series_key(row: dict) -> str:
    return "|".join(
        [
            str(row.get("site_type") or "unspecified"),
            str(row.get("enumeration_type") or "unspecified"),
            str(row.get("diversity_bucket") or row.get("replacement_label") or "unspecified"),
        ]
    )


def _packet_analog_series_summary(packet_rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in packet_rows:
        groups[_packet_series_key(row)].append(row)
    series = []
    for key, rows in groups.items():
        scores = [_optional_float(row.get("score")) for row in rows if _optional_float(row.get("score")) is not None]
        evidence_scores = [
            _optional_float(row.get("evidence_confidence_calibration_score"))
            for row in rows
            if _optional_float(row.get("evidence_confidence_calibration_score")) is not None
        ]
        residuals = [
            abs(_optional_float(row.get("evidence_confidence_max_abs_residual")) or 0.0)
            for row in rows
            if _optional_float(row.get("evidence_confidence_max_abs_residual")) is not None
        ]
        decisions = Counter(str(row.get("decision_recommendation") or "unknown") for row in rows)
        novelty_count = sum(1 for row in rows if row.get("novelty_batch_pick") is True or str(row.get("novelty_batch_pick")).lower() == "true")
        severe_conflict_count = sum(
            1
            for row in rows
            if any(
                flag in {"target_family_activity_contradiction", "target_family_activity_cliff_high", "activity_cliff_high"}
                for flag in str(row.get("evidence_conflict_flags") or "").split(";")
                if flag
            )
        )
        top_rows = sorted(rows, key=lambda item: _float(item.get("score")), reverse=True)[:5]
        series.append(
            {
                "series_key": key,
                "site_type": rows[0].get("site_type"),
                "operator": rows[0].get("enumeration_type"),
                "diversity_bucket": rows[0].get("diversity_bucket"),
                "candidate_count": len(rows),
                "top_score": round(max(scores), 4) if scores else None,
                "mean_score": round(sum(scores) / len(scores), 4) if scores else None,
                "mean_evidence_confidence_score": round(sum(evidence_scores) / len(evidence_scores), 4) if evidence_scores else None,
                "max_abs_evidence_residual": round(max(residuals), 4) if residuals else None,
                "novelty_pick_count": novelty_count,
                "severe_conflict_count": severe_conflict_count,
                "decision_counts": dict(decisions.most_common()),
                "representative_candidate_ids": ";".join(str(row.get("candidate_id")) for row in top_rows if row.get("candidate_id")),
                "series_packet_action": (
                    "review_conflict"
                    if severe_conflict_count
                    else "primary_series"
                    if decisions.get("make", 0) >= max(1, len(rows) // 2)
                    else "backup_series"
                ),
            }
        )
    series.sort(key=lambda row: (row.get("series_packet_action") != "primary_series", -(row.get("top_score") or 0), -(row.get("candidate_count") or 0)))
    return {
        "series_count": len(series),
        "series": series,
        "one_page_summary": series[:8],
    }


def _packet_uncertainty_band(row: dict) -> dict:
    center = next(
        (
            value
            for value in [
                _optional_float(row.get("evidence_confidence_calibration_score")),
                _optional_float(row.get("evidence_consistency_score")),
                _optional_float(row.get("score")),
            ]
            if value is not None
        ),
        50.0,
    )
    status = str(row.get("evidence_confidence_status") or "").strip().lower()
    residual = abs(_optional_float(row.get("evidence_confidence_max_abs_residual")) or 0.0)
    source_count = int(_optional_float(row.get("evidence_confidence_source_count")) or 0)
    half_width = max(5.0, residual * 100.0)
    basis = []
    if residual:
        basis.append(f"max_abs_residual={residual:.3f}")
    if status in {"no_evidence_sources", "uncalibrated", "unknown"}:
        half_width += 10.0
        basis.append(f"evidence_status={status or 'unknown'}")
    elif status in {"provisional", "collect_more_outcomes"}:
        half_width += 6.0
        basis.append(f"evidence_status={status}")
    elif status:
        basis.append(f"evidence_status={status}")
    if source_count <= 1:
        half_width += 4.0
        basis.append(f"source_count={source_count}")
    half_width = max(5.0, min(35.0, half_width))
    low = max(0.0, center - half_width)
    high = min(100.0, center + half_width)
    return {
        "evidence_confidence_interval_low": round(low, 4),
        "evidence_confidence_interval_high": round(high, 4),
        "evidence_confidence_interval_width": round(high - low, 4),
        "evidence_confidence_interval_basis": "; ".join(basis) or "default_minimum_interval",
    }


def _packet_evidence_uncertainty_summary(packet_rows: list[dict]) -> dict:
    statuses = Counter(str(row.get("evidence_confidence_status") or "unknown") for row in packet_rows)
    residual_rows = []
    interval_rows = []
    for row in packet_rows:
        interval_width = _optional_float(row.get("evidence_confidence_interval_width"))
        if interval_width is not None:
            interval_rows.append(
                {
                    "candidate_id": row.get("candidate_id"),
                    "decision_recommendation": row.get("decision_recommendation"),
                    "evidence_confidence_interval_low": row.get("evidence_confidence_interval_low"),
                    "evidence_confidence_interval_high": row.get("evidence_confidence_interval_high"),
                    "evidence_confidence_interval_width": round(interval_width, 4),
                    "evidence_confidence_interval_basis": row.get("evidence_confidence_interval_basis"),
                }
            )
        residual = _optional_float(row.get("evidence_confidence_max_abs_residual"))
        if residual is None:
            continue
        residual_rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "decision_recommendation": row.get("decision_recommendation"),
                "score": row.get("score"),
                "evidence_confidence_status": row.get("evidence_confidence_status"),
                "evidence_confidence_target_family": row.get("evidence_confidence_target_family"),
                "evidence_confidence_assay_type": row.get("evidence_confidence_assay_type"),
                "evidence_confidence_max_abs_residual": round(abs(residual), 4),
                "evidence_confidence_residual_basis": row.get("evidence_confidence_residual_basis"),
                "evidence_confidence_interval_width": row.get("evidence_confidence_interval_width"),
            }
        )
    residual_rows.sort(
        key=lambda row: (
            -float(row.get("evidence_confidence_max_abs_residual") or 0.0),
            str(row.get("candidate_id") or ""),
        )
    )
    residual_values = [float(row["evidence_confidence_max_abs_residual"]) for row in residual_rows]
    high_uncertainty = [
        row
        for row in packet_rows
        if str(row.get("evidence_confidence_status") or "unknown").lower() in {"unknown", "provisional", "uncalibrated", "no_evidence_sources"}
        or (_optional_float(row.get("evidence_confidence_max_abs_residual")) or 0.0) >= 0.25
        or (_optional_float(row.get("evidence_confidence_interval_width")) or 0.0) >= 30
    ]
    interval_rows.sort(
        key=lambda row: (
            -float(row.get("evidence_confidence_interval_width") or 0.0),
            str(row.get("candidate_id") or ""),
        )
    )
    interval_widths = [float(row["evidence_confidence_interval_width"]) for row in interval_rows]
    return {
        "status_counts": dict(statuses.most_common()),
        "candidate_count_with_residual": len(residual_rows),
        "high_uncertainty_candidate_count": len(high_uncertainty),
        "mean_abs_residual": round(sum(residual_values) / len(residual_values), 4) if residual_values else None,
        "max_abs_residual": round(max(residual_values), 4) if residual_values else None,
        "mean_confidence_interval_width": round(sum(interval_widths) / len(interval_widths), 4) if interval_widths else None,
        "max_confidence_interval_width": round(max(interval_widths), 4) if interval_widths else None,
        "top_residual_candidates": residual_rows[:8],
        "top_interval_candidates": interval_rows[:8],
    }


def build_decision_packet(
    rows: list[dict],
    *,
    project_name: str | None = None,
    source_run_id: str | None = None,
    parent_smiles: str | None = None,
    direction: str | None = None,
    site_type: str | None = None,
    limit: int | None = 50,
) -> dict:
    sorted_rows = sorted(rows, key=lambda row: _float(row.get("score")), reverse=True)
    if limit is not None:
        sorted_rows = sorted_rows[:limit]
    packet_rows = []
    for rank, row in enumerate(sorted_rows, start=1):
        recommendation, rationale = decision_recommendation(row)
        packet_rows.append(
            {
                "packet_rank": rank,
                "candidate_id": row.get("candidate_id"),
                "decision_recommendation": recommendation,
                "decision_rationale": rationale,
                "score": row.get("score"),
                "score_without_strategy_prior": row.get("score_without_strategy_prior"),
                "strategy_learning_score_delta": row.get("strategy_learning_score_delta"),
                "queue_analog_series_delta_score_delta": row.get("queue_analog_series_delta_score_delta"),
                "score_after_queue_analog_series_delta": row.get("score_after_queue_analog_series_delta"),
                "multi_objective_score_delta": row.get("multi_objective_score_delta"),
                "multi_objective_profile_id": row.get("multi_objective_profile_id"),
                "multi_objective_score": row.get("multi_objective_score"),
                "multi_objective_potency_score": row.get("multi_objective_potency_score"),
                "multi_objective_stability_score": row.get("multi_objective_stability_score"),
                "multi_objective_permeability_score": row.get("multi_objective_permeability_score"),
                "multi_objective_liability_score": row.get("multi_objective_liability_score"),
                "multi_objective_constraint_flags": row.get("multi_objective_constraint_flags"),
                "multi_objective_basis": row.get("multi_objective_basis"),
                "site_type": row.get("site_type") or site_type,
                "direction": row.get("direction") or direction,
                "enumeration_type": row.get("enumeration_type"),
                "diversity_bucket": row.get("diversity_bucket"),
                "replacement_label": row.get("replacement_label"),
                "evidence_consistency_score": row.get("evidence_consistency_score"),
                "evidence_confidence_calibration_score": row.get("evidence_confidence_calibration_score"),
                "evidence_confidence_adjustment": row.get("evidence_confidence_adjustment"),
                "evidence_confidence_sources": row.get("evidence_confidence_sources"),
                "evidence_confidence_source_count": row.get("evidence_confidence_source_count"),
                "evidence_confidence_status": row.get("evidence_confidence_status"),
                "evidence_confidence_target_family": row.get("evidence_confidence_target_family"),
                "evidence_confidence_assay_type": row.get("evidence_confidence_assay_type"),
                "evidence_confidence_max_abs_residual": row.get("evidence_confidence_max_abs_residual"),
                "evidence_confidence_residual_basis": row.get("evidence_confidence_residual_basis"),
                **_packet_uncertainty_band(row),
                "evidence_conflict_flags": row.get("evidence_conflict_flags"),
                "evidence_context_judgment": row.get("evidence_context_judgment"),
                "evidence_target_family": row.get("evidence_target_family"),
                "evidence_target_family_normalized": row.get("evidence_target_family_normalized"),
                "evidence_assay_type": row.get("evidence_assay_type"),
                "mmp_precedent_strength": row.get("mmp_precedent_strength"),
                "transform_activity_score": row.get("transform_activity_score"),
                "risk_score": row.get("risk_score"),
                "synthetic_score": row.get("synthetic_score"),
                "scaffold_context_score": row.get("scaffold_context_score"),
                "scaffold_local_evidence_score": row.get("scaffold_local_evidence_score"),
                "scaffold_local_evidence_strength": row.get("scaffold_local_evidence_strength"),
                "scaffold_local_mmp_score": row.get("scaffold_local_mmp_score") or row.get("scaffold_local_evidence_score"),
                "scaffold_local_mmp_strength": row.get("scaffold_local_mmp_strength") or row.get("scaffold_local_evidence_strength"),
                "endpoint_gate_decision": row.get("endpoint_gate_decision"),
                "endpoint_gate_endpoint": row.get("endpoint_gate_endpoint"),
                "endpoint_gate_basis": row.get("endpoint_gate_basis"),
                "scaffold_operator_prior_score": row.get("scaffold_operator_prior_score"),
                "scaffold_operator_prior_basis": row.get("scaffold_operator_prior_basis"),
                "strategy_learning_prior_score": row.get("strategy_learning_prior_score"),
                "strategy_learning_score_adjustment": row.get("strategy_learning_score_adjustment"),
                "strategy_learning_recommendation": row.get("strategy_learning_recommendation"),
                "strategy_learning_basis": row.get("strategy_learning_basis"),
                "queue_analog_series_delta_action": row.get("queue_analog_series_delta_action"),
                "queue_analog_series_delta_score_adjustment": row.get("queue_analog_series_delta_score_adjustment"),
                "queue_analog_series_delta_mean_priority_delta": row.get("queue_analog_series_delta_mean_priority_delta"),
                "queue_analog_series_delta_basis": row.get("queue_analog_series_delta_basis"),
                "public_strategy_signal_score": row.get("public_strategy_signal_score"),
                "public_strategy_signal_basis": row.get("public_strategy_signal_basis"),
                "public_strategy_signal_count": row.get("public_strategy_signal_count"),
                "novelty_batch_pick": row.get("novelty_batch_pick"),
                "novelty_batch_rank": row.get("novelty_batch_rank"),
                "novelty_batch_tier": row.get("novelty_batch_tier"),
                "recommended_experiment": recommended_experiment(row),
                "smiles": row.get("smiles"),
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "source_run_id": source_run_id,
        "parent_smiles": parent_smiles,
        "direction": direction,
        "site_type": site_type,
        "candidate_count": len(packet_rows),
        "decision_counts": {
            label: sum(1 for row in packet_rows if row["decision_recommendation"] == label)
            for label in ["make", "defer", "reject"]
        },
        "analog_series_summary": _packet_analog_series_summary(packet_rows),
        "evidence_uncertainty_summary": _packet_evidence_uncertainty_summary(packet_rows),
        "candidates": packet_rows,
    }


def decision_packet_csv_text(packet: dict) -> str:
    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=DECISION_PACKET_FIELDS)
    writer.writeheader()
    for row in packet.get("candidates") or []:
        writer.writerow({key: row.get(key, "") for key in DECISION_PACKET_FIELDS})
    return handle.getvalue()


def decision_packet_markdown(packet: dict) -> str:
    lines = [
        "# Medchem Decision Packet",
        "",
        f"- Project: `{packet.get('project_name') or ''}`",
        f"- Parent: `{packet.get('parent_smiles') or ''}`",
        f"- Direction: `{packet.get('direction') or ''}`",
        f"- Candidates: `{packet.get('candidate_count')}`",
        "",
        "| Rank | Candidate | Decision | Score | Evidence | Rationale | Experiment |",
        "| ---: | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in packet.get("candidates") or []:
        lines.append(
            "| {rank} | `{cid}` | {decision} | {score} | {evidence} | {rationale} | {experiment} |".format(
                rank=row.get("packet_rank"),
                cid=row.get("candidate_id"),
                decision=row.get("decision_recommendation"),
                score=row.get("score"),
                evidence=row.get("evidence_consistency_score"),
                rationale=str(row.get("decision_rationale") or "").replace("|", "/"),
                experiment=str(row.get("recommended_experiment") or "").replace("|", "/"),
            )
        )
    analog = (packet.get("analog_series_summary") or {}).get("one_page_summary") or []
    if analog:
        lines.extend(
            [
                "",
                "## Analog Series Summary",
                "",
                "| Series | Candidates | Action | Top Score | Mean Evidence | Residual | Representatives |",
                "| --- | ---: | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for row in analog:
            lines.append(
                "| {series} | {count} | `{action}` | {top} | {evidence} | {residual} | `{examples}` |".format(
                    series=str(row.get("series_key") or "").replace("|", "/"),
                    count=row.get("candidate_count"),
                    action=row.get("series_packet_action"),
                    top=row.get("top_score"),
                    evidence=row.get("mean_evidence_confidence_score"),
                    residual=row.get("max_abs_evidence_residual"),
                    examples=row.get("representative_candidate_ids") or "",
                )
            )
    uncertainty = packet.get("evidence_uncertainty_summary") or {}
    top_residuals = uncertainty.get("top_residual_candidates") or []
    if uncertainty:
        status_text = ", ".join(f"{key}: {value}" for key, value in (uncertainty.get("status_counts") or {}).items())
        lines.extend(
            [
                "",
                "## Evidence Uncertainty",
                "",
                f"- Status counts: {status_text or 'none'}",
                f"- High-uncertainty candidates: `{uncertainty.get('high_uncertainty_candidate_count')}`",
                f"- Max absolute residual: `{uncertainty.get('max_abs_residual')}`",
                f"- Mean confidence interval width: `{uncertainty.get('mean_confidence_interval_width')}`",
                f"- Max confidence interval width: `{uncertainty.get('max_confidence_interval_width')}`",
            ]
        )
    if top_residuals:
        lines.extend(
            [
                "",
                "| Candidate | Decision | Residual | Interval Width | Context | Basis |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for row in top_residuals:
            context = "/".join(
                part
                for part in [
                    str(row.get("evidence_confidence_target_family") or ""),
                    str(row.get("evidence_confidence_assay_type") or ""),
                ]
                if part
            )
            lines.append(
                "| `{cid}` | {decision} | {residual} | {interval} | {context} | {basis} |".format(
                    cid=row.get("candidate_id") or "",
                    decision=row.get("decision_recommendation") or "",
                    residual=row.get("evidence_confidence_max_abs_residual"),
                    interval=row.get("evidence_confidence_interval_width"),
                    context=context.replace("|", "/"),
                    basis=str(row.get("evidence_confidence_residual_basis") or "").replace("|", "/"),
                )
            )
    lines.append("")
    return "\n".join(lines)


def write_decision_packet(packet: dict, output_prefix: str | Path) -> dict:
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    csv_path.write_text(decision_packet_csv_text(packet), encoding="utf-8")
    md_path.write_text(decision_packet_markdown(packet), encoding="utf-8")
    return {"json": str(json_path.resolve()), "csv": str(csv_path.resolve()), "markdown": str(md_path.resolve())}


def _packet_digest(packet: dict) -> str:
    key = {
        "project_name": packet.get("project_name"),
        "source_run_id": packet.get("source_run_id"),
        "parent_smiles": packet.get("parent_smiles"),
        "direction": packet.get("direction"),
        "site_type": packet.get("site_type"),
        "candidates": [
            {
                "candidate_id": row.get("candidate_id"),
                "decision_recommendation": row.get("decision_recommendation"),
                "score": row.get("score"),
            }
            for row in packet.get("candidates") or []
        ],
    }
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode("utf-8")).hexdigest()[:12].upper()


def save_decision_packet(
    packet: dict,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    packet_id: str | None = None,
    status: str = "needs_review",
    reviewer: str | None = None,
    review_note: str | None = None,
) -> str:
    if status not in PACKET_REVIEW_STATUSES:
        raise ValueError(f"Unsupported packet review status: {status}")
    now = datetime.now(timezone.utc).isoformat()
    packet_id = packet_id or packet.get("packet_id") or f"DPK-{_packet_digest(packet)}"
    payload = {**packet, "packet_id": packet_id, "review_status": status}
    conn = initialize_database(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO project_decision_packet (
                packet_id, project_name, source_run_id, parent_smiles, direction,
                site_type, status, reviewer, review_note, candidate_count,
                decision_counts_json, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                (SELECT created_at FROM project_decision_packet WHERE packet_id=?),
                ?
            ), ?)
            """,
            (
                packet_id,
                packet.get("project_name"),
                packet.get("source_run_id"),
                packet.get("parent_smiles"),
                packet.get("direction"),
                packet.get("site_type"),
                status,
                reviewer,
                review_note,
                packet.get("candidate_count"),
                json.dumps(packet.get("decision_counts") or {}, sort_keys=True),
                json.dumps(payload, sort_keys=True),
                packet_id,
                packet.get("created_at") or now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO project_decision_packet_event (
                event_id, packet_id, status, reviewer, note, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"DPE-{uuid.uuid4().hex[:12].upper()}",
                packet_id,
                status,
                reviewer,
                review_note or "Decision packet saved.",
                now,
                json.dumps({"packet_id": packet_id, "status": status, "reviewer": reviewer, "note": review_note}, sort_keys=True),
            ),
        )
        conn.commit()
        return packet_id
    finally:
        conn.close()


def _packet_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    try:
        item["decision_counts"] = json.loads(item.pop("decision_counts_json") or "{}")
    except json.JSONDecodeError:
        item["decision_counts"] = {}
    try:
        item["packet"] = json.loads(item.pop("payload_json") or "{}")
    except json.JSONDecodeError:
        item["packet"] = {}
    return item


def list_decision_packets(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if project_name:
            rows = conn.execute(
                """
                SELECT * FROM project_decision_packet
                WHERE project_name=?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project_name, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM project_decision_packet ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [_packet_row(row) for row in rows]
    finally:
        conn.close()


def load_decision_packet(db_path: str | Path, packet_id: str) -> dict | None:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM project_decision_packet WHERE packet_id=?", (packet_id,)).fetchone()
        return _packet_row(row) if row else None
    finally:
        conn.close()


def update_decision_packet_review(
    db_path: str | Path,
    packet_id: str,
    *,
    status: str,
    reviewer: str | None = None,
    review_note: str | None = None,
) -> None:
    if status not in PACKET_REVIEW_STATUSES:
        raise ValueError(f"Unsupported packet review status: {status}")
    now = datetime.now(timezone.utc).isoformat()
    conn = initialize_database(db_path)
    try:
        conn.execute(
            """
            UPDATE project_decision_packet
            SET status=?, reviewer=?, review_note=?, updated_at=?
            WHERE packet_id=?
            """,
            (status, reviewer, review_note or "", now, packet_id),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO project_decision_packet_event (
                event_id, packet_id, status, reviewer, note, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"DPE-{uuid.uuid4().hex[:12].upper()}",
                packet_id,
                status,
                reviewer,
                review_note or "",
                now,
                json.dumps({"packet_id": packet_id, "status": status, "reviewer": reviewer, "note": review_note or ""}, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def compare_decision_packets(base_packet: dict, head_packet: dict) -> dict:
    base_rows = {row.get("candidate_id"): row for row in base_packet.get("candidates") or [] if row.get("candidate_id")}
    head_rows = {row.get("candidate_id"): row for row in head_packet.get("candidates") or [] if row.get("candidate_id")}
    added = sorted(set(head_rows) - set(base_rows))
    removed = sorted(set(base_rows) - set(head_rows))
    changed = []
    for candidate_id in sorted(set(base_rows).intersection(head_rows)):
        base = base_rows[candidate_id]
        head = head_rows[candidate_id]
        if base.get("decision_recommendation") != head.get("decision_recommendation"):
            changed.append(
                {
                    "candidate_id": candidate_id,
                    "base_decision": base.get("decision_recommendation"),
                    "head_decision": head.get("decision_recommendation"),
                    "base_score": base.get("score"),
                    "head_score": head.get("score"),
                }
            )
    return {
        "base_created_at": base_packet.get("created_at"),
        "head_created_at": head_packet.get("created_at"),
        "base_candidate_count": len(base_rows),
        "head_candidate_count": len(head_rows),
        "added_candidate_ids": added,
        "removed_candidate_ids": removed,
        "decision_change_count": len(changed),
        "decision_changes": changed,
        "base_decision_counts": base_packet.get("decision_counts") or {},
        "head_decision_counts": head_packet.get("decision_counts") or {},
    }


def _optional_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _outcome_bucket(row: dict) -> str:
    stop_go = str(row.get("stop_go_decision") or "").strip().lower().replace(" ", "_")
    if stop_go in {"go", "stop", "retest", "watch"}:
        return {"go": "positive", "stop": "negative", "retest": "retest", "watch": "watch"}[stop_go]
    score = _optional_float(row.get("normalized_score"))
    if score is not None:
        if score >= 70.0:
            return "positive"
        if score <= 35.0:
            return "negative"
        return "watch"
    classification = str(row.get("classification") or "").strip().lower().replace(" ", "_")
    if classification in {"active", "pass", "positive", "improved", "go", "hit"}:
        return "positive"
    if classification in {"inactive", "fail", "failed", "negative", "worse", "stop"}:
        return "negative"
    if classification in {"retest", "repeat"}:
        return "retest"
    return "watch"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "now":
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _within_window(row: dict, window_start: datetime | None) -> bool:
    if window_start is None:
        return True
    recorded_at = _parse_datetime(row.get("recorded_at"))
    if recorded_at is None:
        return True
    return recorded_at >= window_start


def _packet_observation_rows(
    conn: sqlite3.Connection,
    packet: dict,
    *,
    window_start: datetime | None = None,
) -> list[dict]:
    project_name = packet.get("project_name")
    source_run_id = packet.get("source_run_id")
    feedback_rows = conn.execute(
        """
        SELECT f.feedback_id AS observation_id, 'feedback' AS observation_type,
               f.run_id, f.candidate_id, COALESCE(f.project_name, pr.project_name, '') AS project_name,
               f.endpoint AS endpoint_group, f.assay_name, f.assay_type, f.normalized_score, f.classification,
               NULL AS stop_go_decision, f.recorded_at
        FROM project_feedback f
        LEFT JOIN project_run pr ON pr.run_id=f.run_id
        WHERE (? IS NULL OR COALESCE(f.project_name, pr.project_name, '')=?)
          AND (? IS NULL OR f.run_id=?)
        """,
        (project_name, project_name, source_run_id, source_run_id),
    ).fetchall()
    event_rows = conn.execute(
        """
        SELECT e.event_id AS observation_id, 'experiment_event' AS observation_type,
               e.run_id, e.candidate_id, COALESCE(p.project_name, pr.project_name, '') AS project_name,
               e.endpoint_group, e.assay_name, e.assay_type, e.normalized_score,
               e.classification, e.stop_go_decision, e.recorded_at
        FROM project_experiment_event e
        LEFT JOIN project_experiment_plan p ON p.plan_id=e.plan_id
        LEFT JOIN project_run pr ON pr.run_id=e.run_id
        WHERE (? IS NULL OR COALESCE(p.project_name, pr.project_name, '')=?)
          AND (? IS NULL OR e.run_id=?)
        """,
        (project_name, project_name, source_run_id, source_run_id),
    ).fetchall()
    rows = [dict(row) for row in feedback_rows] + [dict(row) for row in event_rows]
    return [row for row in rows if _within_window(row, window_start)]


def build_decision_packet_retrospective(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    packet_id: str | None = None,
    since_days: int | None = None,
) -> dict:
    if packet_id:
        packet_row = load_decision_packet(db_path, packet_id)
        packets = [packet_row] if packet_row else []
    else:
        packets = list_decision_packets(db_path=db_path, project_name=project_name, limit=100)
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    window_start = None
    if since_days is not None and int(since_days) > 0:
        window_start = datetime.now(timezone.utc) - timedelta(days=int(since_days))
    try:
        packet_reports = []
        for packet_row in packets:
            packet = packet_row.get("packet") or {}
            candidates = packet.get("candidates") or []
            observations = _packet_observation_rows(conn, packet, window_start=window_start)
            observations_by_candidate: dict[str, list[dict]] = defaultdict(list)
            for observation in observations:
                if observation.get("candidate_id"):
                    observations_by_candidate[str(observation["candidate_id"])].append(observation)

            recommendation_summary: dict[str, Counter] = defaultdict(Counter)
            candidate_outcomes = []
            for candidate in candidates:
                candidate_id = str(candidate.get("candidate_id") or "")
                candidate_obs = observations_by_candidate.get(candidate_id, [])
                buckets = Counter(_outcome_bucket(obs) for obs in candidate_obs)
                scores = [
                    value
                    for value in (_optional_float(obs.get("normalized_score")) for obs in candidate_obs)
                    if value is not None
                ]
                recommendation = str(candidate.get("decision_recommendation") or "unknown")
                recommendation_summary[recommendation]["candidate_count"] += 1
                if candidate_obs:
                    recommendation_summary[recommendation]["observed_count"] += 1
                if buckets.get("positive", 0):
                    recommendation_summary[recommendation]["positive_candidate_count"] += 1
                if buckets.get("negative", 0):
                    recommendation_summary[recommendation]["negative_candidate_count"] += 1
                for bucket, count in buckets.items():
                    recommendation_summary[recommendation][f"{bucket}_count"] += count
                candidate_outcomes.append(
                    {
                        "candidate_id": candidate_id,
                        "decision_recommendation": recommendation,
                        "packet_score": candidate.get("score"),
                        "site_type": candidate.get("site_type"),
                        "direction": candidate.get("direction"),
                        "enumeration_type": candidate.get("enumeration_type"),
                        "diversity_bucket": candidate.get("diversity_bucket"),
                        "replacement_label": candidate.get("replacement_label"),
                        "target_family": candidate.get("evidence_target_family_normalized") or candidate.get("evidence_target_family") or "unspecified",
                        "endpoint_group": candidate.get("endpoint_gate_endpoint") or candidate.get("evidence_endpoint_group") or "unspecified",
                        "observed_count": len(candidate_obs),
                        "positive_count": buckets.get("positive", 0),
                        "negative_count": buckets.get("negative", 0),
                        "watch_count": buckets.get("watch", 0),
                        "retest_count": buckets.get("retest", 0),
                        "mean_normalized_score": round(sum(scores) / len(scores), 4) if scores else None,
                        "outcome_bucket": (
                            "positive"
                            if buckets.get("positive", 0)
                            else "negative"
                            if buckets.get("negative", 0)
                            else "retest"
                            if buckets.get("retest", 0)
                            else "watch"
                            if candidate_obs
                            else "unobserved"
                        ),
                    }
                )
            observed_candidates = [row for row in candidate_outcomes if row["observed_count"]]
            positive_candidates = [row for row in observed_candidates if row["positive_count"]]
            packet_reports.append(
                {
                    "packet_id": packet_row.get("packet_id") or packet.get("packet_id"),
                    "project_name": packet.get("project_name"),
                    "status": packet_row.get("status") or packet.get("review_status"),
                    "source_run_id": packet.get("source_run_id"),
                    "candidate_count": len(candidates),
                    "observed_candidate_count": len(observed_candidates),
                    "overall_hit_rate": round(len(positive_candidates) / len(observed_candidates), 4) if observed_candidates else None,
                    "recommendation_summary": [
                        {
                            "decision_recommendation": recommendation,
                            **dict(counts),
                            "hit_rate": (
                                round(counts.get("positive_candidate_count", 0) / counts.get("observed_count", 1), 4)
                                if counts.get("observed_count")
                                else None
                            ),
                        }
                        for recommendation, counts in sorted(recommendation_summary.items())
                    ],
                    "candidate_outcomes": candidate_outcomes,
                }
            )
    finally:
        conn.close()
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "packet_id": packet_id,
        "window_days": int(since_days) if since_days is not None else None,
        "window_start": window_start.isoformat() if window_start else None,
        "packet_count": len(packet_reports),
        "packets": packet_reports,
    }


def write_decision_packet_retrospective(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def build_decision_strategy_learning_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    since_days: int | None = None,
    strategy_version: str = "strategy-learning-v0.2",
    policy_version: str | None = None,
) -> dict:
    retrospective = build_decision_packet_retrospective(db_path=db_path, project_name=project_name, since_days=since_days)
    groups: dict[tuple[str, str, str, str], dict] = {}
    for packet in retrospective.get("packets") or []:
        for row in packet.get("candidate_outcomes") or []:
            key = (
                str(row.get("site_type") or "unspecified"),
                str(row.get("enumeration_type") or "unspecified"),
                str(row.get("target_family") or "unspecified"),
                str(row.get("endpoint_group") or "unspecified"),
            )
            item = groups.setdefault(
                key,
                {
                    "site_type": key[0],
                    "operator": key[1],
                    "target_family": key[2],
                    "endpoint_group": key[3],
                    "strategy_version": strategy_version,
                    "policy_version": policy_version,
                    "window_days": int(since_days) if since_days is not None else None,
                    "window_start": retrospective.get("window_start"),
                    "candidate_count": 0,
                    "observed_candidate_count": 0,
                    "positive_candidate_count": 0,
                    "negative_candidate_count": 0,
                    "retest_candidate_count": 0,
                    "packet_scores": [],
                    "decision_counts": Counter(),
                    "example_candidate_ids": [],
                },
            )
            item["candidate_count"] += 1
            item["decision_counts"][row.get("decision_recommendation") or "unknown"] += 1
            if row.get("packet_score") is not None:
                score = _optional_float(row.get("packet_score"))
                if score is not None:
                    item["packet_scores"].append(score)
            if row.get("observed_count"):
                item["observed_candidate_count"] += 1
                item["example_candidate_ids"].append(row.get("candidate_id"))
            if row.get("positive_count"):
                item["positive_candidate_count"] += 1
            if row.get("negative_count"):
                item["negative_candidate_count"] += 1
            if row.get("retest_count"):
                item["retest_candidate_count"] += 1

    strategies = []
    for item in groups.values():
        observed = int(item["observed_candidate_count"])
        positives = int(item["positive_candidate_count"])
        negatives = int(item["negative_candidate_count"])
        hit_rate = round(positives / observed, 4) if observed else None
        if observed >= 3 and hit_rate is not None and hit_rate >= 0.6:
            recommendation = "promote_strategy"
        elif observed >= 3 and negatives > positives:
            recommendation = "deprioritize_strategy"
        elif observed:
            recommendation = "watch_strategy"
        else:
            recommendation = "collect_outcomes"
        scores = item.pop("packet_scores")
        decision_counts = item.pop("decision_counts")
        strategies.append(
            {
                **item,
                "hit_rate": hit_rate,
                "mean_packet_score": round(sum(scores) / len(scores), 4) if scores else None,
                "decision_counts": dict(decision_counts.most_common()),
                "strategy_recommendation": recommendation,
                "example_candidate_ids": ";".join(str(cid) for cid in item.get("example_candidate_ids", [])[:8] if cid),
            }
        )
    strategies.sort(
        key=lambda row: (
            row.get("observed_candidate_count") or 0,
            row.get("hit_rate") if row.get("hit_rate") is not None else -1,
            row.get("candidate_count") or 0,
        ),
        reverse=True,
    )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "strategy_version": strategy_version,
        "policy_version": policy_version,
        "window_days": int(since_days) if since_days is not None else None,
        "window_start": retrospective.get("window_start"),
        "packet_count": retrospective.get("packet_count", 0),
        "strategy_count": len(strategies),
        "observed_strategy_count": sum(1 for row in strategies if row.get("observed_candidate_count")),
        "strategies": strategies,
        "recommended_next_actions": [
            "Collect outcomes for unobserved high-volume strategies before changing priors.",
            "Promote strategies with observed hit rate >= 0.6 and at least three observed candidates.",
            "Deprioritize strategy buckets with repeated negative outcomes.",
        ],
    }


def write_decision_strategy_learning_report(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
