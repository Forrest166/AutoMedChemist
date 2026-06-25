from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
APPROVED_DECISIONS = {"approved", "accept", "accepted", "apply"}
DEFAULT_RESIDUAL_ADJUSTMENT_REVIEWS_PATH = Path("data/profiles/calibrated/endpoint_family_residual_adjustment_reviews.csv")
DEFAULT_RESIDUAL_ADJUSTED_PROFILE_PATH = Path("data/profiles/evidence_weighted_residual_adjusted.yaml")


def residual_adjustment_id(row: dict) -> str:
    key = "|".join(
        [
            str(row.get("evidence_source") or ""),
            str(row.get("endpoint_group") or ""),
            str(row.get("target_family") or ""),
            str(row.get("recommended_weight_action") or ""),
        ]
    )
    return f"RPA-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:10].upper()}"


def _normalize(value: object) -> str:
    return str(value or "").strip().lower()


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _model_rows(source: dict) -> list[dict]:
    if source.get("rows"):
        return [dict(row) for row in source.get("rows") or [] if isinstance(row, dict)]
    if source.get("endpoint_family_residual_rows"):
        return [dict(row) for row in source.get("endpoint_family_residual_rows") or [] if isinstance(row, dict)]
    return []


def build_residual_adjustment_review_template(
    model: dict,
    *,
    reviewer: str = "",
    min_confidence: str = "medium",
    min_abs_score_shift: float = 1.0,
    auto_decision: str = "",
) -> list[dict]:
    """Create reviewer sign-off rows for endpoint-family residual profile adjustments."""
    min_rank = CONFIDENCE_ORDER.get(_normalize(min_confidence), 1)
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for row in _model_rows(model):
        confidence = _normalize(row.get("adjustment_confidence") or (row.get("score_profile_adjustment") or {}).get("confidence"))
        score_shift = _float(row.get("suggested_score_shift") or (row.get("score_profile_adjustment") or {}).get("score_shift"))
        action = _normalize(row.get("recommended_weight_action"))
        if CONFIDENCE_ORDER.get(confidence, 0) < min_rank:
            continue
        if abs(score_shift) < float(min_abs_score_shift):
            continue
        if action == "keep_current_weight":
            continue
        rows.append(
            {
                "adjustment_id": residual_adjustment_id(row),
                "review_decision": auto_decision,
                "reviewer": reviewer,
                "reviewed_at": now if auto_decision else "",
                "evidence_source": row.get("evidence_source"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "recommended_weight_action": row.get("recommended_weight_action"),
                "suggested_score_shift": score_shift,
                "adjustment_confidence": confidence,
                "holdout_check_status": row.get("holdout_check_status"),
                "observed_count": row.get("observed_count"),
                "max_abs_residual": row.get("max_abs_residual"),
                "review_note": "auto-approved medium/high confidence residual adjustment" if auto_decision else "",
            }
        )
    return rows


def write_residual_adjustment_reviews(rows: list[dict], path: str | Path) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "adjustment_id",
        "review_decision",
        "reviewer",
        "reviewed_at",
        "evidence_source",
        "endpoint_group",
        "target_family",
        "recommended_weight_action",
        "suggested_score_shift",
        "adjustment_confidence",
        "holdout_check_status",
        "observed_count",
        "max_abs_residual",
        "review_note",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def load_residual_adjustment_reviews(path: str | Path | None) -> list[dict]:
    if path is None:
        return []
    review_path = Path(path)
    if not review_path.exists():
        return []
    if review_path.suffix.lower() == ".json":
        data = json.loads(review_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
        return [dict(row) for row in data.get("reviews") or [] if isinstance(row, dict)]
    with review_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _review_lookup(reviews: list[dict]) -> dict[str, dict]:
    lookup = {}
    for review in reviews:
        adjustment_id = str(review.get("adjustment_id") or "").strip()
        if adjustment_id:
            lookup[adjustment_id] = review
        key = "|".join(
            [
                _normalize(review.get("evidence_source")),
                _normalize(review.get("endpoint_group")),
                _normalize(review.get("target_family")),
            ]
        )
        lookup[key] = review
    return lookup


def build_residual_profile_adjustment_document(
    model: dict,
    *,
    reviews: list[dict],
    base_profile: dict,
    reviewer: str = "",
    min_confidence: str = "medium",
    min_abs_score_shift: float = 1.0,
) -> dict:
    lookup = _review_lookup(reviews)
    min_rank = CONFIDENCE_ORDER.get(_normalize(min_confidence), 1)
    adjustments = []
    for row in _model_rows(model):
        adjustment_id = residual_adjustment_id(row)
        review = lookup.get(adjustment_id) or lookup.get(
            "|".join([_normalize(row.get("evidence_source")), _normalize(row.get("endpoint_group")), _normalize(row.get("target_family"))])
        )
        if _normalize((review or {}).get("review_decision") or (review or {}).get("decision")) not in APPROVED_DECISIONS:
            continue
        adjustment = row.get("score_profile_adjustment") or {}
        confidence = _normalize(row.get("adjustment_confidence") or adjustment.get("confidence"))
        score_shift = _float(row.get("suggested_score_shift") or adjustment.get("score_shift"))
        if CONFIDENCE_ORDER.get(confidence, 0) < min_rank or abs(score_shift) < float(min_abs_score_shift):
            continue
        adjustments.append(
            {
                "adjustment_id": adjustment_id,
                "evidence_source": row.get("evidence_source"),
                "endpoint_group": row.get("endpoint_group"),
                "target_family": row.get("target_family"),
                "score_shift": round(score_shift, 4),
                "score_shift_ci_low": row.get("suggested_score_shift_ci_low") or adjustment.get("score_shift_ci_low"),
                "score_shift_ci_high": row.get("suggested_score_shift_ci_high") or adjustment.get("score_shift_ci_high"),
                "weight_multiplier": adjustment.get("weight_multiplier"),
                "adjustment_confidence": confidence,
                "recommended_weight_action": row.get("recommended_weight_action"),
                "holdout_check_status": row.get("holdout_check_status"),
                "observed_count": row.get("observed_count"),
                "max_abs_residual": row.get("max_abs_residual"),
                "review_status": "approved",
                "reviewer": (review or {}).get("reviewer") or reviewer,
                "reviewed_at": (review or {}).get("reviewed_at") or datetime.now(timezone.utc).isoformat(),
                "review_note": (review or {}).get("review_note") or "",
            }
        )
    profile = dict(base_profile)
    parent_profile_id = base_profile.get("profile_id") or "base"
    profile["profile_id"] = f"{parent_profile_id}_residual_adjusted"
    profile["name"] = f"{base_profile.get('name') or parent_profile_id} + residual adjusted"
    profile["parent_profile_id"] = parent_profile_id
    profile["endpoint_family_residual_adjustments"] = {
        "enabled": True,
        "version": "endpoint-family-residual-adjustments-0.1",
        "source_model_created_at": model.get("created_at"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_required": True,
        "applied_count": len(adjustments),
        "max_abs_total_score_shift": 10.0,
        "adjustments": adjustments,
    }
    return profile


def write_residual_adjusted_profile(profile: dict, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=False), encoding="utf-8")


def endpoint_family_residual_adjustment_for_candidate(
    row: dict,
    *,
    profile: dict,
    target_context: dict | None = None,
) -> dict:
    config = profile.get("endpoint_family_residual_adjustments") or {}
    if not config or config.get("enabled") is False:
        return {
            "endpoint_family_residual_score_adjustment": 0.0,
            "endpoint_family_residual_adjustment_ids": "",
            "endpoint_family_residual_adjustment_basis": "",
        }
    context = target_context or {}
    endpoint = _normalize(context.get("endpoint_group") or row.get("evidence_confidence_endpoint") or row.get("endpoint_gate_endpoint") or row.get("direction"))
    family = _normalize(
        context.get("target_family")
        or row.get("evidence_confidence_target_family")
        or row.get("evidence_target_family_normalized")
        or row.get("evidence_target_family")
    )
    sources = {
        _normalize(value)
        for value in str(row.get("evidence_confidence_sources") or "").replace(",", ";").split(";")
        if _normalize(value)
    }
    total = 0.0
    ids = []
    bases = []
    for adjustment in config.get("adjustments") or []:
        if _normalize(adjustment.get("endpoint_group")) != endpoint:
            continue
        if _normalize(adjustment.get("target_family")) != family:
            continue
        source = _normalize(adjustment.get("evidence_source"))
        if source and source not in sources:
            continue
        shift = _float(adjustment.get("score_shift"))
        total += shift
        ids.append(str(adjustment.get("adjustment_id") or ""))
        bases.append(f"{source}:{endpoint}/{family} shift={shift:+.2f}")
    cap = abs(_float(config.get("max_abs_total_score_shift"), 10.0))
    total = max(-cap, min(cap, total))
    return {
        "endpoint_family_residual_score_adjustment": round(total, 4),
        "endpoint_family_residual_adjustment_ids": ";".join(item for item in ids if item),
        "endpoint_family_residual_adjustment_basis": "; ".join(bases),
    }
