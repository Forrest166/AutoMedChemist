from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import initialize_database


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_EVIDENCE_CONFIDENCE_REPORT_PATH = Path("data/substituents/evidence_confidence_report.json")
DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH = Path("data/substituents/evidence_residual_task_registry.json")

EVIDENCE_RESIDUAL_TASK_STATUSES = [
    "open",
    "planned",
    "outcomes_imported",
    "closed",
    "resolved_by_calibration",
    "retired",
]

SOURCE_DEFINITIONS = [
    {
        "source_id": "public_mmp",
        "label": "Public MMP",
        "score_fields": ["mmp_precedent_score"],
        "presence_fields": ["mmp_precedent_strength", "mmp_pair_count", "mmp_exact_pair_count"],
        "neutral_strengths": {"", "none", "unknown"},
    },
    {
        "source_id": "chembl_activity",
        "label": "ChEMBL activity",
        "score_fields": ["transform_activity_score"],
        "presence_fields": ["rule_activity_judgment", "transform_activity_cliff_risk", "rule_activity_confidence"],
        "neutral_strengths": {"", "none", "unknown"},
    },
    {
        "source_id": "project_feedback",
        "label": "Project feedback",
        "score_fields": ["evidence_project_mean_score"],
        "presence_fields": ["evidence_project_mean_score"],
        "neutral_strengths": set(),
    },
    {
        "source_id": "scaffold_local",
        "label": "Scaffold-local evidence",
        "score_fields": ["scaffold_local_evidence_score", "scaffold_local_mmp_score"],
        "presence_fields": ["scaffold_local_evidence_strength", "scaffold_local_evidence_count", "scaffold_local_mmp_count"],
        "neutral_strengths": {"", "none", "unknown"},
    },
]

