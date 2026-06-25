from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from rdkit import Chem

from .database import initialize_database
from .feedback import _float_or_none
from .mmp import load_mmp_evidence
from .target_context import normalize_assay_type
from .target_families import normalize_target_family
from .transform_priors import load_transform_priors, transform_prior_lookup


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")
DEFAULT_TRANSFORM_PRIORS_PATH = Path("data/rules/transform_priors.yaml")
DEFAULT_MMP_EVIDENCE_PATH = Path("data/mmp/chembl_mmp_transform_evidence.yaml")


def evidence_from_prior(prior: dict | None) -> dict:
    if not prior:
        return {}
    return {
        "transform_evidence_level": prior.get("evidence_level"),
        "transform_mmp_pair_count": prior.get("mmp_pair_count", 0),
        "transform_confidence": prior.get("confidence"),
        "transform_activity_cliff_risk": prior.get("activity_cliff_risk"),
        "transform_expected_effects": prior.get("expected_effects") or {},
        "transform_evidence_note": prior.get("evidence_note"),
    }


def canonical_attachment_smiles(smiles: str | None) -> str | None:
    if not smiles:
        return None
    if "*" not in str(smiles):
        return None
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        return None
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        return None
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def _candidate_source_fragments(row: dict, selected_site: dict | None = None) -> set[str]:
    fragments = set()
    label = str(row.get("replacement_label") or "")
    if "->" in label:
        left = label.split("->", 1)[0].strip()
        halogen = {"F": "F[*:1]", "Cl": "Cl[*:1]", "Br": "Br[*:1]", "I": "I[*:1]"}.get(left)
        if halogen:
            fragments.add(halogen)
        if left == "OMe":
            fragments.update({"CO[*:1]", "[*:1]OC"})
    site_type = (selected_site or {}).get("site_type") or row.get("site_type")
    if site_type == "aromatic_halide" and not fragments:
        fragments.update({"Cl[*:1]", "Br[*:1]", "I[*:1]", "F[*:1]"})
    return {canonical for canonical in (canonical_attachment_smiles(item) for item in fragments) if canonical}


def _mmp_rows_with_canonical(mmp_rows: list[dict]) -> list[dict]:
    rows = []
    for row in mmp_rows:
        left = canonical_attachment_smiles(row.get("variable_from_smiles"))
        right = canonical_attachment_smiles(row.get("variable_to_smiles"))
        if not left or not right:
            continue
        rows.append({**row, "_canonical_from": left, "_canonical_to": right})
    return rows


def _oriented_delta(match: dict, field: str) -> float | None:
    value = _float_or_none(match.get(field))
    if value is None:
        return None
    return -value if match.get("_reverse_delta") else value


def _weighted_delta(matches: list[dict], field: str) -> float | None:
    values = []
    for match in matches:
        delta = _oriented_delta(match, field)
        if delta is None:
            continue
        weight = max(int(match.get("pair_count") or 1), 1)
        values.append((delta, weight))
    if not values:
        return None
    total = sum(weight for _delta, weight in values)
    return round(sum(delta * weight for delta, weight in values) / total, 4)


def _precedent_strength(matches: list[dict]) -> str:
    if not matches:
        return "none"
    exact_pair_count = sum(int(item.get("pair_count") or 0) for item in matches if item.get("mmp_match_type", "").startswith("exact_pair"))
    total_pair_count = sum(int(item.get("pair_count") or 0) for item in matches)
    if exact_pair_count >= 4 or total_pair_count >= 12:
        return "high"
    if exact_pair_count >= 1 or total_pair_count >= 4:
        return "medium"
    return "low"


