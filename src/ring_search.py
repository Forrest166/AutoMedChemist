from __future__ import annotations

import sqlite3
from pathlib import Path

from .database import initialize_database


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")

RING_NOVELTY_SCORE = {
    "approved_drug_precedented": 96.0,
    "clinical_trial_precedented": 92.0,
    "ertl_common": 86.0,
    "ertl_precedented": 78.0,
    "ertl_expansion": 70.0,
    "long_tail_or_unranked": 55.0,
}


def _like(value: str | None) -> str | None:
    if not value:
        return None
    return f"%{value.strip()}%"


def _bucket_sql() -> tuple[str, str]:
    novelty_sql = """
        CASE
            WHEN source_dataset='approved_drug_ring_systems' THEN 'approved_drug_precedented'
            WHEN source_dataset='clinical_trial_ring_systems' THEN 'clinical_trial_precedented'
            WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 5000 THEN 'ertl_common'
            WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 50000 THEN 'ertl_precedented'
            WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 250000 THEN 'ertl_expansion'
            ELSE 'long_tail_or_unranked'
        END
    """
    diversity_sql = """
        COALESCE(ring_class, 'unclassified') || ':' ||
        CASE
            WHEN COALESCE(heavy_atom_count, 0) <= 6 THEN 'small'
            WHEN COALESCE(heavy_atom_count, 0) <= 10 THEN 'medium'
            ELSE 'large'
        END || ':' ||
        CASE
            WHEN COALESCE(hetero_atom_count, 0)=0 THEN 'carbocycle'
            WHEN COALESCE(hetero_atom_count, 0)<=2 THEN 'hetero_low'
            ELSE 'hetero_rich'
        END || ':' ||
        CASE
            WHEN COALESCE(aromatic_ring_count, 0)>0 THEN 'aromatic'
            ELSE 'aliphatic'
        END
    """
    return novelty_sql, diversity_sql


def search_ring_systems(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    query: str | None = None,
    ring_class: str | None = None,
    source_dataset: str | None = None,
    min_heavy_atoms: int | None = None,
    max_heavy_atoms: int | None = None,
    novelty_bucket: str | None = None,
    diversity_bucket: str | None = None,
    limit: int = 100,
) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    where = []
    params: list[object] = []
    if query:
        where.append("(canonical_smiles LIKE ? OR ring_id LIKE ? OR source_name LIKE ? OR source_dataset LIKE ?)")
        like = _like(query)
        params.extend([like, like, like, like])
    if ring_class:
        where.append("ring_class = ?")
        params.append(ring_class)
    if source_dataset:
        where.append("source_dataset = ?")
        params.append(source_dataset)
    if min_heavy_atoms is not None:
        where.append("heavy_atom_count >= ?")
        params.append(int(min_heavy_atoms))
    if max_heavy_atoms is not None:
        where.append("heavy_atom_count <= ?")
        params.append(int(max_heavy_atoms))
    novelty_sql, diversity_sql = _bucket_sql()
    if novelty_bucket:
        where.append(f"({novelty_sql}) = ?")
        params.append(novelty_bucket)
    if diversity_bucket:
        where.append(f"({diversity_sql}) = ?")
        params.append(diversity_bucket)
    sql = """
        SELECT ring_id, canonical_smiles, source_name, source_dataset, source_rank,
               ring_class, ring_count, hetero_atom_count, aromatic_ring_count,
               heavy_atom_count, fsp3, source_reference,
               {novelty_sql} AS ring_novelty_bucket,
               {diversity_sql} AS ring_diversity_bucket
        FROM ring_system
    """.format(novelty_sql=novelty_sql, diversity_sql=diversity_sql)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE WHEN source_dataset='approved_drug_ring_systems' THEN 0 WHEN source_dataset='clinical_trial_ring_systems' THEN 1 ELSE 2 END, source_rank ASC LIMIT ?"
    params.append(int(limit))
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def ring_source_summary(*, db_path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT source_name, source_dataset, ring_class, COUNT(*) AS count,
                       MIN(source_rank) AS best_rank,
                       AVG(heavy_atom_count) AS mean_heavy_atom_count
                FROM ring_system
                GROUP BY source_name, source_dataset, ring_class
                ORDER BY count DESC
                """
            ).fetchall()
        ]
    finally:
        conn.close()


def ring_system_bucket_lookup(
    smiles_values: list[str] | tuple[str, ...] | set[str],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, dict]:
    values = sorted({str(value) for value in smiles_values if value})
    if not values:
        return {}
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    novelty_sql, diversity_sql = _bucket_sql()
    lookup: dict[str, dict] = {}
    try:
        for start in range(0, len(values), 500):
            chunk = values[start : start + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT canonical_smiles, source_dataset, source_rank, ring_class,
                       heavy_atom_count, hetero_atom_count, aromatic_ring_count,
                       {novelty_sql} AS ring_novelty_bucket,
                       {diversity_sql} AS ring_diversity_bucket
                FROM ring_system
                WHERE canonical_smiles IN ({placeholders})
                ORDER BY CASE WHEN source_dataset='approved_drug_ring_systems' THEN 0
                              WHEN source_dataset='clinical_trial_ring_systems' THEN 1
                              ELSE 2 END,
                         COALESCE(source_rank, 999999999)
                """,
                chunk,
            ).fetchall()
            for row in rows:
                smiles = str(row["canonical_smiles"])
                if smiles not in lookup:
                    lookup[smiles] = dict(row)
        return lookup
    finally:
        conn.close()