SCORE_BINS = [
    (0.0, 39.999, "0-39"),
    (40.0, 59.999, "40-59"),
    (60.0, 79.999, "60-79"),
    (80.0, 100.0, "80-100"),
]


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _json_loads(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _normalized_endpoint(value: str | None) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    return text or "unspecified"


def _normalized_context(value: str | None) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    return text or "unspecified"


def _endpoint_for_observation(observation: dict, payload: dict) -> str:
    return _normalized_endpoint(
        observation.get("endpoint_group")
        or observation.get("endpoint")
        or payload.get("endpoint_gate_endpoint")
        or payload.get("evidence_endpoint_group")
        or payload.get("direction")
    )


def _target_family_for_observation(observation: dict, payload: dict) -> str:
    return _normalized_context(
        payload.get("evidence_target_family_normalized")
        or payload.get("evidence_target_family")
        or (payload.get("target_context") or {}).get("target_family")
        or observation.get("target_family")
    )


def _assay_type_for_observation(observation: dict, payload: dict) -> str:
    return _normalized_context(
        observation.get("assay_type")
        or payload.get("evidence_assay_type")
        or (payload.get("target_context") or {}).get("assay_type")
        or observation.get("assay_name")
    )


def _context_scope(endpoint: str, target_family: str, assay_type: str) -> str:
    if endpoint == "all":
        return "global"
    if target_family != "all" and assay_type != "all":
        return "endpoint_target_family_assay"
    if target_family != "all":
        return "endpoint_target_family"
    if assay_type != "all":
        return "endpoint_assay"
    return "endpoint"


def _calibration_contexts(endpoint: str, target_family: str, assay_type: str) -> list[tuple[str, str, str]]:
    contexts = [("all", "all", "all"), (endpoint, "all", "all")]
    if target_family not in {"", "all", "unspecified"}:
        contexts.append((endpoint, target_family, "all"))
    if assay_type not in {"", "all", "unspecified"}:
        contexts.append((endpoint, "all", assay_type))
    if target_family not in {"", "all", "unspecified"} and assay_type not in {"", "all", "unspecified"}:
        contexts.append((endpoint, target_family, assay_type))
    return list(dict.fromkeys(contexts))


def _outcome_value(row: dict) -> float | None:
    score = _float_or_none(row.get("normalized_score"))
    if score is not None:
        return _clamp(score, 0.0, 100.0) / 100.0
    stop_go = str(row.get("stop_go_decision") or "").strip().lower().replace(" ", "_")
    if stop_go in {"go", "positive"}:
        return 1.0
    if stop_go in {"stop", "negative"}:
        return 0.0
    if stop_go in {"watch", "retest"}:
        return 0.5
    classification = str(row.get("classification") or "").strip().lower().replace(" ", "_")
    if classification in {"active", "pass", "positive", "improved", "go", "hit"}:
        return 1.0
    if classification in {"inactive", "fail", "failed", "negative", "worse", "stop"}:
        return 0.0
    if classification in {"watch", "retest", "repeat", "inconclusive"}:
        return 0.5
    return None


def _outcome_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 0.7:
        return "positive"
    if value <= 0.35:
        return "negative"
    return "watch"


def _bin_label(score: float) -> str:
    for low, high, label in SCORE_BINS:
        if low <= score <= high:
            return label
    return "80-100" if score > 100 else "0-39"


def candidate_evidence_sources(row: dict) -> list[dict]:
    sources = []
    for source_def in SOURCE_DEFINITIONS:
        score = next((_float_or_none(row.get(field)) for field in source_def["score_fields"] if _float_or_none(row.get(field)) is not None), None)
        if score is None:
            continue
        presence_values = [str(row.get(field) or "").strip().lower() for field in source_def["presence_fields"]]
        if source_def["neutral_strengths"] and all(value in source_def["neutral_strengths"] for value in presence_values):
            if abs(score - 50.0) < 0.001:
                continue
        sources.append(
            {
                "source_id": source_def["source_id"],
                "label": source_def["label"],
                "score": _clamp(score, 0.0, 100.0),
            }
        )
    return sources


def _candidate_observation_rows(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params = (project_name, project_name)
        feedback_rows = conn.execute(
            """
            SELECT f.feedback_id AS observation_id, 'feedback' AS observation_type,
                   f.run_id, f.candidate_id, COALESCE(f.project_name, pr.project_name, '') AS project_name,
                   f.endpoint AS endpoint_group, f.assay_name, f.assay_type, f.normalized_score,
                   f.classification, NULL AS stop_go_decision, f.recorded_at,
                   pc.payload_json
            FROM project_feedback f
            LEFT JOIN project_run pr ON pr.run_id=f.run_id
            LEFT JOIN project_candidate pc ON pc.run_id=f.run_id AND pc.candidate_id=f.candidate_id
            WHERE (? IS NULL OR COALESCE(f.project_name, pr.project_name, '')=?)
            """,
            params,
        ).fetchall()
        try:
            event_rows = conn.execute(
                """
                SELECT e.event_id AS observation_id, 'experiment_event' AS observation_type,
                       e.run_id, e.candidate_id, COALESCE(p.project_name, pr.project_name, '') AS project_name,
                       e.endpoint_group, e.assay_name, e.assay_type, e.normalized_score,
                       e.classification, e.stop_go_decision, e.recorded_at,
                       pc.payload_json
                FROM project_experiment_event e
                LEFT JOIN project_experiment_plan p ON p.plan_id=e.plan_id
                LEFT JOIN project_run pr ON pr.run_id=e.run_id
                LEFT JOIN project_candidate pc ON pc.run_id=e.run_id AND pc.candidate_id=e.candidate_id
                WHERE (? IS NULL OR COALESCE(p.project_name, pr.project_name, '')=?)
                """,
                params,
            ).fetchall()
        except sqlite3.Error:
            event_rows = []
    finally:
        conn.close()

    observations = []
    for row in [*feedback_rows, *event_rows]:
        item = dict(row)
        payload = _json_loads(item.pop("payload_json", None))
        if not payload:
            continue
        outcome = _outcome_value(item)
        if outcome is None:
            continue
        observations.append({**item, "payload": payload, "outcome_value": outcome, "outcome_bucket": _outcome_bucket(outcome)})
    return observations


def _aggregate_entries(
    observations: list[dict],
    *,
    min_observations: int = 3,
) -> list[dict]:
    groups: dict[tuple[str, str, str, str], dict] = {}
    bin_groups: dict[tuple[str, str, str, str, str], dict] = {}
    for observation in observations:
        payload = observation["payload"]
        endpoint = _endpoint_for_observation(observation, payload)
        target_family = _target_family_for_observation(observation, payload)
        assay_type = _assay_type_for_observation(observation, payload)
        contexts = _calibration_contexts(endpoint, target_family, assay_type)
        for source in candidate_evidence_sources(payload):
            score = float(source["score"])
            for endpoint_key, family_key, assay_key in contexts:
                key = (endpoint_key, family_key, assay_key, source["source_id"])
                item = groups.setdefault(
                    key,
                    {
                        "endpoint_group": endpoint_key,
                        "target_family": family_key,
                        "assay_type": assay_key,
                        "context_scope": _context_scope(endpoint_key, family_key, assay_key),
                        "evidence_source": source["source_id"],
                        "source_label": source["label"],
                        "observed_count": 0,
                        "positive_count": 0,
                        "negative_count": 0,
                        "watch_count": 0,
                        "score_sum": 0.0,
                        "outcome_sum": 0.0,
                        "example_candidate_ids": [],
                    },
                )
                item["observed_count"] += 1
                item[f"{observation['outcome_bucket']}_count"] += 1
                item["score_sum"] += score
                item["outcome_sum"] += float(observation["outcome_value"])
                if observation.get("candidate_id") and len(item["example_candidate_ids"]) < 8:
                    item["example_candidate_ids"].append(str(observation["candidate_id"]))

                bin_key = (*key, _bin_label(score))
                bin_item = bin_groups.setdefault(
                    bin_key,
                    {
                        "endpoint_group": endpoint_key,
                        "target_family": family_key,
                        "assay_type": assay_key,
                        "context_scope": _context_scope(endpoint_key, family_key, assay_key),
                        "evidence_source": source["source_id"],
                        "score_bin": _bin_label(score),
                        "observed_count": 0,
                        "positive_count": 0,
                        "negative_count": 0,
                        "watch_count": 0,
                        "score_sum": 0.0,
                        "outcome_sum": 0.0,
                    },
                )
                bin_item["observed_count"] += 1
                bin_item[f"{observation['outcome_bucket']}_count"] += 1
                bin_item["score_sum"] += score
                bin_item["outcome_sum"] += float(observation["outcome_value"])

    entries = []
    bins_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for key, item in bin_groups.items():
        observed = int(item["observed_count"])
        item_out = {
            **{name: value for name, value in item.items() if name not in {"score_sum", "outcome_sum"}},
            "mean_evidence_score": round(float(item["score_sum"]) / observed, 4) if observed else None,
            "observed_hit_rate": round(float(item["outcome_sum"]) / observed, 4) if observed else None,
        }
        bins_by_key[(key[0], key[1], key[2], key[3])].append(item_out)

    for key, item in groups.items():
        observed = int(item["observed_count"])
        mean_evidence = float(item.pop("score_sum")) / observed if observed else 50.0
        hit_rate = float(item.pop("outcome_sum")) / observed if observed else 0.5
        expected_hit_rate = _clamp(mean_evidence / 100.0, 0.0, 1.0)
        gap = hit_rate - expected_hit_rate
        enough = observed >= int(min_observations)
        multiplier = _clamp(1.0 + gap * 0.3, 0.75, 1.25) if enough else 1.0
        score_shift = _clamp(gap * 20.0, -12.0, 12.0) if enough else 0.0
        if not enough:
            status = "collect_more_outcomes"
        elif abs(gap) <= 0.08:
            status = "well_calibrated"
        elif gap > 0:
            status = "under_confident"
        else:
            status = "over_confident"
        entries.append(
            {
                **item,
                "mean_evidence_score": round(mean_evidence, 4),
                "observed_hit_rate": round(hit_rate, 4),
                "expected_hit_rate": round(expected_hit_rate, 4),
                "calibration_gap": round(gap, 4),
                "calibration_residual": round(gap, 4),
                "confidence_multiplier": round(multiplier, 4),
                "score_shift": round(score_shift, 4),
                "calibration_status": status,
                "confidence_level": "high" if observed >= 20 else "medium" if observed >= min_observations else "low",
                "calibration_points": sorted(bins_by_key.get(key, []), key=lambda row: row["score_bin"]),
                "example_candidate_ids": ";".join(item.get("example_candidate_ids") or []),
            }
        )
    scope_order = {"global": 0, "endpoint": 1, "endpoint_target_family": 2, "endpoint_assay": 3, "endpoint_target_family_assay": 4}
    entries.sort(
        key=lambda row: (
            scope_order.get(row.get("context_scope"), 9),
            row["endpoint_group"],
            row.get("target_family") or "",
            row.get("assay_type") or "",
            row["evidence_source"],
        )
    )
    return entries


def _residual_quality_summary(entries: list[dict], *, min_residual_observations: int = 6) -> dict:
    residual_entries = [
        item
        for item in entries
        if _float_or_none(item.get("calibration_residual")) is not None
    ]
    groups: dict[tuple[str, str], dict] = {}
    for item in residual_entries:
        key = (str(item.get("context_scope") or "unknown"), str(item.get("evidence_source") or "unknown"))
        residual = abs(float(item.get("calibration_residual") or 0.0))
        bucket = groups.setdefault(
            key,
            {
                "context_scope": key[0],
                "evidence_source": key[1],
                "entry_count": 0,
                "abs_residual_sum": 0.0,
                "actionable_abs_residual_sum": 0.0,
                "max_abs_residual": 0.0,
                "max_actionable_abs_residual": 0.0,
                "actionable_entry_count": 0,
                "thin_sample_entry_count": 0,
                "over_confident_count": 0,
                "under_confident_count": 0,
                "well_calibrated_count": 0,
                "collect_more_outcomes_count": 0,
            },
        )
        observed_count = int(item.get("observed_count") or 0)
        actionable = observed_count >= int(min_residual_observations)
        bucket["entry_count"] += 1
        bucket["abs_residual_sum"] += residual
        bucket["max_abs_residual"] = max(float(bucket["max_abs_residual"]), residual)
        if actionable:
            bucket["actionable_entry_count"] += 1
            bucket["actionable_abs_residual_sum"] += residual
            bucket["max_actionable_abs_residual"] = max(float(bucket["max_actionable_abs_residual"]), residual)
        else:
            bucket["thin_sample_entry_count"] += 1
        status = str(item.get("calibration_status") or "unknown")
        if f"{status}_count" in bucket:
            bucket[f"{status}_count"] += 1
    by_context = []
    for item in groups.values():
        count = int(item["entry_count"])
        actionable_count = int(item["actionable_entry_count"])
        by_context.append(
            {
                **{key: value for key, value in item.items() if key not in {"abs_residual_sum", "actionable_abs_residual_sum"}},
                "mean_abs_residual": round(float(item["abs_residual_sum"]) / count, 4) if count else None,
                "mean_actionable_abs_residual": round(float(item["actionable_abs_residual_sum"]) / actionable_count, 4)
                if actionable_count
                else None,
                "max_abs_residual": round(float(item["max_abs_residual"]), 4),
                "max_actionable_abs_residual": round(float(item["max_actionable_abs_residual"]), 4),
            }
        )
    by_context.sort(
        key=lambda row: (
            -float(row.get("max_actionable_abs_residual") or 0.0),
            -float(row.get("max_abs_residual") or 0.0),
            row["context_scope"],
            row["evidence_source"],
        )
    )
    top_residuals = sorted(
        (
            {
                "context_scope": item.get("context_scope"),
                "endpoint_group": item.get("endpoint_group"),
                "target_family": item.get("target_family"),
                "assay_type": item.get("assay_type"),
                "evidence_source": item.get("evidence_source"),
                "observed_count": item.get("observed_count"),
                "residual_sample_status": "actionable"
                if int(item.get("observed_count") or 0) >= int(min_residual_observations)
                else "thin_sample",
                "residual_actionable": int(item.get("observed_count") or 0) >= int(min_residual_observations),
                "calibration_status": item.get("calibration_status"),
                "confidence_level": item.get("confidence_level"),
                "calibration_residual": item.get("calibration_residual"),
                "abs_residual": round(abs(float(item.get("calibration_residual") or 0.0)), 4),
                "example_candidate_ids": item.get("example_candidate_ids"),
            }
            for item in residual_entries
        ),
        key=lambda row: (-float(row["abs_residual"]), str(row.get("endpoint_group") or ""), str(row.get("evidence_source") or "")),
    )[:20]
    actionable_residual_count = sum(1 for item in residual_entries if int(item.get("observed_count") or 0) >= int(min_residual_observations))
    return {
        "min_residual_observations": int(min_residual_observations),
        "residual_entry_count": len(residual_entries),
        "actionable_residual_count": actionable_residual_count,
        "thin_sample_residual_count": len(residual_entries) - actionable_residual_count,
        "max_actionable_abs_residual": round(
            max(
                (
                    abs(float(item.get("calibration_residual") or 0.0))
                    for item in residual_entries
                    if int(item.get("observed_count") or 0) >= int(min_residual_observations)
                ),
                default=0.0,
            ),
            4,
        ),
        "calibration_status_counts": dict(Counter(str(item.get("calibration_status") or "unknown") for item in entries).most_common()),
        "confidence_level_counts": dict(Counter(str(item.get("confidence_level") or "unknown") for item in entries).most_common()),
        "by_context_and_source": by_context,
        "top_residuals": top_residuals,
    }


def _residual_trend_key(row: dict) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("context_scope") or "unknown"),
        _normalized_endpoint(row.get("endpoint_group")),
        _normalized_context(row.get("target_family") or "all"),
        _normalized_context(row.get("assay_type") or "all"),
        str(row.get("evidence_source") or "unknown"),
    )


