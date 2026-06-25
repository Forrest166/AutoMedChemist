from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

from .database import initialize_database


DEFAULT_DB_PATH = Path("data/localmedchem.sqlite")

RING_NOVELTY_SQL = """
    CASE
        WHEN source_dataset='approved_drug_ring_systems' THEN 'approved_drug_precedented'
        WHEN source_dataset='clinical_trial_ring_systems' THEN 'clinical_trial_precedented'
        WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 5000 THEN 'ertl_common'
        WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 50000 THEN 'ertl_precedented'
        WHEN source_dataset='ertl_4m_ring_systems' AND COALESCE(source_rank, 999999999) <= 250000 THEN 'ertl_expansion'
        ELSE 'long_tail_or_unranked'
    END
"""

RING_DIVERSITY_SQL = """
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


def recommend_ring_systems(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    search: str | None = None,
    source_dataset: str | None = "ertl_4m_ring_systems",
    ring_class: str | None = None,
    min_heavy_atom_count: int | None = None,
    max_heavy_atom_count: int | None = None,
    min_hetero_atom_count: int | None = None,
    max_hetero_atom_count: int | None = None,
    max_source_rank: int | None = None,
    novelty_bucket: str | None = None,
    diversity_bucket: str | None = None,
    limit: int = 50,
    order_by: str = "source_rank",
    cache_path: str | Path | None = None,
    cache_ttl_seconds: int | float | None = 86400,
) -> dict:
    """Retrieve ring-system replacement candidates from the governed ring library."""
    limit = max(1, min(int(limit or 50), 500))
    filters = {
        "search": search,
        "source_dataset": source_dataset,
        "ring_class": ring_class,
        "min_heavy_atom_count": min_heavy_atom_count,
        "max_heavy_atom_count": max_heavy_atom_count,
        "min_hetero_atom_count": min_hetero_atom_count,
        "max_hetero_atom_count": max_hetero_atom_count,
        "max_source_rank": max_source_rank,
        "novelty_bucket": novelty_bucket,
        "diversity_bucket": diversity_bucket,
        "limit": limit,
        "order_by": order_by,
    }
    db_file = Path(db_path)
    db_stat = db_file.stat() if db_file.exists() else None
    cache_key_payload = {
        "filters": filters,
        "db_path": str(db_file.resolve()),
        "db_size": db_stat.st_size if db_stat else None,
        "db_mtime_ns": db_stat.st_mtime_ns if db_stat else None,
    }
    cache_key = hashlib.sha256(json.dumps(cache_key_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    if cache_path:
        cached = _read_cache(cache_path, cache_key=cache_key, ttl_seconds=cache_ttl_seconds)
        if cached is not None:
            return cached

    started = time.perf_counter()
    conn = initialize_database(db_path)
    conn.row_factory = sqlite3.Row
    where = []
    params: list[object] = []
    if search:
        like = f"%{str(search).strip()}%"
        where.append("(ring_id LIKE ? OR canonical_smiles LIKE ? OR source_name LIKE ? OR source_reference LIKE ?)")
        params.extend([like, like, like, like])
    if source_dataset:
        where.append("source_dataset = ?")
        params.append(source_dataset)
    if ring_class:
        where.append("ring_class = ?")
        params.append(ring_class)
    if min_heavy_atom_count is not None:
        where.append("heavy_atom_count >= ?")
        params.append(int(min_heavy_atom_count))
    if max_heavy_atom_count is not None:
        where.append("heavy_atom_count <= ?")
        params.append(int(max_heavy_atom_count))
    if min_hetero_atom_count is not None:
        where.append("hetero_atom_count >= ?")
        params.append(int(min_hetero_atom_count))
    if max_hetero_atom_count is not None:
        where.append("hetero_atom_count <= ?")
        params.append(int(max_hetero_atom_count))
    if max_source_rank is not None:
        where.append("source_rank <= ?")
        params.append(int(max_source_rank))
    if novelty_bucket:
        where.append(f"({RING_NOVELTY_SQL}) = ?")
        params.append(novelty_bucket)
    if diversity_bucket:
        where.append(f"({RING_DIVERSITY_SQL}) = ?")
        params.append(diversity_bucket)

    allowed_order = {
        "source_rank": "COALESCE(source_rank, 999999999), canonical_smiles",
        "heavy_atom_count": "COALESCE(heavy_atom_count, 999999999), COALESCE(source_rank, 999999999)",
        "hetero_atom_count": "COALESCE(hetero_atom_count, 999999999), COALESCE(source_rank, 999999999)",
        "novelty": "ring_novelty_bucket, COALESCE(source_rank, 999999999)",
        "canonical_smiles": "canonical_smiles",
    }
    order_sql = allowed_order.get(order_by, allowed_order["source_rank"])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    ring_id, smiles, canonical_smiles, source_dataset, source_rank,
                    ring_class, ring_count, hetero_atom_count, aromatic_ring_count,
                    heavy_atom_count, fsp3, source_reference,
                    {RING_NOVELTY_SQL} AS ring_novelty_bucket,
                    {RING_DIVERSITY_SQL} AS ring_diversity_bucket
                FROM ring_system
                {where_sql}
                ORDER BY {order_sql}
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        ]
        total = int(conn.execute(f"SELECT COUNT(*) FROM ring_system {where_sql}", params).fetchone()[0])
    finally:
        conn.close()

    class_counts = Counter(str(row.get("ring_class") or "unclassified") for row in rows)
    novelty_counts = Counter(str(row.get("ring_novelty_bucket") or "unknown") for row in rows)
    report = {
        "filters": filters,
        "total_matching_count": total,
        "returned_count": len(rows),
        "summary": {
            "ring_class_counts": dict(class_counts.most_common()),
            "novelty_bucket_counts": dict(novelty_counts.most_common()),
        },
        "query_elapsed_ms": round((time.perf_counter() - started) * 1000.0, 4),
        "cache": {
            "enabled": bool(cache_path),
            "hit": False,
            "cache_path": str(Path(cache_path).resolve()) if cache_path else None,
            "cache_key": cache_key if cache_path else None,
            "ttl_seconds": cache_ttl_seconds,
        },
        "rows": rows,
    }
    if cache_path:
        _write_cache(cache_path, cache_key=cache_key, report=report)
    return report


def _read_cache(cache_path: str | Path, *, cache_key: str, ttl_seconds: int | float | None) -> dict | None:
    path = Path(cache_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if payload.get("cache_key") != cache_key:
        return None
    created_epoch = float(payload.get("created_at_epoch") or 0.0)
    if ttl_seconds is not None and created_epoch and (time.time() - created_epoch) > float(ttl_seconds):
        return None
    report = payload.get("report")
    if not isinstance(report, dict):
        return None
    cached_report = dict(report)
    cached_report["cache"] = {
        "enabled": True,
        "hit": True,
        "cache_path": str(path.resolve()),
        "cache_key": cache_key,
        "ttl_seconds": ttl_seconds,
    }
    return cached_report


def _write_cache(cache_path: str | Path, *, cache_key: str, report: dict) -> None:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stored_report = dict(report)
    stored_report.pop("cache", None)
    payload = {
        "cache_key": cache_key,
        "created_at_epoch": time.time(),
        "report": stored_report,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_ring_recommendations(report: dict, *, json_out: str | Path, csv_out: str | Path | None = None) -> None:
    json_path = Path(json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not csv_out:
        return
    csv_path = Path(csv_out)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ring_id",
        "canonical_smiles",
        "source_dataset",
        "source_rank",
        "ring_class",
        "ring_count",
        "hetero_atom_count",
        "aromatic_ring_count",
        "heavy_atom_count",
        "fsp3",
        "ring_novelty_bucket",
        "ring_diversity_bucket",
        "source_reference",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
