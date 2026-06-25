from __future__ import annotations

import json
from collections import Counter


def _float_or_none(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_flags(value) -> list[str]:
    return [item for item in str(value or "").split(";") if item]


def _list_or_json(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _judgment_from_score(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= 70:
        return "supportive"
    if score <= 45:
        return "contradictory"
    return "mixed"


def _row(source: str, judgment: str, score, strength=None, details=None, evidence_count=None) -> dict:
    return {
        "evidence_source": source,
        "judgment": judgment or "missing",
        "score": score,
        "strength": strength,
        "evidence_count": evidence_count,
        "details": details,
    }


def candidate_evidence_matrix(candidate: dict) -> list[dict]:
    """Return side-by-side evidence channels for one candidate row."""
    rows: list[dict] = []
    rows.append(
        _row(
            "global_mmp",
            "contradictory" if _split_flags(candidate.get("mmp_contradiction_flags")) else _judgment_from_score(_float_or_none(candidate.get("mmp_precedent_score"))),
            candidate.get("mmp_precedent_score"),
            candidate.get("mmp_precedent_strength"),
            candidate.get("mmp_transform_ids"),
            candidate.get("mmp_pair_count") or candidate.get("mmp_exact_pair_count"),
        )
    )
    rows.append(
        _row(
            "transform_activity",
            candidate.get("rule_activity_judgment") or _judgment_from_score(_float_or_none(candidate.get("transform_activity_score"))),
            candidate.get("transform_activity_score"),
            candidate.get("rule_activity_confidence"),
            candidate.get("transform_activity_cliff_risk"),
            candidate.get("activity_target_summary_count") or candidate.get("activity_target_family_summary_count"),
        )
    )
    rows.append(
        _row(
            "target_family",
            candidate.get("evidence_context_judgment") or "missing",
            candidate.get("evidence_consistency_score"),
            candidate.get("evidence_target_family_label") or candidate.get("evidence_target_family_normalized"),
            candidate.get("evidence_context_mean_delta_pchembl"),
            candidate.get("evidence_context_match_count"),
        )
    )
    rows.append(
        _row(
            "project_feedback",
            _judgment_from_score(_float_or_none(candidate.get("evidence_project_mean_score"))),
            candidate.get("evidence_project_mean_score"),
            None,
            candidate.get("evidence_conflict_flags"),
            None,
        )
    )
    rows.append(
        _row(
            "scaffold_local",
            _judgment_from_score(_float_or_none(candidate.get("scaffold_local_evidence_score"))),
            candidate.get("scaffold_local_evidence_score"),
            candidate.get("scaffold_local_evidence_strength"),
            candidate.get("scaffold_local_evidence_ids"),
            candidate.get("scaffold_local_evidence_count"),
        )
    )
    rows.append(
        _row(
            "endpoint_gate",
            candidate.get("endpoint_gate_decision") or "missing",
            candidate.get("endpoint_gate_go_score"),
            candidate.get("endpoint_gate_endpoint"),
            candidate.get("endpoint_gate_reason"),
            None,
        )
    )
    return rows


def candidate_evidence_examples(candidate: dict, *, max_examples: int = 8) -> list[dict]:
    """Return compact matched analog/replacement examples backing the evidence matrix."""
    examples: list[dict] = []
    for item in _list_or_json(candidate.get("mmp_top_examples")):
        if not isinstance(item, dict):
            continue
        examples.append(
            {
                "evidence_source": "global_mmp",
                "example_id": item.get("transform_id"),
                "match_type": item.get("match_type"),
                "source_structure_smiles": item.get("variable_from_smiles"),
                "target_structure_smiles": item.get("variable_to_smiles"),
                "pair_count": item.get("pair_count"),
                "example_molecule_ids": ";".join(item.get("example_molecule_ids") or []),
                "activity_delta": None,
                "source_name": "public_mmp",
            }
        )
    for item in _list_or_json(candidate.get("scaffold_local_evidence_examples")):
        if not isinstance(item, dict):
            continue
        examples.append(
            {
                "evidence_source": "scaffold_local",
                "example_id": item.get("replacement_id"),
                "match_type": "reverse" if item.get("reverse_match") else "forward",
                "source_structure_smiles": item.get("source_smiles"),
                "target_structure_smiles": item.get("target_smiles"),
                "pair_count": item.get("weight"),
                "example_molecule_ids": "",
                "activity_delta": item.get("activity_delta"),
                "source_name": item.get("source_name") or item.get("local_evidence_type"),
            }
        )
    seen = set()
    compact = []
    for item in examples:
        key = (
            item.get("evidence_source"),
            item.get("example_id"),
            item.get("source_structure_smiles"),
            item.get("target_structure_smiles"),
        )
        if key in seen:
            continue
        seen.add(key)
        compact.append(item)
        if len(compact) >= max_examples:
            break
    return compact


def candidate_evidence_bundle(candidate: dict) -> dict:
    matrix = candidate_evidence_matrix(candidate)
    examples = candidate_evidence_examples(candidate)
    return {
        "candidate_id": candidate.get("candidate_id"),
        "evidence_matrix": matrix,
        "matched_analog_examples": examples,
        "example_count": len(examples),
        "disagreement": evidence_disagreement_summary([candidate])["candidates"],
    }


def evidence_disagreement_summary(candidates: list[dict]) -> dict:
    """Summarize evidence-channel disagreement across candidate rows."""
    candidate_rows = []
    source_counter: Counter[str] = Counter()
    severe_flags = Counter()
    for candidate in candidates:
        matrix = candidate_evidence_matrix(candidate)
        judgments = {row["evidence_source"]: row["judgment"] for row in matrix if row["judgment"] != "missing"}
        supportive = {source for source, judgment in judgments.items() if judgment in {"supportive", "supported", "go"}}
        contradictory = {
            source
            for source, judgment in judgments.items()
            if judgment in {"contradictory", "contradicted", "stop", "reject"}
        }
        flags = _split_flags(candidate.get("evidence_conflict_flags"))
        for flag in flags:
            severe_flags[flag] += 1
        if supportive and contradictory:
            for source in supportive.union(contradictory):
                source_counter[source] += 1
            candidate_rows.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "score": candidate.get("score"),
                    "replacement_label": candidate.get("replacement_label"),
                    "supportive_sources": ";".join(sorted(supportive)),
                    "contradictory_sources": ";".join(sorted(contradictory)),
                    "conflict_flags": ";".join(flags),
                }
            )
    return {
        "candidate_count": len(candidates),
        "disagreement_count": len(candidate_rows),
        "disagreement_rate": round(len(candidate_rows) / len(candidates), 4) if candidates else 0.0,
        "source_disagreement_counts": dict(source_counter.most_common()),
        "conflict_flag_counts": dict(severe_flags.most_common()),
        "candidates": candidate_rows,
    }
