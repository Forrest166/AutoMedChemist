from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable

from .database import initialize_database


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")


RING_OUTCOME_ENUMERATION_TYPES = {
    "ring_library_recommendation",
    "ring_rgroup_joint_recommendation",
    "ring_network_replacement",
    "scaffold_replacement",
}
POSITIVE_CLASSES = {"active", "positive", "pass", "hit", "improved", "go", "make"}
NEGATIVE_CLASSES = {"inactive", "negative", "fail", "miss", "worse", "no_go", "no-go", "reject"}


def _float_or_none(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _payload(value: object) -> dict:
    try:
        payload = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _outcome(row: dict) -> str:
    classification = str(row.get("classification") or "").strip().lower()
    score = _float_or_none(row.get("normalized_score"))
    if classification in POSITIVE_CLASSES or (score is not None and score >= 70):
        return "positive"
    if classification in NEGATIVE_CLASSES or (score is not None and score <= 30):
        return "negative"
    if score is not None:
        return "neutral"
    return "unobserved"


def _candidate_rows(db_path: str | Path, project_name: str | None = None) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params: tuple = ()
        where = ""
        if project_name:
            where = "WHERE pr.project_name=?"
            params = (project_name,)
        rows = conn.execute(
            f"""
            SELECT
                pr.project_name,
                pr.direction,
                pr.site_type AS run_site_type,
                pc.run_id,
                pc.candidate_id,
                pc.rank,
                pc.score,
                pc.enumeration_type,
                pc.replacement_label,
                pc.payload_json,
                pf.feedback_id,
                pf.endpoint,
                pf.assay_name,
                pf.assay_type,
                pf.normalized_score,
                pf.classification,
                pf.recorded_at
            FROM project_candidate pc
            JOIN project_run pr ON pr.run_id = pc.run_id
            LEFT JOIN project_feedback pf
                ON pf.run_id = pc.run_id AND pf.candidate_id = pc.candidate_id
            {where}
            """,
            params,
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _ring_context(row: dict) -> dict:
    payload = _payload(row.get("payload_json"))
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "project_name": row.get("project_name"),
        "run_id": row.get("run_id"),
        "candidate_id": row.get("candidate_id"),
        "enumeration_type": row.get("enumeration_type") or payload.get("enumeration_type"),
        "endpoint": row.get("endpoint") or payload.get("endpoint_group") or "unspecified",
        "direction": row.get("direction") or payload.get("direction") or "unspecified",
        "site_type": payload.get("site_type") or row.get("run_site_type") or "unspecified",
        "ring_novelty_bucket": payload.get("ring_novelty_bucket") or metadata.get("ring_novelty_bucket") or "unspecified",
        "ring_diversity_bucket": payload.get("ring_diversity_bucket") or metadata.get("ring_diversity_bucket") or "unspecified",
        "ring_source_dataset": metadata.get("ring_library_source_dataset") or payload.get("ring_source_dataset") or "unspecified",
        "replacement_class": payload.get("replacement_class") or metadata.get("replacement_class") or "unspecified",
        "score": _float_or_none(row.get("score")),
        "rank": row.get("rank"),
        "normalized_score": _float_or_none(row.get("normalized_score")),
        "classification": row.get("classification"),
        "outcome": _outcome(row),
    }


def _group_key(row: dict) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("enumeration_type") or "unspecified"),
        str(row.get("endpoint") or "unspecified"),
        str(row.get("ring_novelty_bucket") or "unspecified"),
        str(row.get("ring_diversity_bucket") or "unspecified"),
        str(row.get("replacement_class") or "unspecified"),
    )


def _candidate_key(row: dict) -> str:
    return f"{row.get('run_id') or ''}::{row.get('candidate_id') or ''}"


