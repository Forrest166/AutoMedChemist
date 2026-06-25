from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except Exception:
        return None


def _append_unique(items: list[str], value: str | None) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def build_candidate_explanation(row: dict) -> dict:
    why: list[str] = []
    review: list[str] = []
    evidence: list[str] = []

    score = _as_float(row.get("score"))
    direction_score = _as_float(row.get("direction_score"))
    property_score = _as_float(row.get("property_score"))
    transform_prior = _as_float(row.get("transform_prior_score"))
    sar_score = _as_float(row.get("sar_neighborhood_score"))
    mmp_score = _as_float(row.get("mmp_precedent_score"))

    if score is not None:
        _append_unique(why, f"overall score {score:.1f}")
    if direction_score is not None and direction_score >= 70:
        _append_unique(why, f"matches the requested {row.get('direction') or 'design'} direction")
    if property_score is not None and property_score >= 80:
        _append_unique(why, "keeps core property profile in range")
    if transform_prior is not None and transform_prior >= 70:
        _append_unique(why, f"supported transform prior ({transform_prior:.0f})")
    if sar_score is not None and sar_score >= 70:
        _append_unique(why, f"{row.get('sar_neighborhood_strength') or 'local'} SAR neighborhood support")
    if mmp_score is not None and mmp_score >= 70:
        _append_unique(why, f"{row.get('mmp_precedent_strength') or 'public'} MMP precedent support")
    if row.get("site_class_candidate_guidance"):
        _append_unique(why, str(row.get("site_class_candidate_guidance")))

    if row.get("site_class_requires_review") in {True, "True", "true", "1", 1}:
        _append_unique(review, f"site-class review required: {row.get('site_class_governance_action') or row.get('site_class')}")
    if row.get("site_class_risk_note"):
        _append_unique(review, str(row.get("site_class_risk_note")))
    if row.get("endpoint_gate_decision") in {"hold", "watch"}:
        _append_unique(review, f"endpoint gate is {row.get('endpoint_gate_decision')}: {row.get('endpoint_gate_reason') or 'review endpoint evidence'}")
    if row.get("evidence_conflict_flags"):
        _append_unique(review, f"evidence flags: {row.get('evidence_conflict_flags')}")
    if row.get("mmp_contradiction_flags"):
        _append_unique(review, f"MMP contradiction flags: {row.get('mmp_contradiction_flags')}")
    if row.get("route_risk_flags"):
        _append_unique(review, f"route review flags: {row.get('route_risk_flags')}")

    for key, label in [
        ("replacement_label", "replacement"),
        ("enumeration_type", "source"),
        ("sar_neighbor_note", "SAR"),
        ("mmp_precedent_note", "MMP"),
        ("public_strategy_signal_basis", "public signal"),
        ("evidence_confidence_basis", "confidence"),
    ]:
        value = row.get(key)
        if value:
            _append_unique(evidence, f"{label}: {value}")

    summary_parts = []
    if row.get("replacement_label"):
        summary_parts.append(str(row.get("replacement_label")))
    if score is not None:
        summary_parts.append(f"score {score:.1f}")
    if row.get("site_class"):
        summary_parts.append(f"{row.get('site_class')} review context")
    if not summary_parts:
        summary_parts.append(str(row.get("candidate_id") or "candidate"))
    if not why:
        _append_unique(why, row.get("recommendation_reason") or "candidate kept by local scoring and governance filters")
    if not evidence:
        _append_unique(evidence, "local candidate row fields")

    return {
        "candidate_explanation_summary": "; ".join(summary_parts),
        "why_recommended": " | ".join(why[:6]),
        "why_review": " | ".join(review[:6]) if review else "No immediate governance review flag from local evidence.",
        "evidence_snapshot": " | ".join(evidence[:6]),
    }


def annotate_candidate_explanations(rows: list[dict]) -> list[dict]:
    for row in rows:
        row.update(build_candidate_explanation(row))
    return rows
