from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .database import initialize_database
from .target_context import standardize_target_context


DEFAULT_TARGET_CONTEXT_PROFILES_PATH = Path("data/rules/target_context_profiles.yaml")
DEFAULT_MULTI_OBJECTIVE_CALIBRATION_REPORT_PATH = Path("data/projects/demo/multi_objective_calibration_report.json")

DEFAULT_TARGET_CONTEXT_PROFILE = {
    "profile_id": "balanced_project_context",
    "endpoint_group": "all",
    "target_family": "all",
    "assay_type": "all",
    "score_weights": {
        "potency": 0.42,
        "metabolic_stability": 0.2,
        "permeability": 0.2,
        "liability": 0.18,
    },
    "adjustment_scale": 0.12,
    "max_adjustment": 6.0,
    "constraints": {
        "max_tpsa": 115,
        "max_mw": 550,
        "max_hbd": 3,
        "max_hba": 10,
        "max_rotatable_bonds": 9,
        "max_abs_residual_for_clean_boost": 0.25,
    },
}


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float | None:
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def _json_loads(text: str | None) -> dict:
    try:
        payload = json.loads(text or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_target_context_profiles(path: str | Path = DEFAULT_TARGET_CONTEXT_PROFILES_PATH) -> list[dict]:
    profile_path = Path(path)
    if not profile_path.exists():
        return [dict(DEFAULT_TARGET_CONTEXT_PROFILE)]
    with profile_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, list):
        profiles = data
    else:
        profiles = data.get("profiles") or []
    return profiles or [dict(DEFAULT_TARGET_CONTEXT_PROFILE)]


def _profile_specificity(profile: dict, context: dict) -> tuple[int, int, int]:
    endpoint = str(profile.get("endpoint_group") or "all").lower()
    family = str(profile.get("target_family") or "all").lower()
    assay = str(profile.get("assay_type") or "all").lower()
    context_endpoint = str(context.get("endpoint_group") or "").lower()
    context_family = str(context.get("target_family") or "").lower()
    context_assay = str(context.get("assay_type") or "").lower()
    if endpoint not in {"all", context_endpoint}:
        return (-1, -1, -1)
    if family not in {"all", context_family}:
        return (-1, -1, -1)
    if assay not in {"all", context_assay}:
        return (-1, -1, -1)
    return (
        1 if endpoint == context_endpoint and endpoint != "all" else 0,
        1 if family == context_family and family != "all" else 0,
        1 if assay == context_assay and assay != "all" else 0,
    )


def select_target_context_profile(
    target_context: dict | None,
    *,
    profiles: list[dict] | None = None,
    profiles_path: str | Path = DEFAULT_TARGET_CONTEXT_PROFILES_PATH,
) -> dict:
    context = standardize_target_context(target_context or {})
    candidates = profiles if profiles is not None else load_target_context_profiles(profiles_path)
    scored = []
    for profile in candidates:
        specificity = _profile_specificity(profile, context)
        if specificity[0] < 0:
            continue
        scored.append((specificity, profile))
    if not scored:
        return {**DEFAULT_TARGET_CONTEXT_PROFILE, "matched_context": context}
    scored.sort(key=lambda item: item[0], reverse=True)
    return {**DEFAULT_TARGET_CONTEXT_PROFILE, **scored[0][1], "matched_context": context}


def _score_potency(row: dict, base_score: float | None = None) -> float:
    values = [
        _float_or_none(base_score),
        _float_or_none(row.get("direction_score")),
        _float_or_none(row.get("transform_activity_score")),
        _float_or_none(row.get("evidence_confidence_calibration_score")),
        _float_or_none(row.get("evidence_consistency_score")),
        _float_or_none(row.get("mmp_precedent_score")),
        _float_or_none(row.get("public_strategy_signal_score")),
    ]
    return round(_clamp(_mean([value for value in values if value is not None]) or 50.0, 0.0, 100.0), 2)


def _score_stability(row: dict, target_context: dict) -> float:
    score = 55.0
    direction = str(row.get("direction") or "").lower()
    label = " ".join(
        str(row.get(key) or "").lower()
        for key in ["replacement_label", "replacement_class", "functional_rule_id", "recommendation_reason"]
    )
    if "metabolism" in direction or "stability" in str(target_context.get("endpoint_group") or "").lower():
        score += 12.0
    if any(token in label for token in ["fluoro", "f->", "deuter", "bioisostere", "metabolism"]):
        score += 10.0
    if "possible_soft_spot" in label or "soft_spot" in label:
        score -= 15.0
    delta_clogp = _float_or_none(row.get("delta_clogp"))
    if delta_clogp is not None:
        if delta_clogp <= -0.3:
            score += 4.0
        elif delta_clogp >= 0.8:
            score -= 5.0
    return round(_clamp(score, 0.0, 100.0), 2)


