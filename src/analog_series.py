from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .assay_learning import build_assay_learning_report, endpoint_gate_from_learning
from .database import initialize_database
from .decision_packet import list_decision_packets


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_ANALOG_SERIES_REPORT_PATH = Path("data/projects/demo/analog_series_report.json")
DEFAULT_QUEUE_ANALOG_SERIES_DELTA_PATH = Path("data/projects/closed_loop/queue_analog_series_delta.json")
DEFAULT_QUEUE_ANALOG_SERIES_POLICY_PATH = Path("data/rules/queue_analog_series_policy.yaml")

DEFAULT_QUEUE_ANALOG_SERIES_ACTION_BASES = {
    "expand_or_measure_series": 4.0,
    "measure_representatives": 2.5,
    "review_feedback_driven_shift": 1.0,
    "watch_series": 0.0,
    "deprioritize_series": -6.0,
}

DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_WEIGHTS = {
    "mean_priority_delta": 0.5,
    "observed_feedback_high": 1.0,
    "observed_feedback_low": -1.5,
    "residual_medium": 1.0,
    "residual_high": 2.0,
}

DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_CAPS = {
    "mean_priority_delta_abs": 3.0,
    "min_adjustment": -8.0,
    "max_adjustment": 6.0,
    "observed_feedback_high_threshold": 70.0,
    "observed_feedback_low_threshold": 35.0,
    "residual_medium_threshold": 0.15,
    "residual_high_threshold": 0.3,
}


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_loads(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_endpoint_text(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    return text or "project_panel"


def _normalize_policy_context_text(value: Any, *, default: str = "all") -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    return text or default


def _queue_policy_context_key(endpoint_group: Any, target_family: Any = None) -> str:
    return "|".join(
        [
            _normalize_endpoint_text(endpoint_group),
            _normalize_policy_context_text(target_family, default="all"),
        ]
    )


def _target_family_from_context(row: dict | None = None, target_context: dict | None = None) -> str:
    row = row or {}
    target_context = target_context or {}
    embedded_context = row.get("target_context") if isinstance(row.get("target_context"), dict) else {}
    return _normalize_policy_context_text(
        target_context.get("target_family")
        or row.get("target_family")
        or row.get("target_family_normalized")
        or row.get("evidence_target_family_normalized")
        or row.get("evidence_target_family")
        or embedded_context.get("target_family"),
        default="all",
    )


def _queue_policy_series_context_key(series: dict, target_context: dict | None = None) -> str:
    endpoint = series.get("endpoint_group") or series.get("primary_endpoint_group") or (target_context or {}).get("endpoint_group") or "project_panel"
    target_family = _target_family_from_context(series, target_context)
    return _queue_policy_context_key(endpoint, target_family)


def _queue_policy_candidate_context_key(row: dict, target_context: dict | None = None) -> str:
    endpoint = (
        (target_context or {}).get("endpoint_group")
        or row.get("endpoint_gate_endpoint")
        or row.get("evidence_confidence_endpoint")
        or row.get("evidence_endpoint_group")
        or row.get("endpoint_group")
        or row.get("direction")
        or "project_panel"
    )
    return _queue_policy_context_key(endpoint, _target_family_from_context(row, target_context))


def _outcome_bucket(row: dict) -> str:
    stop_go = str(row.get("stop_go_decision") or "").strip().lower().replace(" ", "_")
    if stop_go in {"go", "positive"}:
        return "positive"
    if stop_go in {"stop", "negative"}:
        return "negative"
    if stop_go in {"watch", "retest"}:
        return "watch"
    score = _float_or_none(row.get("normalized_score"))
    if score is not None:
        if score >= 70:
            return "positive"
        if score <= 35:
            return "negative"
        return "watch"
    classification = str(row.get("classification") or "").strip().lower().replace(" ", "_")
    if classification in {"active", "pass", "positive", "improved", "go", "hit"}:
        return "positive"
    if classification in {"inactive", "fail", "failed", "negative", "worse", "stop"}:
        return "negative"
    return "watch"


def _load_csv_rows(path: str | Path) -> list[dict]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _candidate_rows_from_db(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    limit: int = 5000,
) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT pc.run_id, pc.candidate_id, pc.rank, pc.score, pc.decision_status,
                   pc.enumeration_type, pc.replacement_label, pr.project_name,
                   pr.direction AS run_direction, pr.created_at AS run_created_at,
                   pc.payload_json
            FROM project_candidate pc
            LEFT JOIN project_run pr ON pr.run_id=pc.run_id
            WHERE (? IS NULL OR pr.project_name=?)
            ORDER BY pr.created_at DESC, pc.rank ASC
            LIMIT ?
            """,
            (project_name, project_name, int(limit)),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        item = dict(row)
        payload = _json_loads(item.pop("payload_json", None))
        if payload:
            result.append({**item, **payload})
    return result


def _outcomes_by_candidate(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> dict[tuple[str | None, str], list[dict]]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        feedback_rows = conn.execute(
            """
            SELECT f.run_id, f.candidate_id, COALESCE(f.project_name, pr.project_name, '') AS project_name,
                   f.endpoint AS endpoint_group, f.assay_name, f.assay_type, f.normalized_score,
                   f.classification, NULL AS stop_go_decision, f.recorded_at
            FROM project_feedback f
            LEFT JOIN project_run pr ON pr.run_id=f.run_id
            WHERE (? IS NULL OR COALESCE(f.project_name, pr.project_name, '')=?)
            """,
            (project_name, project_name),
        ).fetchall()
        try:
            event_rows = conn.execute(
                """
                SELECT e.run_id, e.candidate_id, COALESCE(p.project_name, pr.project_name, '') AS project_name,
                       e.endpoint_group, e.assay_name, e.assay_type, e.normalized_score,
                       e.classification, e.stop_go_decision, e.recorded_at
                FROM project_experiment_event e
                LEFT JOIN project_experiment_plan p ON p.plan_id=e.plan_id
                LEFT JOIN project_run pr ON pr.run_id=e.run_id
                WHERE (? IS NULL OR COALESCE(p.project_name, pr.project_name, '')=?)
                """,
                (project_name, project_name),
            ).fetchall()
        except sqlite3.Error:
            event_rows = []
    finally:
        conn.close()
    grouped: dict[tuple[str | None, str], list[dict]] = defaultdict(list)
    for row in [*feedback_rows, *event_rows]:
        item = dict(row)
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id:
            continue
        grouped[(item.get("run_id"), candidate_id)].append(item)
        grouped[(None, candidate_id)].append(item)
    return grouped


def _decision_counts_by_candidate(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    decision_packet_path: str | Path | None = None,
) -> dict[str, Counter]:
    packets = []
    if decision_packet_path:
        packet = _json_loads(Path(decision_packet_path).read_text(encoding="utf-8")) if Path(decision_packet_path).exists() else {}
        if packet:
            packets.append({"packet": packet})
    else:
        try:
            packets = list_decision_packets(db_path=db_path, project_name=project_name, limit=100)
        except Exception:
            packets = []
    counts: dict[str, Counter] = defaultdict(Counter)
    for packet_row in packets:
        packet = packet_row.get("packet") or packet_row
        for row in packet.get("candidates") or []:
            candidate_id = str(row.get("candidate_id") or "")
            if not candidate_id:
                continue
            counts[candidate_id][str(row.get("decision_recommendation") or "unknown")] += 1
    return counts


def _endpoint_threshold_lookup(report: dict | None) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for item in (report or {}).get("endpoints") or []:
        endpoint = _normalize_endpoint_text(item.get("endpoint_group"))
        lookup[endpoint] = endpoint_gate_from_learning(report or {}, endpoint)
    return lookup


def _endpoint_gate_for_series(report: dict | None, endpoint: str | None) -> dict:
    endpoint = _normalize_endpoint_text(endpoint)
    lookup = _endpoint_threshold_lookup(report)
    return lookup.get(endpoint) or endpoint_gate_from_learning(report or {}, endpoint)


def _candidate_endpoint(row: dict) -> str:
    return _normalize_endpoint_text(
        row.get("endpoint_gate_endpoint")
        or row.get("evidence_confidence_endpoint")
        or row.get("evidence_endpoint_group")
        or row.get("direction")
        or row.get("endpoint_group")
    )


def series_key_for_candidate(row: dict) -> str:
    site = str(row.get("site_type") or "unspecified")
    operator = str(row.get("enumeration_type") or "unspecified")
    if row.get("diversity_bucket"):
        bucket = str(row.get("diversity_bucket"))
    elif row.get("novelty_batch_bucket"):
        bucket = str(row.get("novelty_batch_bucket"))
    elif row.get("ring_diversity_bucket"):
        bucket = f"ring:{row.get('ring_diversity_bucket')}"
    else:
        bucket = str(row.get("replacement_class") or row.get("functional_rule_id") or row.get("replacement_label") or "unspecified")
    return "|".join([site, operator, bucket])


def _series_recommendation(summary: dict) -> str:
    observed = int(summary.get("observed_candidate_count") or 0)
    positive = int(summary.get("positive_count") or 0)
    negative = int(summary.get("negative_count") or 0)
    hit_rate = summary.get("hit_rate")
    if observed >= 3 and hit_rate is not None and hit_rate >= 0.6:
        return "expand_series"
    if observed >= 2 and negative > positive:
        return "deprioritize_series"
    if summary.get("novelty_batch_pick_count") and not observed:
        return "measure_representatives"
    if summary.get("severe_conflict_count"):
        return "review_evidence_conflict"
    return "keep_in_watchlist"


def _series_evidence_sufficiency(summary: dict) -> dict:
    observed = int(summary.get("observed_candidate_count") or 0)
    candidate_count = int(summary.get("candidate_count") or 0)
    endpoint_events = int(summary.get("endpoint_event_count") or 0)
    residual = _float_or_none(summary.get("max_evidence_confidence_abs_residual"))
    public_score = _float_or_none(summary.get("mean_public_strategy_signal_score"))
    severe_conflicts = int(summary.get("severe_conflict_count") or 0)
    score = 18.0
    if observed:
        score += min(42.0, observed * 14.0)
    if endpoint_events:
        score += min(14.0, endpoint_events * 0.7)
    if candidate_count >= 3:
        score += 8.0
    elif candidate_count:
        score += 4.0
    if public_score is not None:
        score += min(8.0, max(0.0, (public_score - 55.0) / 5.0))
    if residual is not None:
        if residual >= 0.3:
            score -= 18.0
        elif residual >= 0.15:
            score -= 8.0
    if severe_conflicts:
        score -= min(20.0, severe_conflicts * 8.0)
    score = round(_clamp(score, 0.0, 100.0), 2)
    if severe_conflicts:
        status = "conflict_review"
        action = "review_conflicting_evidence_before_expansion"
    elif score >= 70:
        status = "sufficient"
        action = "use_for_series_prioritization"
    elif observed == 0:
        status = "needs_first_measurement"
        action = "measure_representative_candidates"
    elif residual is not None and residual >= 0.15:
        status = "needs_residual_resolution"
        action = "run_endpoint_residual_followup"
    else:
        status = "needs_more_depth"
        action = "add_replicates_or_second_endpoint"
    return {
        "evidence_sufficiency_score": score,
        "evidence_sufficiency_status": status,
        "evidence_sufficiency_gap": round(100.0 - score, 2),
        "next_evidence_action": action,
    }


def _series_example(row: dict) -> dict:
    return {
        "run_id": row.get("run_id"),
        "project_name": row.get("project_name"),
        "candidate_id": row.get("candidate_id"),
        "rank": row.get("rank"),
        "score": row.get("score"),
        "decision_status": row.get("decision_status"),
        "replacement_label": row.get("replacement_label"),
        "novelty_batch_pick": row.get("novelty_batch_pick"),
        "novelty_batch_tier": row.get("novelty_batch_tier"),
        "endpoint_gate_decision": row.get("endpoint_gate_decision"),
        "evidence_confidence_max_abs_residual": row.get("evidence_confidence_max_abs_residual"),
        "smiles": row.get("smiles"),
    }


def build_analog_series_report(
    *,
    rows: list[dict] | None = None,
    candidates_csv: str | Path | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    decision_packet_path: str | Path | None = None,
    assay_learning_report: dict | None = None,
    candidate_limit: int = 5000,
) -> dict:
    candidate_rows = list(rows or [])
    if not candidate_rows and candidates_csv:
        candidate_rows = _load_csv_rows(candidates_csv)
    if not candidate_rows:
        candidate_rows = _candidate_rows_from_db(db_path=db_path, project_name=project_name, limit=candidate_limit)

    outcomes = _outcomes_by_candidate(db_path=db_path, project_name=project_name)
    decision_counts = _decision_counts_by_candidate(db_path=db_path, project_name=project_name, decision_packet_path=decision_packet_path)
    if assay_learning_report is None:
        try:
            assay_learning_report = build_assay_learning_report(db_path=db_path, project_name=project_name)
        except Exception:
            assay_learning_report = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in candidate_rows:
        grouped[series_key_for_candidate(row)].append(row)

    series_rows = []
    for key, items in grouped.items():
        scores = [value for value in (_float_or_none(row.get("score")) for row in items) if value is not None]
        deltas = [value for value in (_float_or_none(row.get("strategy_learning_score_delta")) for row in items) if value is not None]
        confidence_scores = [value for value in (_float_or_none(row.get("evidence_confidence_calibration_score")) for row in items) if value is not None]
        residual_values = [value for value in (_float_or_none(row.get("evidence_confidence_max_abs_residual")) for row in items) if value is not None]
        public_scores = [value for value in (_float_or_none(row.get("public_strategy_signal_score")) for row in items) if value is not None]
        endpoint_counts = Counter(str(row.get("endpoint_gate_decision") or "unknown") for row in items)
        candidate_endpoint_counts = Counter(_candidate_endpoint(row) for row in items)
        novelty_count = sum(1 for row in items if str(row.get("novelty_batch_pick")).lower() == "true" or row.get("novelty_batch_pick") is True)
        severe_conflict_count = sum(
            1
            for row in items
            if any(
                flag in {"target_family_activity_contradiction", "target_family_activity_cliff_high", "activity_cliff_high"}
                for flag in str(row.get("evidence_conflict_flags") or "").split(";")
                if flag
            )
        )
        observed_count = positive_count = negative_count = watch_count = 0
        endpoint_observations = Counter()
        normalized_scores = []
        series_decisions = Counter()
        for row in items:
            candidate_id = str(row.get("candidate_id") or "")
            for decision, count in decision_counts.get(candidate_id, Counter()).items():
                series_decisions[decision] += count
            observations = outcomes.get((row.get("run_id"), candidate_id)) or outcomes.get((None, candidate_id), [])
            if observations:
                observed_count += 1
            buckets = Counter(_outcome_bucket(obs) for obs in observations)
            positive_count += int(buckets.get("positive", 0) > 0)
            negative_count += int(buckets.get("negative", 0) > 0)
            watch_count += int(buckets.get("watch", 0) > 0)
            for obs in observations:
                observed_endpoint = _normalize_endpoint_text(obs.get("endpoint_group") or "unspecified")
                endpoint_observations[observed_endpoint] += 1
                candidate_endpoint_counts[observed_endpoint] += 1
                score = _float_or_none(obs.get("normalized_score"))
                if score is not None:
                    normalized_scores.append(score)

        examples = sorted((_series_example(row) for row in items), key=lambda row: _float_or_none(row.get("score")) or 0.0, reverse=True)[:8]
        first = items[0]
        primary_endpoint = (endpoint_observations or candidate_endpoint_counts).most_common(1)[0][0] if (endpoint_observations or candidate_endpoint_counts) else "project_panel"
        endpoint_gate = _endpoint_gate_for_series(assay_learning_report, primary_endpoint)
        summary = {
            "series_key": key,
            "site_type": first.get("site_type"),
            "operator": first.get("enumeration_type"),
            "primary_endpoint_group": primary_endpoint,
            "endpoint_learned_go_score": endpoint_gate.get("go_score"),
            "endpoint_learned_stop_score": endpoint_gate.get("stop_score"),
            "endpoint_learning_basis": endpoint_gate.get("learning_basis"),
            "endpoint_gate_source": endpoint_gate.get("gate_source"),
            "endpoint_event_count": endpoint_gate.get("event_count"),
            "endpoint_retest_event_count": endpoint_gate.get("retest_event_count"),
            "endpoint_mean_assay_confidence_score": endpoint_gate.get("mean_assay_confidence_score"),
            "diversity_bucket": first.get("diversity_bucket") or first.get("novelty_batch_bucket") or first.get("ring_diversity_bucket"),
            "replacement_class": first.get("replacement_class"),
            "candidate_count": len(items),
            "top_score": round(max(scores), 4) if scores else None,
            "mean_score": _mean(scores),
            "mean_strategy_delta": _mean(deltas),
            "mean_evidence_confidence_score": _mean(confidence_scores),
            "mean_evidence_confidence_abs_residual": _mean(residual_values),
            "max_evidence_confidence_abs_residual": round(max(residual_values), 4) if residual_values else None,
            "high_residual_candidate_count": sum(1 for value in residual_values if value >= 0.15),
            "mean_public_strategy_signal_score": _mean(public_scores),
            "novelty_batch_pick_count": novelty_count,
            "endpoint_go_count": int(endpoint_counts.get("go", 0)),
            "endpoint_hold_count": int(endpoint_counts.get("hold", 0)),
            "endpoint_stop_count": int(endpoint_counts.get("stop", 0)),
            "severe_conflict_count": severe_conflict_count,
            "observed_candidate_count": observed_count,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "watch_count": watch_count,
            "hit_rate": round(positive_count / observed_count, 4) if observed_count else None,
            "mean_observed_score": _mean(normalized_scores),
            "observed_endpoint_counts": dict(endpoint_observations.most_common()),
            "candidate_endpoint_counts": dict(candidate_endpoint_counts.most_common()),
            "decision_recommendation_counts": dict(series_decisions.most_common()),
            "example_candidates": examples,
        }
        summary.update(_series_evidence_sufficiency(summary))
        summary["series_recommendation"] = _series_recommendation(summary)
        series_rows.append(summary)

    series_rows.sort(
        key=lambda row: (
            {"expand_series": 0, "measure_representatives": 1, "review_evidence_conflict": 2, "keep_in_watchlist": 3, "deprioritize_series": 4}.get(
                row.get("series_recommendation"), 9
            ),
            -(row.get("top_score") or 0),
            -(row.get("candidate_count") or 0),
        )
    )
    recommendation_counts = Counter(row.get("series_recommendation") for row in series_rows)
    sufficiency_counts = Counter(row.get("evidence_sufficiency_status") for row in series_rows)
    endpoint_thresholds = [
        {
            "endpoint_group": endpoint,
            "go_score": gate.get("go_score"),
            "stop_score": gate.get("stop_score"),
            "learning_basis": gate.get("learning_basis"),
            "gate_source": gate.get("gate_source"),
            "event_count": gate.get("event_count"),
            "retest_event_count": gate.get("retest_event_count"),
            "mean_assay_confidence_score": gate.get("mean_assay_confidence_score"),
        }
        for endpoint, gate in sorted(_endpoint_threshold_lookup(assay_learning_report).items())
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "candidate_count": len(candidate_rows),
        "series_count": len(series_rows),
        "observed_series_count": sum(1 for row in series_rows if row.get("observed_candidate_count")),
        "recommendation_counts": dict(recommendation_counts.most_common()),
        "evidence_sufficiency_status_counts": dict(sufficiency_counts.most_common()),
        "sufficient_series_count": int(sufficiency_counts.get("sufficient", 0)),
        "evidence_gap_series_count": sum(
            1
            for row in series_rows
            if str(row.get("evidence_sufficiency_status") or "") in {"needs_first_measurement", "needs_residual_resolution", "needs_more_depth", "conflict_review"}
        ),
        "endpoint_thresholds": endpoint_thresholds,
        "series": series_rows,
        "recommended_next_actions": [
            "Expand analog series with observed hit-rate support and consistent evidence.",
            "Measure novelty-batch representatives before scaling unobserved series.",
            "Deprioritize series with repeated negative outcomes unless a new target-context rationale is added.",
            "Use endpoint thresholds and residual fields to separate true SAR signal from thin-sample calibration gaps.",
            "Prioritize next experiments by evidence_sufficiency_status before expanding large unmeasured series.",
        ],
    }


def write_analog_series_report(report: dict, output_path: str | Path = DEFAULT_ANALOG_SERIES_REPORT_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def default_queue_analog_series_policy() -> dict:
    return {
        "policy_id": "queue_analog_series_delta_policy",
        "active_version": "heuristic-v1",
        "created_at": "baseline",
        "updated_at": "baseline",
        "change_log": [
            {
                "event_type": "created",
                "version": "heuristic-v1",
                "note": "Baseline queue analog-series delta policy.",
            }
        ],
        "versions": [
            {
                "version": "heuristic-v1",
                "status": "active",
                "created_at": "baseline",
                "parent_version": None,
                "source_report": None,
                "calibration_basis": "hand_seeded_baseline",
                "training_series_count": 0,
                "action_base_adjustments": dict(DEFAULT_QUEUE_ANALOG_SERIES_ACTION_BASES),
                "context_action_base_adjustments": {},
                "feature_weights": dict(DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_WEIGHTS),
                "feature_caps": dict(DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_CAPS),
                "notes": "Default policy mirrors the original rule-based score adjustment.",
            }
        ],
    }


def active_queue_analog_series_policy(policy: dict | None, *, active_version: str | None = None) -> dict:
    document = policy or default_queue_analog_series_policy()
    if "versions" not in document:
        return document
    version = active_version or document.get("active_version")
    versions = document.get("versions") or []
    if version:
        matched = next((item for item in versions if str(item.get("version")) == str(version)), None)
        if matched:
            return matched
    matched = next((item for item in versions if str(item.get("status")) == "active"), None)
    return matched or (versions[-1] if versions else default_queue_analog_series_policy()["versions"][0])


def load_queue_analog_series_policy(
    path: str | Path = DEFAULT_QUEUE_ANALOG_SERIES_POLICY_PATH,
    *,
    active_version: str | None = None,
) -> dict:
    policy_path = Path(path)
    if not policy_path.exists():
        return active_queue_analog_series_policy(default_queue_analog_series_policy(), active_version=active_version)
    try:
        with policy_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        data = {}
    if not data:
        data = default_queue_analog_series_policy()
    return active_queue_analog_series_policy(data, active_version=active_version)


def load_queue_analog_series_policy_document(path: str | Path = DEFAULT_QUEUE_ANALOG_SERIES_POLICY_PATH) -> dict:
    policy_path = Path(path)
    if not policy_path.exists():
        return default_queue_analog_series_policy()
    try:
        with policy_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        data = {}
    if not data:
        return default_queue_analog_series_policy()
    data.setdefault("policy_id", "queue_analog_series_delta_policy")
    data.setdefault("active_version", active_queue_analog_series_policy(data).get("version"))
    data.setdefault("versions", [])
    data.setdefault("change_log", [])
    return data


def write_queue_analog_series_policy(policy: dict, output_path: str | Path = DEFAULT_QUEUE_ANALOG_SERIES_POLICY_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(policy, handle, sort_keys=False, allow_unicode=False)


def _policy_feature_value(series: dict, policy: dict) -> float:
    weights = {**DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_WEIGHTS, **(policy.get("feature_weights") or {})}
    caps = {**DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_CAPS, **(policy.get("feature_caps") or {})}
    value = 0.0
    mean_delta = _float_or_none(series.get("mean_priority_delta"))
    if mean_delta is not None:
        cap = float(caps.get("mean_priority_delta_abs") or 3.0)
        value += _clamp(mean_delta, -cap, cap) * float(weights.get("mean_priority_delta") or 0.0)
    observed = _float_or_none(series.get("mean_observed_feedback"))
    if observed is not None:
        if observed >= float(caps.get("observed_feedback_high_threshold") or 70.0):
            value += float(weights.get("observed_feedback_high") or 0.0)
        elif observed <= float(caps.get("observed_feedback_low_threshold") or 35.0):
            value += float(weights.get("observed_feedback_low") or 0.0)
    residual = _float_or_none(series.get("max_evidence_confidence_abs_residual"))
    if residual is not None:
        if residual >= float(caps.get("residual_high_threshold") or 0.3):
            value += float(weights.get("residual_high") or 0.0)
        elif residual >= float(caps.get("residual_medium_threshold") or 0.15):
            value += float(weights.get("residual_medium") or 0.0)
    return value


def _learned_action_target(series: dict, base_policy: dict) -> float:
    action = str(series.get("series_delta_action") or "watch_series")
    bases = {**DEFAULT_QUEUE_ANALOG_SERIES_ACTION_BASES, **(base_policy.get("action_base_adjustments") or {})}
    caps = {**DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_CAPS, **(base_policy.get("feature_caps") or {})}
    raw = float(bases.get(action, 0.0)) + _policy_feature_value(series, base_policy)
    return _clamp(raw, float(caps.get("min_adjustment") or -8.0), float(caps.get("max_adjustment") or 6.0))


def calibrate_queue_analog_series_policy(
    delta_report: dict,
    *,
    previous_policy: dict | None = None,
    version: str | None = None,
    reviewer: str | None = None,
    note: str | None = None,
    blend: float = 0.45,
) -> dict:
    """Create a new queue-series policy version from observed priority deltas."""
    document = previous_policy or default_queue_analog_series_policy()
    active = active_queue_analog_series_policy(document)
    now = datetime.now(timezone.utc).isoformat()
    new_version = version or f"series-policy-{now[:10].replace('-', '')}-{len(document.get('versions') or []) + 1:03d}"
    blend = _clamp(float(blend), 0.0, 1.0)
    action_series: dict[str, list[dict]] = defaultdict(list)
    context_action_series: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for series in delta_report.get("series") or []:
        action = str(series.get("series_delta_action") or "watch_series")
        action_series[action].append(series)
        context_action_series[_queue_policy_series_context_key(series)][action].append(series)

    old_bases = {**DEFAULT_QUEUE_ANALOG_SERIES_ACTION_BASES, **(active.get("action_base_adjustments") or {})}
    learned_bases = dict(old_bases)
    action_summaries = []
    for action, rows in sorted(action_series.items()):
        targets = [_learned_action_target(row, active) for row in rows]
        if not targets:
            continue
        learned_target = sum(targets) / len(targets)
        old_base = float(old_bases.get(action, 0.0))
        new_base = _clamp((1.0 - blend) * old_base + blend * learned_target, -8.0, 6.0)
        learned_bases[action] = round(new_base, 4)
        action_summaries.append(
            {
                "series_delta_action": action,
                "series_count": len(rows),
                "previous_base_adjustment": round(old_base, 4),
                "learned_target_adjustment": round(learned_target, 4),
                "new_base_adjustment": round(new_base, 4),
            }
        )

    old_context_bases = {
        str(context): {str(action): float(value) for action, value in (actions or {}).items()}
        for context, actions in (active.get("context_action_base_adjustments") or {}).items()
        if isinstance(actions, dict)
    }
    learned_context_bases: dict[str, dict[str, float]] = {context: dict(actions) for context, actions in old_context_bases.items()}
    context_summaries = []
    for context_key, actions in sorted(context_action_series.items()):
        endpoint_group, target_family = (context_key.split("|", 1) + ["all"])[:2]
        context_bases = learned_context_bases.setdefault(context_key, {})
        for action, rows in sorted(actions.items()):
            targets = [_learned_action_target(row, active) for row in rows]
            if not targets:
                continue
            learned_target = sum(targets) / len(targets)
            previous_base = float(old_context_bases.get(context_key, {}).get(action, old_bases.get(action, 0.0)))
            new_base = _clamp((1.0 - blend) * previous_base + blend * learned_target, -8.0, 6.0)
            context_bases[action] = round(new_base, 4)
            context_summaries.append(
                {
                    "context_key": context_key,
                    "endpoint_group": endpoint_group,
                    "target_family": target_family,
                    "series_delta_action": action,
                    "series_count": len(rows),
                    "previous_base_adjustment": round(previous_base, 4),
                    "learned_target_adjustment": round(learned_target, 4),
                    "new_base_adjustment": round(new_base, 4),
                }
            )

    versions = []
    for item in document.get("versions") or []:
        copied = dict(item)
        if copied.get("status") == "active":
            copied["status"] = "archived"
        versions.append(copied)
    calibrated_version = {
        "version": new_version,
        "status": "active",
        "created_at": now,
        "parent_version": active.get("version"),
        "source_report": delta_report.get("project_name") or "queue_analog_series_delta",
        "calibration_basis": "priority_delta_feedback",
        "training_series_count": int(delta_report.get("series_count") or len(delta_report.get("series") or [])),
        "training_candidate_count": int(delta_report.get("candidate_count") or 0),
        "action_base_adjustments": learned_bases,
        "context_action_base_adjustments": learned_context_bases,
        "feature_weights": {**DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_WEIGHTS, **(active.get("feature_weights") or {})},
        "feature_caps": {**DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_CAPS, **(active.get("feature_caps") or {})},
        "action_summaries": action_summaries,
        "context_summaries": context_summaries,
        "notes": note or "Calibrated from queue analog-series priority deltas.",
    }
    versions.append(calibrated_version)
    change_log = list(document.get("change_log") or [])
    change_log.append(
        {
            "event_type": "calibrated",
            "version": new_version,
            "parent_version": active.get("version"),
            "reviewer": reviewer,
            "created_at": now,
            "note": note or "",
        }
    )
    return {
        **document,
        "active_version": new_version,
        "updated_at": now,
        "versions": versions,
        "change_log": change_log,
        "latest_calibration": {
            "version": new_version,
            "series_count": calibrated_version["training_series_count"],
            "candidate_count": calibrated_version["training_candidate_count"],
            "action_summaries": action_summaries,
            "context_summaries": context_summaries,
        },
    }


def rollback_queue_analog_series_policy(
    policy: dict,
    *,
    version: str,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    versions = []
    found = False
    for item in policy.get("versions") or []:
        copied = dict(item)
        if str(copied.get("version")) == str(version):
            copied["status"] = "active"
            found = True
        elif copied.get("status") == "active":
            copied["status"] = "archived"
        versions.append(copied)
    if not found:
        raise ValueError(f"Queue analog-series policy version not found: {version}")
    now = datetime.now(timezone.utc).isoformat()
    change_log = list(policy.get("change_log") or [])
    change_log.append(
        {
            "event_type": "rollback",
            "version": version,
            "reviewer": reviewer,
            "created_at": now,
            "note": note or "",
        }
    )
    return {
        **policy,
        "active_version": version,
        "updated_at": now,
        "versions": versions,
        "change_log": change_log,
    }


def _priority_delta_series_key(row: dict) -> str:
    endpoint = "project_panel"
    feedback_rows = row.get("feedback_rows") or []
    if feedback_rows:
        endpoint = str(feedback_rows[0].get("endpoint") or endpoint)
    elif row.get("endpoint_control_deltas"):
        endpoint = str(row["endpoint_control_deltas"][0].get("endpoint_group") or endpoint)
    return "|".join(
        [
            endpoint,
            str(row.get("enumeration_type") or "unspecified"),
            str(row.get("replacement_label") or "unspecified"),
        ]
    )


def load_queue_analog_series_delta_report(path: str | Path = DEFAULT_QUEUE_ANALOG_SERIES_DELTA_PATH) -> dict:
    report_path = Path(path)
    if not report_path.exists():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _queue_delta_lookup(report: dict | None) -> dict[str, dict]:
    return {
        str(item.get("series_key") or ""): item
        for item in (report or {}).get("series") or []
        if item.get("series_key")
    }


def _queue_delta_candidate_keys(row: dict, target_context: dict | None = None) -> list[str]:
    endpoints = [
        (target_context or {}).get("endpoint_group"),
        row.get("endpoint_gate_endpoint"),
        row.get("evidence_confidence_endpoint"),
        row.get("evidence_endpoint_group"),
        row.get("direction"),
        "project_panel",
    ]
    operators = [
        row.get("enumeration_type"),
        "unspecified",
    ]
    replacements = [
        row.get("replacement_label"),
        row.get("replacement_class"),
        row.get("diversity_bucket"),
        "unspecified",
    ]
    keys = []
    for endpoint in endpoints:
        if not endpoint:
            continue
        for operator in operators:
            if not operator:
                continue
            for replacement in replacements:
                if not replacement:
                    continue
                keys.append("|".join([str(endpoint), str(operator), str(replacement)]))
    return list(dict.fromkeys(keys))


def _context_action_bases_for_series(series: dict, policy: dict, target_context: dict | None = None) -> tuple[dict[str, float], str]:
    action_bases = {**DEFAULT_QUEUE_ANALOG_SERIES_ACTION_BASES, **(policy.get("action_base_adjustments") or {})}
    context_bases = policy.get("context_action_base_adjustments") or {}
    exact_context = _queue_policy_series_context_key(series, target_context)
    endpoint = exact_context.split("|", 1)[0]
    family = exact_context.split("|", 1)[1] if "|" in exact_context else "all"
    fallback_contexts = [
        exact_context,
        _queue_policy_context_key(endpoint, "all"),
        _queue_policy_context_key("project_panel", family),
        _queue_policy_context_key("project_panel", "all"),
    ]
    for context_key in dict.fromkeys(fallback_contexts):
        scoped = context_bases.get(context_key)
        if isinstance(scoped, dict) and scoped:
            return {**action_bases, **{str(key): float(value) for key, value in scoped.items()}}, context_key
    return action_bases, "global"


def _queue_delta_adjustment(series: dict, policy: dict | None = None, *, target_context: dict | None = None) -> tuple[float, str, str]:
    policy = policy or active_queue_analog_series_policy(default_queue_analog_series_policy())
    action = str(series.get("series_delta_action") or "no_series_delta")
    bases, context_key = _context_action_bases_for_series(series, policy, target_context)
    caps = {**DEFAULT_QUEUE_ANALOG_SERIES_FEATURE_CAPS, **(policy.get("feature_caps") or {})}
    base = float(bases.get(action, 0.0)) + _policy_feature_value(series, policy)
    adjustment = round(
        _clamp(
            base,
            float(caps.get("min_adjustment") or -8.0),
            float(caps.get("max_adjustment") or 6.0),
        ),
        4,
    )
    basis = (
        f"policy={policy.get('version', 'heuristic-v1')}; context={context_key}; {action}; "
        f"mean_priority_delta={series.get('mean_priority_delta')}; "
        f"mean_observed_feedback={series.get('mean_observed_feedback')}; "
        f"max_residual={series.get('max_evidence_confidence_abs_residual')}; n={series.get('candidate_count')}"
    )
    return adjustment, basis, context_key


def queue_analog_series_delta_for_candidate(
    row: dict,
    report: dict | None,
    *,
    target_context: dict | None = None,
    policy: dict | None = None,
) -> dict:
    lookup = _queue_delta_lookup(report)
    selected_policy = active_queue_analog_series_policy(policy) if policy and "versions" in policy else policy
    matched_key = next((key for key in _queue_delta_candidate_keys(row, target_context) if key in lookup), None)
    if not matched_key:
        return {
            "queue_analog_series_delta_key": "",
            "queue_analog_series_delta_action": "no_series_delta_match",
            "queue_analog_series_policy_version": (selected_policy or {}).get("version") or "heuristic-v1",
            "queue_analog_series_delta_score_adjustment": 0.0,
            "queue_analog_series_delta_basis": "",
            "queue_analog_series_policy_context": _queue_policy_candidate_context_key(row, target_context),
            "queue_analog_series_delta_mean_priority_delta": None,
            "queue_analog_series_delta_mean_observed_feedback": None,
            "queue_analog_series_delta_max_abs_residual": None,
            "queue_analog_series_delta_high_residual_count": 0,
            "queue_analog_series_delta_candidate_count": 0,
        }
    series = lookup[matched_key]
    adjustment, basis, policy_context = _queue_delta_adjustment(series, selected_policy, target_context=target_context)
    return {
        "queue_analog_series_delta_key": matched_key,
        "queue_analog_series_delta_action": series.get("series_delta_action"),
        "queue_analog_series_policy_version": (selected_policy or {}).get("version") or "heuristic-v1",
        "queue_analog_series_delta_score_adjustment": adjustment,
        "queue_analog_series_delta_basis": basis,
        "queue_analog_series_policy_context": policy_context,
        "queue_analog_series_delta_mean_priority_delta": series.get("mean_priority_delta"),
        "queue_analog_series_delta_mean_observed_feedback": series.get("mean_observed_feedback"),
        "queue_analog_series_delta_max_abs_residual": series.get("max_evidence_confidence_abs_residual"),
        "queue_analog_series_delta_high_residual_count": series.get("high_residual_candidate_count", 0),
        "queue_analog_series_delta_candidate_count": series.get("candidate_count", 0),
    }


def annotate_queue_analog_series_delta_prior(
    rows: list[dict],
    *,
    report: dict | None = None,
    report_path: str | Path | None = DEFAULT_QUEUE_ANALOG_SERIES_DELTA_PATH,
    policy: dict | None = None,
    policy_path: str | Path | None = DEFAULT_QUEUE_ANALOG_SERIES_POLICY_PATH,
    policy_version: str | None = None,
    target_context: dict | None = None,
) -> list[dict]:
    series_report = report if report is not None else load_queue_analog_series_delta_report(report_path) if report_path else {}
    selected_policy = policy if policy is not None else load_queue_analog_series_policy(policy_path, active_version=policy_version) if policy_path else None
    return [
        {
            **row,
            **queue_analog_series_delta_for_candidate(row, series_report, target_context=target_context, policy=selected_policy),
        }
        for row in rows
    ]


def _queue_series_action(summary: dict) -> str:
    delta = _float_or_none(summary.get("mean_priority_delta"))
    if delta is not None and delta >= 2:
        return "expand_or_measure_series"
    if delta is not None and delta <= -2:
        return "deprioritize_series"
    if summary.get("feedback_linked_count", 0):
        return "review_feedback_driven_shift"
    if summary.get("new_priority_count", 0):
        return "measure_representatives"
    return "watch_series"


def build_queue_analog_series_delta(priority_delta_report: dict) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in priority_delta_report.get("priority_delta_rows") or []:
        grouped[_priority_delta_series_key(row)].append(row)
    series_rows = []
    for key, rows in grouped.items():
        before_scores = [value for value in (_float_or_none(row.get("priority_score_before")) for row in rows) if value is not None]
        after_scores = [value for value in (_float_or_none(row.get("priority_score_after")) for row in rows) if value is not None]
        deltas = [value for value in (_float_or_none(row.get("priority_score_delta")) for row in rows) if value is not None]
        observed_scores = [value for value in (_float_or_none(row.get("observed_feedback_mean")) for row in rows) if value is not None]
        residual_values = [value for value in (_float_or_none(row.get("evidence_confidence_max_abs_residual")) for row in rows) if value is not None]
        status_counts = Counter(str(row.get("status") or "unknown") for row in rows)
        feedback_linked = sum(1 for row in rows if row.get("feedback_rows"))
        endpoints = Counter()
        target_families = Counter()
        for row in rows:
            target_family = _target_family_from_context(row)
            if target_family and target_family != "all":
                target_families[target_family] += 1
            for feedback in row.get("feedback_rows") or []:
                endpoints[str(feedback.get("endpoint") or "unspecified")] += 1
                feedback_family = _target_family_from_context(feedback)
                if feedback_family and feedback_family != "all":
                    target_families[feedback_family] += 1
            for endpoint_delta in row.get("endpoint_control_deltas") or []:
                endpoints[str(endpoint_delta.get("endpoint_group") or "unspecified")] += 1
                endpoint_family = _target_family_from_context(endpoint_delta)
                if endpoint_family and endpoint_family != "all":
                    target_families[endpoint_family] += 1
        examples = [
            {
                "candidate_id": row.get("candidate_id"),
                "run_id": row.get("run_id"),
                "status": row.get("status"),
                "priority_score_delta": row.get("priority_score_delta"),
                "replacement_label": row.get("replacement_label"),
                "observed_feedback_mean": row.get("observed_feedback_mean"),
                "smiles": row.get("smiles"),
            }
            for row in sorted(rows, key=lambda item: abs(float(item.get("priority_score_delta") or 0.0)), reverse=True)[:8]
        ]
        summary = {
            "series_key": key,
            "endpoint_group": key.split("|")[0] if key else "project_panel",
            "target_family": target_families.most_common(1)[0][0] if target_families else "all",
            "target_family_counts": dict(target_families.most_common()),
            "operator": rows[0].get("enumeration_type"),
            "replacement_label": rows[0].get("replacement_label"),
            "candidate_count": len(rows),
            "feedback_linked_count": feedback_linked,
            "new_priority_count": int(status_counts.get("new_priority", 0)),
            "priority_up_count": int(status_counts.get("priority_up", 0)),
            "priority_down_count": int(status_counts.get("priority_down", 0) + status_counts.get("resolved_or_removed", 0)),
            "mean_priority_before": _mean(before_scores),
            "mean_priority_after": _mean(after_scores),
                "mean_priority_delta": _mean(deltas),
                "mean_observed_feedback": _mean(observed_scores),
                "mean_evidence_confidence_abs_residual": _mean(residual_values),
                "max_evidence_confidence_abs_residual": round(max(residual_values), 4) if residual_values else None,
                "high_residual_candidate_count": sum(1 for value in residual_values if value >= 0.15),
                "status_counts": dict(status_counts.most_common()),
            "endpoint_counts": dict(endpoints.most_common()),
            "example_candidates": examples,
        }
        summary["series_delta_action"] = _queue_series_action(summary)
        series_rows.append(summary)
    series_rows.sort(
        key=lambda row: (
            {"expand_or_measure_series": 0, "measure_representatives": 1, "review_feedback_driven_shift": 2, "watch_series": 3, "deprioritize_series": 4}.get(
                row.get("series_delta_action"), 9
            ),
            -abs(float(row.get("mean_priority_delta") or 0.0)),
            -(row.get("candidate_count") or 0),
        )
    )
    action_counts = Counter(row.get("series_delta_action") for row in series_rows)
    return {
        "project_name": priority_delta_report.get("project_name"),
        "candidate_count": priority_delta_report.get("candidate_count", 0),
        "series_count": len(series_rows),
        "feedback_linked_count": priority_delta_report.get("feedback_linked_count", 0),
        "action_counts": dict(action_counts.most_common()),
        "series": series_rows,
        "recommended_next_actions": [
            "Review feedback-driven series shifts before changing generation policy.",
            "Use expand_or_measure_series groups as next-batch representatives.",
            "Deprioritize series with persistent negative priority deltas unless new context is added.",
        ],
    }


def write_queue_analog_series_delta_report(report: dict, output_path: str | Path = DEFAULT_QUEUE_ANALOG_SERIES_DELTA_PATH) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