def candidate_mmp_precedent(
    row: dict,
    *,
    mmp_rows: list[dict] | None = None,
    selected_site: dict | None = None,
    max_examples: int = 3,
) -> dict:
    target = canonical_attachment_smiles(row.get("substituent_smiles"))
    if not target:
        result = {
            "mmp_precedent_strength": "none",
            "mmp_precedent_count": 0,
            "mmp_pair_count": 0,
            "mmp_example_count": 0,
            "mmp_precedent_note": "No canonical attachment fragment available for MMP matching.",
        }
        combined = {**row, **result}
        result["mmp_contradiction_flags"] = ";".join(mmp_contradiction_flags(combined))
        result["mmp_precedent_score"] = round(score_mmp_precedent(combined), 2)
        return result

    evidence = _mmp_rows_with_canonical(mmp_rows or load_mmp_evidence(DEFAULT_MMP_EVIDENCE_PATH))
    sources = _candidate_source_fragments(row, selected_site=selected_site)
    matches = []
    for item in evidence:
        left = item["_canonical_from"]
        right = item["_canonical_to"]
        match_type = None
        reverse_delta = False
        if target == right and left in sources:
            match_type = "exact_pair_forward"
        elif target == left and right in sources:
            match_type = "exact_pair_reverse"
            reverse_delta = True
        elif target == right:
            match_type = "exact_target_as_to"
        elif target == left:
            match_type = "exact_target_as_from"
            reverse_delta = True
        if match_type:
            matches.append({**item, "mmp_match_type": match_type, "_reverse_delta": reverse_delta})

    matches.sort(
        key=lambda item: (
            1 if str(item.get("mmp_match_type")).startswith("exact_pair") else 0,
            int(item.get("pair_count") or 0),
            int(item.get("example_count") or 0),
        ),
        reverse=True,
    )
    top = matches[:max_examples]
    example_ids = []
    for item in top:
        for example_id in item.get("example_molecule_ids") or []:
            if example_id not in example_ids:
                example_ids.append(example_id)
    strength = _precedent_strength(matches)
    pair_count = sum(int(item.get("pair_count") or 0) for item in matches)
    exact_pairs = sum(1 for item in matches if str(item.get("mmp_match_type")).startswith("exact_pair"))
    result = {
        "mmp_precedent_strength": strength,
        "mmp_precedent_count": len(matches),
        "mmp_pair_count": pair_count,
        "mmp_exact_pair_count": exact_pairs,
        "mmp_example_count": sum(int(item.get("example_count") or 0) for item in matches),
        "mmp_transform_ids": ";".join(str(item.get("transform_id")) for item in top if item.get("transform_id")),
        "mmp_example_molecule_ids": ";".join(example_ids[:12]),
        "mmp_mean_delta_fragment_mw": _weighted_delta(matches, "mean_delta_fragment_mw"),
        "mmp_mean_delta_clogp": _weighted_delta(matches, "mean_delta_clogp"),
        "mmp_mean_delta_tpsa": _weighted_delta(matches, "mean_delta_tpsa"),
        "mmp_top_examples": [
            {
                "transform_id": item.get("transform_id"),
                "match_type": item.get("mmp_match_type"),
                "variable_from_smiles": item.get("variable_from_smiles"),
                "variable_to_smiles": item.get("variable_to_smiles"),
                "pair_count": item.get("pair_count"),
                "example_molecule_ids": (item.get("example_molecule_ids") or [])[:5],
                "mean_delta_clogp": _oriented_delta(item, "mean_delta_clogp"),
                "mean_delta_tpsa": _oriented_delta(item, "mean_delta_tpsa"),
            }
            for item in top
        ],
        "mmp_precedent_note": (
            f"{strength} precedent from {len(matches)} exact public MMP variable matches; "
            f"{exact_pairs} matched the candidate source and target fragments."
        )
        if matches
        else "No exact public MMP variable match for the candidate fragment.",
    }
    combined = {**row, **result}
    result["mmp_contradiction_flags"] = ";".join(mmp_contradiction_flags(combined))
    result["mmp_precedent_score"] = round(score_mmp_precedent(combined), 2)
    return result


def mmp_contradiction_flags(row: dict) -> list[str]:
    flags = []
    candidate_clogp = _float_or_none(row.get("delta_clogp"))
    mmp_clogp = _float_or_none(row.get("mmp_mean_delta_clogp"))
    if candidate_clogp is not None and mmp_clogp is not None and abs(candidate_clogp) >= 0.5 and abs(mmp_clogp) >= 0.5:
        if candidate_clogp * mmp_clogp < 0:
            flags.append("clogp_delta_direction_conflict")
    candidate_tpsa = _float_or_none(row.get("delta_tpsa"))
    mmp_tpsa = _float_or_none(row.get("mmp_mean_delta_tpsa"))
    if candidate_tpsa is not None and mmp_tpsa is not None and abs(candidate_tpsa) >= 10.0 and abs(mmp_tpsa) >= 10.0:
        if candidate_tpsa * mmp_tpsa < 0:
            flags.append("tpsa_delta_direction_conflict")
    if str(row.get("transform_activity_cliff_risk") or "").lower() == "high" and row.get("mmp_precedent_strength") == "none":
        flags.append("high_cliff_risk_without_public_mmp")
    return flags