def _residual_trend_row(row: dict) -> dict:
    residual = _float_or_none(row.get("calibration_residual"))
    return {
        "context_scope": row.get("context_scope"),
        "endpoint_group": row.get("endpoint_group"),
        "target_family": row.get("target_family"),
        "assay_type": row.get("assay_type"),
        "evidence_source": row.get("evidence_source"),
        "observed_count": int(row.get("observed_count") or 0),
        "calibration_status": row.get("calibration_status"),
        "calibration_residual": round(float(residual), 4) if residual is not None else None,
        "abs_residual": round(abs(float(residual)), 4) if residual is not None else None,
        "residual_sample_status": row.get("residual_sample_status"),
        "residual_actionable": row.get("residual_actionable"),
    }


def evidence_residual_trend_delta(previous_report: dict | None, current_report: dict, *, limit: int = 20) -> dict:
    if not previous_report:
        return {"status": "no_previous_report", "changed_count": 0, "new_count": 0, "resolved_count": 0}
    previous_lookup = {
        _residual_trend_key(row): row
        for row in previous_report.get("entries") or []
        if _float_or_none(row.get("calibration_residual")) is not None
    }
    current_lookup = {
        _residual_trend_key(row): row
        for row in current_report.get("entries") or []
        if _float_or_none(row.get("calibration_residual")) is not None
    }
    changed = []
    for key, current in current_lookup.items():
        previous = previous_lookup.get(key)
        if previous is None:
            continue
        previous_residual = float(previous.get("calibration_residual") or 0.0)
        current_residual = float(current.get("calibration_residual") or 0.0)
        residual_delta = current_residual - previous_residual
        count_delta = int(current.get("observed_count") or 0) - int(previous.get("observed_count") or 0)
        status_changed = str(current.get("calibration_status") or "") != str(previous.get("calibration_status") or "")
        if abs(residual_delta) < 0.0001 and count_delta == 0 and not status_changed:
            continue
        changed.append(
            {
                **_residual_trend_row(current),
                "previous_residual": round(previous_residual, 4),
                "residual_delta": round(residual_delta, 4),
                "observed_count_delta": count_delta,
                "previous_calibration_status": previous.get("calibration_status"),
            }
        )
    new_rows = [_residual_trend_row(row) for key, row in current_lookup.items() if key not in previous_lookup]
    resolved_rows = [_residual_trend_row(row) for key, row in previous_lookup.items() if key not in current_lookup]
    changed.sort(key=lambda row: (-abs(float(row.get("residual_delta") or 0.0)), -float(row.get("abs_residual") or 0.0)))
    new_rows.sort(key=lambda row: -float(row.get("abs_residual") or 0.0))
    resolved_rows.sort(key=lambda row: -float(row.get("abs_residual") or 0.0))
    return {
        "status": "compared",
        "previous_created_at": previous_report.get("created_at"),
        "current_created_at": current_report.get("created_at"),
        "changed_count": len(changed),
        "new_count": len(new_rows),
        "resolved_count": len(resolved_rows),
        "top_changed_residuals": changed[:limit],
        "new_top_residuals": new_rows[:limit],
        "resolved_top_residuals": resolved_rows[:limit],
    }


def _residual_chart_key(row: dict) -> tuple[str, str, str, str, str]:
    return _residual_trend_key(row)


def _residual_chart_action(row: dict, *, trend_status: str = "") -> str:
    sample_status = str(row.get("residual_sample_status") or "").lower()
    calibration_status = str(row.get("calibration_status") or "unknown").lower()
    abs_residual = _float_or_none(row.get("abs_residual"))
    if abs_residual is None:
        residual = _float_or_none(row.get("calibration_residual"))
        abs_residual = abs(float(residual)) if residual is not None else 0.0
    if trend_status == "resolved":
        return "confirm_resolved_context"
    if sample_status == "thin_sample":
        return "collect_targeted_outcomes"
    if calibration_status == "over_confident":
        return "downweight_or_collect_negative_controls"
    if calibration_status == "under_confident":
        return "review_for_cautious_weight_boost"
    if abs_residual >= 0.2:
        return "monitor_high_residual_context"
    return "monitor"


