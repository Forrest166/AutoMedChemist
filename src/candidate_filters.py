from __future__ import annotations


def _split_flags(value: str | None) -> set[str]:
    return {flag for flag in str(value or "").split(";") if flag}


def profile_risk_bucket(row: dict) -> str:
    risk_score = row.get("risk_score")
    evidence_penalty = row.get("evidence_penalty")
    try:
        risk_value = float(risk_score)
    except (TypeError, ValueError):
        risk_value = 100.0
    try:
        penalty_value = float(evidence_penalty)
    except (TypeError, ValueError):
        penalty_value = 0.0
    if risk_value < 50 or penalty_value >= 25:
        return "high"
    if risk_value < 75 or penalty_value >= 10:
        return "medium"
    return "low"


def candidate_filter_options(rows: list[dict]) -> dict:
    flags = sorted({flag for row in rows for flag in _split_flags(row.get("evidence_conflict_flags"))})
    return {
        "evidence_flags": flags,
        "diversity_buckets": sorted({str(row.get("diversity_bucket")) for row in rows if row.get("diversity_bucket")}),
        "site_types": sorted({str(row.get("site_type")) for row in rows if row.get("site_type")}),
        "enumeration_types": sorted({str(row.get("enumeration_type")) for row in rows if row.get("enumeration_type")}),
        "endpoint_gates": sorted({str(row.get("endpoint_gate_decision")) for row in rows if row.get("endpoint_gate_decision")}),
        "profile_risk_buckets": ["low", "medium", "high"],
    }


def apply_candidate_filters(
    rows: list[dict],
    *,
    evidence_conflict: str = "all",
    diversity_buckets: list[str] | tuple[str, ...] | None = None,
    site_types: list[str] | tuple[str, ...] | None = None,
    enumeration_types: list[str] | tuple[str, ...] | None = None,
    profile_risk: str = "all",
    endpoint_gate: str = "all",
    diverse_only: bool = False,
) -> list[dict]:
    bucket_filter = {str(item) for item in diversity_buckets or [] if item}
    site_filter = {str(item) for item in site_types or [] if item}
    enum_filter = {str(item) for item in enumeration_types or [] if item}
    filtered = []
    for row in rows:
        flags = _split_flags(row.get("evidence_conflict_flags"))
        if evidence_conflict == "no_conflicts" and flags:
            continue
        if evidence_conflict == "any_conflict" and not flags:
            continue
        if evidence_conflict not in {"all", "no_conflicts", "any_conflict"} and evidence_conflict not in flags:
            continue
        if bucket_filter and str(row.get("diversity_bucket")) not in bucket_filter:
            continue
        if site_filter and str(row.get("site_type")) not in site_filter:
            continue
        if enum_filter and str(row.get("enumeration_type")) not in enum_filter:
            continue
        if profile_risk != "all" and profile_risk_bucket(row) != profile_risk:
            continue
        if endpoint_gate != "all" and str(row.get("endpoint_gate_decision") or "") != endpoint_gate:
            continue
        if diverse_only and not row.get("diverse_pick"):
            continue
        filtered.append(dict(row, profile_risk_bucket=profile_risk_bucket(row)))
    return filtered
