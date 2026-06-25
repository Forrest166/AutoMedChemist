from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .profile_ab_matrix import DEFAULT_PROFILE_AB_MATRIX_PATH


DEFAULT_PROFILE_AB_MATERIAL_REVIEW_PATH = Path("data/projects/demo/profile_ab_material_change_review.json")
DEFAULT_PROFILE_AB_MATERIAL_REVIEW_CSV_PATH = Path("data/projects/demo/profile_ab_material_change_review.csv")

ACCEPTED_MATERIAL_DECISIONS = {"accepted", "accepted_with_review", "accepted_for_current_profile"}


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_material_candidate_diff(row: dict, *, top_n_threshold: int, score_delta_threshold: float) -> bool:
    membership = str(row.get("membership") or "")
    if membership and membership != "shared":
        return True
    if abs(_float(row.get("score_delta"))) >= float(score_delta_threshold):
        return True
    base_rank = _int(row.get("base_rank"))
    candidate_rank = _int(row.get("candidate_rank"))
    if base_rank and candidate_rank and min(base_rank, candidate_rank) <= int(top_n_threshold):
        return abs(base_rank - candidate_rank) >= int(top_n_threshold)
    return False


def _decision_status(decision: str) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized in ACCEPTED_MATERIAL_DECISIONS:
        return "accepted"
    if normalized in {"rejected", "blocked"}:
        return "blocked"
    return "review_required"


def build_profile_ab_material_change_review(
    *,
    root: str | Path = ".",
    matrix_path: str | Path = DEFAULT_PROFILE_AB_MATRIX_PATH,
    project_name: str | None = "demo_learning",
    reviewer: str = "codex",
    decision: str = "needs_medchem_review",
    note: str | None = None,
) -> dict:
    root_path = Path(root)
    matrix_file = Path(matrix_path)
    if not matrix_file.is_absolute():
        matrix_file = root_path / matrix_file
    matrix = _read_json(matrix_file)
    thresholds = matrix.get("material_change_thresholds") or {}
    top_n_threshold = _int(thresholds.get("changed_top_n_count") or 3)
    score_delta_threshold = _float(thresholds.get("max_score_delta") or 5.0)
    normalized_decision = str(decision or "needs_medchem_review").strip().lower()
    acceptance_status = _decision_status(normalized_decision)
    now = datetime.now(timezone.utc)

    summary_lookup = {str(row.get("scenario_id") or ""): dict(row) for row in matrix.get("summary_rows") or []}
    material_scenarios = [
        row
        for row in summary_lookup.values()
        if row.get("material_change") or str(row.get("review_status") or "") == "review_required"
    ]
    material_ids = {str(row.get("scenario_id") or "") for row in material_scenarios}
    candidate_diff_rows = []
    scenario_review_rows = []
    for report in matrix.get("scenario_reports") or []:
        scenario_id = str(report.get("scenario_id") or "")
        if scenario_id not in material_ids:
            continue
        summary = summary_lookup.get(scenario_id, {})
        scenario_review_rows.append(
            {
                "scenario_id": scenario_id,
                "review_status": summary.get("review_status") or report.get("review_status"),
                "material_change": bool(summary.get("material_change")),
                "changed_top_n_count": summary.get("changed_top_n_count"),
                "max_score_delta": summary.get("max_score_delta"),
                "decision": normalized_decision,
                "acceptance_status": acceptance_status,
                "acceptance_basis": note or "Material A/B movement retained with candidate-level audit trail.",
            }
        )
        for candidate in report.get("rows") or []:
            if not _is_material_candidate_diff(
                candidate,
                top_n_threshold=top_n_threshold,
                score_delta_threshold=score_delta_threshold,
            ):
                continue
            candidate_diff_rows.append(
                {
                    "scenario_id": scenario_id,
                    "smiles": summary.get("smiles"),
                    "direction": summary.get("direction"),
                    "site_class": summary.get("site_class"),
                    "candidate_key": candidate.get("candidate_key"),
                    "base_candidate_id": candidate.get("base_candidate_id"),
                    "candidate_candidate_id": candidate.get("candidate_candidate_id"),
                    "base_rank": candidate.get("base_rank"),
                    "candidate_rank": candidate.get("candidate_rank"),
                    "rank_delta": candidate.get("rank_delta"),
                    "membership": candidate.get("membership"),
                    "base_score": candidate.get("base_score"),
                    "candidate_score": candidate.get("candidate_score"),
                    "score_delta": candidate.get("score_delta"),
                    "multi_objective_score_delta": candidate.get("multi_objective_score_delta"),
                    "strategy_learning_score_delta": candidate.get("strategy_learning_score_delta"),
                    "endpoint_family_residual_score_delta": candidate.get("endpoint_family_residual_score_delta"),
                    "enumeration_type": candidate.get("enumeration_type"),
                    "replacement_label": candidate.get("replacement_label"),
                    "decision": normalized_decision,
                    "acceptance_status": acceptance_status,
                }
            )

    scenario_status_counts = Counter(row["acceptance_status"] for row in scenario_review_rows)
    report_status = (
        "accepted"
        if material_scenarios and scenario_status_counts.get("accepted", 0) == len(material_scenarios)
        else "no_material_change"
        if not material_scenarios
        else "review_required"
    )
    if scenario_status_counts.get("blocked", 0):
        report_status = "blocked"
    return {
        "created_at": now.isoformat(),
        "status": report_status,
        "project_name": project_name,
        "matrix_path": str(matrix_file),
        "matrix_created_at": matrix.get("created_at"),
        "reviewer": reviewer,
        "decision": normalized_decision,
        "note": note or "",
        "scenario_count": int(matrix.get("scenario_count") or 0),
        "material_change_scenario_count": len(material_scenarios),
        "review_required_scenario_count": sum(1 for row in material_scenarios if str(row.get("review_status") or "") == "review_required"),
        "candidate_diff_count": len(candidate_diff_rows),
        "accepted_profile_change_count": scenario_status_counts.get("accepted", 0),
        "blocked_profile_change_count": scenario_status_counts.get("blocked", 0),
        "acceptance_status_counts": dict(scenario_status_counts.most_common()),
        "material_change_thresholds": {
            "changed_top_n_count": top_n_threshold,
            "max_score_delta": score_delta_threshold,
        },
        "scenario_review_rows": scenario_review_rows,
        "candidate_diff_rows": candidate_diff_rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Keep this candidate-level diff attached to any profile activation decision.",
            "Review any accepted_with_review scenario again if the active project context or profile weights change.",
            "Do not substitute vendor/procurement evidence for profile A/B acceptance.",
        ],
    }


def write_profile_ab_material_change_review(
    report: dict,
    output_path: str | Path = DEFAULT_PROFILE_AB_MATERIAL_REVIEW_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROFILE_AB_MATERIAL_REVIEW_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("candidate_diff_rows") or []]
    fieldnames = [
        "scenario_id",
        "smiles",
        "direction",
        "site_class",
        "candidate_key",
        "base_candidate_id",
        "candidate_candidate_id",
        "base_rank",
        "candidate_rank",
        "rank_delta",
        "membership",
        "base_score",
        "candidate_score",
        "score_delta",
        "multi_objective_score_delta",
        "strategy_learning_score_delta",
        "endpoint_family_residual_score_delta",
        "enumeration_type",
        "replacement_label",
        "decision",
        "acceptance_status",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
