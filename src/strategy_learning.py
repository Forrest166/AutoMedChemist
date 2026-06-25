from __future__ import annotations

from pathlib import Path

import yaml

from .decision_packet import build_decision_strategy_learning_report
from .target_context import normalize_endpoint_group, normalize_target_family


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_POLICY_PATH = Path("data/rules/strategy_learning_policy.yaml")
DEFAULT_STRATEGY_VERSION = "strategy-learning-v0.2"

RECOMMENDATION_PRIOR_SCORES = {
    "promote_strategy": 88.0,
    "watch_strategy": 68.0,
    "collect_outcomes": 55.0,
    "deprioritize_strategy": 35.0,
}

DEFAULT_STRATEGY_POLICY = {
    "policy_version": "strategy-learning-policy-default",
    "strategy_version": DEFAULT_STRATEGY_VERSION,
    "default_window_days": 365,
    "recommendation_prior_scores": RECOMMENDATION_PRIOR_SCORES,
    "default": {
        "policy_id": "default",
        "min_observed_for_rate": 3,
        "promote_hit_rate": 0.6,
        "deprioritize_hit_rate": 0.35,
        "hit_rate_score_span": 20.0,
        "prior_score_bounds": [20.0, 95.0],
        "prior_weight_multiplier": 1.0,
        "score_adjustments": {
            "promote_strategy": 3.0,
            "watch_strategy": 0.5,
            "collect_outcomes": 0.0,
            "deprioritize_strategy": -4.0,
        },
        "operator_score_adjustments": {},
        "site_type_score_adjustments": {},
    },
    "endpoint_policies": {},
}