def _score_permeability(row: dict) -> float:
    score = 92.0
    mw = _float_or_none(row.get("mw"))
    tpsa = _float_or_none(row.get("tpsa"))
    hbd = _float_or_none(row.get("hbd"))
    hba = _float_or_none(row.get("hba"))
    rot = _float_or_none(row.get("rotatable_bonds"))
    clogp = _float_or_none(row.get("clogp"))
    if mw is not None and mw > 500:
        score -= min(28.0, (mw - 500.0) * 0.18)
    if tpsa is not None and tpsa > 90:
        score -= min(32.0, (tpsa - 90.0) * 0.5)
    if hbd is not None and hbd > 2:
        score -= (hbd - 2.0) * 8.0
    if hba is not None and hba > 8:
        score -= (hba - 8.0) * 4.0
    if rot is not None and rot > 8:
        score -= (rot - 8.0) * 3.0
    if clogp is not None:
        if 1.0 <= clogp <= 3.5:
            score += 4.0
        elif clogp < -0.5 or clogp > 5.0:
            score -= 10.0
    return round(_clamp(score, 0.0, 100.0), 2)


def _score_liability(row: dict) -> float:
    score = _float_or_none(row.get("risk_score"))
    score = 75.0 if score is None else score
    flags = ";".join(
        str(row.get(key) or "")
        for key in ["evidence_conflict_flags", "mmp_contradiction_flags", "scaffold_context_flags"]
    ).lower()
    if "contradiction" in flags or "activity_cliff_high" in flags:
        score -= 18.0
    if "pka_context_dependent" in flags or "asymmetric" in flags:
        score -= 7.0
    residual = _float_or_none(row.get("evidence_confidence_max_abs_residual"))
    if residual is not None and residual >= 0.25:
        score -= 8.0
    return round(_clamp(score, 0.0, 100.0), 2)


def multi_objective_score_for_candidate(
    row: dict,
    *,
    target_context: dict | None = None,
    profile: dict | None = None,
    profiles_path: str | Path = DEFAULT_TARGET_CONTEXT_PROFILES_PATH,
    base_score: float | None = None,
) -> dict:
    selected = profile or select_target_context_profile(target_context, profiles_path=profiles_path)
    context = selected.get("matched_context") or standardize_target_context(target_context or {})
    weights = {
        "potency": 0.42,
        "metabolic_stability": 0.2,
        "permeability": 0.2,
        "liability": 0.18,
        **(selected.get("score_weights") or {}),
    }
    total = sum(max(float(value), 0.0) for value in weights.values()) or 1.0
    normalized_weights = {key: max(float(value), 0.0) / total for key, value in weights.items()}
    component_scores = {
        "potency": _score_potency(row, base_score=base_score),
        "metabolic_stability": _score_stability(row, context),
        "permeability": _score_permeability(row),
        "liability": _score_liability(row),
    }
    score = round(sum(component_scores[key] * normalized_weights.get(key, 0.0) for key in component_scores), 2)
    constraints = {**(DEFAULT_TARGET_CONTEXT_PROFILE.get("constraints") or {}), **(selected.get("constraints") or {})}
    flags = []
    for field, threshold_key in [
        ("tpsa", "max_tpsa"),
        ("mw", "max_mw"),
        ("hbd", "max_hbd"),
        ("hba", "max_hba"),
        ("rotatable_bonds", "max_rotatable_bonds"),
    ]:
        value = _float_or_none(row.get(field))
        threshold = _float_or_none(constraints.get(threshold_key))
        if value is not None and threshold is not None and value > threshold:
            flags.append(f"{field}_above_{threshold_key}")
    residual = _float_or_none(row.get("evidence_confidence_max_abs_residual"))
    max_clean_residual = _float_or_none(constraints.get("max_abs_residual_for_clean_boost"))
    if residual is not None and max_clean_residual is not None and residual > max_clean_residual:
        flags.append("high_evidence_residual")
    scale = float(selected.get("adjustment_scale") or DEFAULT_TARGET_CONTEXT_PROFILE["adjustment_scale"])
    max_adjustment = float(selected.get("max_adjustment") or DEFAULT_TARGET_CONTEXT_PROFILE["max_adjustment"])
    adjustment = _clamp((score - 50.0) * scale, -max_adjustment, max_adjustment)
    if flags and adjustment > 0:
        adjustment = max(0.0, adjustment - min(3.0, len(flags) * 0.75))
    basis = "; ".join(f"{key}={value:.1f} w={normalized_weights.get(key, 0.0):.2f}" for key, value in component_scores.items())
    return {
        "multi_objective_profile_id": selected.get("profile_id"),
        "multi_objective_score": score,
        "multi_objective_score_adjustment": round(adjustment, 4),
        "multi_objective_potency_score": component_scores["potency"],
        "multi_objective_stability_score": component_scores["metabolic_stability"],
        "multi_objective_permeability_score": component_scores["permeability"],
        "multi_objective_liability_score": component_scores["liability"],
        "multi_objective_constraint_flags": ";".join(flags),
        "multi_objective_basis": basis,
        "multi_objective_weights_json": json.dumps(normalized_weights, sort_keys=True),
    }


