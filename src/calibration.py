from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import yaml

from .database import initialize_database
from .assay_learning import build_assay_learning_report, endpoint_gate_from_learning
from .feedback import (
    COMPONENT_FIELDS,
    PROPERTY_FIELDS,
    WEIGHT_KEYS,
    _candidate_payload,
    _float_or_none,
    _percentile,
    _rows_for_project,
    endpoint_group_from_text,
)
from .scoring import component_weights


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    xs = [left for left, _right in pairs]
    ys = [right for _left, right in pairs]
    mean_x = mean(xs)
    mean_y = mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _observations(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        if not row.get("feedback_id"):
            continue
        score = _float_or_none(row.get("normalized_score"))
        if score is None:
            continue
        endpoint_group = endpoint_group_from_text(row.get("endpoint"), row.get("assay_type"), row.get("assay_name"))
        key = (endpoint_group, str(row.get("run_id")), str(row.get("candidate_id")))
        item = grouped.setdefault(
            key,
            {
                "endpoint_group": endpoint_group,
                "project_name": row.get("project_name"),
                "run_id": row.get("run_id"),
                "candidate_id": row.get("candidate_id"),
                "direction": row.get("direction"),
                "site_type": row.get("site_type"),
                "payload": _candidate_payload(row),
                "scores": [],
                "assays": [],
            },
        )
        item["scores"].append(score)
        item["assays"].append(str(row.get("assay_name") or row.get("endpoint") or "unspecified"))

    observations = []
    for item in grouped.values():
        payload = item.get("payload") or {}
        observations.append(
            {
                **item,
                "normalized_score": round(mean(item["scores"]), 4),
                "assay_count": len(item["scores"]),
                "payload": payload,
            }
        )
    return observations


def _component_metrics(observations: list[dict]) -> dict:
    metrics = {}
    for component in COMPONENT_FIELDS:
        pairs = []
        for obs in observations:
            value = _float_or_none((obs.get("payload") or {}).get(component))
            score = _float_or_none(obs.get("normalized_score"))
            if value is not None and score is not None:
                pairs.append((value, score))
        if not pairs:
            continue
        values_sorted = sorted(pairs, key=lambda pair: pair[1], reverse=True)
        top_n = max(1, math.ceil(len(values_sorted) * 0.33))
        top_values = [value for value, _score in values_sorted[:top_n]]
        bottom_values = [value for value, _score in values_sorted[-top_n:]]
        correlation = _pearson(pairs)
        metrics[component] = {
            "n": len(pairs),
            "correlation": round(correlation, 4) if correlation is not None else None,
            "top_mean": round(mean(top_values), 4) if top_values else None,
            "bottom_mean": round(mean(bottom_values), 4) if bottom_values else None,
            "top_minus_bottom": round(mean(top_values) - mean(bottom_values), 4) if top_values and bottom_values else None,
        }
    return metrics


def _score_weights_from_metrics(metrics: dict) -> dict:
    adjusted = dict(component_weights())
    for component, item in metrics.items():
        key = WEIGHT_KEYS.get(component)
        if not key:
            continue
        correlation = item.get("correlation")
        delta = item.get("top_minus_bottom")
        shift = 0.0
        if correlation is not None and abs(correlation) >= 0.2:
            shift += 0.06 * float(correlation)
        if delta is not None and abs(delta) >= 8.0:
            shift += 0.025 if delta > 0 else -0.025
        adjusted[key] = max(0.0, adjusted.get(key, 0.0) + shift)
    return component_weights(overrides=adjusted)


def _property_windows(observations: list[dict]) -> dict:
    if not observations:
        return {}
    positives = [obs for obs in observations if float(obs.get("normalized_score") or 0) >= 70.0]
    if len(positives) < 2:
        ranked = sorted(observations, key=lambda obs: obs.get("normalized_score") or 0, reverse=True)
        positives = ranked[: max(2, math.ceil(len(ranked) * 0.33))]
    windows = {}
    for field in PROPERTY_FIELDS:
        values = []
        for obs in positives:
            value = _float_or_none((obs.get("payload") or {}).get(field))
            if value is not None:
                values.append(value)
        if len(values) < 2:
            continue
        low = _percentile(values, 0.1)
        high = _percentile(values, 0.9)
        margin = max((high - low) * 0.2, 0.5 if field in {"clogp", "hbd", "hba", "rotatable_bonds"} else 5.0)
        windows[field] = {
            "min": round(low - margin, 2),
            "max": round(high + margin, 2),
            "basis": f"{len(values)} high-scoring feedback observations",
        }
    return windows


def _endpoint_summary(endpoint: str, observations: list[dict], min_feedback: int, *, learning_report: dict | None = None) -> dict:
    metrics = _component_metrics(observations)
    weights = _score_weights_from_metrics(metrics) if len(observations) >= min_feedback else component_weights()
    assays = Counter(assay for obs in observations for assay in obs.get("assays", []))
    directions = Counter(str(obs.get("direction") or "unspecified") for obs in observations)
    site_types = Counter(str(obs.get("site_type") or "unspecified") for obs in observations)
    scores = [float(obs.get("normalized_score")) for obs in observations if obs.get("normalized_score") is not None]
    return {
        "endpoint_group": endpoint,
        "feedback_count": sum(int(obs.get("assay_count") or 0) for obs in observations),
        "candidate_count": len(observations),
        "status": "calibrated" if len(observations) >= min_feedback else "insufficient_feedback",
        "basis": f"{len(observations)} candidates with endpoint feedback; minimum is {min_feedback}.",
        "score_weights": weights,
        "component_metrics": metrics,
        "property_windows": _property_windows(observations),
        "assay_counts": dict(assays.most_common()),
        "direction_counts": dict(directions.most_common()),
        "site_type_counts": dict(site_types.most_common()),
        "normalized_score_mean": round(mean(scores), 4) if scores else None,
        "endpoint_gate": endpoint_gate_from_learning(learning_report or {}, endpoint),
    }


def calibrate_project_models(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    min_feedback: int = 3,
) -> dict:
    conn = initialize_database(db_path)
    try:
        rows = _rows_for_project(conn, project_name=project_name)
    finally:
        conn.close()

    observations = _observations(rows)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for obs in observations:
        grouped[obs["endpoint_group"]].append(obs)

    created_at = datetime.now(timezone.utc).isoformat()
    calibration_id = f"CAL-{uuid.uuid4().hex[:12].upper()}"
    learning_report = build_assay_learning_report(db_path=db_path, project_name=project_name)
    endpoints = [
        _endpoint_summary(endpoint, grouped[endpoint], min_feedback, learning_report=learning_report)
        for endpoint in sorted(grouped)
    ]
    return {
        "calibration_id": calibration_id,
        "created_at": created_at,
        "project_name": project_name,
        "min_feedback": min_feedback,
        "endpoint_count": len(endpoints),
        "feedback_count": sum(item["feedback_count"] for item in endpoints),
        "candidate_count": sum(item["candidate_count"] for item in endpoints),
        "endpoints": endpoints,
        "assay_learning": learning_report,
    }


def save_calibration_report(report: dict, *, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    conn = initialize_database(db_path)
    try:
        for endpoint in report.get("endpoints", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO project_model_calibration (
                    calibration_id, project_name, endpoint_group, feedback_count,
                    candidate_count, score_weights_json, property_windows_json,
                    metrics_json, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.get("calibration_id"),
                    report.get("project_name"),
                    endpoint.get("endpoint_group"),
                    endpoint.get("feedback_count"),
                    endpoint.get("candidate_count"),
                    json.dumps(endpoint.get("score_weights") or {}, sort_keys=True),
                    json.dumps(endpoint.get("property_windows") or {}, sort_keys=True),
                    json.dumps(endpoint.get("component_metrics") or {}, sort_keys=True),
                    json.dumps(endpoint, sort_keys=True),
                    report.get("created_at"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def write_calibration_report(report: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _slug(value: str | None) -> str:
    value = value or "all"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "all"


def write_calibration_profiles(report: dict, output_dir: str | Path) -> list[Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    project_slug = _slug(report.get("project_name"))
    for endpoint in report.get("endpoints", []):
        if endpoint.get("status") != "calibrated":
            continue
        endpoint_slug = _slug(endpoint.get("endpoint_group"))
        profile = {
            "profile_id": f"{project_slug}_{endpoint_slug}_calibrated",
            "name": f"{report.get('project_name') or 'All projects'} {endpoint.get('endpoint_group')} calibrated",
            "description": "Generated from saved candidate feedback; review before production use.",
            "score_weights": endpoint.get("score_weights") or {},
            "filters": {},
            "calibration": {
                "calibration_id": report.get("calibration_id"),
                "created_at": report.get("created_at"),
                "endpoint_group": endpoint.get("endpoint_group"),
                "feedback_count": endpoint.get("feedback_count"),
                "candidate_count": endpoint.get("candidate_count"),
                "property_windows": endpoint.get("property_windows") or {},
                "endpoint_gate": endpoint.get("endpoint_gate") or {},
            },
        }
        path = out_dir / f"{profile['profile_id']}.yaml"
        path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=False), encoding="utf-8")
        written.append(path)
    return written