def score_mmp_precedent(row: dict) -> float:
    base = {
        "high": 90.0,
        "medium": 76.0,
        "low": 60.0,
        "none": 42.0,
    }.get(str(row.get("mmp_precedent_strength") or "none"), 42.0)
    exact_pairs = int(row.get("mmp_exact_pair_count") or 0)
    pair_count = int(row.get("mmp_pair_count") or 0)
    if exact_pairs:
        base += min(10.0, exact_pairs * 3.0)
    elif pair_count >= 4:
        base += 4.0
    flags = mmp_contradiction_flags(row)
    base -= 12.0 * len(flags)
    return max(0.0, min(100.0, base))


def annotate_mmp_precedents(
    rows: list[dict],
    *,
    mmp_rows: list[dict] | None = None,
    selected_site: dict | None = None,
) -> list[dict]:
    evidence = mmp_rows if mmp_rows is not None else load_mmp_evidence(DEFAULT_MMP_EVIDENCE_PATH)
    enriched = []
    for row in rows:
        updated = {
            **row,
            **candidate_mmp_precedent(row, mmp_rows=evidence, selected_site=selected_site),
        }
        flags = mmp_contradiction_flags(updated)
        updated["mmp_contradiction_flags"] = ";".join(flags)
        updated["mmp_precedent_score"] = round(score_mmp_precedent(updated), 2)
        enriched.append(updated)
    return enriched