def build_evidence_residual_trend_chart(report: dict) -> list[dict]:
    """Flatten residual calibration entries into rows suitable for charts and dashboards."""
    delta = report.get("residual_trend_delta") or {}
    changed_lookup = {
        _residual_chart_key(row): row
        for row in delta.get("top_changed_residuals") or []
    }
    new_lookup = {
        _residual_chart_key(row): row
        for row in delta.get("new_top_residuals") or []
    }
    rows = []
    for entry in report.get("entries") or []:
        residual = _float_or_none(entry.get("calibration_residual"))
        if residual is None:
            continue
        base = _residual_trend_row(entry)
        key = _residual_chart_key(entry)
        changed = changed_lookup.get(key)
        new = new_lookup.get(key)
        previous_residual = _float_or_none((changed or {}).get("previous_residual"))
        residual_delta = _float_or_none((changed or {}).get("residual_delta"))
        if new:
            trend_status = "new"
            trend_direction = "new_context"
        elif changed:
            trend_status = "changed"
            previous_abs = abs(float(previous_residual or 0.0))
            current_abs = abs(float(base.get("calibration_residual") or 0.0))
            if current_abs > previous_abs + 0.0001:
                trend_direction = "residual_worsened"
            elif current_abs < previous_abs - 0.0001:
                trend_direction = "residual_improved"
            else:
                trend_direction = "status_or_sample_changed"
        else:
            trend_status = "unchanged"
            trend_direction = "flat"
        row = {
            **base,
            "chart_id": _residual_task_id(base),
            "created_at": report.get("created_at"),
            "trend_status": trend_status,
            "trend_direction": trend_direction,
            "previous_residual": round(float(previous_residual), 4) if previous_residual is not None else None,
            "residual_delta": round(float(residual_delta), 4) if residual_delta is not None else None,
            "observed_count_delta": (changed or {}).get("observed_count_delta"),
        }
        row["recommended_action"] = _residual_chart_action(row, trend_status=trend_status)
        rows.append(row)

    for resolved in delta.get("resolved_top_residuals") or []:
        base = _residual_trend_row(resolved)
        row = {
            **base,
            "chart_id": _residual_task_id(base),
            "created_at": report.get("created_at"),
            "trend_status": "resolved",
            "trend_direction": "resolved_context",
            "previous_residual": base.get("calibration_residual"),
            "residual_delta": None,
            "observed_count_delta": None,
            "recommended_action": _residual_chart_action(base, trend_status="resolved"),
        }
        rows.append(row)

    trend_rank = {"changed": 0, "new": 1, "resolved": 2, "unchanged": 3}
    rows.sort(
        key=lambda item: (
            trend_rank.get(str(item.get("trend_status")), 9),
            -float(item.get("abs_residual") or 0.0),
            str(item.get("endpoint_group") or ""),
            str(item.get("evidence_source") or ""),
        )
    )
    return rows


def write_evidence_residual_trend_chart(
    rows: list[dict],
    *,
    json_path: str | Path,
    csv_path: str | Path | None = None,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "chart_id",
        "context_scope",
        "endpoint_group",
        "target_family",
        "assay_type",
        "evidence_source",
        "observed_count",
        "calibration_status",
        "calibration_residual",
        "abs_residual",
        "residual_sample_status",
        "trend_status",
        "trend_direction",
        "previous_residual",
        "residual_delta",
        "recommended_action",
    ]
    with csv_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def build_endpoint_family_residual_model(report: dict) -> dict:
    """Summarize residual calibration by source, endpoint, and target family."""
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for entry in report.get("entries") or []:
        residual = _float_or_none(entry.get("calibration_residual"))
        if residual is None:
            continue
        endpoint = _normalized_endpoint(entry.get("endpoint_group"))
        family = _normalized_context(entry.get("target_family") or "all")
        if endpoint == "all" or family == "all":
            continue
        source = str(entry.get("evidence_source") or "unknown")
        grouped[(source, endpoint, family)].append(entry)

    rows = []
    for (source, endpoint, family), entries in sorted(grouped.items()):
        residuals = [float(entry.get("calibration_residual") or 0.0) for entry in entries]
        abs_residuals = [abs(value) for value in residuals]
        observed = sum(int(entry.get("observed_count") or 0) for entry in entries)
        mean_residual = sum(residuals) / len(residuals)
        mean_abs = sum(abs_residuals) / len(abs_residuals)
        if len(residuals) > 1:
            variance = sum((value - mean_residual) ** 2 for value in residuals) / (len(residuals) - 1)
            interval_half_width = 1.96 * math.sqrt(variance) / math.sqrt(len(residuals))
        else:
            interval_half_width = 0.0
        sample_floor = min(0.5, 0.5 / math.sqrt(max(observed, 1)))
        if len(residuals) < 2:
            sample_floor = max(sample_floor, 0.18)
        interval_half_width = max(interval_half_width, sample_floor)
        ci_low = _clamp(mean_residual - interval_half_width, -1.0, 1.0)
        ci_high = _clamp(mean_residual + interval_half_width, -1.0, 1.0)
        score_shift = _clamp(mean_residual * 20.0, -10.0, 10.0)
        score_shift_low = _clamp(ci_low * 20.0, -10.0, 10.0)
        score_shift_high = _clamp(ci_high * 20.0, -10.0, 10.0)
        if observed >= 30 and len(entries) >= 3:
            holdout_status = "holdout_ready"
        elif observed >= 12 and len(entries) >= 2:
            holdout_status = "limited_holdout_ready"
        elif observed < 8 or len(entries) < 2:
            holdout_status = "thin_holdout"
        else:
            holdout_status = "monitor_until_more_outcomes"
        interval_width = ci_high - ci_low
        if holdout_status == "holdout_ready" and interval_width <= 0.2:
            adjustment_confidence = "high"
        elif holdout_status in {"holdout_ready", "limited_holdout_ready"} and interval_width <= 0.35:
            adjustment_confidence = "medium"
        else:
            adjustment_confidence = "low"
        status_counts = Counter(str(entry.get("calibration_status") or "unknown") for entry in entries)
        thin_count = sum(1 for entry in entries if entry.get("residual_sample_status") == "thin_sample")
        if thin_count:
            action = "collect_more_endpoint_family_outcomes"
        elif mean_residual <= -0.12:
            action = "downweight_source_for_endpoint_family"
        elif mean_residual >= 0.12:
            action = "consider_cautious_source_boost"
        elif mean_abs >= 0.08:
            action = "monitor_endpoint_family_residual"
        else:
            action = "keep_current_weight"
        rows.append(
            {
                "evidence_source": source,
                "endpoint_group": endpoint,
                "target_family": family,
                "entry_count": len(entries),
                "observed_count": observed,
                "mean_residual": round(mean_residual, 4),
                "mean_residual_ci_low": round(ci_low, 4),
                "mean_residual_ci_high": round(ci_high, 4),
                "mean_residual_ci_width": round(interval_width, 4),
                "mean_abs_residual": round(mean_abs, 4),
                "max_abs_residual": round(max(abs_residuals), 4),
                "over_confident_count": int(status_counts.get("over_confident", 0)),
                "under_confident_count": int(status_counts.get("under_confident", 0)),
                "well_calibrated_count": int(status_counts.get("well_calibrated", 0)),
                "thin_sample_entry_count": thin_count,
                "holdout_check_status": holdout_status,
                "holdout_basis": f"observed_count={observed}; entry_count={len(entries)}",
                "adjustment_confidence": adjustment_confidence,
                "recommended_weight_action": action,
                "suggested_score_shift": round(score_shift, 4),
                "suggested_score_shift_ci_low": round(score_shift_low, 4),
                "suggested_score_shift_ci_high": round(score_shift_high, 4),
                "score_profile_adjustment": {
                    "score_shift": round(score_shift, 4),
                    "score_shift_ci_low": round(score_shift_low, 4),
                    "score_shift_ci_high": round(score_shift_high, 4),
                    "weight_multiplier": round(_clamp(1.0 + mean_residual * 0.35, 0.75, 1.25), 4),
                    "confidence": adjustment_confidence,
                    "holdout_check_status": holdout_status,
                },
            }
        )
    rows.sort(
        key=lambda row: (
            {"downweight_source_for_endpoint_family": 0, "consider_cautious_source_boost": 1, "collect_more_endpoint_family_outcomes": 2}.get(
                row["recommended_weight_action"], 3
            ),
            -float(row.get("max_abs_residual") or 0.0),
            str(row.get("evidence_source") or ""),
        )
    )
    action_counts = Counter(row["recommended_weight_action"] for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_report_created_at": report.get("created_at"),
        "project_name": report.get("project_name"),
        "model_scope": "endpoint_family",
        "row_count": len(rows),
        "action_counts": dict(action_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use downweight rows as candidates for endpoint-family-specific evidence penalties after review.",
            "Treat boost rows as cautious suggestions until additional outcomes confirm the residual direction.",
            "Route collect-more rows into the next assay batch when they overlap active design priorities.",
            "Only promote endpoint-family score-profile changes after medium/high confidence rows pass reviewer sign-off.",
        ],
    }


