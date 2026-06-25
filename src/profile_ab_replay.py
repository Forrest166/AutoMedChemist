from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline import run_mvp


DEFAULT_PROFILE_AB_REPLAY_REPORT_PATH = Path("data/projects/demo/profile_ab_replay_report.json")
DEFAULT_PROFILE_AB_REPLAY_CSV_PATH = Path("data/projects/demo/profile_ab_replay_report.csv")


def _float(value: Any, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_key(row: dict) -> str:
    return str(row.get("smiles") or row.get("canonical_smiles") or row.get("candidate_id") or "")


def _profile_id(result: dict, fallback: str) -> str:
    profile = result.get("scoring_profile") or {}
    return str(profile.get("profile_id") or profile.get("name") or fallback)


def compare_profile_run_results(
    base_result: dict,
    candidate_result: dict,
    *,
    top_n: int = 20,
    base_label: str = "base",
    candidate_label: str = "candidate",
) -> dict:
    base_rows = [dict(row) for row in base_result.get("candidates") or []]
    candidate_rows = [dict(row) for row in candidate_result.get("candidates") or []]
    base_sorted = sorted(base_rows, key=lambda row: _float(row.get("score")), reverse=True)
    candidate_sorted = sorted(candidate_rows, key=lambda row: _float(row.get("score")), reverse=True)
    base_by_key = {_candidate_key(row): row for row in base_sorted if _candidate_key(row)}
    candidate_by_key = {_candidate_key(row): row for row in candidate_sorted if _candidate_key(row)}
    base_rank = {_candidate_key(row): idx for idx, row in enumerate(base_sorted, start=1) if _candidate_key(row)}
    candidate_rank = {_candidate_key(row): idx for idx, row in enumerate(candidate_sorted, start=1) if _candidate_key(row)}
    base_top = set(list(base_rank)[: int(top_n)])
    candidate_top = set(list(candidate_rank)[: int(top_n)])
    all_keys = sorted(set(base_by_key) | set(candidate_by_key), key=lambda key: candidate_rank.get(key, base_rank.get(key, 999999)))
    rows = []
    score_deltas = []
    promoted_count = 0
    demoted_count = 0
    for key in all_keys:
        base = base_by_key.get(key, {})
        candidate = candidate_by_key.get(key, {})
        base_score = _float(base.get("score")) if base else None
        candidate_score = _float(candidate.get("score")) if candidate else None
        score_delta = None if base_score is None or candidate_score is None else round(candidate_score - base_score, 4)
        if score_delta is not None:
            score_deltas.append(score_delta)
        rank_delta = None
        if key in base_rank and key in candidate_rank:
            rank_delta = int(base_rank[key]) - int(candidate_rank[key])
            if rank_delta > 0:
                promoted_count += 1
            elif rank_delta < 0:
                demoted_count += 1
        membership = "shared"
        if key in candidate_top and key not in base_top:
            membership = "new_candidate_top"
        elif key in base_top and key not in candidate_top:
            membership = "lost_base_top"
        elif key not in base_by_key:
            membership = "candidate_only"
        elif key not in candidate_by_key:
            membership = "base_only"
        rows.append(
            {
                "candidate_key": key,
                "base_candidate_id": base.get("candidate_id"),
                "candidate_candidate_id": candidate.get("candidate_id"),
                "base_rank": base_rank.get(key),
                "candidate_rank": candidate_rank.get(key),
                "rank_delta": rank_delta,
                "base_score": base_score,
                "candidate_score": candidate_score,
                "score_delta": score_delta,
                "membership": membership,
                "base_recommendation": base.get("recommendation"),
                "candidate_recommendation": candidate.get("recommendation"),
                "endpoint_family_residual_score_delta": candidate.get("endpoint_family_residual_score_delta"),
                "multi_objective_score_delta": candidate.get("multi_objective_score_delta"),
                "strategy_learning_score_delta": candidate.get("strategy_learning_score_delta"),
                "enumeration_type": candidate.get("enumeration_type") or base.get("enumeration_type"),
                "site_type": candidate.get("site_type") or base.get("site_type"),
                "replacement_label": candidate.get("replacement_label") or base.get("replacement_label"),
            }
        )
    status = "ready" if rows else "empty"
    changed_top_n_count = len(base_top.symmetric_difference(candidate_top))
    review_flag_count = changed_top_n_count + sum(1 for value in score_deltas if abs(value) >= 5.0)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "review_status": "review_required" if review_flag_count else "no_material_change",
        "base_profile_id": _profile_id(base_result, base_label),
        "candidate_profile_id": _profile_id(candidate_result, candidate_label),
        "top_n": int(top_n),
        "base_candidate_count": len(base_rows),
        "candidate_candidate_count": len(candidate_rows),
        "shared_candidate_count": len(set(base_by_key) & set(candidate_by_key)),
        "changed_top_n_count": changed_top_n_count,
        "promoted_count": promoted_count,
        "demoted_count": demoted_count,
        "max_score_delta": round(max((abs(value) for value in score_deltas), default=0.0), 4),
        "mean_score_delta": round(sum(score_deltas) / len(score_deltas), 4) if score_deltas else 0.0,
        "membership_counts": dict(Counter(row["membership"] for row in rows).most_common()),
        "rows": rows,
    }


