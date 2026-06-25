from __future__ import annotations

from pathlib import Path

from .target_families import normalize_target_context
from .transform_evidence import project_transform_feedback, transform_activity_feedback


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")

DEFAULT_FLAG_PENALTIES = {
    "mmp_property_conflict": 10.0,
    "public_activity_contradiction": 14.0,
    "activity_cliff_high": 18.0,
    "activity_cliff_medium": 8.0,
    "target_family_activity_contradiction": 16.0,
    "target_family_activity_cliff_high": 20.0,
    "target_family_activity_cliff_medium": 9.0,
    "project_negative_public_positive": 18.0,
    "project_positive_public_contradicted": 6.0,
}

PROFILE_MULTIPLIERS = {
    "metabolic_stability": 1.2,
    "solubility_rescue": 1.1,
    "cns": 1.15,
    "oral_systemic": 1.0,
    "covalent_probe": 1.0,
}


def _float_or_none(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _profile_penalty_config(profile: dict | None) -> tuple[dict[str, float], float]:
    profile = profile or {}
    configured = profile.get("evidence_penalties") or {}
    penalties = dict(DEFAULT_FLAG_PENALTIES)
    penalties.update({str(key): float(value) for key, value in (configured.get("flags") or {}).items()})
    profile_id = str(profile.get("profile_id") or "default")
    multiplier = float(configured.get("multiplier") or PROFILE_MULTIPLIERS.get(profile_id, 1.0))
    return penalties, multiplier


def _target_context(profile: dict | None) -> dict:
    profile = profile or {}
    context = profile.get("target_context") or profile.get("evidence_context") or {}
    normalized = normalize_target_context(context)
    return {
        "target_family": str(context.get("target_family") or "").strip(),
        "target_family_normalized": str(normalized.get("target_family_normalized") or "").strip(),
        "target_family_label": str(normalized.get("target_family_label") or "").strip(),
        "target_family_weight": float(normalized.get("target_family_weight") or 1.0),
        "assay_type": str(context.get("assay_type") or context.get("standard_type") or "").strip(),
        "endpoint_group": str(context.get("endpoint_group") or "").strip(),
    }


def evidence_consistency_for_candidate(
    row: dict,
    *,
    project_feedback: dict[str, dict] | None = None,
    activity_feedback: dict[str, dict] | None = None,
    profile: dict | None = None,
) -> dict:
    flags: list[str] = []
    rule_id = str(row.get("functional_rule_id") or "")
    project_item = (project_feedback or {}).get(rule_id, {}) if rule_id else {}
    activity_item = (activity_feedback or {}).get(rule_id, {}) if rule_id else {}

    mmp_flags = [
        flag
        for flag in str(row.get("mmp_contradiction_flags") or "").split(";")
        if flag
    ]
    if mmp_flags:
        flags.append("mmp_property_conflict")

    activity_judgment = str(activity_item.get("activity_judgment") or "").lower()
    activity_cliff_risk = str(activity_item.get("activity_cliff_risk") or row.get("transform_activity_cliff_risk") or "").lower()
    target_context = activity_item.get("target_context") or {}
    context_judgment = str(target_context.get("target_context_judgment") or "").lower()
    context_cliff_risk = str(target_context.get("target_context_cliff_risk") or "").lower()
    context_match_count = int(target_context.get("target_context_match_count") or 0)
    if activity_judgment == "contradicted":
        flags.append("public_activity_contradiction")
    if activity_cliff_risk == "high":
        flags.append("activity_cliff_high")
    elif activity_cliff_risk == "medium":
        flags.append("activity_cliff_medium")
    if context_judgment == "contradicted":
        flags.append("target_family_activity_contradiction")
    if context_cliff_risk == "high":
        flags.append("target_family_activity_cliff_high")
    elif context_cliff_risk == "medium":
        flags.append("target_family_activity_cliff_medium")

    project_mean = _float_or_none(project_item.get("mean_normalized_score"))
    public_positive = row.get("mmp_precedent_strength") in {"medium", "high"} or activity_judgment == "supported" or context_judgment == "supported"
    if project_mean is not None and project_mean <= 35 and public_positive:
        flags.append("project_negative_public_positive")
    if project_mean is not None and project_mean >= 70 and activity_judgment == "contradicted":
        flags.append("project_positive_public_contradicted")

    penalties, multiplier = _profile_penalty_config(profile)
    family_weight = float(_target_context(profile).get("target_family_weight") or 1.0)
    raw_penalty = 0.0
    for flag in sorted(set(flags)):
        flag_penalty = penalties.get(flag, 0.0)
        if flag.startswith("target_family_"):
            flag_penalty *= family_weight
        raw_penalty += flag_penalty
    raw_penalty *= multiplier
    score = max(0.0, min(100.0, 100.0 - raw_penalty))
    return {
        "evidence_consistency_score": round(score, 2),
        "evidence_penalty": round(raw_penalty, 2),
        "evidence_conflict_flags": ";".join(sorted(set(flags))),
        "evidence_mmp_property_flags": ";".join(mmp_flags),
        "evidence_activity_judgment": activity_judgment or None,
        "evidence_activity_cliff_risk": activity_cliff_risk or None,
        "evidence_target_family": _target_context(profile).get("target_family") or None,
        "evidence_target_family_normalized": _target_context(profile).get("target_family_normalized") or None,
        "evidence_target_family_label": _target_context(profile).get("target_family_label") or None,
        "evidence_assay_type": _target_context(profile).get("assay_type") or None,
        "evidence_context_match_count": context_match_count,
        "evidence_context_family_weight": family_weight,
        "evidence_context_judgment": context_judgment or None,
        "evidence_context_cliff_risk": context_cliff_risk or None,
        "evidence_context_mean_delta_pchembl": target_context.get("target_context_mean_delta_pchembl"),
        "evidence_project_mean_score": project_mean,
    }


def annotate_evidence_consistency(
    rows: list[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    profile: dict | None = None,
) -> list[dict]:
    try:
        project_feedback = project_transform_feedback(db_path=db_path, project_name=project_name)
    except Exception:
        project_feedback = {}
    try:
        context = _target_context(profile)
        activity_feedback = transform_activity_feedback(
            db_path=db_path,
            target_family=context.get("target_family_normalized") or context.get("target_family") or None,
            assay_type=context.get("assay_type") or None,
        )
    except Exception:
        activity_feedback = {}
    enriched = []
    for row in rows:
        enriched.append(
            {
                **row,
                **evidence_consistency_for_candidate(
                    row,
                    project_feedback=project_feedback,
                    activity_feedback=activity_feedback,
                    profile=profile,
                ),
            }
        )
    return enriched
