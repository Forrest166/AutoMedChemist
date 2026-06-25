from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .analog_series import active_queue_analog_series_policy, queue_analog_series_delta_for_candidate
from .multi_objective import (
    DEFAULT_TARGET_CONTEXT_PROFILE,
    _candidate_outcome_rows,
    _component_scores_for_row,
    _context_matches,
    select_target_context_profile,
)


DEFAULT_REPLAY_REPORT_PATH = Path("data/projects/demo/closed_loop_replay_report.json")


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_yaml(path: str | Path) -> dict:
    yaml_path = Path(path)
    if not yaml_path.exists():
        return {}
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _stable_bucket(*parts: Any, modulo: int = 5) -> int:
    import hashlib

    text = "|".join(str(part or "") for part in parts)
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16) % int(modulo)


def _normalized_weights(profile: dict) -> dict[str, float]:
    weights = {
        "potency": 0.42,
        "metabolic_stability": 0.2,
        "permeability": 0.2,
        "liability": 0.18,
        **(profile.get("score_weights") or {}),
    }
    total = sum(max(float(value), 0.0) for value in weights.values()) or 1.0
    return {key: max(float(value), 0.0) / total for key, value in weights.items()}


def _score_components(components: dict[str, float], weights: dict[str, float]) -> float:
    return round(sum(float(components.get(key) or 0.0) * weights.get(key, 0.0) for key in components), 4)