def annotate_ring_replacement_buckets(
    records: list[dict],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    preferred_novelty_buckets: list[str] | tuple[str, ...] | set[str] | None = None,
    preferred_diversity_buckets: list[str] | tuple[str, ...] | set[str] | None = None,
) -> list[dict]:
    lookup = ring_system_bucket_lookup(
        [str(row.get("replacement_canonical_smiles") or "") for row in records],
        db_path=db_path,
    )
    novelty_preference = {str(item) for item in preferred_novelty_buckets or [] if item}
    diversity_preference = {str(item) for item in preferred_diversity_buckets or [] if item}
    annotated = []
    for row in records:
        target = str(row.get("replacement_canonical_smiles") or "")
        bucket = lookup.get(target) or {}
        novelty = bucket.get("ring_novelty_bucket")
        diversity = bucket.get("ring_diversity_bucket")
        score = RING_NOVELTY_SCORE.get(str(novelty), 50.0)
        basis = []
        if novelty:
            basis.append(str(novelty))
        if diversity:
            basis.append(str(diversity))
        if novelty and novelty in novelty_preference:
            score += 10.0
            basis.append("preferred_novelty")
        if diversity and diversity in diversity_preference:
            score += 8.0
            basis.append("preferred_diversity")
        annotated.append(
            {
                **row,
                "ring_novelty_bucket": novelty,
                "ring_diversity_bucket": diversity,
                "ring_sampling_score": round(max(0.0, min(100.0, score)), 2) if bucket else None,
                "ring_sampling_basis": ";".join(dict.fromkeys(basis)),
            }
        )
    return annotated


def ring_frequency_score(row: dict | None) -> float | None:
    if not row:
        return None
    dataset = str(row.get("source_dataset") or "")
    rank = row.get("source_rank")
    try:
        rank_value = int(rank)
    except (TypeError, ValueError):
        rank_value = 999999
    if dataset == "approved_drug_ring_systems":
        base = 94.0
    elif dataset == "clinical_trial_ring_systems":
        base = 88.0
    elif dataset == "ertl_4m_ring_systems":
        base = 82.0
    else:
        base = 68.0
    if rank_value <= 250:
        base += 6.0
    elif rank_value <= 2000:
        base += 3.0
    elif rank_value >= 100000:
        base -= 8.0
    return max(0.0, min(100.0, base))


def score_candidate_ring_evidence(candidate_row: dict, substituent_record: dict | None = None) -> float | None:
    record = substituent_record or {}
    evidence = record.get("network_evidence") or record.get("ring_evidence") or {}
    if evidence:
        weight = evidence.get("edge_weight") or evidence.get("evidence_count") or evidence.get("source_rank")
        try:
            weight_value = float(weight or 0)
        except (TypeError, ValueError):
            weight_value = 0.0
        source = str(evidence.get("source_name") or "")
        reference = str(evidence.get("source_reference") or "")
        if "Shearer" in source or "clinical" in source.lower():
            return 90.0
        if "Ertl" in source or "peter-ertl" in reference:
            return min(92.0, 68.0 + weight_value ** 0.5)
        if evidence.get("replacement_class") in {"heteroaryl_bioisostere", "saturated_heterocycle_replacement"}:
            return 84.0
        if "Bajorath" in source:
            return min(90.0, 66.0 + weight_value ** 0.5)
        return min(84.0, 60.0 + weight_value ** 0.5)
    enum_type = str(candidate_row.get("enumeration_type") or "")
    if enum_type == "scaffold_replacement":
        label = str(candidate_row.get("replacement_label") or "").lower()
        if "pyridyl" in label or "morpholine" in label:
            return 84.0
        if "bicyclo" in label or "cubane" in label:
            return 62.0
        return 74.0
    if "ring_network" in enum_type or "rgroup_network" in enum_type:
        return 72.0
    return None