def _outcome_value(row: dict) -> float | None:
    score = _float_or_none(row.get("normalized_score"))
    if score is not None:
        return _clamp(score, 0.0, 100.0) / 100.0
    classification = str(row.get("classification") or row.get("stop_go_decision") or "").strip().lower().replace(" ", "_")
    if classification in {"active", "pass", "positive", "improved", "go", "hit", "selected", "shortlisted"}:
        return 1.0
    if classification in {"inactive", "fail", "failed", "negative", "worse", "stop", "rejected"}:
        return 0.0
    if classification in {"watch", "retest", "repeat", "inconclusive"}:
        return 0.5
    return None


def _observation_context(row: dict, payload: dict) -> dict:
    payload_context = payload.get("target_context") if isinstance(payload.get("target_context"), dict) else {}
    return standardize_target_context(
        {
            "endpoint_group": row.get("endpoint_group") or row.get("endpoint") or payload.get("endpoint_gate_endpoint") or payload.get("direction"),
            "target_family": payload.get("evidence_target_family_normalized")
            or payload.get("evidence_target_family")
            or payload_context.get("target_family")
            or row.get("target_family"),
            "assay_type": row.get("assay_type") or payload.get("evidence_assay_type") or payload_context.get("assay_type"),
        }
    )


def _context_matches(row_context: dict, requested: dict | None) -> bool:
    if not requested:
        return True
    context = standardize_target_context(requested)
    for key in ["endpoint_group", "target_family", "assay_type"]:
        expected = str(context.get(key) or "").lower()
        if expected in {"", "all", "unspecified"}:
            continue
        actual = str(row_context.get(key) or "").lower()
        if actual != expected:
            return False
    return True


def _candidate_outcome_rows(
    *,
    db_path: str | Path,
    project_name: str | None = None,
    target_context: dict | None = None,
) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params = (project_name, project_name)
        feedback_rows = conn.execute(
            """
            SELECT pc.run_id, pc.candidate_id, pc.score AS base_score, pc.payload_json,
                   COALESCE(f.project_name, pr.project_name, '') AS project_name,
                   f.endpoint AS endpoint_group, f.assay_name, f.assay_type, f.normalized_score,
                   f.classification, NULL AS stop_go_decision
            FROM project_feedback f
            JOIN project_candidate pc ON pc.run_id=f.run_id AND pc.candidate_id=f.candidate_id
            LEFT JOIN project_run pr ON pr.run_id=pc.run_id
            WHERE (? IS NULL OR COALESCE(f.project_name, pr.project_name, '')=?)
            """,
            params,
        ).fetchall()
        try:
            event_rows = conn.execute(
                """
                SELECT pc.run_id, pc.candidate_id, pc.score AS base_score, pc.payload_json,
                       COALESCE(p.project_name, pr.project_name, '') AS project_name,
                       e.endpoint_group, e.assay_name, e.assay_type, e.normalized_score,
                       e.classification, e.stop_go_decision
                FROM project_experiment_event e
                JOIN project_candidate pc ON pc.run_id=e.run_id AND pc.candidate_id=e.candidate_id
                LEFT JOIN project_experiment_plan p ON p.plan_id=e.plan_id
                LEFT JOIN project_run pr ON pr.run_id=pc.run_id
                WHERE (? IS NULL OR COALESCE(p.project_name, pr.project_name, '')=?)
                """,
                params,
            ).fetchall()
        except sqlite3.Error:
            event_rows = []
    finally:
        conn.close()
    rows = []
    for raw in [*feedback_rows, *event_rows]:
        item = dict(raw)
        payload = _json_loads(item.get("payload_json"))
        if not payload:
            continue
        outcome = _outcome_value(item)
        if outcome is None:
            continue
        context = _observation_context(item, payload)
        if not _context_matches(context, target_context):
            continue
        rows.append({**item, "payload": payload, "target_context": context, "outcome_value": outcome})
    return rows