def _deep_merge(left: dict, right: dict | None) -> dict:
    merged = dict(left)
    for key, value in (right or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_strategy_learning_policy(path: str | Path | None = DEFAULT_POLICY_PATH) -> dict:
    """Load endpoint strategy policy, falling back to conservative defaults."""
    policy = dict(DEFAULT_STRATEGY_POLICY)
    policy["default"] = dict(DEFAULT_STRATEGY_POLICY["default"])
    policy["recommendation_prior_scores"] = dict(RECOMMENDATION_PRIOR_SCORES)
    if path is None:
        return policy
    policy_path = Path(path)
    if not policy_path.exists():
        return policy
    with policy_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return _deep_merge(policy, loaded)


def endpoint_policy_for(endpoint_group: str | None, policy: dict | None = None) -> dict:
    policy = policy or load_strategy_learning_policy()
    endpoint = normalize_endpoint_group(endpoint_group) or str(endpoint_group or "default")
    default_policy = dict(policy.get("default") or {})
    endpoint_cfg = ((policy.get("endpoint_policies") or {}).get(endpoint) or {})
    merged = _deep_merge(default_policy, endpoint_cfg)
    merged["policy_version"] = policy.get("policy_version")
    merged["strategy_version"] = policy.get("strategy_version") or DEFAULT_STRATEGY_VERSION
    merged["endpoint_group"] = endpoint
    merged["policy_id"] = merged.get("policy_id") or endpoint or "default"
    return merged


def _policy_prior_scores(policy: dict | None) -> dict[str, float]:
    scores = (policy or {}).get("recommendation_prior_scores") or RECOMMENDATION_PRIOR_SCORES
    return {key: float(scores.get(key, default)) for key, default in RECOMMENDATION_PRIOR_SCORES.items()}


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _score_bounds(endpoint_policy: dict) -> tuple[float, float]:
    bounds = endpoint_policy.get("prior_score_bounds") or [20.0, 95.0]
    if not isinstance(bounds, (list, tuple)) or len(bounds) < 2:
        return 20.0, 95.0
    return _float(bounds[0], 20.0), _float(bounds[1], 95.0)


def _policy_recommendation(strategy: dict, endpoint_policy: dict) -> str:
    recommendation = str(strategy.get("strategy_recommendation") or "collect_outcomes")
    observed = _int(strategy.get("observed_candidate_count"), 0)
    hit_rate = strategy.get("hit_rate")
    min_observed = _int(endpoint_policy.get("min_observed_for_rate"), 3)
    if hit_rate is None or observed < min_observed:
        return recommendation
    rate = _float(hit_rate)
    if rate >= _float(endpoint_policy.get("promote_hit_rate"), 0.6):
        return "promote_strategy"
    if rate <= _float(endpoint_policy.get("deprioritize_hit_rate"), 0.35):
        return "deprioritize_strategy"
    return "watch_strategy"


def _policy_score_adjustment(row: dict, recommendation: str, endpoint_policy: dict) -> float:
    multiplier = _float(endpoint_policy.get("prior_weight_multiplier"), 1.0)
    score_adjustments = endpoint_policy.get("score_adjustments") or {}
    operator_adjustments = endpoint_policy.get("operator_score_adjustments") or {}
    site_adjustments = endpoint_policy.get("site_type_score_adjustments") or {}
    operator = str(row.get("enumeration_type") or "unspecified")
    site_type = str(row.get("site_type") or "unspecified")
    base = _float(score_adjustments.get(recommendation), 0.0) * multiplier
    base += _float(operator_adjustments.get(operator), 0.0)
    base += _float(site_adjustments.get(site_type), 0.0)
    return round(max(-10.0, min(10.0, base)), 3)


def _context_family(target_context: dict | None) -> str | None:
    context = target_context or {}
    return normalize_target_family(context.get("target_family") or context.get("target_family_raw"))


def _context_endpoint(target_context: dict | None) -> str | None:
    context = target_context or {}
    return normalize_endpoint_group(
        context.get("endpoint_group") or context.get("endpoint"),
        assay_type=context.get("assay_type") or context.get("standard_type"),
        assay_name=context.get("assay_name"),
    )


def _row_family(row: dict, target_context: dict | None) -> str:
    return (
        _context_family(target_context)
        or normalize_target_family(row.get("evidence_target_family_normalized") or row.get("evidence_target_family"))
        or "unspecified"
    )


def _row_endpoint(row: dict, target_context: dict | None) -> str:
    return (
        _context_endpoint(target_context)
        or normalize_endpoint_group(row.get("endpoint_gate_endpoint") or row.get("evidence_endpoint_group"))
        or "unspecified"
    )


def strategy_learning_lookup(report: dict | None) -> dict[tuple[str, str, str, str], dict]:
    lookup = {}
    for row in (report or {}).get("strategies") or []:
        key = (
            str(row.get("site_type") or "unspecified"),
            str(row.get("operator") or row.get("enumeration_type") or "unspecified"),
            str(row.get("target_family") or "unspecified"),
            str(row.get("endpoint_group") or "unspecified"),
        )
        lookup[key] = row
    return lookup


def _candidate_keys(row: dict, target_context: dict | None) -> list[tuple[str, str, str, str]]:
    site_type = str(row.get("site_type") or "unspecified")
    operator = str(row.get("enumeration_type") or "unspecified")
    family = _row_family(row, target_context)
    endpoint = _row_endpoint(row, target_context)
    return [
        (site_type, operator, family, endpoint),
        (site_type, operator, family, "unspecified"),
        (site_type, operator, "unspecified", endpoint),
        (site_type, operator, "unspecified", "unspecified"),
    ]


def strategy_prior_for_candidate(
    row: dict,
    lookup: dict[tuple[str, str, str, str], dict],
    *,
    target_context: dict | None = None,
    policy: dict | None = None,
) -> dict:
    policy = policy or load_strategy_learning_policy()
    endpoint = _row_endpoint(row, target_context)
    endpoint_policy = endpoint_policy_for(endpoint, policy)
    prior_scores = _policy_prior_scores(policy)
    policy_fields = {
        "strategy_learning_policy_version": policy.get("policy_version"),
        "strategy_learning_strategy_version": policy.get("strategy_version") or DEFAULT_STRATEGY_VERSION,
        "strategy_learning_endpoint_policy": endpoint_policy.get("policy_id"),
        "strategy_learning_window_days": policy.get("default_window_days"),
        "strategy_learning_prior_weight_multiplier": _float(endpoint_policy.get("prior_weight_multiplier"), 1.0),
    }
    matched_key = None
    strategy = None
    for key in _candidate_keys(row, target_context):
        if key in lookup:
            matched_key = key
            strategy = lookup[key]
            break
    if not strategy:
        return {
            **policy_fields,
            "strategy_learning_prior_score": None,
            "strategy_learning_prior_adjustment": 0.0,
            "strategy_learning_score_adjustment": 0.0,
            "strategy_learning_recommendation": "no_strategy_signal",
            "strategy_learning_basis": "no_matching_observed_strategy",
            "strategy_learning_hit_rate": None,
            "strategy_learning_observed_candidate_count": 0,
        }

    recommendation = _policy_recommendation(strategy, endpoint_policy)
    score = prior_scores.get(recommendation, prior_scores["collect_outcomes"])
    observed = int(strategy.get("observed_candidate_count") or 0)
    hit_rate = strategy.get("hit_rate")
    min_observed = _int(endpoint_policy.get("min_observed_for_rate"), 3)
    if hit_rate is not None and observed >= min_observed:
        span = _float(endpoint_policy.get("hit_rate_score_span"), 20.0)
        low, high = _score_bounds(endpoint_policy)
        score = max(low, min(high, score + (float(hit_rate) - 0.5) * span))
    adjustment = round((score - prior_scores["collect_outcomes"]) / 5.0, 3)
    score_adjustment = _policy_score_adjustment(row, recommendation, endpoint_policy)
    return {
        **policy_fields,
        "strategy_learning_prior_score": round(score, 2),
        "strategy_learning_prior_adjustment": adjustment,
        "strategy_learning_score_adjustment": score_adjustment,
        "strategy_learning_recommendation": recommendation,
        "strategy_learning_basis": ":".join(matched_key or ()),
        "strategy_learning_hit_rate": hit_rate,
        "strategy_learning_observed_candidate_count": observed,
    }


def annotate_strategy_learning_prior(
    rows: list[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    target_context: dict | None = None,
    report: dict | None = None,
    policy: dict | None = None,
    policy_path: str | Path | None = DEFAULT_POLICY_PATH,
) -> list[dict]:
    if not rows:
        return rows
    policy = policy or load_strategy_learning_policy(policy_path)
    if report is None and project_name:
        report = build_decision_strategy_learning_report(
            db_path=db_path,
            project_name=project_name,
            since_days=policy.get("default_window_days"),
            strategy_version=policy.get("strategy_version") or DEFAULT_STRATEGY_VERSION,
            policy_version=policy.get("policy_version"),
        )
    lookup = strategy_learning_lookup(report)
    if not lookup:
        endpoint = _row_endpoint(rows[0], target_context)
        endpoint_policy = endpoint_policy_for(endpoint, policy)
        return [
            {
                **row,
                "strategy_learning_policy_version": policy.get("policy_version"),
                "strategy_learning_strategy_version": policy.get("strategy_version") or DEFAULT_STRATEGY_VERSION,
                "strategy_learning_endpoint_policy": endpoint_policy.get("policy_id"),
                "strategy_learning_window_days": policy.get("default_window_days"),
                "strategy_learning_prior_weight_multiplier": _float(endpoint_policy.get("prior_weight_multiplier"), 1.0),
                "strategy_learning_prior_score": None,
                "strategy_learning_prior_adjustment": 0.0,
                "strategy_learning_score_adjustment": 0.0,
                "strategy_learning_recommendation": "no_strategy_signal",
                "strategy_learning_basis": "no_strategy_report",
                "strategy_learning_hit_rate": None,
                "strategy_learning_observed_candidate_count": 0,
            }
            for row in rows
        ]
    return [
        {
            **row,
            **strategy_prior_for_candidate(row, lookup, target_context=target_context, policy=policy),
        }
        for row in rows
    ]


def compare_strategy_policy_effect(rows: list[dict], *, top_n: int = 20) -> dict:
    """Compare ranking with learned strategy policy enabled vs the base score."""
    if not rows:
        return {
            "candidate_count": 0,
            "changed_top_n_count": 0,
            "max_score_delta": 0.0,
            "rows": [],
        }
    base_sorted = sorted(
        rows,
        key=lambda row: float(row.get("score_without_strategy_prior") if row.get("score_without_strategy_prior") is not None else row.get("score") or 0),
        reverse=True,
    )
    policy_sorted = sorted(rows, key=lambda row: float(row.get("score") or 0), reverse=True)
    base_rank = {row.get("candidate_id"): idx for idx, row in enumerate(base_sorted, start=1)}
    policy_rank = {row.get("candidate_id"): idx for idx, row in enumerate(policy_sorted, start=1)}
    comparison_rows = []
    deltas = []
    for row in policy_sorted:
        candidate_id = row.get("candidate_id")
        base_score = row.get("score_without_strategy_prior")
        if base_score is None:
            base_score = row.get("score")
        score = row.get("score")
        delta = round(_float(score) - _float(base_score), 4)
        deltas.append(delta)
        comparison_rows.append(
            {
                "candidate_id": candidate_id,
                "rank_with_strategy": policy_rank.get(candidate_id),
                "rank_without_strategy": base_rank.get(candidate_id),
                "rank_delta": (base_rank.get(candidate_id) or 0) - (policy_rank.get(candidate_id) or 0),
                "score": score,
                "score_without_strategy_prior": base_score,
                "strategy_score_delta": delta,
                "strategy_learning_prior_score": row.get("strategy_learning_prior_score"),
                "strategy_learning_score_adjustment": row.get("strategy_learning_score_adjustment"),
                "strategy_learning_recommendation": row.get("strategy_learning_recommendation"),
                "strategy_learning_endpoint_policy": row.get("strategy_learning_endpoint_policy"),
                "strategy_learning_basis": row.get("strategy_learning_basis"),
            }
        )
    base_top = {row.get("candidate_id") for row in base_sorted[:top_n]}
    policy_top = {row.get("candidate_id") for row in policy_sorted[:top_n]}
    return {
        "candidate_count": len(rows),
        "top_n": top_n,
        "changed_top_n_count": len(base_top.symmetric_difference(policy_top)),
        "max_score_delta": round(max((abs(delta) for delta in deltas), default=0.0), 4),
        "mean_score_delta": round(sum(deltas) / len(deltas), 4) if deltas else 0.0,
        "policy_version": next((row.get("strategy_learning_policy_version") for row in rows if row.get("strategy_learning_policy_version")), None),
        "rows": comparison_rows,
    }
