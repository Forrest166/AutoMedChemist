from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_EVIDENCE_VALUE_REPORT_PATH = Path("data/projects/demo/evidence_value_report.json")
DEFAULT_EVIDENCE_VALUE_CSV_PATH = Path("data/projects/demo/evidence_value_report.csv")
DEFAULT_EVIDENCE_VALUE_CALIBRATION_PATH = Path("data/projects/demo/evidence_value_calibration_report.json")
DEFAULT_EVIDENCE_VALUE_CALIBRATION_CSV_PATH = Path("data/projects/demo/evidence_value_calibration_report.csv")
DEFAULT_EVIDENCE_VALUE_ACTIVE_POLICY_PATH = Path("data/projects/demo/evidence_value_policy_active.json")

EVIDENCE_VALUE_POLICY = {
    "version": "evidence-value-heuristic-v1",
    "weights": {
        "candidate_priority": 0.42,
        "sar_link": 1.25,
        "contradiction": 5.0,
        "sufficiency_gap": 8.0,
        "material_ab": 4.0,
        "rollback_impact": 2.4,
    },
}


def _resolve(root_path: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root_path / item


def _load_active_policy(root_path: Path, active_policy_path: str | Path) -> dict:
    active = _read_json(_resolve(root_path, active_policy_path))
    weights = active.get("weights") if isinstance(active.get("weights"), dict) else {}
    if active.get("activation_status") == "active" and weights:
        return {
            "version": active.get("policy_version") or active.get("version") or EVIDENCE_VALUE_POLICY["version"],
            "weights": {**EVIDENCE_VALUE_POLICY["weights"], **weights},
            "source": "manual_activation",
            "source_proposal_id": active.get("source_proposal_id") or active.get("proposal_id"),
            "activated_at": active.get("activated_at"),
        }
    return EVIDENCE_VALUE_POLICY

VALUE_DRIVER_WEIGHT_MAP = {
    "public_sar_prior": "sar_link",
    "contradiction_resolution": "contradiction",
    "evidence_gap": "sufficiency_gap",
    "material_profile_ab": "material_ab",
    "rollback_sensitive": "rollback_impact",
}


def _read_json(path: str | Path) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _score_id(*parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"EV-{digest}"


def _identity_keys(row: dict) -> set[str]:
    keys = set()
    for field in ["queue_id", "candidate_id", "smiles", "candidate_key"]:
        value = str(row.get(field) or "").strip()
        if value:
            keys.add(f"{field}:{value}")
    return keys


def _rollback_lookup(report: dict) -> dict[str, dict]:
    lookup = {}
    for row in report.get("rows") or []:
        for key in _identity_keys(row):
            lookup[key] = dict(row)
    return lookup


def _triage_signal_counts(report: dict) -> dict[str, dict]:
    signal_counts = {}
    for row in report.get("rows") or []:
        for key in [str(row.get("source_signal_id") or ""), str(row.get("signal_key") or "")]:
            if key:
                signal_counts[key] = row
    return signal_counts


def _triage_identity_counts(report: dict) -> dict[str, list[dict]]:
    lookup: dict[str, list[dict]] = defaultdict(list)
    for row in report.get("rows") or []:
        for queue_id in str(row.get("queue_ids") or "").split(";"):
            if queue_id.strip():
                lookup[f"queue_id:{queue_id.strip()}"].append(dict(row))
        for candidate_id in str(row.get("candidate_ids") or "").split(";"):
            if candidate_id.strip():
                lookup[f"candidate_id:{candidate_id.strip()}"].append(dict(row))
        for link in row.get("candidate_links") or []:
            for key in _identity_keys(link):
                lookup[key].append(dict(row))
    return lookup


def _linked_triage_count(candidate_row: dict, triage_by_signal: dict[str, dict], triage_by_identity: dict[str, list[dict]]) -> int:
    triage_ids = set()
    for signal_id in str(candidate_row.get("public_sar_signal_examples") or "").split(";"):
        if signal_id.strip() in triage_by_signal:
            triage_ids.add(str(triage_by_signal[signal_id.strip()].get("triage_id") or signal_id.strip()))
    for key in _identity_keys(candidate_row):
        for triage in triage_by_identity.get(key) or []:
            triage_ids.add(str(triage.get("triage_id") or json.dumps(triage, sort_keys=True)))
    return len(triage_ids)


def _tier(score: float) -> str:
    if score >= 36:
        return "high_value"
    if score >= 22:
        return "medium_value"
    return "watch"


def _sufficiency_gap_factor(row: dict) -> float:
    status = str(row.get("evidence_sufficiency_status") or "")
    if status == "conflict_review":
        return 1.0
    if status.startswith("needs"):
        return 0.8
    if status and status != "sufficient":
        return 0.45
    return 0.0


def _action(row: dict, *, linked_triage_count: int, rollback: dict) -> str:
    if linked_triage_count or _int(row.get("public_sar_contradiction_count")):
        return "resolve_public_sar_contradiction"
    if _sufficiency_gap_factor(row):
        return "run_evidence_gap_measurement"
    if rollback:
        return "profile_sensitive_retest_or_review"
    if _int(row.get("public_sar_link_count")):
        return "confirm_public_sar_prior"
    return "maintain_queue_review"


def build_evidence_value_report(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    candidate_priority_path: str | Path = "data/projects/demo/candidate_evidence_priority_report.json",
    contradiction_triage_path: str | Path = "data/projects/demo/public_sar_contradiction_triage.json",
    rollback_replay_path: str | Path = "data/projects/demo/profile_promotion_rollback_replay.json",
    active_policy_path: str | Path = DEFAULT_EVIDENCE_VALUE_ACTIVE_POLICY_PATH,
) -> dict:
    root_path = Path(root)
    priority = _read_json(_resolve(root_path, candidate_priority_path))
    triage = _read_json(_resolve(root_path, contradiction_triage_path))
    rollback = _read_json(_resolve(root_path, rollback_replay_path))
    rollback_by_identity = _rollback_lookup(rollback)
    triage_by_signal = _triage_signal_counts(triage)
    triage_by_identity = _triage_identity_counts(triage)
    policy = _load_active_policy(root_path, active_policy_path)
    weights = policy["weights"]
    rows = []
    for source in priority.get("rows") or []:
        linked_rollback = {}
        for key in _identity_keys(source):
            if key in rollback_by_identity:
                linked_rollback = rollback_by_identity[key]
                break
        linked_triage = _linked_triage_count(source, triage_by_signal, triage_by_identity)
        rollback_impact = abs(_float(linked_rollback.get("rollback_score_delta"))) + abs(_float(linked_rollback.get("rollback_rank_delta"))) * 0.18
        gap_factor = _sufficiency_gap_factor(source)
        sar_links = _int(source.get("public_sar_link_count"))
        contradiction_units = _int(source.get("public_sar_contradiction_count")) + linked_triage
        material_units = _int(source.get("material_ab_diff_count"))
        value_score = (
            _float(source.get("candidate_evidence_priority_score")) * weights["candidate_priority"]
            + min(12.0, sar_links * weights["sar_link"])
            + min(20.0, contradiction_units * weights["contradiction"])
            + gap_factor * weights["sufficiency_gap"]
            + min(12.0, material_units * weights["material_ab"])
            + min(18.0, rollback_impact * weights["rollback_impact"])
        )
        value_score = round(max(0.0, min(100.0, value_score)), 2)
        driver_flags = []
        if sar_links:
            driver_flags.append("public_sar_prior")
        if contradiction_units:
            driver_flags.append("contradiction_resolution")
        if gap_factor:
            driver_flags.append("evidence_gap")
        if material_units:
            driver_flags.append("material_profile_ab")
        if linked_rollback:
            driver_flags.append("rollback_sensitive")
        rows.append(
            {
                "evidence_value_id": _score_id(source.get("queue_id"), source.get("candidate_id"), source.get("smiles")),
                "project_name": project_name,
                "queue_id": source.get("queue_id"),
                "candidate_id": source.get("candidate_id"),
                "smiles": source.get("smiles") or source.get("candidate_key"),
                "endpoint_group": source.get("endpoint_group"),
                "analog_series_key": source.get("analog_series_key"),
                "candidate_evidence_priority_score": source.get("candidate_evidence_priority_score"),
                "candidate_evidence_priority_tier": source.get("candidate_evidence_priority_tier"),
                "public_sar_link_count": sar_links,
                "public_sar_contradiction_count": _int(source.get("public_sar_contradiction_count")),
                "linked_contradiction_triage_count": linked_triage,
                "material_ab_diff_count": material_units,
                "evidence_sufficiency_status": source.get("evidence_sufficiency_status"),
                "rollback_score_delta": linked_rollback.get("rollback_score_delta"),
                "rollback_rank_delta": linked_rollback.get("rollback_rank_delta"),
                "evidence_value_score": value_score,
                "evidence_value_tier": _tier(value_score),
                "next_evidence_action": _action(source, linked_triage_count=linked_triage, rollback=linked_rollback),
                "value_driver_flags": ";".join(driver_flags),
                "policy_version": policy["version"],
            }
        )
    rows.sort(
        key=lambda row: (
            {"high_value": 0, "medium_value": 1, "watch": 2}.get(str(row.get("evidence_value_tier")), 9),
            -_float(row.get("evidence_value_score")),
            _int(row.get("queue_id", "").replace("NDQ-", ""), 9999),
        )
    )
    tier_counts = Counter(str(row.get("evidence_value_tier") or "unknown") for row in rows)
    action_counts = Counter(str(row.get("next_evidence_action") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "project_name": project_name,
        "policy": policy,
        "row_count": len(rows),
        "high_value_count": tier_counts.get("high_value", 0),
        "medium_value_count": tier_counts.get("medium_value", 0),
        "contradiction_resolution_count": action_counts.get("resolve_public_sar_contradiction", 0),
        "evidence_gap_measurement_count": action_counts.get("run_evidence_gap_measurement", 0),
        "tier_counts": dict(tier_counts.most_common()),
        "action_counts": dict(action_counts.most_common()),
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "rows": rows,
        "recommended_next_actions": [
            "Use high_value rows to prioritize the next measurement or manual SAR review slot.",
            "Treat this as a calibratable evidence-value policy; weights should be adjusted only after measured feedback arrives.",
            "Keep vendor/procurement signals out of evidence-value scoring.",
        ],
    }


def write_evidence_value_report(
    report: dict,
    output_path: str | Path = DEFAULT_EVIDENCE_VALUE_REPORT_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_VALUE_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    fieldnames = [
        "evidence_value_id",
        "project_name",
        "queue_id",
        "candidate_id",
        "smiles",
        "endpoint_group",
        "analog_series_key",
        "candidate_evidence_priority_score",
        "candidate_evidence_priority_tier",
        "public_sar_link_count",
        "public_sar_contradiction_count",
        "linked_contradiction_triage_count",
        "material_ab_diff_count",
        "evidence_sufficiency_status",
        "rollback_score_delta",
        "rollback_rank_delta",
        "evidence_value_score",
        "evidence_value_tier",
        "next_evidence_action",
        "value_driver_flags",
        "policy_version",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _summary_stats(rows: list[dict]) -> dict:
    errors = [_float(row.get("score_error")) for row in rows]
    if not errors:
        return {
            "row_count": 0,
            "mean_absolute_error": None,
            "mean_signed_error": None,
            "max_abs_error": None,
        }
    return {
        "row_count": len(errors),
        "mean_absolute_error": round(sum(abs(value) for value in errors) / len(errors), 4),
        "mean_signed_error": round(sum(errors) / len(errors), 4),
        "max_abs_error": round(max(abs(value) for value in errors), 4),
    }


def _rank_alignment_rate(rows: list[dict]) -> float | None:
    if len(rows) < 2:
        return None
    predicted = [_float(row.get("predicted_evidence_value_score")) for row in rows]
    observed = [_float(row.get("normalized_observed_score")) for row in rows]
    pred_med = _median(predicted)
    obs_med = _median(observed)
    aligned = 0
    for row in rows:
        pred_high = _float(row.get("predicted_evidence_value_score")) >= pred_med
        obs_high = _float(row.get("normalized_observed_score")) >= obs_med
        if pred_high == obs_high:
            aligned += 1
    return round(aligned / len(rows), 4)


def _group_stats(rows: list[dict], group_field: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(group_field) or "unknown")].append(row)
    result = []
    for key, group_rows in sorted(grouped.items()):
        result.append({group_field: key, **_summary_stats(group_rows)})
    return result


def _driver_flags(row: dict) -> list[str]:
    flags = [part.strip() for part in str(row.get("value_driver_flags") or "").split(";") if part.strip()]
    return flags or ["unknown"]


def _driver_error_summary(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        for flag in _driver_flags(row):
            grouped[flag].append(row)
    result = []
    for flag, group_rows in grouped.items():
        stats = _summary_stats(group_rows)
        signed_error = stats.get("mean_signed_error")
        recommended_direction = "hold"
        if signed_error is not None and abs(float(signed_error)) >= 8:
            recommended_direction = "increase" if float(signed_error) > 0 else "decrease"
        result.append(
            {
                "value_driver": flag,
                "mapped_weight": VALUE_DRIVER_WEIGHT_MAP.get(flag, ""),
                **stats,
                "recommended_direction": recommended_direction,
                "priority_score": round(abs(float(signed_error or 0.0)) * max(1, int(stats.get("row_count") or 0)) ** 0.5, 4),
            }
        )
    result.sort(key=lambda row: (-_float(row.get("priority_score")), str(row.get("value_driver") or "")))
    return result


def _weight_adjustments(rows: list[dict]) -> list[dict]:
    suggestions = []
    if not rows:
        return suggestions
    by_type = {row["measurement_type"]: row for row in _group_stats(rows, "measurement_type")}
    contradiction = by_type.get("public_sar_contradiction_resolution") or {}
    contradiction_error = contradiction.get("mean_signed_error")
    if contradiction_error is not None and abs(float(contradiction_error)) >= 8:
        suggestions.append(
            {
                "weight": "contradiction",
                "direction": "increase" if float(contradiction_error) > 0 else "decrease",
                "basis": "public_sar_contradiction_resolution_mean_signed_error",
                "observed_mean_signed_error": contradiction_error,
                "current_weight": EVIDENCE_VALUE_POLICY["weights"]["contradiction"],
            }
        )
    profile_rows = [
        row
        for row in rows
        if str(row.get("measurement_type") or "") == "profile_sensitive_rank_retest"
        or "material_profile_ab" in str(row.get("value_driver_flags") or "")
    ]
    profile_stats = _summary_stats(profile_rows)
    profile_error = profile_stats.get("mean_signed_error")
    if profile_error is not None and abs(float(profile_error)) >= 8:
        suggestions.append(
            {
                "weight": "material_ab",
                "direction": "increase" if float(profile_error) > 0 else "decrease",
                "basis": "profile_sensitive_or_material_ab_mean_signed_error",
                "observed_mean_signed_error": profile_error,
                "current_weight": EVIDENCE_VALUE_POLICY["weights"]["material_ab"],
            }
        )
    gap_rows = [row for row in rows if str(row.get("measurement_type") or "") in {"residual_endpoint_followup", "replicate_conflict_endpoint"}]
    gap_stats = _summary_stats(gap_rows)
    gap_error = gap_stats.get("mean_signed_error")
    if gap_error is not None and abs(float(gap_error)) >= 8:
        suggestions.append(
            {
                "weight": "sufficiency_gap",
                "direction": "increase" if float(gap_error) > 0 else "decrease",
                "basis": "gap_or_conflict_measurement_mean_signed_error",
                "observed_mean_signed_error": gap_error,
                "current_weight": EVIDENCE_VALUE_POLICY["weights"]["sufficiency_gap"],
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "weight": "none",
                "direction": "hold",
                "basis": "calibration_errors_within_current_manual_threshold",
                "current_policy_version": EVIDENCE_VALUE_POLICY["version"],
            }
        )
    return suggestions


def build_evidence_value_calibration_report(
    *,
    root: str | Path = ".",
    project_name: str | None = "demo_learning",
    evidence_value_path: str | Path = DEFAULT_EVIDENCE_VALUE_REPORT_PATH,
    measurement_import_path: str | Path = "data/projects/demo/measurement_feedback_result_import_report.json",
) -> dict:
    root_path = Path(root)
    evidence_file = Path(evidence_value_path)
    if not evidence_file.is_absolute():
        evidence_file = root_path / evidence_file
    import_file = Path(measurement_import_path)
    if not import_file.is_absolute():
        import_file = root_path / import_file
    evidence_report = _read_json(evidence_file)
    import_report = _read_json(import_file)
    policy = evidence_report.get("policy") or EVIDENCE_VALUE_POLICY
    rows = []
    for raw in import_report.get("rows") or []:
        row = dict(raw)
        if not _bool(row.get("calibration_ready")):
            continue
        observed = _float(row.get("normalized_observed_score"))
        predicted = _float(row.get("predicted_evidence_value_score"))
        row["score_error"] = round(observed - predicted, 4)
        rows.append(row)
    if not import_report or import_report.get("status") in {"needs_real_measurement_feedback", "validation_failed"}:
        status = "needs_real_measurement_feedback"
    elif not rows:
        status = "needs_normalized_measurement_scores"
    else:
        status = "calibrated"
    stats = _summary_stats(rows)
    type_rows = _group_stats(rows, "measurement_type") if rows else []
    action_rows = _group_stats(rows, "next_evidence_action") if rows else []
    driver_rows = _driver_error_summary(rows) if rows else []
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "policy": policy,
        "evidence_value_status": evidence_report.get("status"),
        "measurement_import_status": import_report.get("status") or "missing",
        "measurement_import_row_count": import_report.get("importable_row_count", 0),
        "calibration_row_count": len(rows),
        "mean_absolute_error": stats.get("mean_absolute_error"),
        "mean_signed_error": stats.get("mean_signed_error"),
        "max_abs_error": stats.get("max_abs_error"),
        "rank_alignment_rate": _rank_alignment_rate(rows),
        "measurement_type_error_summary": type_rows,
        "action_error_summary": action_rows,
        "value_driver_error_summary": driver_rows,
        "priority_driver_weight_adjustments": [
            {
                "value_driver": row.get("value_driver"),
                "weight": row.get("mapped_weight"),
                "direction": row.get("recommended_direction"),
                "mean_signed_error": row.get("mean_signed_error"),
                "mean_absolute_error": row.get("mean_absolute_error"),
                "row_count": row.get("row_count"),
                "priority_score": row.get("priority_score"),
            }
            for row in driver_rows
            if row.get("mapped_weight") and row.get("recommended_direction") in {"increase", "decrease"}
        ],
        "recommended_weight_adjustments": _weight_adjustments(rows),
        "rows": rows,
        "blocked_scopes": ["vendor", "procurement", "supplier_purchase"],
        "recommended_next_actions": [
            "Collect calibration-ready measurement feedback before changing evidence-value weights.",
            "Use signed error by measurement_type to decide which heuristic weight to adjust first.",
            "Keep all calibration changes reviewable; do not auto-activate weight changes from a single import.",
        ],
    }


def write_evidence_value_calibration_report(
    report: dict,
    output_path: str | Path = DEFAULT_EVIDENCE_VALUE_CALIBRATION_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_VALUE_CALIBRATION_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    fieldnames = [
        "measurement_plan_id",
        "measurement_type",
        "queue_id",
        "candidate_id",
        "endpoint_group",
        "observed_value",
        "observed_unit",
        "normalized_observed_score",
        "predicted_evidence_value_score",
        "score_error",
        "value_driver_flags",
        "next_evidence_action",
        "assay_confidence",
        "reviewer",
        "imported_at",
    ]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