def _component_scores_for_row(row: dict, profile: dict) -> dict[str, float]:
    payload = dict(row.get("payload") or {})
    context = row.get("target_context") or profile.get("matched_context") or {}
    base_score = _float_or_none(row.get("base_score")) or _float_or_none(payload.get("score"))
    return {
        "potency": _score_potency(payload, base_score=base_score),
        "metabolic_stability": _score_stability(payload, context),
        "permeability": _score_permeability(payload),
        "liability": _score_liability(payload),
    }


def calibrate_multi_objective_profile(
    *,
    db_path: str | Path = Path("data/localmedchem.sqlite"),
    project_name: str | None = None,
    target_context: dict | None = None,
    base_profile: dict | None = None,
    profiles_path: str | Path = DEFAULT_TARGET_CONTEXT_PROFILES_PATH,
    min_observations: int = 4,
) -> dict:
    """Calibrate multi-objective component weights from historical outcomes."""
    selected = base_profile or select_target_context_profile(target_context, profiles_path=profiles_path)
    rows = _candidate_outcome_rows(db_path=db_path, project_name=project_name, target_context=target_context)
    base_weights = {
        "potency": 0.42,
        "metabolic_stability": 0.2,
        "permeability": 0.2,
        "liability": 0.18,
        **(selected.get("score_weights") or {}),
    }
    total = sum(max(float(value), 0.0) for value in base_weights.values()) or 1.0
    normalized_base = {key: max(float(value), 0.0) / total for key, value in base_weights.items()}
    diagnostics = []
    multipliers = {key: 1.0 for key in normalized_base}
    scored_rows = []
    for row in rows:
        components = _component_scores_for_row(row, selected)
        scored_rows.append({**row, "component_scores": components})
    for component in ["potency", "metabolic_stability", "permeability", "liability"]:
        positive = [row["component_scores"][component] for row in scored_rows if float(row["outcome_value"]) >= 0.7]
        negative = [row["component_scores"][component] for row in scored_rows if float(row["outcome_value"]) <= 0.35]
        watch = [row["component_scores"][component] for row in scored_rows if 0.35 < float(row["outcome_value"]) < 0.7]
        positive_mean = _mean(positive)
        negative_mean = _mean(negative)
        separation = (positive_mean - negative_mean) if positive_mean is not None and negative_mean is not None else None
        if separation is not None and len(scored_rows) >= int(min_observations):
            multipliers[component] = _clamp(1.0 + separation / 80.0, 0.55, 1.55)
        diagnostics.append(
            {
                "component": component,
                "base_weight": round(normalized_base.get(component, 0.0), 4),
                "positive_count": len(positive),
                "negative_count": len(negative),
                "watch_count": len(watch),
                "positive_mean_component_score": round(positive_mean, 4) if positive_mean is not None else None,
                "negative_mean_component_score": round(negative_mean, 4) if negative_mean is not None else None,
                "separation": round(separation, 4) if separation is not None else None,
                "weight_multiplier": round(multipliers[component], 4),
            }
        )
    adjusted = {key: normalized_base[key] * multipliers.get(key, 1.0) for key in normalized_base}
    adjusted_total = sum(adjusted.values()) or 1.0
    calibrated_weights = {key: round(value / adjusted_total, 4) for key, value in adjusted.items()}
    status = "calibrated" if len(scored_rows) >= int(min_observations) else "insufficient_data"
    profile_id = selected.get("profile_id") or DEFAULT_TARGET_CONTEXT_PROFILE["profile_id"]
    calibrated_profile = {
        **selected,
        "profile_id": f"{profile_id}_calibrated_{project_name or 'project'}",
        "score_weights": calibrated_weights,
        "calibration_status": status,
        "calibration_project_name": project_name,
        "calibration_observation_count": len(scored_rows),
        "calibration_basis": "historical_candidate_outcomes",
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "created_at": calibrated_profile["calibrated_at"],
        "project_name": project_name,
        "status": status,
        "observation_count": len(scored_rows),
        "min_observations": int(min_observations),
        "base_profile_id": profile_id,
        "target_context": standardize_target_context(target_context or selected.get("matched_context") or {}),
        "base_weights": {key: round(value, 4) for key, value in normalized_base.items()},
        "calibrated_profile": calibrated_profile,
        "component_diagnostics": diagnostics,
        "recommended_next_actions": [
            "Use calibrated weights for the next project run when observation_count meets the minimum.",
            "Keep manual review for components with weak positive/negative separation.",
            "Refresh this report after each closed-loop result import.",
        ],
    }


def write_multi_objective_calibration_report(report: dict, output_path: str | Path = DEFAULT_MULTI_OBJECTIVE_CALIBRATION_REPORT_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def write_multi_objective_profile(profile: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(profile, handle, sort_keys=False, allow_unicode=False)