def project_transform_feedback(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> dict[str, dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params: tuple = ()
        where = ""
        if project_name:
            where = "WHERE pr.project_name = ?"
            params = (project_name,)
        rows = conn.execute(
            f"""
            SELECT
                pc.payload_json,
                pf.normalized_score,
                pf.classification
            FROM project_candidate pc
            JOIN project_run pr ON pr.run_id = pc.run_id
            JOIN project_feedback pf
                ON pf.run_id = pc.run_id AND pf.candidate_id = pc.candidate_id
            {where}
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        rule_id = payload.get("functional_rule_id")
        if not rule_id:
            continue
        grouped[str(rule_id)].append(
            {
                "replacement_label": payload.get("replacement_label"),
                "normalized_score": row["normalized_score"],
                "classification": row["classification"],
            }
        )

    summary = {}
    for rule_id, items in grouped.items():
        scores = [_float_or_none(item.get("normalized_score")) for item in items]
        scores = [score for score in scores if score is not None]
        classes = Counter(str(item.get("classification") or "unclassified") for item in items)
        summary[rule_id] = {
            "rule_id": rule_id,
            "replacement_label": next((item.get("replacement_label") for item in items if item.get("replacement_label")), None),
            "project_pair_count": len(items),
            "mean_normalized_score": round(mean(scores), 4) if scores else None,
            "classification_counts": dict(classes.most_common()),
        }
    return summary


def _norm_context(value: str | None) -> str:
    return str(value or "").strip().lower()


def _norm_family_context(value: str | None) -> str:
    if not value:
        return ""
    normalized = normalize_target_family(str(value))
    return str(normalized.get("target_family_normalized") or value).strip().lower()


def _context_activity_summary(items: list[dict], *, target_family: str | None = None, assay_type: str | None = None) -> dict:
    wanted_family = _norm_family_context(target_family)
    wanted_assay = normalize_assay_type(assay_type) or _norm_context(assay_type)
    if not wanted_family and not wanted_assay:
        return {}
    matches = []
    for item in items:
        try:
            payload = json.loads(item.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        for summary in payload.get("target_family_summaries") or []:
            family = _norm_family_context(summary.get("target_family_normalized") or summary.get("target_family"))
            standard_type = normalize_assay_type(summary.get("standard_type")) or _norm_context(summary.get("standard_type"))
            if wanted_family and wanted_family != family:
                continue
            if wanted_assay and wanted_assay != standard_type:
                continue
            matches.append(summary)
    if not matches:
        return {
            "target_context_match_count": 0,
            "target_context_judgment": None,
            "target_context_cliff_risk": None,
            "target_context_mean_delta_pchembl": None,
        }
    deltas = [_float_or_none(item.get("delta_pchembl")) for item in matches]
    deltas = [delta for delta in deltas if delta is not None]
    mean_delta = mean(deltas) if deltas else 0.0
    if mean_delta >= 0.25:
        judgment = "supported"
    elif mean_delta <= -0.25:
        judgment = "contradicted"
    else:
        judgment = "inconclusive"
    max_abs_delta = max((abs(delta) for delta in deltas), default=0.0)
    cliff_count = sum(1 for item in matches if item.get("activity_cliff"))
    if cliff_count and max_abs_delta >= 1.0:
        cliff_risk = "high"
    elif cliff_count or max_abs_delta >= 0.5:
        cliff_risk = "medium"
    else:
        cliff_risk = "low"
    return {
        "target_context_match_count": len(matches),
        "target_context_judgment": judgment,
        "target_context_cliff_risk": cliff_risk,
        "target_context_mean_delta_pchembl": round(mean_delta, 4) if deltas else None,
        "target_context_max_abs_delta_pchembl": round(max_abs_delta, 4),
    }


def transform_activity_feedback(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    target_family: str | None = None,
    assay_type: str | None = None,
) -> dict[str, dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                rule_id,
                replacement_label,
                target_summary_count,
                target_family_summary_count,
                activity_cliff_count,
                mean_delta_pchembl,
                mean_family_delta_pchembl,
                max_abs_delta_pchembl,
                activity_cliff_risk,
                rule_activity_judgment,
                replicate_count,
                assay_confidence,
                assay_confidence_score,
                uncertainty_score,
                payload_json
            FROM transform_activity_summary
            WHERE rule_id IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        try:
            payload = json.loads(item.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        item.update(
            {
                key: payload.get(key, item.get(key))
                for key in [
                    "rule_activity_judgment_note",
                    "replicate_count",
                    "assay_confidence",
                    "assay_confidence_score",
                    "uncertainty_score",
                ]
            }
        )
        grouped[str(item["rule_id"])].append(item)

    summaries = {}
    for rule_id, items in grouped.items():
        judgments = Counter(str(item.get("rule_activity_judgment") or "inconclusive") for item in items)
        supported = judgments.get("supported", 0)
        contradicted = judgments.get("contradicted", 0)
        if supported > contradicted:
            consensus = "supported"
        elif contradicted > supported:
            consensus = "contradicted"
        else:
            consensus = "inconclusive"
        family_deltas = [_float_or_none(item.get("mean_family_delta_pchembl")) for item in items]
        family_deltas = [delta for delta in family_deltas if delta is not None]
        confidence_values = [_float_or_none(item.get("assay_confidence_score")) for item in items]
        confidence_values = [score for score in confidence_values if score is not None]
        uncertainty_values = [_float_or_none(item.get("uncertainty_score")) for item in items]
        uncertainty_values = [score for score in uncertainty_values if score is not None]
        confidence_counts = Counter(str(item.get("assay_confidence") or "none") for item in items)
        context_summary = _context_activity_summary(items, target_family=target_family, assay_type=assay_type)
        summaries[rule_id] = {
            "rule_id": rule_id,
            "replacement_label": next((item.get("replacement_label") for item in items if item.get("replacement_label")), None),
            "activity_summary_count": len(items),
            "activity_replicate_count": sum(int(item.get("replicate_count") or 0) for item in items),
            "activity_target_summary_count": sum(int(item.get("target_summary_count") or 0) for item in items),
            "activity_target_family_summary_count": sum(int(item.get("target_family_summary_count") or 0) for item in items),
            "activity_cliff_count": sum(int(item.get("activity_cliff_count") or 0) for item in items),
            "activity_judgment": consensus,
            "activity_judgment_counts": dict(judgments),
            "assay_confidence_counts": dict(confidence_counts.most_common()),
            "assay_confidence_score": round(mean(confidence_values), 4) if confidence_values else None,
            "uncertainty_score": round(mean(uncertainty_values), 4) if uncertainty_values else None,
            "mean_family_delta_pchembl": round(mean(family_deltas), 4) if family_deltas else None,
            "max_abs_delta_pchembl": max((_float_or_none(item.get("max_abs_delta_pchembl")) or 0 for item in items), default=0),
            "activity_cliff_risk": max(
                (str(item.get("activity_cliff_risk") or "none") for item in items),
                key=lambda label: {"none": 0, "low": 1, "medium": 2, "high": 3}.get(label, 0),
                default="none",
            ),
            "target_context": context_summary,
        }
    return summaries


def build_transform_evidence_report(
    *,
    priors_path: str | Path = DEFAULT_TRANSFORM_PRIORS_PATH,
    mmp_evidence_path: str | Path = DEFAULT_MMP_EVIDENCE_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
) -> dict:
    priors = load_transform_priors(priors_path)
    by_rule = transform_prior_lookup(priors)
    feedback = project_transform_feedback(db_path=db_path, project_name=project_name)
    activity_feedback = transform_activity_feedback(db_path=db_path)
    entries = []
    for rule_id in sorted(set(by_rule).union(feedback).union(activity_feedback)):
        prior = by_rule.get(rule_id, {})
        project = feedback.get(rule_id, {})
        activity = activity_feedback.get(rule_id, {})
        entries.append(
            {
                "rule_id": rule_id,
                "replacement_label": prior.get("replacement_label") or project.get("replacement_label") or activity.get("replacement_label"),
                "evidence_level": prior.get("evidence_level"),
                "prior_score": prior.get("prior_score"),
                "confidence": prior.get("confidence"),
                "mmp_pair_count": prior.get("mmp_pair_count", 0),
                "project_pair_count": project.get("project_pair_count", 0),
                "mean_normalized_score": project.get("mean_normalized_score"),
                "activity_summary_count": activity.get("activity_summary_count", 0),
                "activity_replicate_count": activity.get("activity_replicate_count", 0),
                "activity_target_family_summary_count": activity.get("activity_target_family_summary_count", 0),
                "activity_judgment": activity.get("activity_judgment", "inconclusive"),
                "activity_judgment_counts": activity.get("activity_judgment_counts") or {},
                "assay_confidence_score": activity.get("assay_confidence_score"),
                "uncertainty_score": activity.get("uncertainty_score"),
                "mean_family_delta_pchembl": activity.get("mean_family_delta_pchembl"),
                "activity_cliff_count": activity.get("activity_cliff_count", 0),
                "activity_cliff_risk": prior.get("activity_cliff_risk"),
                "expected_effects": prior.get("expected_effects") or {},
                "evidence_note": prior.get("evidence_note"),
                "classification_counts": project.get("classification_counts") or {},
            }
        )
    public_mmp = load_mmp_evidence(mmp_evidence_path)
    return {
        "project_name": project_name,
        "transform_count": len(entries),
        "project_evidence_count": sum(1 for item in entries if item.get("project_pair_count")),
        "public_mmp_evidence_count": len(public_mmp),
        "top_public_mmp_examples": public_mmp[:20],
        "entries": entries,
    }


def write_transform_evidence_report(report: dict, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def write_transform_evidence_markdown(report: dict, output_path: str | Path) -> None:
    lines = [
        "# Transform Evidence Report",
        "",
        f"Project: {report.get('project_name') or 'all'}",
        f"Transforms: {report.get('transform_count')}",
        f"Transforms with project evidence: {report.get('project_evidence_count')}",
        f"Public MMP transforms: {report.get('public_mmp_evidence_count')}",
        "",
        "## Entries",
        "",
    ]
    for item in report.get("entries", []):
        lines.append(
            f"- {item.get('rule_id')} {item.get('replacement_label')}: "
            f"evidence={item.get('evidence_level')}, prior={item.get('prior_score')}, "
            f"confidence={item.get('confidence')}, project_pairs={item.get('project_pair_count')}"
        )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
