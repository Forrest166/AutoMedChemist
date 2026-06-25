from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import yaml

from .ring_library import normalize_attachment_smiles
from .target_families import normalize_target_family


DEFAULT_ACTIVITY_PATH = Path(__file__).resolve().parents[2] / "data" / "activity" / "chembl_activity_evidence.yaml"
HIGH_CONFIDENCE_STANDARD_TYPES = {"IC50", "EC50", "KI", "KD", "POTENCY"}


def _float_or_none(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def infer_target_family(row: dict) -> str | None:
    explicit = row.get("target_family")
    if explicit:
        return str(explicit)
    pref_name = row.get("target_pref_name") or row.get("pref_name")
    target_type = row.get("target_type")
    organism = row.get("target_organism") or row.get("organism")
    if pref_name:
        name = str(pref_name)
        lower = name.lower()
        if "cytochrome p450" in lower:
            family = "Cytochrome P450"
        elif "kinase" in lower:
            family = "Kinase"
        elif "receptor" in lower:
            family = "Receptor"
        elif "transporter" in lower:
            family = "Transporter"
        elif target_type and str(target_type).upper() == "PROTEIN FAMILY":
            family = name
        else:
            family = name
        if organism:
            return f"{family} | {organism}"
        return family
    return row.get("target_chembl_id")


def normalize_activity_row(raw: dict) -> dict | None:
    molecule_id = raw.get("molecule_chembl_id")
    target_id = raw.get("target_chembl_id")
    standard_type = raw.get("standard_type")
    if not molecule_id or not target_id or not standard_type:
        return None
    evidence_key = f"{raw.get('activity_id') or ''}:{molecule_id}:{target_id}:{standard_type}:{raw.get('standard_value')}"
    digest = hashlib.sha1(evidence_key.encode("utf-8")).hexdigest()[:14].upper()
    inferred_family = infer_target_family(raw)
    normalized_family = normalize_target_family(
        inferred_family,
        target_pref_name=raw.get("target_pref_name") or raw.get("pref_name"),
        target_type=raw.get("target_type"),
    )
    return {
        "evidence_id": f"ACT-{digest}",
        "activity_id": raw.get("activity_id"),
        "molecule_chembl_id": molecule_id,
        "target_chembl_id": target_id,
        "target_pref_name": raw.get("target_pref_name") or raw.get("pref_name"),
        "target_type": raw.get("target_type"),
        "target_organism": raw.get("target_organism") or raw.get("organism"),
        "target_family": inferred_family,
        **normalized_family,
        "standard_type": standard_type,
        "standard_relation": raw.get("standard_relation") or raw.get("relation"),
        "standard_value": _float_or_none(raw.get("standard_value")),
        "standard_units": raw.get("standard_units"),
        "pchembl_value": _float_or_none(raw.get("pchembl_value")),
        "assay_chembl_id": raw.get("assay_chembl_id"),
        "document_chembl_id": raw.get("document_chembl_id"),
        "source_name": "ChEMBL activity API",
    }


def load_activity_evidence(path: str | Path | None = None) -> list[dict]:
    activity_path = Path(path) if path is not None else DEFAULT_ACTIVITY_PATH
    if not activity_path.exists():
        return []
    with activity_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return list(data.get("activities") or [])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported activity evidence shape: {activity_path}")


def save_activity_evidence(rows: list[dict], path: str | Path, metadata: dict | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_name": "ChEMBL activity API",
        "version": "chembl-activity-0.1",
        "metadata": metadata or {},
        "activities": rows,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def validate_activity_evidence(rows: list[dict]) -> dict:
    issues = []
    seen = set()
    for row in rows:
        evidence_id = row.get("evidence_id")
        if not evidence_id:
            issues.append({"severity": "error", "check": "activity_id_missing", "item_id": None, "message": "Missing evidence_id"})
        elif evidence_id in seen:
            issues.append({"severity": "error", "check": "activity_id_duplicate", "item_id": evidence_id, "message": "Duplicate evidence_id"})
        seen.add(evidence_id)
        if row.get("pchembl_value") is None and row.get("standard_value") is None:
            issues.append({"severity": "warning", "check": "activity_value_missing", "item_id": evidence_id, "message": "No numeric activity value"})
    return {
        "activity_count": len(rows),
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "issues": issues,
    }


def activity_cliff_summary(rows: list[dict], cliff_threshold: float = 1.0) -> dict:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        pchembl = _float_or_none(row.get("pchembl_value"))
        if pchembl is None:
            continue
        grouped[(str(row.get("target_chembl_id")), str(row.get("standard_type")))].append(row)

    cliffs = []
    for (target, standard_type), items in grouped.items():
        molecule_values = defaultdict(list)
        for item in items:
            molecule_values[item["molecule_chembl_id"]].append(float(item["pchembl_value"]))
        means = {mol: sum(values) / len(values) for mol, values in molecule_values.items() if values}
        if len(means) < 2:
            continue
        low_mol = min(means, key=means.get)
        high_mol = max(means, key=means.get)
        delta = means[high_mol] - means[low_mol]
        if delta >= cliff_threshold:
            cliffs.append(
                {
                    "target_chembl_id": target,
                    "standard_type": standard_type,
                    "molecule_count": len(means),
                    "low_molecule_chembl_id": low_mol,
                    "high_molecule_chembl_id": high_mol,
                    "delta_pchembl": round(delta, 4),
                }
            )
    cliffs.sort(key=lambda row: row["delta_pchembl"], reverse=True)
    return {
        "activity_count": len(rows),
        "target_type_group_count": len(grouped),
        "activity_cliff_group_count": len(cliffs),
        "activity_cliffs": cliffs[:100],
    }


def _activity_values_by_molecule(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        pchembl = _float_or_none(row.get("pchembl_value"))
        if pchembl is None:
            continue
        grouped[str(row.get("molecule_chembl_id"))].append({**row, "pchembl_value": pchembl})
    return grouped


def _molecule_group_values(activity_by_molecule: dict[str, list[dict]], molecule_ids: list[str]) -> dict[tuple[str, str], list[float]]:
    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for molecule_id in molecule_ids:
        for row in activity_by_molecule.get(str(molecule_id), []):
            key = (str(row.get("target_chembl_id")), str(row.get("standard_type")))
            values[key].append(float(row["pchembl_value"]))
    return values


def _molecule_family_rows(activity_by_molecule: dict[str, list[dict]], molecule_ids: list[str]) -> dict[tuple[str, str], list[dict]]:
    values: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for molecule_id in molecule_ids:
        for row in activity_by_molecule.get(str(molecule_id), []):
            family = infer_target_family(row)
            if not family:
                continue
            normalized = normalize_target_family(
                row.get("target_family_normalized") or family,
                target_pref_name=row.get("target_pref_name"),
                target_type=row.get("target_type"),
            )
            key = (str(normalized.get("target_family_normalized") or family), str(row.get("standard_type")))
            values[key].append(row)
    return values


def _orientation_for_mapping(mapping: dict, mmp_row: dict) -> str:
    try:
        mapping_from = normalize_attachment_smiles(mapping.get("variable_from_smiles") or "")
        mapping_to = normalize_attachment_smiles(mapping.get("variable_to_smiles") or "")
        mmp_from = normalize_attachment_smiles(mmp_row.get("variable_from_smiles") or "")
        mmp_to = normalize_attachment_smiles(mmp_row.get("variable_to_smiles") or "")
    except Exception:
        return "unknown"
    if (mapping_from, mapping_to) == (mmp_from, mmp_to):
        return "forward"
    if (mapping_from, mapping_to) == (mmp_to, mmp_from):
        return "reverse"
    return "unknown"


def _mean_pchembl(rows: list[dict]) -> float:
    values = [float(row["pchembl_value"]) for row in rows if _float_or_none(row.get("pchembl_value")) is not None]
    return mean(values) if values else 0.0


def _assay_confidence_bucket(score: float | None) -> str:
    if score is None:
        return "none"
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def _uncertainty_from_confidence(score: float | None) -> float | None:
    if score is None:
        return None
    return round(max(0.05, 1.0 - (float(score) / 100.0)), 3)


def _assay_confidence_score(
    *,
    from_activity_count: int,
    to_activity_count: int,
    standard_type: str | None,
    from_target_count: int = 1,
    to_target_count: int = 1,
    assay_count: int = 0,
    document_count: int = 0,
) -> float:
    min_side_count = min(int(from_activity_count or 0), int(to_activity_count or 0))
    total_count = int(from_activity_count or 0) + int(to_activity_count or 0)
    score = 38.0
    if min_side_count >= 2:
        score += 15.0
    if min_side_count >= 3:
        score += 7.0
    if total_count >= 8:
        score += 5.0
    min_target_count = min(int(from_target_count or 0), int(to_target_count or 0))
    if min_target_count >= 2:
        score += 10.0
    if min_target_count >= 3:
        score += 5.0
    if str(standard_type or "").upper() in HIGH_CONFIDENCE_STANDARD_TYPES:
        score += 10.0
    if assay_count >= 2:
        score += 6.0
    if document_count >= 2:
        score += 4.0
    if min_side_count <= 1:
        score -= 6.0
    return round(max(20.0, min(95.0, score)), 2)


def _row_diversity_count(rows: list[dict], field: str) -> int:
    return len({row.get(field) for row in rows if row.get(field)})


def _mean_optional(values: list[float | int | None]) -> float | None:
    parsed = [float(value) for value in values if value not in {None, ""}]
    return round(mean(parsed), 4) if parsed else None


def _rule_activity_judgment(family_summaries: list[dict], support_threshold: float = 0.3) -> tuple[str, str]:
    if not family_summaries:
        return "inconclusive", "No target-family activity comparison was available."
    supported = sum(1 for row in family_summaries if row["delta_pchembl"] >= support_threshold)
    contradicted = sum(1 for row in family_summaries if row["delta_pchembl"] <= -support_threshold)
    neutral = len(family_summaries) - supported - contradicted
    mean_delta = mean(row["delta_pchembl"] for row in family_summaries)
    supported_weight = sum(
        float(row.get("assay_confidence_score") or 50.0) / 100.0
        for row in family_summaries
        if row["delta_pchembl"] >= support_threshold
    )
    contradicted_weight = sum(
        float(row.get("assay_confidence_score") or 50.0) / 100.0
        for row in family_summaries
        if row["delta_pchembl"] <= -support_threshold
    )
    mean_confidence = _mean_optional([row.get("assay_confidence_score") for row in family_summaries])
    if supported_weight > contradicted_weight:
        return (
            "supported",
            f"{supported} target-family groups improved by at least {support_threshold} pChEMBL; "
            f"{contradicted} moved against the rule; mean family delta {mean_delta:+.2f}; "
            f"confidence-weighted support {supported_weight:.2f} vs {contradicted_weight:.2f}."
            + (f" Mean assay confidence {mean_confidence:.1f}." if mean_confidence is not None else ""),
        )
    if contradicted_weight > supported_weight:
        return (
            "contradicted",
            f"{contradicted} target-family groups decreased by at least {support_threshold} pChEMBL; "
            f"{supported} supported the rule; mean family delta {mean_delta:+.2f}; "
            f"confidence-weighted support {supported_weight:.2f} vs {contradicted_weight:.2f}."
            + (f" Mean assay confidence {mean_confidence:.1f}." if mean_confidence is not None else ""),
        )
    return (
        "inconclusive",
        f"Target-family evidence is mixed or weak: {supported} supported, {contradicted} contradicted, {neutral} neutral; "
        f"confidence-weighted support {supported_weight:.2f} vs {contradicted_weight:.2f}.",
    )


def transform_activity_summaries(
    *,
    mmp_rows: list[dict],
    mapping_rows: list[dict],
    activity_rows: list[dict],
    cliff_threshold: float = 1.0,
    max_target_summaries: int = 20,
) -> list[dict]:
    mmp_by_id = {str(row.get("transform_id")): row for row in mmp_rows}
    activity_by_molecule = _activity_values_by_molecule(activity_rows)
    summaries: list[dict] = []
    for mapping in mapping_rows:
        mmp_row = mmp_by_id.get(str(mapping.get("transform_id")))
        if not mmp_row:
            continue
        orientation = _orientation_for_mapping(mapping, mmp_row)
        from_ids = list(mmp_row.get("from_example_molecule_ids") or [])
        to_ids = list(mmp_row.get("to_example_molecule_ids") or [])
        if orientation == "reverse":
            from_ids, to_ids = to_ids, from_ids
        elif orientation == "unknown" and not (from_ids and to_ids):
            examples = list(mmp_row.get("example_molecule_ids") or [])
            midpoint = len(examples) // 2
            from_ids, to_ids = examples[:midpoint], examples[midpoint:]

        from_values = _molecule_group_values(activity_by_molecule, from_ids)
        to_values = _molecule_group_values(activity_by_molecule, to_ids)
        from_family_values = _molecule_family_rows(activity_by_molecule, from_ids)
        to_family_values = _molecule_family_rows(activity_by_molecule, to_ids)
        target_summaries = []
        for key in sorted(set(from_values).intersection(to_values)):
            left = from_values[key]
            right = to_values[key]
            if not left or not right:
                continue
            mean_from = mean(left)
            mean_to = mean(right)
            delta = mean_to - mean_from
            confidence_score = _assay_confidence_score(
                from_activity_count=len(left),
                to_activity_count=len(right),
                standard_type=key[1],
            )
            target_summaries.append(
                {
                    "target_chembl_id": key[0],
                    "standard_type": key[1],
                    "from_activity_count": len(left),
                    "to_activity_count": len(right),
                    "replicate_count": len(left) + len(right),
                    "mean_from_pchembl": round(mean_from, 4),
                    "mean_to_pchembl": round(mean_to, 4),
                    "delta_pchembl": round(delta, 4),
                    "activity_cliff": abs(delta) >= cliff_threshold,
                    "assay_confidence": _assay_confidence_bucket(confidence_score),
                    "assay_confidence_score": confidence_score,
                    "uncertainty_score": _uncertainty_from_confidence(confidence_score),
                }
            )
        target_summaries.sort(key=lambda row: abs(row["delta_pchembl"]), reverse=True)
        family_summaries = []
        for key in sorted(set(from_family_values).intersection(to_family_values)):
            left_rows = from_family_values[key]
            right_rows = to_family_values[key]
            if not left_rows or not right_rows:
                continue
            mean_from = _mean_pchembl(left_rows)
            mean_to = _mean_pchembl(right_rows)
            delta = mean_to - mean_from
            from_target_count = len({row.get("target_chembl_id") for row in left_rows if row.get("target_chembl_id")})
            to_target_count = len({row.get("target_chembl_id") for row in right_rows if row.get("target_chembl_id")})
            confidence_score = _assay_confidence_score(
                from_activity_count=len(left_rows),
                to_activity_count=len(right_rows),
                from_target_count=from_target_count,
                to_target_count=to_target_count,
                standard_type=key[1],
                assay_count=_row_diversity_count([*left_rows, *right_rows], "assay_chembl_id"),
                document_count=_row_diversity_count([*left_rows, *right_rows], "document_chembl_id"),
            )
            family_summaries.append(
                {
                    "target_family": key[0],
                    "target_family_normalized": key[0],
                    "target_family_label": normalize_target_family(key[0]).get("target_family_label"),
                    "target_family_weight": normalize_target_family(key[0]).get("target_family_weight"),
                    "standard_type": key[1],
                    "from_activity_count": len(left_rows),
                    "to_activity_count": len(right_rows),
                    "replicate_count": len(left_rows) + len(right_rows),
                    "from_target_count": from_target_count,
                    "to_target_count": to_target_count,
                    "assay_count": _row_diversity_count([*left_rows, *right_rows], "assay_chembl_id"),
                    "document_count": _row_diversity_count([*left_rows, *right_rows], "document_chembl_id"),
                    "mean_from_pchembl": round(mean_from, 4),
                    "mean_to_pchembl": round(mean_to, 4),
                    "delta_pchembl": round(delta, 4),
                    "activity_cliff": abs(delta) >= cliff_threshold,
                    "assay_confidence": _assay_confidence_bucket(confidence_score),
                    "assay_confidence_score": confidence_score,
                    "uncertainty_score": _uncertainty_from_confidence(confidence_score),
                }
            )
        family_summaries.sort(key=lambda row: abs(row["delta_pchembl"]), reverse=True)
        family_deltas = [row["delta_pchembl"] for row in family_summaries]
        rule_judgment, rule_judgment_note = _rule_activity_judgment(family_summaries)
        deltas = [row["delta_pchembl"] for row in target_summaries]
        cliff_count = sum(1 for row in target_summaries if row["activity_cliff"])
        confidence_basis = family_summaries or target_summaries
        confidence_score = _mean_optional([row.get("assay_confidence_score") for row in confidence_basis])
        uncertainty_score = _mean_optional([row.get("uncertainty_score") for row in confidence_basis])
        risk = "none"
        if cliff_count >= 3 or any(abs(delta) >= 2.0 for delta in deltas):
            risk = "high"
        elif cliff_count:
            risk = "medium"
        elif target_summaries:
            risk = "low"
        summary_key = f"{mapping.get('mapping_id')}:{mapping.get('rule_id')}:{mapping.get('transform_id')}"
        digest = hashlib.sha1(summary_key.encode("utf-8")).hexdigest()[:14].upper()
        summaries.append(
            {
                "summary_id": f"TAS-{digest}",
                "mapping_id": mapping.get("mapping_id"),
                "rule_id": mapping.get("rule_id"),
                "replacement_label": mapping.get("replacement_label"),
                "transform_id": mapping.get("transform_id"),
                "orientation": orientation,
                "from_molecule_count": len(set(from_ids)),
                "to_molecule_count": len(set(to_ids)),
                "target_summary_count": len(target_summaries),
                "target_family_summary_count": len(family_summaries),
                "activity_cliff_count": cliff_count,
                "mean_delta_pchembl": round(mean(deltas), 4) if deltas else None,
                "mean_family_delta_pchembl": round(mean(family_deltas), 4) if family_deltas else None,
                "max_abs_delta_pchembl": round(max(abs(delta) for delta in deltas), 4) if deltas else None,
                "activity_cliff_risk": risk,
                "rule_activity_judgment": rule_judgment,
                "rule_activity_judgment_note": rule_judgment_note,
                "replicate_count": sum(int(row.get("replicate_count") or 0) for row in confidence_basis),
                "assay_confidence": _assay_confidence_bucket(confidence_score),
                "assay_confidence_score": confidence_score,
                "uncertainty_score": uncertainty_score,
                "target_summaries": target_summaries[:max_target_summaries],
                "target_family_summaries": family_summaries[:max_target_summaries],
            }
        )
    summaries.sort(key=lambda row: (row["activity_cliff_count"], row.get("max_abs_delta_pchembl") or 0), reverse=True)
    return summaries


def auto_mmp_activity_summaries(
    *,
    mmp_rows: list[dict],
    activity_rows: list[dict],
    min_pair_count: int = 2,
    max_transforms: int = 250,
    cliff_threshold: float = 1.0,
) -> list[dict]:
    mapping_rows = []
    ranked = sorted(mmp_rows, key=lambda row: (int(row.get("pair_count") or 0), int(row.get("example_count") or 0)), reverse=True)
    for row in ranked:
        if int(row.get("pair_count") or 0) < min_pair_count:
            continue
        if not (row.get("from_example_molecule_ids") and row.get("to_example_molecule_ids")):
            continue
        mapping_rows.append(
            {
                "mapping_id": f"AUTO-{row.get('transform_id')}",
                "rule_id": "AUTO_MMP",
                "replacement_label": f"{row.get('variable_from_smiles')}->{row.get('variable_to_smiles')}",
                "transform_id": row.get("transform_id"),
                "variable_from_smiles": row.get("variable_from_smiles"),
                "variable_to_smiles": row.get("variable_to_smiles"),
            }
        )
        if len(mapping_rows) >= max_transforms:
            break
    return transform_activity_summaries(
        mmp_rows=mmp_rows,
        mapping_rows=mapping_rows,
        activity_rows=activity_rows,
        cliff_threshold=cliff_threshold,
    )


def aggregate_transform_activity(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        family_rows = row.get("target_family_summaries") or []
        target_rows = row.get("target_summaries") or []
        confidence = str(row.get("assay_confidence") or "none")
        family_keys = {(str(item.get("target_family") or "unspecified"), str(item.get("standard_type") or "unspecified")) for item in family_rows}
        if not family_keys:
            family_keys = {(str(item.get("target_chembl_id") or "unspecified"), str(item.get("standard_type") or "unspecified")) for item in target_rows}
        if not family_keys:
            family_keys = {("unspecified", "unspecified")}
        for target_family, assay_type in family_keys:
            grouped[
                (
                    str(row.get("rule_id") or "unmapped"),
                    str(row.get("replacement_label") or row.get("transform_id")),
                    target_family,
                    assay_type,
                )
            ].append({**row, "confidence_bucket": confidence})
    aggregates = []
    for (rule_id, replacement_label, target_family, assay_type), items in grouped.items():
        deltas = [float(item.get("mean_family_delta_pchembl") or item.get("mean_delta_pchembl")) for item in items if item.get("mean_family_delta_pchembl") is not None or item.get("mean_delta_pchembl") is not None]
        max_abs = [float(item.get("max_abs_delta_pchembl")) for item in items if item.get("max_abs_delta_pchembl") is not None]
        risk_counts = Counter(str(item.get("activity_cliff_risk") or "none") for item in items)
        confidence_counts = Counter(str(item.get("confidence_bucket") or "none") for item in items)
        uncertainty_values = [
            float(item.get("uncertainty_score"))
            for item in items
            if item.get("uncertainty_score") not in {None, ""}
        ]
        aggregates.append(
            {
                "rule_id": rule_id,
                "replacement_label": replacement_label,
                "target_family": target_family,
                "assay_type": assay_type,
                "summary_count": len(items),
                "target_summary_count": sum(int(item.get("target_summary_count") or 0) for item in items),
                "target_family_summary_count": sum(int(item.get("target_family_summary_count") or 0) for item in items),
                "activity_cliff_count": sum(int(item.get("activity_cliff_count") or 0) for item in items),
                "mean_delta_pchembl": round(mean(deltas), 4) if deltas else None,
                "max_abs_delta_pchembl": round(max(max_abs), 4) if max_abs else None,
                "risk_counts": dict(risk_counts.most_common()),
                "confidence_counts": dict(confidence_counts.most_common()),
                "mean_uncertainty_score": round(mean(uncertainty_values), 4) if uncertainty_values else None,
            }
        )
    aggregates.sort(key=lambda row: (row["activity_cliff_count"], row.get("max_abs_delta_pchembl") or 0, row["summary_count"]), reverse=True)
    return aggregates


def save_transform_activity_report(rows: list[dict], path: str | Path, *, auto_rows: list[dict] | None = None) -> dict:
    combined = [*rows, *(auto_rows or [])]
    report = {
        "summary_count": len(rows),
        "auto_summary_count": len(auto_rows or []),
        "combined_summary_count": len(combined),
        "summaries_with_activity": sum(1 for row in rows if row.get("target_summary_count")),
        "activity_cliff_summary_count": sum(1 for row in rows if row.get("activity_cliff_count")),
        "summaries_with_target_family_activity": sum(1 for row in rows if row.get("target_family_summary_count")),
        "rule_activity_judgment_counts": {
            label: sum(1 for row in rows if row.get("rule_activity_judgment") == label)
            for label in ["supported", "contradicted", "inconclusive"]
        },
        "assay_confidence_counts": {
            label: sum(1 for row in rows if row.get("assay_confidence") == label)
            for label in ["high", "medium", "low", "none"]
        },
        "summaries": rows,
        "auto_summaries": auto_rows or [],
        "aggregates": aggregate_transform_activity(combined),
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def save_activity_report(rows: list[dict], path: str | Path) -> dict:
    report = {
        **validate_activity_evidence(rows),
        "activity_cliff_summary": activity_cliff_summary(rows),
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