def _summarize_group(rows: Iterable[dict], *, min_group_outcomes: int) -> dict:
    materialized = list(rows)
    first = materialized[0]
    observed = [row for row in materialized if row["outcome"] != "unobserved"]
    scores = [row["normalized_score"] for row in observed if row.get("normalized_score") is not None]
    outcome_counts = Counter(row["outcome"] for row in materialized)
    observed_count = len(observed)
    hit_rate = round(outcome_counts.get("positive", 0) / observed_count, 4) if observed_count else None
    mean_score = round(mean(scores), 4) if scores else None
    if observed_count < min_group_outcomes:
        action = "insufficient_outcomes"
    elif hit_rate is not None and hit_rate >= 0.6 and (mean_score is None or mean_score >= 60):
        action = "promote_context"
    elif hit_rate is not None and (hit_rate <= 0.25 or (mean_score is not None and mean_score < 40)):
        action = "downweight_context"
    else:
        action = "monitor_context"
    return {
        "enumeration_type": first["enumeration_type"],
        "endpoint": first["endpoint"],
        "ring_novelty_bucket": first["ring_novelty_bucket"],
        "ring_diversity_bucket": first["ring_diversity_bucket"],
        "replacement_class": first["replacement_class"],
        "candidate_count": len({_candidate_key(row) for row in materialized}),
        "row_count": len(materialized),
        "observed_count": observed_count,
        "positive_count": outcome_counts.get("positive", 0),
        "negative_count": outcome_counts.get("negative", 0),
        "neutral_count": outcome_counts.get("neutral", 0),
        "unobserved_count": outcome_counts.get("unobserved", 0),
        "mean_normalized_score": mean_score,
        "hit_rate": hit_rate,
        "learning_action": action,
        "example_candidate_ids": ";".join(row["candidate_id"] for row in materialized[:5]),
    }


def build_ring_outcome_learning_report(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    project_name: str | None = None,
    min_group_outcomes: int = 2,
) -> dict:
    rows = [_ring_context(row) for row in _candidate_rows(db_path, project_name=project_name)]
    ring_rows = [row for row in rows if row["enumeration_type"] in RING_OUTCOME_ENUMERATION_TYPES]
    observed = [row for row in ring_rows if row["outcome"] != "unobserved"]
    groups: dict[tuple[str, str, str, str, str], list[dict]] = defaultdict(list)
    for row in ring_rows:
        groups[_group_key(row)].append(row)
    summaries = [_summarize_group(group_rows, min_group_outcomes=min_group_outcomes) for group_rows in groups.values()]
    summaries.sort(
        key=lambda row: (
            row["learning_action"] != "promote_context",
            -(row.get("observed_count") or 0),
            -(row.get("hit_rate") or 0),
            row["enumeration_type"],
        )
    )
    status = "ready" if observed else "no_ring_outcomes"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_name": project_name,
        "min_group_outcomes": min_group_outcomes,
        "ring_candidate_count": len({_candidate_key(row) for row in ring_rows}),
        "ring_outcome_row_count": len(ring_rows),
        "observed_outcome_count": len(observed),
        "group_count": len(summaries),
        "outcome_counts": dict(Counter(row["outcome"] for row in ring_rows).most_common()),
        "enumeration_counts": dict(Counter(row["enumeration_type"] for row in ring_rows).most_common()),
        "learning_groups": summaries,
        "promote_contexts": [row for row in summaries if row["learning_action"] == "promote_context"],
        "downweight_contexts": [row for row in summaries if row["learning_action"] == "downweight_context"],
        "recommended_next_actions": [
            "Use promote_context groups as candidates for profile/rule weight review after chemist sign-off.",
            "Use downweight_context groups as review targets before further ring-library expansion in the same endpoint.",
            "Keep insufficient_outcomes groups in the residual assay queue until they pass the minimum outcome count.",
        ],
    }


def write_ring_outcome_learning_report(
    report: dict,
    *,
    json_path: str | Path,
    csv_path: str | Path | None = None,
) -> None:
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path is None:
        return
    rows = report.get("learning_groups") or []
    csv_out = Path(csv_path)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "enumeration_type",
        "endpoint",
        "ring_novelty_bucket",
        "ring_diversity_bucket",
        "replacement_class",
        "candidate_count",
        "observed_count",
        "positive_count",
        "negative_count",
        "neutral_count",
        "hit_rate",
        "mean_normalized_score",
        "learning_action",
        "example_candidate_ids",
    ]
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