def write_endpoint_family_residual_model(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _residual_task_id(row: dict) -> str:
    key = "|".join(
        [
            str(row.get("context_scope") or ""),
            str(row.get("endpoint_group") or ""),
            str(row.get("target_family") or ""),
            str(row.get("assay_type") or ""),
            str(row.get("evidence_source") or ""),
        ]
    )
    import hashlib

    return f"EVTASK-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:10].upper()}"


def build_evidence_residual_data_tasks(
    report: dict,
    *,
    max_tasks: int = 20,
    min_abs_residual: float = 0.12,
) -> list[dict]:
    """Convert residual calibration gaps into data-collection tasks."""
    min_observations = int(report.get("min_residual_observations") or 6)
    rows = []
    scope_multiplier = {
        "global": 0.65,
        "endpoint": 1.0,
        "endpoint_assay": 1.15,
        "endpoint_target_family": 1.25,
        "endpoint_target_family_assay": 1.45,
    }
    source_multiplier = {
        "project_feedback": 1.35,
        "scaffold_local": 1.2,
        "chembl_activity": 1.1,
        "public_mmp": 1.0,
    }
    for row in (report.get("residual_quality_summary") or {}).get("top_residuals") or []:
        abs_residual = _float_or_none(row.get("abs_residual")) or 0.0
        observed = int(row.get("observed_count") or 0)
        thin_sample = observed < min_observations
        if abs_residual < float(min_abs_residual) and not thin_sample:
            continue
        calibration_status = str(row.get("calibration_status") or "unknown")
        if thin_sample:
            action = "collect_targeted_outcomes"
            priority = "high" if abs_residual >= 0.2 else "medium"
        elif calibration_status == "over_confident":
            action = "collect_negative_controls_or_downweight_source"
            priority = "high" if abs_residual >= 0.25 else "medium"
        elif calibration_status == "under_confident":
            action = "collect_positive_confirmations_or_raise_source_weight"
            priority = "high" if abs_residual >= 0.25 else "medium"
        else:
            action = "monitor_residual_context"
            priority = "medium" if abs_residual >= 0.2 else "low"
        sample_gap = max(0.0, float(min_observations - observed) / float(max(min_observations, 1)))
        observation_uncertainty = 1.0 / ((observed + 1) ** 0.5)
        context_weight = scope_multiplier.get(str(row.get("context_scope") or ""), 0.9)
        evidence_weight = source_multiplier.get(str(row.get("evidence_source") or ""), 1.0)
        expected_information_gain = _clamp(
            ((abs_residual * 0.7) + (sample_gap * 0.2) + (observation_uncertainty * 0.1)) * context_weight * evidence_weight,
            0.0,
            1.5,
        )
        suggested_outcomes = max(1, max(0, min_observations - observed))
        if expected_information_gain >= 0.5 and not thin_sample:
            suggested_outcomes = max(suggested_outcomes, 2)
        rows.append(
            {
                "task_id": _residual_task_id(row),
                "priority": priority,
                "recommended_action": action,
                "context_scope": row.get("context_scope"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "assay_type": row.get("assay_type"),
                "evidence_source": row.get("evidence_source"),
                "calibration_status": calibration_status,
                "observed_count": observed,
                "additional_outcome_target": max(0, min_observations - observed),
                "expected_information_gain": round(expected_information_gain, 4),
                "suggested_next_outcome_count": suggested_outcomes,
                "information_gain_basis": (
                    f"abs_residual={abs_residual:.4f}; sample_gap={sample_gap:.4f}; "
                    f"observation_uncertainty={observation_uncertainty:.4f}; "
                    f"context_weight={context_weight:.2f}; source_weight={evidence_weight:.2f}"
                ),
                "abs_residual": round(abs_residual, 4),
                "calibration_residual": row.get("calibration_residual"),
                "residual_sample_status": "thin_sample" if thin_sample else "actionable",
                "example_candidate_ids": row.get("example_candidate_ids"),
            }
        )
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    rows.sort(
        key=lambda item: (
            -float(item.get("expected_information_gain") or 0.0),
            priority_rank.get(item["priority"], 9),
            -float(item.get("abs_residual") or 0.0),
            item["task_id"],
        )
    )
    return rows[: int(max_tasks)]


def load_evidence_residual_task_registry(path: str | Path = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH) -> dict:
    registry_path = Path(path)
    if not registry_path.exists():
        return {"task_count": 0, "tasks": []}
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    if isinstance(data, list):
        data = {"tasks": data}
    data.setdefault("tasks", [])
    data.setdefault("task_count", len(data.get("tasks") or []))
    return data


def sync_evidence_residual_task_registry(
    tasks: list[dict],
    *,
    existing_registry: dict | None = None,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    """Merge current residual tasks into a status-preserving task registry."""
    now = datetime.now(timezone.utc).isoformat()
    registry = existing_registry or {"tasks": []}
    existing = {str(item.get("task_id")): dict(item) for item in registry.get("tasks") or [] if item.get("task_id")}
    current_ids = {str(item.get("task_id")) for item in tasks if item.get("task_id")}
    out = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        previous = existing.get(task_id, {})
        status = str(previous.get("status") or "open")
        if status not in EVIDENCE_RESIDUAL_TASK_STATUSES:
            status = "open"
        history = list(previous.get("status_history") or [])
        if not previous:
            history.append({"status": status, "created_at": now, "reviewer": reviewer, "note": note or "Task opened from residual calibration."})
        elif any(previous.get(key) != task.get(key) for key in ["priority", "recommended_action", "abs_residual", "observed_count"]):
            history.append({"status": status, "created_at": now, "reviewer": reviewer, "note": note or "Residual task signal refreshed."})
        out.append(
            {
                **previous,
                **task,
                "status": status,
                "created_at": previous.get("created_at") or now,
                "updated_at": now if previous else previous.get("updated_at") or now,
                "last_seen_at": now,
                "reviewer": previous.get("reviewer") or reviewer,
                "status_note": previous.get("status_note") or "",
                "lifecycle_state": "active",
                "status_history": history[-20:],
            }
        )

    for task_id, previous in existing.items():
        if task_id in current_ids:
            continue
        if task_id.startswith("RINGTASK-") or previous.get("task_source") == "ring_outcome_overlay":
            out.append(previous)
            continue
        status = str(previous.get("status") or "open")
        history = list(previous.get("status_history") or [])
        if status in {"open", "planned", "outcomes_imported"}:
            status = "resolved_by_calibration"
            history.append({"status": status, "created_at": now, "reviewer": reviewer, "note": note or "Task no longer appears in current residual report."})
        out.append(
            {
                **previous,
                "status": status,
                "updated_at": now,
                "lifecycle_state": "not_in_current_report",
                "status_history": history[-20:],
            }
        )

    status_counts = Counter(str(item.get("status") or "unknown") for item in out)
    priority_counts = Counter(str(item.get("priority") or "unknown") for item in out if item.get("lifecycle_state") == "active")
    return {
        "created_at": now,
        "task_count": len(out),
        "active_task_count": sum(1 for item in out if item.get("lifecycle_state") == "active"),
        "status_counts": dict(status_counts.most_common()),
        "active_priority_counts": dict(priority_counts.most_common()),
        "tasks": sorted(
            out,
            key=lambda item: (
                item.get("lifecycle_state") != "active",
                {"open": 0, "planned": 1, "outcomes_imported": 2, "closed": 3, "resolved_by_calibration": 4, "retired": 5}.get(str(item.get("status")), 9),
                {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority")), 9),
                -float(item.get("abs_residual") or 0.0),
                str(item.get("task_id") or ""),
            ),
        ),
    }


def _write_residual_task_csv(tasks: list[dict], path: str | Path) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    preferred = [
        "task_id",
        "status",
        "lifecycle_state",
        "priority",
        "recommended_action",
        "endpoint_group",
        "target_family",
        "assay_type",
        "evidence_source",
        "observed_count",
        "additional_outcome_target",
        "abs_residual",
        "calibration_status",
        "residual_sample_status",
        "created_at",
        "updated_at",
        "last_seen_at",
        "reviewer",
        "status_note",
    ]
    extras = sorted({key for row in tasks for key in row if key not in preferred and key != "status_history"})
    fieldnames = preferred + extras
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in tasks:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_evidence_residual_task_registry(
    registry: dict,
    path: str | Path = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    *,
    csv_path: str | Path | None = None,
) -> None:
    registry_path = Path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is not None:
        _write_residual_task_csv(registry.get("tasks") or [], csv_path)


def update_evidence_residual_task_status(
    task_id: str,
    *,
    status: str,
    registry_path: str | Path = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    if status not in EVIDENCE_RESIDUAL_TASK_STATUSES:
        raise ValueError(f"Unsupported evidence residual task status: {status}")
    registry = load_evidence_residual_task_registry(registry_path)
    now = datetime.now(timezone.utc).isoformat()
    updated = False
    tasks = []
    for task in registry.get("tasks") or []:
        if str(task.get("task_id")) != str(task_id):
            tasks.append(task)
            continue
        history = list(task.get("status_history") or [])
        history.append({"status": status, "created_at": now, "reviewer": reviewer, "note": note or ""})
        tasks.append(
            {
                **task,
                "status": status,
                "updated_at": now,
                "reviewer": reviewer or task.get("reviewer"),
                "status_note": note or task.get("status_note") or "",
                "status_history": history[-20:],
            }
        )
        updated = True
    if not updated:
        raise ValueError(f"Evidence residual task not found: {task_id}")
    registry = {
        **registry,
        "created_at": registry.get("created_at") or now,
        "updated_at": now,
        "task_count": len(tasks),
        "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in tasks).most_common()),
        "tasks": tasks,
    }
    write_evidence_residual_task_registry(registry, registry_path)
    return registry


def _residual_task_rows(source: dict | list[dict]) -> list[dict]:
    rows = source.get("tasks") if isinstance(source, dict) else source
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def residual_tasks_to_experiment_plan(
    tasks_or_registry: dict | list[dict],
    *,
    project_name: str | None = None,
    owner: str = "",
    batch_size: int = 24,
    created_at: str | None = None,
) -> list[dict]:
    """Convert residual calibration tasks into experiment-plan rows."""
    created = created_at or datetime.now(timezone.utc).isoformat()
    rows = []
    allowed_statuses = {"open", "planned"}
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    tasks = [
        task
        for task in _residual_task_rows(tasks_or_registry)
        if str(task.get("status") or "open") in allowed_statuses and str(task.get("lifecycle_state") or "active") == "active"
    ]
    tasks.sort(
        key=lambda item: (
            priority_rank.get(str(item.get("priority") or "low"), 9),
            -float(item.get("expected_information_gain") or 0.0),
            -float(item.get("abs_residual") or 0.0),
            str(item.get("task_id") or ""),
        )
    )
    for index, task in enumerate(tasks[: int(batch_size)], start=1):
        task_id = str(task.get("task_id") or f"EVTASK-{index:03d}")
        is_ring_task = task_id.startswith("RINGTASK-") or task.get("task_source") == "ring_outcome_overlay"
        endpoint = _normalized_endpoint(task.get("endpoint_group"))
        assay_type = _normalized_context(task.get("assay_type"))
        planned_assay = "" if assay_type in {"all", "unspecified"} else assay_type
        priority_score = round(float(task.get("abs_residual") or 0.0) * 100.0, 4)
        if is_ring_task:
            priority_score = round(max(priority_score, float(task.get("expected_information_gain") or 0.0) * 100.0), 4)
        replacement_label = ""
        if is_ring_task:
            replacement_label = "|".join(
                part
                for part in [
                    str(task.get("replacement_class") or "").strip(),
                    str(task.get("ring_diversity_bucket") or "").strip(),
                    str(task.get("ring_novelty_bucket") or "").strip(),
                ]
                if part
            )
        rationale = (
            f"{task.get('recommended_action')}; source={task.get('evidence_source')}; "
            f"context={task.get('context_scope')}; residual={task.get('calibration_residual')}"
        )
        notes = f"Residual task {task_id}; target_family={task.get('target_family')}; additional_outcomes={task.get('additional_outcome_target')}"
        if is_ring_task:
            rationale = (
                f"{task.get('recommended_action')}; ring_context={task.get('source_context_id')}; "
                f"learning_action={task.get('learning_action')}; hit_rate={task.get('hit_rate')}; "
                f"proposed_adjustment={task.get('proposed_score_adjustment')}"
            )
            notes = (
                f"Ring outcome task {task_id}; context={task.get('source_context_id')}; "
                f"additional_outcomes={task.get('additional_outcome_target')}; gate_reasons={task.get('gate_reasons')}"
            )
        rows.append(
            {
                "plan_id": f"EPL-RES-{task_id}"[:96],
                "plan_rank": index,
                "plan_role": "ring_outcome_residual_task" if is_ring_task else "evidence_residual_task",
                "project_name": project_name or task.get("project_name") or "evidence_residual",
                "run_id": "",
                "candidate_id": "",
                "endpoint_group": endpoint,
                "site_type": "",
                "direction": "collect_ring_outcome_evidence" if is_ring_task else "calibrate_evidence_confidence",
                "enumeration_type": task.get("enumeration_type") if is_ring_task else "",
                "replacement_label": replacement_label,
                "candidate_score": "",
                "priority_score": priority_score,
                "rationale": rationale,
                "created_at": created,
                "owner": owner,
                "planned_assay": planned_assay,
                "status": "planned",
                "notes": notes,
                "result_value": "",
                "result_unit": "",
                "result_relation": "",
                "classification": "",
                "normalized_score": "",
                "replicate_count": "",
                "replicate_cv": "",
                "assay_confidence": "",
                "assay_confidence_score": "",
                "stop_go_decision": "",
                "retest_reason": "",
                "result_recorded_at": "",
                "residual_task_id": task_id,
                "residual_task_priority": task.get("priority"),
                "residual_task_action": task.get("recommended_action"),
                "target_family": task.get("target_family"),
                "evidence_source": task.get("evidence_source"),
                "ring_outcome_context_id": task.get("source_context_id") if is_ring_task else "",
                "ring_novelty_bucket": task.get("ring_novelty_bucket") if is_ring_task else "",
                "ring_diversity_bucket": task.get("ring_diversity_bucket") if is_ring_task else "",
                "ring_learning_action": task.get("learning_action") if is_ring_task else "",
            }
        )
    return rows


def update_residual_tasks_from_experiment_plan(
    plan_rows: list[dict],
    *,
    registry_path: str | Path = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    registry = load_evidence_residual_task_registry(registry_path)
    now = datetime.now(timezone.utc).isoformat()
    task_updates = {str(row.get("residual_task_id") or ""): row for row in plan_rows if row.get("residual_task_id")}
    updated_count = 0
    tasks = []
    for task in registry.get("tasks") or []:
        task_id = str(task.get("task_id") or "")
        plan_row = task_updates.get(task_id)
        if not plan_row:
            tasks.append(task)
            continue
        status = "planned" if str(task.get("status") or "open") == "open" else str(task.get("status") or "planned")
        history = list(task.get("status_history") or [])
        history.append(
            {
                "status": status,
                "created_at": now,
                "reviewer": reviewer,
                "note": note or f"Linked to experiment plan {plan_row.get('plan_id')}.",
            }
        )
        linked_plan_ids = list(dict.fromkeys([*(task.get("linked_plan_ids") or []), str(plan_row.get("plan_id") or "")]))
        tasks.append(
            {
                **task,
                "status": status,
                "updated_at": now,
                "reviewer": reviewer or task.get("reviewer"),
                "status_note": note or task.get("status_note") or "",
                "linked_plan_ids": [item for item in linked_plan_ids if item],
                "status_history": history[-20:],
            }
        )
        updated_count += 1
    registry = {
        **registry,
        "updated_at": now,
        "task_count": len(tasks),
        "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in tasks).most_common()),
        "tasks": tasks,
        "last_plan_sync": {"updated_task_count": updated_count, "created_at": now},
    }
    write_evidence_residual_task_registry(registry, registry_path)
    return registry


def update_residual_tasks_from_experiment_results(
    result_rows: list[dict],
    *,
    registry_path: str | Path = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    registry = load_evidence_residual_task_registry(registry_path)
    now = datetime.now(timezone.utc).isoformat()
    result_updates = {str(row.get("residual_task_id") or ""): row for row in result_rows if row.get("residual_task_id")}
    updated_count = 0
    closed_count = 0
    skipped_blank_count = 0
    tasks = []
    for task in registry.get("tasks") or []:
        task_id = str(task.get("task_id") or "")
        result = result_updates.get(task_id)
        if not result:
            tasks.append(task)
            continue
        raw_status = str(result.get("status") or result.get("result_status") or "").strip().lower().replace(" ", "_")
        if raw_status not in {"completed", "failed", "retest"}:
            tasks.append(task)
            continue
        payload_fields = [
            field
            for field in ["value", "result_value", "normalized_score", "classification", "stop_go_decision"]
            if str(result.get(field) or "").strip()
        ]
        if raw_status == "completed" and not payload_fields:
            skipped_blank_count += 1
            tasks.append(task)
            continue
        close_requested = str(result.get("close_residual_task") or result.get("residual_task_status") or "").strip().lower() in {"true", "1", "yes", "closed", "close"}
        status = "closed" if close_requested and raw_status == "completed" else "outcomes_imported"
        if status == "closed":
            closed_count += 1
        history = list(task.get("status_history") or [])
        history.append(
            {
                "status": status,
                "created_at": now,
                "reviewer": reviewer,
                "note": note
                or f"Experiment result imported from plan {result.get('plan_id')}; result_status={raw_status}; normalized_score={result.get('normalized_score')}.",
            }
        )
        linked_result_ids = list(dict.fromkeys([*(task.get("linked_result_plan_ids") or []), str(result.get("plan_id") or "")]))
        tasks.append(
            {
                **task,
                "status": status,
                "updated_at": now,
                "reviewer": reviewer or task.get("reviewer"),
                "status_note": note or task.get("status_note") or "",
                "last_result_status": raw_status,
                "last_result_normalized_score": result.get("normalized_score"),
                "last_result_classification": result.get("classification"),
                "last_result_payload_fields": payload_fields,
                "last_result_recorded_at": result.get("result_recorded_at") or result.get("recorded_at") or now,
                "linked_result_plan_ids": [item for item in linked_result_ids if item],
                "status_history": history[-20:],
            }
        )
        updated_count += 1
    registry = {
        **registry,
        "updated_at": now,
        "task_count": len(tasks),
        "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in tasks).most_common()),
        "tasks": tasks,
        "last_result_sync": {
            "updated_task_count": updated_count,
            "closed_task_count": closed_count,
            "skipped_blank_result_count": skipped_blank_count,
            "created_at": now,
        },
    }
    write_evidence_residual_task_registry(registry, registry_path)
    return registry


def repair_blank_residual_outcome_imports(
    *,
    registry_path: str | Path = DEFAULT_EVIDENCE_RESIDUAL_TASK_REGISTRY_PATH,
    reviewer: str | None = None,
    note: str | None = None,
) -> dict:
    """Undo residual task outcome statuses that were created without measured payload."""
    registry = load_evidence_residual_task_registry(registry_path)
    now = datetime.now(timezone.utc).isoformat()
    repaired_count = 0
    tasks = []
    for task in registry.get("tasks") or []:
        status = str(task.get("status") or "")
        payload_fields = [field for field in task.get("last_result_payload_fields") or [] if str(field or "").strip()]
        has_payload = bool(
            payload_fields
            or str(task.get("last_result_normalized_score") or "").strip()
            or str(task.get("last_result_classification") or "").strip()
        )
        if status not in {"outcomes_imported", "closed"} or has_payload:
            tasks.append(task)
            continue
        restored = "planned" if task.get("linked_plan_ids") else "open"
        history = list(task.get("status_history") or [])
        history.append(
            {
                "status": restored,
                "created_at": now,
                "reviewer": reviewer or "",
                "note": note or "Reverted blank residual outcome import; awaiting measured result payload.",
            }
        )
        tasks.append(
            {
                **task,
                "status": restored,
                "updated_at": now,
                "reviewer": reviewer or task.get("reviewer"),
                "status_note": note or task.get("status_note") or "",
                "last_result_status": "",
                "last_result_normalized_score": "",
                "last_result_classification": "",
                "last_result_payload_fields": [],
                "status_history": history[-20:],
            }
        )
        repaired_count += 1
    registry = {
        **registry,
        "updated_at": now,
        "task_count": len(tasks),
        "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in tasks).most_common()),
        "tasks": tasks,
        "last_blank_outcome_repair": {"repaired_count": repaired_count, "created_at": now},
    }
    write_evidence_residual_task_registry(registry, registry_path)
    return registry


def build_evidence_confidence_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    min_observations: int = 3,
    min_residual_observations: int = 6,
    previous_report: dict | None = None,
) -> dict:
    observations = _candidate_observation_rows(db_path=db_path, project_name=project_name)
    entries = _aggregate_entries(observations, min_observations=min_observations)
    for entry in entries:
        if _float_or_none(entry.get("calibration_residual")) is None:
            continue
        observed_count = int(entry.get("observed_count") or 0)
        entry["residual_sample_status"] = "actionable" if observed_count >= int(min_residual_observations) else "thin_sample"
        entry["residual_actionable"] = observed_count >= int(min_residual_observations)
    endpoint_counts = Counter(_endpoint_for_observation(row, row["payload"]) for row in observations)
    target_family_counts = Counter(_target_family_for_observation(row, row["payload"]) for row in observations)
    assay_type_counts = Counter(_assay_type_for_observation(row, row["payload"]) for row in observations)
    source_counts = Counter()
    for observation in observations:
        for source in candidate_evidence_sources(observation["payload"]):
            source_counts[source["source_id"]] += 1
    residual_summary = _residual_quality_summary(entries, min_residual_observations=min_residual_observations)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "min_observations": int(min_observations),
        "min_residual_observations": int(min_residual_observations),
        "observation_count": len(observations),
        "endpoint_counts": dict(endpoint_counts.most_common()),
        "target_family_counts": dict(target_family_counts.most_common()),
        "assay_type_counts": dict(assay_type_counts.most_common()),
        "source_counts": dict(source_counts.most_common()),
        "entry_count": len(entries),
        "residual_quality_summary": residual_summary,
        "residual_data_tasks": [],
        "entries": entries,
        "recommended_next_actions": [
            "Collect more measured outcomes for source/endpoint pairs marked collect_more_outcomes.",
            f"Treat residual entries with fewer than {int(min_residual_observations)} observations as thin-sample signals until more outcomes arrive.",
            "Review over_confident evidence sources before increasing their score weight.",
            "Use under_confident sources as candidates for cautious score boosts after medchem review.",
            "Prioritize target-family and assay-type contexts with the largest absolute residuals for calibration data collection.",
        ],
    }
    report["residual_data_tasks"] = build_evidence_residual_data_tasks(report)
    report["residual_trend_delta"] = evidence_residual_trend_delta(previous_report, report)
    return report


def write_evidence_confidence_report(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def load_evidence_confidence_report(path: str | Path | None = None) -> dict:
    report_path = Path(path) if path is not None else DEFAULT_EVIDENCE_CONFIDENCE_REPORT_PATH
    if not report_path.exists():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def evidence_confidence_lookup(report: dict | None) -> dict[tuple[str, str, str, str], dict]:
    return {
        (
            _normalized_endpoint(item.get("endpoint_group")),
            _normalized_context(item.get("target_family") or "all"),
            _normalized_context(item.get("assay_type") or "all"),
            str(item.get("evidence_source") or ""),
        ): item
        for item in (report or {}).get("entries") or []
        if item.get("endpoint_group") and item.get("evidence_source")
    }


def _calibration_item(endpoint: str, target_family: str, assay_type: str, source_id: str, lookup: dict[tuple[str, str, str, str], dict]) -> dict:
    endpoint = _normalized_endpoint(endpoint)
    target_family = _normalized_context(target_family)
    assay_type = _normalized_context(assay_type)
    for key in [
        (endpoint, target_family, assay_type, source_id),
        (endpoint, target_family, "all", source_id),
        (endpoint, "all", assay_type, source_id),
        (endpoint, "all", "all", source_id),
        ("all", "all", "all", source_id),
    ]:
        if key in lookup:
            return lookup[key]
    return {}


def confidence_calibration_for_candidate(
    row: dict,
    *,
    endpoint_group: str | None,
    target_family: str | None = None,
    assay_type: str | None = None,
    lookup: dict[tuple[str, str, str, str], dict],
) -> dict:
    endpoint = _normalized_endpoint(endpoint_group or row.get("endpoint_gate_endpoint") or row.get("direction"))
    family = _normalized_context(target_family or row.get("evidence_target_family_normalized") or row.get("evidence_target_family"))
    assay = _normalized_context(assay_type or row.get("evidence_assay_type"))
    source_rows = []
    for source in candidate_evidence_sources(row):
        item = _calibration_item(endpoint, family, assay, source["source_id"], lookup)
        raw_score = float(source["score"])
        multiplier = float(item.get("confidence_multiplier") or 1.0)
        shift = float(item.get("score_shift") or 0.0)
        adjusted = _clamp(raw_score * multiplier + shift, 0.0, 100.0)
        residual = _float_or_none(item.get("calibration_residual"))
        source_rows.append(
            {
                "evidence_source": source["source_id"],
                "raw_score": round(raw_score, 4),
                "adjusted_score": round(adjusted, 4),
                "adjustment": round(adjusted - raw_score, 4),
                "observed_count": item.get("observed_count", 0),
                "expected_hit_rate": item.get("expected_hit_rate"),
                "observed_hit_rate": item.get("observed_hit_rate"),
                "calibration_residual": residual,
                "context_scope": item.get("context_scope", "uncalibrated"),
                "target_family": item.get("target_family"),
                "assay_type": item.get("assay_type"),
                "calibration_status": item.get("calibration_status", "uncalibrated"),
                "residual_sample_status": item.get("residual_sample_status", "uncalibrated"),
            }
        )
    if not source_rows:
        return {
            "evidence_confidence_calibration_score": None,
            "evidence_confidence_adjustment": None,
            "evidence_confidence_source_count": 0,
            "evidence_confidence_sources": "",
            "evidence_confidence_endpoint": endpoint,
            "evidence_confidence_target_family": family,
            "evidence_confidence_assay_type": assay,
            "evidence_confidence_status": "no_evidence_sources",
            "evidence_confidence_basis": "",
            "evidence_confidence_residual_basis": "",
            "evidence_confidence_max_abs_residual": None,
        }
    raw_mean = sum(float(item["raw_score"]) for item in source_rows) / len(source_rows)
    adjusted_mean = sum(float(item["adjusted_score"]) for item in source_rows) / len(source_rows)
    statuses = [str(item.get("calibration_status") or "uncalibrated") for item in source_rows]
    if any(status in {"over_confident", "under_confident", "well_calibrated"} for status in statuses):
        status = "calibrated"
    elif any(status == "collect_more_outcomes" for status in statuses):
        status = "provisional"
    else:
        status = "uncalibrated"
    basis = "; ".join(
        f"{item['evidence_source']}:{item['calibration_status']} n={item.get('observed_count', 0)} {item.get('residual_sample_status')} adj={item['adjustment']:+.2f}"
        for item in source_rows
    )
    residual_values = [float(item["calibration_residual"]) for item in source_rows if item.get("calibration_residual") is not None]
    residual_basis = "; ".join(
        f"{item['evidence_source']}:{item.get('context_scope')} residual={float(item['calibration_residual']):+.3f}"
        for item in source_rows
        if item.get("calibration_residual") is not None
    )
    return {
        "evidence_confidence_calibration_score": round(adjusted_mean, 2),
        "evidence_confidence_adjustment": round(adjusted_mean - raw_mean, 4),
        "evidence_confidence_source_count": len(source_rows),
        "evidence_confidence_sources": ";".join(item["evidence_source"] for item in source_rows),
        "evidence_confidence_endpoint": endpoint,
        "evidence_confidence_target_family": family,
        "evidence_confidence_assay_type": assay,
        "evidence_confidence_status": status,
        "evidence_confidence_basis": basis,
        "evidence_confidence_residual_basis": residual_basis,
        "evidence_confidence_max_abs_residual": round(max((abs(value) for value in residual_values), default=0.0), 4) if residual_values else None,
        "evidence_confidence_source_details": json.dumps(source_rows, sort_keys=True),
    }


def annotate_evidence_confidence_calibration(
    rows: list[dict],
    *,
    report_path: str | Path | None = DEFAULT_EVIDENCE_CONFIDENCE_REPORT_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    target_context: dict | None = None,
) -> list[dict]:
    report = load_evidence_confidence_report(report_path) if report_path else {}
    if not report:
        report = build_evidence_confidence_report(db_path=db_path, project_name=project_name)
    lookup = evidence_confidence_lookup(report)
    endpoint = (target_context or {}).get("endpoint_group")
    target_family = (target_context or {}).get("target_family")
    assay_type = (target_context or {}).get("assay_type")
    return [
        {
            **row,
            **confidence_calibration_for_candidate(
                row,
                endpoint_group=endpoint or row.get("endpoint_gate_endpoint") or row.get("evidence_endpoint_group") or row.get("direction"),
                target_family=target_family,
                assay_type=assay_type,
                lookup=lookup,
            ),
        }
        for row in rows
    ]