def _rank_metrics(scored_rows: list[dict], score_key: str) -> dict:
    if not scored_rows:
        return {"row_count": 0}
    rows = sorted(scored_rows, key=lambda row: float(row.get(score_key) or 0.0), reverse=True)
    top_n = max(1, len(rows) // 4)
    top = rows[:top_n]
    bottom = rows[-top_n:]
    overall_mean = sum(float(row["outcome_value"]) for row in rows) / len(rows)
    top_mean = sum(float(row["outcome_value"]) for row in top) / len(top)
    bottom_mean = sum(float(row["outcome_value"]) for row in bottom) / len(bottom)
    positives = [row for row in rows if float(row["outcome_value"]) >= 0.7]
    top_positive = [row for row in top if float(row["outcome_value"]) >= 0.7]
    comparable = concordant = 0
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            left_outcome = float(left["outcome_value"])
            right_outcome = float(right["outcome_value"])
            if abs(left_outcome - right_outcome) < 0.001:
                continue
            comparable += 1
            left_score = float(left.get(score_key) or 0.0)
            right_score = float(right.get(score_key) or 0.0)
            if (left_score - right_score) * (left_outcome - right_outcome) > 0:
                concordant += 1
    return {
        "row_count": len(rows),
        "top_quartile_size": len(top),
        "positive_count": len(positives),
        "top_quartile_positive_count": len(top_positive),
        "top_quartile_positive_capture": round(len(top_positive) / len(positives), 4) if positives else None,
        "overall_outcome_mean": round(overall_mean, 4),
        "top_quartile_outcome_mean": round(top_mean, 4),
        "bottom_quartile_outcome_mean": round(bottom_mean, 4),
        "rank_lift": round(top_mean - overall_mean, 4),
        "top_bottom_separation": round(top_mean - bottom_mean, 4),
        "pairwise_concordance": round(concordant / comparable, 4) if comparable else None,
    }


def _stratified_rank_metrics(scored_rows: list[dict]) -> list[dict]:
    strata: dict[tuple[str, str], list[dict]] = {}
    for row in scored_rows:
        context = {
            "endpoint_group": row.get("endpoint_group") or "unspecified",
            "target_family": row.get("target_family") or "unspecified",
            "assay_type": row.get("assay_type") or "unspecified",
        }
        for dimension in ["endpoint_group", "target_family", "assay_type"]:
            key = str(context.get(dimension) or "unspecified")
            strata.setdefault((dimension, key), []).append(row)
        combined = "|".join(str(context.get(key) or "unspecified") for key in ["endpoint_group", "target_family", "assay_type"])
        strata.setdefault(("endpoint_family_assay", combined), []).append(row)
    metrics = []
    for (dimension, value), rows in sorted(strata.items(), key=lambda item: (item[0][0], item[0][1])):
        base = _rank_metrics(rows, "base_score")
        calibrated = _rank_metrics(rows, "calibrated_score")
        metrics.append(
            {
                "dimension": dimension,
                "value": value,
                "row_count": len(rows),
                "base_rank_lift": base.get("rank_lift"),
                "calibrated_rank_lift": calibrated.get("rank_lift"),
                "rank_lift_delta": round(float(calibrated.get("rank_lift") or 0.0) - float(base.get("rank_lift") or 0.0), 4),
                "base_pairwise_concordance": base.get("pairwise_concordance"),
                "calibrated_pairwise_concordance": calibrated.get("pairwise_concordance"),
                "positive_count": calibrated.get("positive_count"),
                "top_quartile_positive_capture": calibrated.get("top_quartile_positive_capture"),
            }
        )
    metrics.sort(
        key=lambda row: (
            {"endpoint_family_assay": 0, "endpoint_group": 1, "target_family": 2, "assay_type": 3}.get(str(row.get("dimension")), 9),
            -int(row.get("row_count") or 0),
            str(row.get("value") or ""),
        )
    )
    return metrics


def build_multi_objective_holdout_report(
    *,
    db_path: str | Path = Path("data/localmedchem.sqlite"),
    project_name: str | None = None,
    target_context: dict | None = None,
    calibrated_profile: dict | None = None,
    calibration_report_path: str | Path = Path("data/projects/demo/multi_objective_calibration_report.json"),
    profiles_path: str | Path = Path("data/rules/target_context_profiles.yaml"),
    holdout_bucket: int = 0,
    bucket_count: int = 5,
) -> dict:
    calibration_report = _read_json(calibration_report_path)
    calibrated = calibrated_profile or calibration_report.get("calibrated_profile") or {}
    base_profile = select_target_context_profile(target_context, profiles_path=profiles_path)
    if not calibrated:
        calibrated = {**DEFAULT_TARGET_CONTEXT_PROFILE, "profile_id": "missing_calibrated_profile"}
    rows = _candidate_outcome_rows(db_path=db_path, project_name=project_name, target_context=target_context)
    holdout = [
        row
        for row in rows
        if _stable_bucket(row.get("run_id"), row.get("candidate_id"), row.get("endpoint_group"), modulo=bucket_count) == int(holdout_bucket)
    ]
    if not holdout and rows:
        holdout = rows[: max(1, len(rows) // max(2, bucket_count))]
    base_weights = _normalized_weights(base_profile)
    calibrated_weights = _normalized_weights(calibrated)
    scored = []
    for row in holdout:
        if not _context_matches(row.get("target_context") or {}, target_context):
            continue
        components = _component_scores_for_row(row, base_profile)
        scored.append(
            {
                "run_id": row.get("run_id"),
                "candidate_id": row.get("candidate_id"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": (row.get("target_context") or {}).get("target_family"),
                "assay_type": (row.get("target_context") or {}).get("assay_type"),
                "outcome_value": row.get("outcome_value"),
                "base_score": _score_components(components, base_weights),
                "calibrated_score": _score_components(components, calibrated_weights),
                "components": components,
            }
        )
    base_metrics = _rank_metrics(scored, "base_score")
    calibrated_metrics = _rank_metrics(scored, "calibrated_score")
    stratified = _stratified_rank_metrics(scored)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "validation_type": "multi_objective_holdout_replay",
        "holdout_bucket": int(holdout_bucket),
        "bucket_count": int(bucket_count),
        "candidate_observation_count": len(rows),
        "holdout_count": len(scored),
        "base_profile_id": base_profile.get("profile_id"),
        "calibrated_profile_id": calibrated.get("profile_id"),
        "base_metrics": base_metrics,
        "calibrated_metrics": calibrated_metrics,
        "delta": {
            "rank_lift_delta": round(float(calibrated_metrics.get("rank_lift") or 0.0) - float(base_metrics.get("rank_lift") or 0.0), 4),
            "pairwise_concordance_delta": round(
                float(calibrated_metrics.get("pairwise_concordance") or 0.0) - float(base_metrics.get("pairwise_concordance") or 0.0),
                4,
            ),
        },
        "stratified_group_count": len(stratified),
        "stratified_metrics": stratified,
        "sample_rows": scored[:20],
    }


def _expected_queue_direction(series: dict) -> str:
    action = str(series.get("series_delta_action") or "")
    mean_delta = _float_or_none(series.get("mean_priority_delta"))
    observed = _float_or_none(series.get("mean_observed_feedback"))
    if action == "deprioritize_series" or (mean_delta is not None and mean_delta <= -1.0) or (observed is not None and observed <= 35.0):
        return "negative"
    if action in {"expand_or_measure_series", "measure_representatives", "review_feedback_driven_shift"}:
        if mean_delta is None or mean_delta >= 0.0 or (observed is not None and observed >= 65.0):
            return "positive"
    if mean_delta is not None and mean_delta >= 1.0:
        return "positive"
    return "neutral"


def build_queue_policy_replay_report(
    delta_report: dict,
    *,
    policy_document: dict | None = None,
    policy_path: str | Path = Path("data/rules/queue_analog_series_policy.yaml"),
) -> dict:
    document = policy_document or _read_yaml(policy_path)
    active_policy = active_queue_analog_series_policy(document) if document else {}
    rows = []
    for series in delta_report.get("series") or []:
        endpoint = series.get("endpoint_group") or "project_panel"
        target_family = series.get("target_family") or "all"
        candidate = {
            "endpoint_group": endpoint,
            "direction": endpoint,
            "target_family": target_family,
            "enumeration_type": series.get("operator") or series.get("enumeration_type") or "unspecified",
            "replacement_label": series.get("replacement_label") or "unspecified",
        }
        scored = queue_analog_series_delta_for_candidate(
            candidate,
            {"series": [series]},
            target_context={"endpoint_group": endpoint, "target_family": target_family},
            policy=active_policy,
        )
        adjustment = float(scored.get("queue_analog_series_delta_score_adjustment") or 0.0)
        expected = _expected_queue_direction(series)
        if expected == "positive":
            aligned = adjustment > 0.0
        elif expected == "negative":
            aligned = adjustment < 0.0
        else:
            aligned = abs(adjustment) <= 1.0
        rows.append(
            {
                "series_key": series.get("series_key"),
                "endpoint_group": endpoint,
                "target_family": target_family,
                "series_delta_action": series.get("series_delta_action"),
                "mean_priority_delta": series.get("mean_priority_delta"),
                "mean_observed_feedback": series.get("mean_observed_feedback"),
                "expected_direction": expected,
                "policy_adjustment": round(adjustment, 4),
                "aligned": bool(aligned),
                "policy_context": scored.get("queue_analog_series_policy_context"),
                "basis": scored.get("queue_analog_series_delta_basis"),
            }
        )
    actionable = [row for row in rows if row["expected_direction"] != "neutral"]
    aligned = [row for row in actionable if row["aligned"]]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validation_type": "queue_policy_series_replay",
        "policy_version": active_policy.get("version"),
        "series_count": len(rows),
        "actionable_series_count": len(actionable),
        "aligned_series_count": len(aligned),
        "alignment_rate": round(len(aligned) / len(actionable), 4) if actionable else None,
        "rows": rows,
    }


def build_closed_loop_replay_report(
    *,
    root: str | Path = ".",
    db_path: str | Path = Path("data/localmedchem.sqlite"),
    project_name: str | None = "demo_learning",
    target_context: dict | None = None,
) -> dict:
    root_path = Path(root)
    delta_report = _read_json(root_path / "data/projects/closed_loop/queue_analog_series_delta.json")
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "multi_objective_holdout": build_multi_objective_holdout_report(
            db_path=db_path,
            project_name=project_name,
            target_context=target_context,
            calibration_report_path=root_path / "data/projects/demo/multi_objective_calibration_report.json",
            profiles_path=root_path / "data/rules/target_context_profiles.yaml",
        ),
        "queue_policy_replay": build_queue_policy_replay_report(
            delta_report,
            policy_path=root_path / "data/rules/queue_analog_series_policy.yaml",
        ),
    }
    queue_alignment = report["queue_policy_replay"].get("alignment_rate")
    rank_delta = (report["multi_objective_holdout"].get("delta") or {}).get("rank_lift_delta")
    report["status"] = "pass" if (queue_alignment is None or queue_alignment >= 0.6) and (rank_delta is None or rank_delta >= -0.02) else "review"
    report["recommended_next_actions"] = [
        "Review queue rows marked unaligned before promoting a policy version.",
        "Prefer calibrated multi-objective weights only when holdout rank lift is non-negative or manually justified.",
        "Rebuild this replay report after each feedback/result import.",
    ]
    return report


def write_closed_loop_replay_report(report: dict, output_path: str | Path = DEFAULT_REPLAY_REPORT_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