def build_profile_ab_replay_report(
    *,
    smiles: str,
    direction: str,
    base_profile_path: str | Path | None = None,
    candidate_profile_path: str | Path | None = None,
    project_name: str | None = "demo_learning",
    target_context: dict | None = None,
    site_index: int = 0,
    top_n: int = 20,
    max_candidates: int = 80,
    max_substituents: int = 80,
    max_network_replacements: int = 25,
    max_scaffold_replacements: int = 20,
    include_advanced: bool = True,
    include_risky: bool = False,
) -> dict:
    base = run_mvp(
        smiles,
        direction,
        scoring_profile_path=base_profile_path,
        project_name=project_name,
        target_context=target_context,
        site_index=site_index,
        max_candidates=max_candidates,
        max_substituents=max_substituents,
        max_network_replacements=max_network_replacements,
        max_scaffold_replacements=max_scaffold_replacements,
        include_advanced=include_advanced,
        include_risky=include_risky,
    )
    candidate = run_mvp(
        smiles,
        direction,
        scoring_profile_path=candidate_profile_path,
        project_name=project_name,
        target_context=target_context,
        site_index=site_index,
        max_candidates=max_candidates,
        max_substituents=max_substituents,
        max_network_replacements=max_network_replacements,
        max_scaffold_replacements=max_scaffold_replacements,
        include_advanced=include_advanced,
        include_risky=include_risky,
    )
    report = compare_profile_run_results(
        base,
        candidate,
        top_n=top_n,
        base_label=str(base_profile_path or "default"),
        candidate_label=str(candidate_profile_path or "candidate"),
    )
    report["inputs"] = {
        "smiles": smiles,
        "direction": direction,
        "base_profile_path": str(Path(base_profile_path).resolve()) if base_profile_path else None,
        "candidate_profile_path": str(Path(candidate_profile_path).resolve()) if candidate_profile_path else None,
        "project_name": project_name,
        "target_context": target_context or {},
        "site_index": site_index,
        "max_candidates": max_candidates,
        "max_substituents": max_substituents,
    }
    return report


def write_profile_ab_replay_report(
    report: dict,
    output_path: str | Path = DEFAULT_PROFILE_AB_REPLAY_REPORT_PATH,
    *,
    csv_path: str | Path | None = DEFAULT_PROFILE_AB_REPLAY_CSV_PATH,
) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = [dict(row) for row in report.get("rows") or []]
    preferred = [
        "candidate_key",
        "base_candidate_id",
        "candidate_candidate_id",
        "base_rank",
        "candidate_rank",
        "rank_delta",
        "base_score",
        "candidate_score",
        "score_delta",
        "membership",
        "enumeration_type",
        "site_type",
        "replacement_label",
    ]
    extras = sorted({key for row in rows for key in row if key not in preferred})
    fieldnames = preferred + extras if rows else ["candidate_key"]
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
